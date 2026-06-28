"""So sánh các hướng cải tiến GNN trên bộ NỘI BỘ v4 (bài toán KHÓ, có importance
edge-weights + còn dư địa). Train sandbox GNN warm-start, đánh giá sampled-negative
(1 dương vs 100 âm). CHỈ sandbox, KHÔNG đụng production. Ghi results/gnn_variant/.
"""
from __future__ import annotations
import argparse, copy, json, logging
from pathlib import Path
import numpy as np, torch

import bench_resume_jd as B
import bench_jobflow_fullspace as JF
from ml_benchmark.graph.builder import GraphBuilder
from ml_benchmark.training.trainer import TrainConfig, Trainer
from ml_benchmark.models.gnn import prepare_data_for_gnn
from ml_benchmark.evaluation.metrics import recall_at_k, ndcg_at_k, mrr

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s")
log = logging.getLogger("v4_variant")
KS = (5, 10, 20)
COLS = ["recall@5", "recall@10", "recall@20", "ndcg@5", "ndcg@10", "ndcg@20", "mrr"]

# (name, model_type, extra TrainConfig kwargs)
VARIANTS = [
    ("sage gốc (mean)",        "graphsage", {}),
    ("gat (attention)",        "gat",       {}),
    ("gat + sum",              "gat_sum",   {}),
    ("gat + L2",               "gat_l2",    {}),
    ("egat (trọng-số-cạnh)",   "egat",      {}),
    ("egat + sum",             "egat_sum",  {}),
    ("gat + contrastive",      "gat",       {"contrastive_weight": 0.2}),
    ("sage + DropEdge",        "graphsage", {"drop_edge_rate": 0.2}),
]


def sampled_eval(score_mat, train_seen, test_pos, nJ, n_neg=100, seed=42):
    srng = np.random.default_rng(seed); allj = np.arange(nJ)
    acc = {f"recall@{k}": [] for k in KS}; acc.update({f"ndcg@{k}": [] for k in KS}); acc["mrr"] = []
    for ci, pos in test_pos.items():
        seen = train_seen.get(ci, set())
        valid = [j for j in pos if j not in seen]
        if not valid:
            continue
        forbidden = set(pos) | seen
        negpool = allj[~np.isin(allj, list(forbidden))]
        for p in valid:
            negs = srng.choice(negpool, size=min(n_neg, len(negpool)), replace=False)
            cand = np.concatenate([[p], negs]); s = score_mat[ci, cand].astype(np.float64)
            y = np.zeros(len(cand)); y[0] = 1.0
            for k in KS:
                acc[f"recall@{k}"].append(recall_at_k(y, s, k)); acc[f"ndcg@{k}"].append(ndcg_at_k(y, s, k))
            acc["mrr"].append(mrr(y, s))
    return {m: float(np.mean(v)) if v else 0.0 for m, v in acc.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="42,123,2024")
    ap.add_argument("--embedding", default="english")
    ap.add_argument("--max-epochs", type=int, default=300)
    args = ap.parse_args()
    seeds = [int(s) for s in args.seeds.split(",")]
    embed = B.make_embedding_provider(args.embedding)
    per = {name: [] for name, *_ in VARIANTS}

    for seed in seeds:
        cvs, jobs, pairs, skill_catalog, cv_domain, job_domain, stats = JF.build_schema(*JF.load_v4(), seed=seed)
        nCV, nJ = len(cvs), len(jobs)
        cvid = {c.cv_id: i for i, c in enumerate(cvs)}; jbid = {j.job_id: i for i, j in enumerate(jobs)}
        train_seen = {}
        for p in [p for p in pairs if p.split in ("train", "val")]:
            train_seen.setdefault(cvid[p.cv_id], set()).add(jbid[p.job_id])
        test_pos = {}
        for p in [p for p in pairs if p.split == "test"]:
            test_pos.setdefault(cvid[p.cv_id], set()).add(jbid[p.job_id])
        log.info("seed %d | nCV=%d nJ=%d nTest=%d", seed, nCV, nJ, len(test_pos))

        graph_train = [p for p in pairs if p.split == "train"]
        data = GraphBuilder(embed).build(cvs, jobs, skill_catalog, graph_train)
        data_eval_src = copy.deepcopy(data)
        to_idx = lambda L: [(cvid[p.cv_id], jbid[p.job_id]) for p in L]

        for name, mt, extra in VARIANTS:
            try:
                cfg = TrainConfig(model_type=mt, hidden_channels=128, num_layers=2, dropout=0.3,
                                  epochs=args.max_epochs, patience=80, seed=seed, use_node_features=True, **extra)
                res = Trainer(cfg).train_generic(
                    data=copy.deepcopy(data),
                    train_pairs=to_idx([p for p in pairs if p.split == "train"]),
                    val_pairs=to_idx([p for p in pairs if p.split == "val"]),
                    test_pairs=to_idx([p for p in pairs if p.split == "test"]),
                    src_type="cv", dst_type="job", num_src=nCV, num_dst=nJ, eval_at_k=KS)
                model = res.model; model.eval(); dev = next(model.parameters()).device
                dclean = prepare_data_for_gnn(copy.deepcopy(data_eval_src)).to(dev)
                with torch.no_grad():
                    z = model.encode(dclean)
                z_cv, z_job = z["cv"], z["job"]
                mat = np.zeros((nCV, nJ), dtype=np.float32)
                with torch.no_grad():
                    for i in range(nCV):
                        mat[i] = torch.sigmoid(model.decoder(z_cv[i].unsqueeze(0).expand(nJ, -1), z_job).squeeze(-1)).detach().cpu().numpy()
                m = sampled_eval(mat, train_seen, test_pos, nJ, seed=seed)
                per[name].append(m)
                log.info("seed %d | %-22s | ndcg@20=%.4f recall@20=%.4f mrr=%.4f",
                         seed, name, m["ndcg@20"], m["recall@20"], m["mrr"])
            except Exception as e:
                log.warning("seed %d | %-22s | FAILED: %s", seed, name, e)

    agg = {name: {c: {"mean": float(np.mean([r[c] for r in per[name]])) if per[name] else 0.0,
                      "std": float(np.std([r[c] for r in per[name]])) if per[name] else 0.0} for c in COLS}
           for name in per}
    Path("results/gnn_variant").mkdir(parents=True, exist_ok=True)
    Path("results/gnn_variant/v4_sweep_3seed.json").write_text(json.dumps(
        {"dataset": "v4 internal, sampled-negative 1:100", "seeds": seeds, "results_mean_std": agg, "per_seed": per}, indent=2))

    base = agg["sage gốc (mean)"]["ndcg@20"]["mean"]
    rows = sorted(per.keys(), key=lambda n: -(agg[n]["ndcg@20"]["mean"]))
    print("\n=== SWEEP TRÊN BỘ v4 NỘI BỘ (sampled-negative 1:100, %d seed) ===" % len(seeds))
    print(f"{'Biến thể':24s} {'NDCG@20':>9s} {'±std':>7s} {'R@20':>8s} {'MRR':>8s} {'ΔNDCG vs gốc':>14s}")
    print("-" * 80)
    for n in rows:
        a = agg[n]; d = a["ndcg@20"]["mean"] - base
        print(f"{n:24s} {a['ndcg@20']['mean']:9.4f} {a['ndcg@20']['std']:7.4f} "
              f"{a['recall@20']['mean']:8.4f} {a['mrr']['mean']:8.4f} {d:+14.4f}")
    print("\nwrote results/gnn_variant/v4_sweep_3seed.json")


if __name__ == "__main__":
    main()
