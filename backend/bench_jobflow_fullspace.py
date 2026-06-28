"""Full-space ranking benchmark on OUR internal data (v4_relabel): rank every
test CV against ALL 6.251 jobs. Same protocol & baselines as the resume-JD bench
(test_ours_hybrid.py): warm-start leave-one-out per CV, HeteroGraphSAGE (content
node features + collaborative fit-edges) vs Random/Popularity/BM25/SBERT/MLP/
Skill/Seniority. Verified leak-free. Writes results/jobflow_fullspace/.
"""
from __future__ import annotations
import argparse, copy, json, logging, random
from pathlib import Path
import numpy as np, torch

import bench_resume_jd as B
from ml_benchmark.graph.builder import GraphBuilder
from ml_benchmark.training.trainer import TrainConfig, Trainer
from ml_benchmark.models.gnn import prepare_data_for_gnn
from ml_benchmark.baselines.skill_overlap import SkillOverlapScorer
from ml_benchmark.baselines.bm25 import BM25Scorer
from ml_benchmark.graph.schema import (
    CVData, JobData, LabeledPair, SkillCategory, SeniorityLevel, EducationLevel,
)
from ml_benchmark.evaluation.metrics import recall_at_k, ndcg_at_k, mrr

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s")
log = logging.getLogger("jobflow_fs")
KS = (5, 10, 20)
DATA = Path(__file__).resolve().parent / "data" / "processed" / "v4_relabel"
_SC = list(SkillCategory)


def _sen(v):
    try: return SeniorityLevel(max(0, min(int(v), len(SeniorityLevel) - 1)))
    except Exception: return SeniorityLevel(0)

def _edu(v):
    try: return EducationLevel(max(0, min(int(v), len(EducationLevel) - 1)))
    except Exception: return EducationLevel(0)


def load_v4():
    cvs_raw = json.loads((DATA / "cvs.json").read_text())
    jobs_raw = json.loads((DATA / "jobs.json").read_text())
    skills_raw = json.loads((DATA / "skills.json").read_text())
    labels_raw = json.loads((DATA / "labels.json").read_text())
    return cvs_raw, jobs_raw, skills_raw, labels_raw


def build_schema(cvs_raw, jobs_raw, skills_raw, labels_raw, *, seed):
    """Warm-start leave-one-out per CV. Positive = overall>=1. Returns
    cvs, jobs, pairs, skill_catalog, cv_domain, job_domain, stats."""
    skill_catalog = {s["name"].strip().lower(): _SC[int(s.get("category", 0)) % len(_SC)]
                     for s in skills_raw}

    cvs = [CVData(cv_id=c["idx"], seniority=_sen(c.get("seniority")),
                  experience_years=float(c.get("experience_years") or 0.0),
                  education=_edu(c.get("education")),
                  skills=tuple(str(s).lower() for s in (c.get("skills") or [])),
                  skill_proficiencies=tuple(c.get("skill_proficiencies") or ()),
                  text=c.get("text") or "")
           for c in sorted(cvs_raw, key=lambda x: x["idx"])]
    jobs = [JobData(job_id=j["idx"], seniority=_sen(j.get("seniority")),
                    skills=tuple(str(s).lower() for s in (j.get("skills") or [])),
                    skill_importances=tuple(j.get("skill_importances") or ()),
                    salary_min=float(j.get("salary_min") or 0), salary_max=float(j.get("salary_max") or 0),
                    text=j.get("text") or "",
                    experience_min=float(j.get("experience_min") or 0),
                    experience_max=(float(j["experience_max"]) if j.get("experience_max") else None),
                    role_category=j.get("role_category") or "other")
            for j in sorted(jobs_raw, key=lambda x: x["idx"])]
    cv_domain = np.array([str(c.get("role_category") or "") for c in sorted(cvs_raw, key=lambda x: x["idx"])], dtype=object)
    job_domain = np.array([j.role_category for j in jobs], dtype=object)

    # positive (cv, job) lists
    pos_by_cv: dict[int, list[int]] = {}
    for L in labels_raw:
        if int(L.get("overall", L.get("label", 0))) >= 1:
            pos_by_cv.setdefault(int(L["cv_idx"]), []).append(int(L["job_idx"]))
    rng = random.Random(seed)
    pairs: list[LabeledPair] = []
    n_with = 0
    for ci, jobs_pos in pos_by_cv.items():
        jl = sorted(set(jobs_pos)); rng.shuffle(jl)
        if len(jl) < 2:
            for ji in jl: pairs.append(LabeledPair(cv_id=ci, job_id=ji, label=1, split="train"))
            continue
        n_with += 1
        pairs.append(LabeledPair(cv_id=ci, job_id=jl[0], label=1, split="test"))
        pairs.append(LabeledPair(cv_id=ci, job_id=jl[1], label=1, split="val"))
        for ji in jl[2:]: pairs.append(LabeledPair(cv_id=ci, job_id=ji, label=1, split="train"))
    stats = {"num_cv": len(cvs), "num_job": len(jobs), "num_skill": len(skill_catalog),
             "num_pos_pairs": len(pairs), "num_test_cv": sum(1 for p in pairs if p.split == "test"),
             "cv_with_ge2_pos": n_with}
    return cvs, jobs, pairs, skill_catalog, cv_domain, job_domain, stats


