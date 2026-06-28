"""Full-space ranking on OUR production data using the REAL production checkpoint
(not a sandbox retrain). Loads checkpoints/latest (pretrain+finetune HeteroGraphSAGE,
hidden 256, multilingual), strips label edges, encodes, then ranks every TEST-split
CV against ALL jobs. Leak-free (test positives never in the encoding graph).

    python eval_prod_fullspace.py --checkpoint checkpoints/latest --data data/processed/v4_relabel
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np, torch

from ml_service.inference.checkpoint import load_checkpoint
from ml_service.models.gnn import prepare_data_for_gnn
from ml_service.training.trainer import _strip_label_edges
from ml_benchmark.evaluation.metrics import recall_at_k, ndcg_at_k, mrr

KS = (5, 10, 20)
COLS = ["recall@5", "recall@10", "recall@20", "ndcg@5", "ndcg@10", "ndcg@20", "mrr"]


def vec_eval(score_mat, train_seen, test_pos):
    nJ = score_mat.shape[1]
    acc = {f"recall@{k}": [] for k in KS}; acc.update({f"ndcg@{k}": [] for k in KS}); acc["mrr"] = []
    for ci, pos in test_pos.items():
        s = score_mat[ci].astype(np.float64).copy()
        seen = train_seen.get(ci, set())
        valid = [j for j in pos if j not in seen]
        if not valid:
            continue
        if seen:
            s[list(seen)] = -np.inf
        y = np.zeros(nJ)
        for j in valid:
            y[j] = 1.0
        for k in KS:
            acc[f"recall@{k}"].append(recall_at_k(y, s, k)); acc[f"ndcg@{k}"].append(ndcg_at_k(y, s, k))
        acc["mrr"].append(mrr(y, s))
    return {m: float(np.mean(v)) if v else 0.0 for m, v in acc.items()}


def main(ckpt: Path, data_dir: Path):
    model, data, cvs, jobs, meta = load_checkpoint(ckpt)
    model.eval()
    clean = prepare_data_for_gnn(_strip_label_edges(data))
    with torch.no_grad():
        z = model.encode(clean)
    z_cv, z_job = z["cv"], z["job"]
    nCV, nJ = z_cv.shape[0], z_job.shape[0]

    # graph-index maps
    cv_gi = {cv.cv_id: i for i, cv in enumerate(cvs)}
    job_gi = {j.job_id: i for i, j in enumerate(jobs)}
    # dataset idx -> db id (labels.json uses dataset idx)
    cv_db = {c["idx"]: c["cv_id"] for c in json.loads((data_dir / "cvs.json").read_text())}
    job_db = {j["idx"]: j["job_id"] for j in json.loads((data_dir / "jobs.json").read_text())}
    labels = json.loads((data_dir / "labels.json").read_text())

    test_pos: dict[int, set] = {}
    train_seen: dict[int, set] = {}
    pop = np.zeros(nJ, dtype=np.float32)
    for L in labels:
        if int(L.get("label", 0)) != 1:  # positives only for ranking targets / seen
            continue
        c = cv_db.get(L["cv_idx"]); j = job_db.get(L["job_idx"])
        if c not in cv_gi or j not in job_gi:
            continue
        ci, ji = cv_gi[c], job_gi[j]
        if L["split"] == "test":
            test_pos.setdefault(ci, set()).add(ji)
        else:  # train / val = seen history
            train_seen.setdefault(ci, set()).add(ji)
            pop[ji] += 1.0

    # leak check
    overlap = sum(len(test_pos[c] & train_seen.get(c, set())) for c in test_pos)
    print(f"n_test_cv={len(test_pos)} n_jobs={nJ} LEAK(must=0)={overlap}", flush=True)

    # ---- score matrices [nCV x nJ] ----
    dev = next(model.parameters()).device
    z_cv, z_job = z_cv.to(dev), z_job.to(dev)
    gnn_mat = np.zeros((nCV, nJ), dtype=np.float32)
    with torch.no_grad():
        jall = torch.arange(nJ, device=dev)
        for i in range(nCV):
            ci = torch.full((nJ,), i, device=dev)
            gnn_mat[i] = model.decode(z, ci, jall).detach().cpu().numpy()

    # text-embedding cosine (SBERT) from node features' first 384 dims
    cvx = clean["cv"].x.detach().cpu().numpy()[:, :384]
    jbx = clean["job"].x.detach().cpu().numpy()[:, :384]
    cvn = cvx / (np.linalg.norm(cvx, axis=1, keepdims=True) + 1e-9)
    jbn = jbx / (np.linalg.norm(jbx, axis=1, keepdims=True) + 1e-9)
    sbert_mat = (cvn @ jbn.T).astype(np.float32)

    # skill jaccard
    cv_sk = [set(c.skills) for c in cvs]; job_sk = [set(j.skills) for j in jobs]
    skill_mat = np.zeros((nCV, nJ), dtype=np.float32)
    for i in range(nCV):
        a = cv_sk[i]
        for jj in range(nJ):
            b = job_sk[jj]; u = len(a | b)
            skill_mat[i, jj] = (len(a & b) / u) if u else 0.0

    cv_sen = np.array([int(c.seniority) for c in cvs]); job_sen = np.array([int(j.seniority) for j in jobs])
    sen_mat = np.clip(1.0 - np.abs(cv_sen[:, None] - job_sen[None, :]) * 0.25, 0, 1).astype(np.float32)
    pop_mat = np.broadcast_to(pop[None, :], (nCV, nJ)).astype(np.float32).copy()
    rng = np.random.default_rng(42)
    rand_mat = rng.random((nCV, nJ)).astype(np.float32)

    # BM25 (lexical) — cached tokenization for speed (CV text = document, job text = query)
    from ml_benchmark.baselines.bm25 import BM25Scorer, _tokenize
    bm = BM25Scorer().fit(cvs)
    bidf, bk1, bb, bavg = bm._idf, bm._k1, bm._b, max(bm._avgdl, 1e-9)
    cv_tf, cv_dl = [], []
    for c in cvs:
        toks = _tokenize(c.text); tf = {}
        for t in toks: tf[t] = tf.get(t, 0) + 1
        cv_tf.append(tf); cv_dl.append(len(toks))
    job_q = []
    for j in jobs:
        qc = {}
        for q in _tokenize(j.text):
            if q in bidf: qc[q] = qc.get(q, 0) + 1
        job_q.append(list(qc.items()))
    bm25_mat = np.zeros((nCV, nJ), dtype=np.float32)
    for i in range(nCV):
        tf = cv_tf[i]; denom = bk1 * (1 - bb + bb * cv_dl[i] / bavg); row = bm25_mat[i]
        for jj in range(nJ):
            sc = 0.0
            for q, cnt in job_q[jj]:
                f = tf.get(q, 0)
                if f: sc += bidf[q] * cnt * f * (bk1 + 1) / (f + denom)
            row[jj] = sc
    print("BM25 matrix done", flush=True)

    # domain (role) match — cv roles from v4 cvs.json by cv_id (checkpoint CVData role may be empty)
    cv_role_by_id = {c["cv_id"]: (c.get("role_category") or "") for c in json.loads((data_dir / "cvs.json").read_text())}
    cv_role = np.array([cv_role_by_id.get(c.cv_id, "") for c in cvs], dtype=object)
    job_role = np.array([j.role_category or "" for j in jobs], dtype=object)
    dom_mat = ((cv_role[:, None] == job_role[None, :]) & (cv_role[:, None] != "")).astype(np.float32)

    # production serving GNN score + full 4-term hybrid
    nrm = lambda m: (m - m.min()) / (m.max() - m.min() + 1e-9)
    gnn_serv = 0.6 * (1.0 / (1.0 + np.exp(-gnn_mat))) + 0.4 * sbert_mat
    a, b, g, d = (meta["hybrid_weights"][k] for k in ("alpha", "beta", "gamma", "delta"))
    hybrid = a * nrm(gnn_serv) + b * nrm(skill_mat) + g * sen_mat + d * dom_mat

    rows = {
        "Random":                  vec_eval(rand_mat, train_seen, test_pos),
        "Popularity (degree)":     vec_eval(pop_mat, train_seen, test_pos),
        "SBERT (cosine)":          vec_eval(sbert_mat, train_seen, test_pos),
        "Skill overlap (rule)":    vec_eval(skill_mat, train_seen, test_pos),
        "Seniority (rule)":        vec_eval(sen_mat, train_seen, test_pos),
        "GNN decoder only":        vec_eval(gnn_mat, train_seen, test_pos),
        "GNN serving (0.6sig+0.4cos)": vec_eval(gnn_serv, train_seen, test_pos),
        "Hybrid 4-term (production)":  vec_eval(hybrid, train_seen, test_pos),
    }
    print("\n=== A) FULL-SPACE RANKING (all jobs) — PRODUCTION model, held-out test (leak=0) ===")
    print(f"{'Method':30s} " + "  ".join(f"{c:>9s}" for c in COLS))
    print("-" * 120)
    for name, m in rows.items():
        print(f"{name:30s} " + "  ".join(f"{m[c]:9.4f}" for c in COLS))

    # ---- B) sampled-negative protocol: 1 positive vs N random negatives (NCF-style) ----
    def sampled_eval(score_mat, n_neg=100, seed=42):
        rng = np.random.default_rng(seed)
        allj = np.arange(nJ)
        acc = {f"recall@{k}": [] for k in KS}; acc.update({f"ndcg@{k}": [] for k in KS}); acc["mrr"] = []
        for ci, pos in test_pos.items():
            seen = train_seen.get(ci, set())
            valid = [j for j in pos if j not in seen]
            if not valid: continue
            forbidden = set(pos) | seen
            negpool = allj[~np.isin(allj, list(forbidden))]
            for p in valid:
                negs = rng.choice(negpool, size=min(n_neg, len(negpool)), replace=False)
                cand = np.concatenate([[p], negs])
                s = score_mat[ci, cand].astype(np.float64)
                y = np.zeros(len(cand)); y[0] = 1.0
                for k in KS:
                    acc[f"recall@{k}"].append(recall_at_k(y, s, k)); acc[f"ndcg@{k}"].append(ndcg_at_k(y, s, k))
                acc["mrr"].append(mrr(y, s))
        return {m: float(np.mean(v)) if v else 0.0 for m, v in acc.items()}

    score_mats = {"Random": rand_mat, "Popularity (degree)": pop_mat, "BM25 (lexical)": bm25_mat,
                  "SBERT (cosine)": sbert_mat, "Skill overlap (rule)": skill_mat, "Seniority (rule)": sen_mat,
                  "GNN decoder only": gnn_mat, "Hybrid 4-term (production)": hybrid}
    # 3 independent negative-sampling seeds -> mean ± std (production model is fixed)
    sample_seeds = [42, 123, 2024]
    per = {name: [sampled_eval(sm, seed=ss) for ss in sample_seeds] for name, sm in score_mats.items()}
    rows_s = {name: {c: float(np.mean([r[c] for r in runs])) for c in COLS} for name, runs in per.items()}
    std_s = {name: {c: float(np.std([r[c] for r in runs])) for c in COLS} for name, runs in per.items()}
    print("\n=== B) SAMPLED-NEGATIVE (1 positive vs 100 random negatives, 3 seeds) — PRODUCTION model ===")
    print(f"{'Method':30s} " + "  ".join(f"{c:>9s}" for c in COLS))
    print("-" * 120)
    for name, m in rows_s.items():
        print(f"{name:30s} " + "  ".join(f"{m[c]:9.4f}" for c in COLS))
    out_s = {"dataset": "JobFlow internal (v4_relabel) — PRODUCTION checkpoint", "checkpoint": str(ckpt),
             "protocol": "sampled-negative: 1 positive vs 100 random negatives (NCF-style), 3 seeds; exclude train+val seen",
             "n_cv": int(nCV), "n_jobs": int(nJ), "n_test_cv": int(len(test_pos)),
             "leak_collisions_must_be_0": int(overlap), "sample_seeds": sample_seeds, "metric_cols": COLS,
             "results_mean": {name: {c: round(rows_s[name][c], 4) for c in COLS} for name in rows_s},
             "results_std": {name: {c: round(std_s[name][c], 4) for c in COLS} for name in rows_s}}
    Path("results/jobflow_prod_fullspace/sampled_3seed.json").write_text(json.dumps(out_s, indent=2))
    print("wrote results/jobflow_prod_fullspace/sampled_3seed.json")

    # ---- C) HARD-NEGATIVE: negatives drawn from the SAME role (domain) as the positive ----
    from collections import defaultdict
    dom_idx = defaultdict(list)
    for j in range(nJ):
        dom_idx[job_role[j]].append(j)
    dom_idx = {d: np.array(v) for d, v in dom_idx.items()}

    def hard_eval(score_mat, n_neg=100, seed=42):
        srng = np.random.default_rng(seed); allj = np.arange(nJ)
        acc = {f"recall@{k}": [] for k in KS}; acc.update({f"ndcg@{k}": [] for k in KS}); acc["mrr"] = []
        for ci, pos in test_pos.items():
            seen = train_seen.get(ci, set()); valid = [j for j in pos if j not in seen]
            if not valid:
                continue
            forbidden = set(pos) | seen
            for pj in valid:
                pool = dom_idx.get(job_role[pj], np.array([], dtype=int))
                same = pool[~np.isin(pool, list(forbidden))] if len(pool) else pool
                if len(same) >= n_neg:
                    negs = srng.choice(same, size=n_neg, replace=False)
                else:
                    rest = allj[~np.isin(allj, list(forbidden | set(same.tolist())))]
                    fill = srng.choice(rest, size=min(n_neg - len(same), len(rest)), replace=False)
                    negs = np.concatenate([same, fill]).astype(int)
                cand = np.concatenate([[pj], negs]); s = score_mat[ci, cand].astype(np.float64)
                y = np.zeros(len(cand)); y[0] = 1.0
                for k in KS:
                    acc[f"recall@{k}"].append(recall_at_k(y, s, k)); acc[f"ndcg@{k}"].append(ndcg_at_k(y, s, k))
                acc["mrr"].append(mrr(y, s))
        return {m: float(np.mean(v)) if v else 0.0 for m, v in acc.items()}

    perh = {name: [hard_eval(sm, seed=ss) for ss in sample_seeds] for name, sm in score_mats.items()}
    rowsh = {name: {c: float(np.mean([r[c] for r in runs])) for c in COLS} for name, runs in perh.items()}
    stdh = {name: {c: float(np.std([r[c] for r in runs])) for c in COLS} for name, runs in perh.items()}
    print("\n=== C) HARD-NEGATIVE (1 pos vs 100 same-role negatives, 3 seeds) — PRODUCTION model ===")
    print(f"{'Method':30s} " + "  ".join(f"{c:>9s}" for c in COLS))
    print("-" * 120)
    for name, m in rowsh.items():
        print(f"{name:30s} " + "  ".join(f"{m[c]:9.4f}" for c in COLS))
    out_h = {"dataset": "JobFlow internal (v4_relabel) — PRODUCTION checkpoint", "checkpoint": str(ckpt),
             "protocol": "HARD-negative sampled: 1 positive vs 100 same-role negatives (fill random if too few), 3 seeds; exclude train+val seen",
             "n_cv": int(nCV), "n_jobs": int(nJ), "n_test_cv": int(len(test_pos)),
             "leak_collisions_must_be_0": int(overlap), "sample_seeds": sample_seeds, "metric_cols": COLS,
             "results_mean": {name: {c: round(rowsh[name][c], 4) for c in COLS} for name in rowsh},
             "results_std": {name: {c: round(stdh[name][c], 4) for c in COLS} for name in rowsh}}
    Path("results/jobflow_prod_fullspace/hard_sampled_3seed.json").write_text(json.dumps(out_h, indent=2))
    print("wrote results/jobflow_prod_fullspace/hard_sampled_3seed.json")

    out = {
        "dataset": "JobFlow internal (v4_relabel) — PRODUCTION checkpoint",
        "checkpoint": str(ckpt),
        "split": "held-out TEST split positives; full-space ranking over all jobs; exclude train+val seen",
        "n_cv": int(nCV), "n_jobs": int(nJ), "n_test_cv": int(len(test_pos)),
        "leak_collisions_must_be_0": int(overlap), "metric_cols": COLS,
        "results": {name: {c: round(float(m[c]), 4) for c in COLS} for name, m in rows.items()},
    }
    p = Path("results/jobflow_prod_fullspace/prod.json"); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2))
    print("\nwrote", p)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", type=Path, default=Path("checkpoints/latest"))
    ap.add_argument("--data", type=Path, default=Path("data/processed/v4_relabel"))
    args = ap.parse_args()
    main(args.checkpoint, args.data)