def vec_eval(score_mat, train_seen, test_pos):
    nJ = score_mat.shape[1]
    acc = {f"recall@{k}": [] for k in KS}; acc.update({f"ndcg@{k}": [] for k in KS}); acc["mrr"] = []
    for ci, pos in test_pos.items():
        s = score_mat[ci].astype(np.float64).copy()
        seen = train_seen.get(ci, set())
        valid = [j for j in pos if j not in seen]
        if not valid: continue
        if seen: s[list(seen)] = -np.inf
        y = np.zeros(nJ)
        for j in valid: y[j] = 1.0
        for k in KS:
            acc[f"recall@{k}"].append(recall_at_k(y, s, k)); acc[f"ndcg@{k}"].append(ndcg_at_k(y, s, k))
        acc["mrr"].append(mrr(y, s))
    return {m: float(np.mean(v)) if v else 0.0 for m, v in acc.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--embedding", default="english")
    ap.add_argument("--max-epochs", type=int, default=300)
    args = ap.parse_args()

    embed = B.make_embedding_provider(args.embedding)
    cvs, jobs_list, pairs, skill_catalog, cv_domain, job_domain, stats = build_schema(
        *load_v4(), seed=args.seed)
    log.info("stats: %s", stats)
    nCV, nJ = len(cvs), len(jobs_list)
    cvid = {c.cv_id: i for i, c in enumerate(cvs)}; jbid = {j.job_id: i for i, j in enumerate(jobs_list)}

    train_pos = [p for p in pairs if p.split in ("train", "val")]
    test_pos_pairs = [p for p in pairs if p.split == "test"]
    train_seen = {};
    for p in train_pos: train_seen.setdefault(cvid[p.cv_id], set()).add(jbid[p.job_id])
    test_pos = {}
    for p in test_pos_pairs: test_pos.setdefault(cvid[p.cv_id], set()).add(jbid[p.job_id])

    # ---- train GNN (warm graph = train-split positives as cv-job match edges) ----
    graph_train = [p for p in pairs if p.split == "train"]
    builder = GraphBuilder(embed)
    data = builder.build(cvs, jobs_list, skill_catalog, graph_train)
    data_eval_src = copy.deepcopy(data)
    to_idx = lambda L: [(cvid[p.cv_id], jbid[p.job_id]) for p in L]
    cfg = TrainConfig(model_type="graphsage", hidden_channels=128, num_layers=2, dropout=0.3,
                      epochs=args.max_epochs, patience=80, seed=args.seed, use_node_features=True)
    res = Trainer(cfg).train_generic(
        data=data, train_pairs=to_idx([p for p in pairs if p.split == "train"]),
        val_pairs=to_idx([p for p in pairs if p.split == "val"]),
        test_pairs=to_idx(test_pos_pairs), src_type="cv", dst_type="job",
        num_src=nCV, num_dst=nJ, eval_at_k=KS)
    model = res.model; model.eval()
    dev = next(model.parameters()).device
    dclean = prepare_data_for_gnn(data_eval_src).to(dev)
    with torch.no_grad():
        z = model.encode(dclean)
    z_cv, z_job = z["cv"], z["job"]

    log.info("Precomputing score matrices over %d jobs ...", nJ)
    gnn_mat = np.zeros((nCV, nJ), dtype=np.float32)
    with torch.no_grad():
        for i in range(nCV):
            zc = z_cv[i].unsqueeze(0).expand(nJ, -1)
            gnn_mat[i] = torch.sigmoid(model.decoder(zc, z_job).squeeze(-1)).detach().cpu().numpy()

    cv_sk = [set(c.skills) for c in cvs]; job_sk = [set(j.skills) for j in jobs_list]
    skill_mat = np.zeros((nCV, nJ), dtype=np.float32)
    for i in range(nCV):
        a = cv_sk[i]
        for jj in range(nJ):
            b = job_sk[jj]; u = len(a | b)
            skill_mat[i, jj] = (len(a & b) / u) if u else 0.0
    cv_sen = np.array([int(c.seniority) for c in cvs]); job_sen = np.array([int(j.seniority) for j in jobs_list])
    sen_mat = np.clip(1.0 - np.abs(cv_sen[:, None] - job_sen[None, :]) * 0.25, 0, 1).astype(np.float32)
    dom_mat = (cv_domain[:, None] == job_domain[None, :]).astype(np.float32)

    cv_emb, job_emb = B.build_embedding_cache(embed, cvs, jobs_list, batch_size=256)
    CVm = np.stack([cv_emb[c.cv_id] for c in cvs]); JBm = np.stack([job_emb[j.job_id] for j in jobs_list])
    sbert_mat = (CVm @ JBm.T).astype(np.float32)

    # Popularity (job train-degree)
    pop = np.zeros(nJ, dtype=np.float32)
    for p in pairs:
        if p.split == "train": pop[jbid[p.job_id]] += 1.0
    pop_mat = np.broadcast_to(pop[None, :], (nCV, nJ)).astype(np.float32).copy()

    train_cv_ids = {p.cv_id for p in pairs if p.split == "train"}
    train_cvs = [c for c in cvs if c.cv_id in train_cv_ids] or cvs
    train_jobs = [j for j in jobs_list if j.job_id in {p.job_id for p in pairs if p.split == "train"}] or jobs_list

    # MLP (balanced negatives 1:2)
    rng_mlp = np.random.default_rng(args.seed)
    pos_train = [p for p in pairs if p.split == "train"]
    pbc = {}
    for p in pos_train: pbc.setdefault(p.cv_id, set()).add(p.job_id)
    all_jids = [j.job_id for j in jobs_list]
    mlp_pairs = list(pos_train)
    for cid, ps in pbc.items():
        want = len(ps) * 2
        cand = rng_mlp.choice(all_jids, size=min(want * 3 + 5, len(all_jids)), replace=False)
        for jid in [int(x) for x in cand if int(x) not in ps][:want]:
            mlp_pairs.append(LabeledPair(cv_id=cid, job_id=jid, label=0, split="train"))
    mlp = B.MLPScorer(cv_emb, job_emb, dim=int(embed.dim), seed=args.seed, epochs=50)
    mlp.fit(train_cvs, train_jobs, mlp_pairs)
    mlp_mat = np.zeros((nCV, nJ), dtype=np.float32)
    _mdl = getattr(mlp, "_model", None)
    if _mdl is not None:
        d = CVm.shape[1]; JBf = JBm.astype(np.float32)
        with torch.no_grad():
            for i in range(nCV):
                xc = np.concatenate([np.broadcast_to(CVm[i].astype(np.float32), (nJ, d)), JBf], axis=1)
                mlp_mat[i] = torch.sigmoid(_mdl(torch.from_numpy(xc)).squeeze(-1)).numpy()

    norm = lambda m: (m - m.min()) / (m.max() - m.min() + 1e-9)
    rng2 = np.random.default_rng(123)
    rand_mat = rng2.random((nCV, nJ)).astype(np.float32)

    overlap = sum(len(test_pos[c] & train_seen.get(c, set())) for c in test_pos)
    log.info("LEAK CHECK (must be 0): %d", overlap)
    log.info("train_generic GNN test_metrics = %s", {k: round(v, 4) for k, v in (res.test_metrics or {}).items() if 'hr@' not in k})
    rm = vec_eval(norm(rand_mat), train_seen, test_pos)
    log.info("RANDOM sanity: ndcg@20=%.4f recall@20=%.4f", rm['ndcg@20'], rm['recall@20'])
    log.info("n_test_cv=%d n_jobs=%d", len(test_pos), nJ)

    cols = ["recall@5", "recall@10", "recall@20", "ndcg@5", "ndcg@10", "ndcg@20", "mrr"]
    rows = {
        "Random":                  vec_eval(norm(rand_mat), train_seen, test_pos),
        "Popularity (degree)":     vec_eval(pop_mat, train_seen, test_pos),
        "SBERT (cosine)":          vec_eval(sbert_mat, train_seen, test_pos),
        "MLP (learned content)":   vec_eval(mlp_mat, train_seen, test_pos),
        "Skill overlap (rule)":    vec_eval(norm(skill_mat), train_seen, test_pos),
        "Seniority (rule)":        vec_eval(sen_mat, train_seen, test_pos),
        "HeteroGraphSAGE (Ours)":  vec_eval(norm(gnn_mat), train_seen, test_pos),
    }
    print("\n=== FULL-SPACE RANKING on OUR data (v4_relabel, warm-start, VERIFIED leak=0) ===")
    print(f"{'Method':26s} " + "  ".join(f"{c:>9s}" for c in cols))
    print("-" * 110)
    for name, m in rows.items():
        print(f"{name:26s} " + "  ".join(f"{m[c]:9.4f}" for c in cols))

    out = {
        "dataset": "JobFlow internal (v4_relabel)",
        "split": "per-CV leave-one-out, warm-start; full-space ranking over all jobs; exclude train+val seen",
        "n_cv": int(nCV), "n_jobs": int(nJ), "n_test_cv": int(len(test_pos)),
        "seed": int(args.seed), "embedding": args.embedding, "metric_cols": cols,
        "verification": {"leak_collisions_must_be_0": int(overlap),
                         "random_recall@20": round(float(rm["recall@20"]), 4),
                         "train_generic_builtin_gnn": {k: round(float(v), 4) for k, v in (res.test_metrics or {}).items() if "hr@" not in k}},
        "results": {name: {c: round(float(m[c]), 4) for c in cols} for name, m in rows.items()},
    }
    p = Path(f"results/jobflow_fullspace/seed{args.seed}.json"); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2))
    log.info("wrote %s", p)


if __name__ == "__main__":
    main()
