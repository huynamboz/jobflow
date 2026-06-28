"""So sánh hàm tổng hợp của bộ mã hóa: GraphSAGE (mean) vs GAT (attention) trên
benchmark warm-start resume-JD, xếp hạng toàn không gian, 3 hạt giống. CHỈ dùng
sandbox ml_benchmark, KHÔNG đụng production. Ghi results/gnn_variant/.
"""
from __future__ import annotations
import argparse, copy, json, logging
from pathlib import Path
import numpy as np, torch

import bench_resume_jd_warm as W
import bench_resume_jd as B
from ml_benchmark.graph.builder import GraphBuilder
from ml_benchmark.training.trainer import TrainConfig, Trainer
from ml_benchmark.models.gnn import prepare_data_for_gnn
from ml_benchmark.evaluation.metrics import recall_at_k, ndcg_at_k, mrr

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s")
log = logging.getLogger("gnn_variant")
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


def gnn_full_eval(model, data_eval_src, nCV, nJ, train_seen, test_pos):
    model.eval(); dev = next(model.parameters()).device
    dclean = prepare_data_for_gnn(copy.deepcopy(data_eval_src)).to(dev)
    with torch.no_grad():
        z = model.encode(dclean)
    z_cv, z_job = z["cv"], z["job"]
    mat = np.zeros((nCV, nJ), dtype=np.float32)
    with torch.no_grad():
        for i in range(nCV):
            zc = z_cv[i].unsqueeze(0).expand(nJ, -1)
            mat[i] = torch.sigmoid(model.decoder(zc, z_job).squeeze(-1)).detach().cpu().numpy()
    return vec_eval(mat, train_seen, test_pos)


# Round 3: các hướng research (DropEdge, Contrastive SimGCL) + tổ hợp với hướng thắng
# (name, model_type, num_layers, extra TrainConfig kwargs)
VARIANTS = [
    ("sage gốc (mean 2L)",        "graphsage", 2, {}),
    ("+ DropEdge 0.2",            "graphsage", 2, {"drop_edge_rate": 0.2}),
    ("+ Contrastive (SimGCL)",    "graphsage", 2, {"contrastive_weight": 0.2}),
    ("+ DropEdge + Contrastive",  "graphsage", 2, {"drop_edge_rate": 0.2, "contrastive_weight": 0.2}),
    ("gat + Contrastive",         "gat",       2, {"contrastive_weight": 0.2}),
    ("gat_sum + Contrastive",     "gat_sum",   2, {"contrastive_weight": 0.2}),
    ("gat_sum + L2 + Contrastive","gat_sum_l2",2, {"contrastive_weight": 0.2}),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="42,123,2024")
    ap.add_argument("--embedding", default="english")
    ap.add_argument("--max-epochs", type=int, default=300)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    seeds = [int(s) for s in args.seeds.split(",")]
    embed = B.make_embedding_provider(args.embedding)
    per = {name: [] for name, *_ in VARIANTS}

    for seed in seeds:
        resumes, jobs, pairs_raw, features = W.load_data(args.smoke, seed)
        cvs, jobs_list, pairs, skill_catalog, stats = W.build_schema_objects(
            resumes, jobs, pairs_raw, features, positive="good_potential", seed=seed)
        nCV, nJ = len(cvs), len(jobs_list)
        cvid = {c.cv_id: i for i, c in enumerate(cvs)}; jbid = {j.job_id: i for i, j in enumerate(jobs_list)}
        train_seen = {}
        for p in [p for p in pairs if p.split in ("train", "val")]:
            train_seen.setdefault(cvid[p.cv_id], set()).add(jbid[p.job_id])
        test_pos = {}
        for p in [p for p in pairs if p.split == "test"]:
            test_pos.setdefault(cvid[p.cv_id], set()).add(jbid[p.job_id])

        graph_train = [p for p in pairs if p.split == "train"]
        builder = GraphBuilder(embed)
        data = builder.build(cvs, jobs_list, skill_catalog, graph_train)
        data_eval_src = copy.deepcopy(data)
        to_idx = lambda L: [(cvid[p.cv_id], jbid[p.job_id]) for p in L]

        for name, mt, nl, extra in VARIANTS:
            try:
                cfg = TrainConfig(model_type=mt, hidden_channels=128, num_layers=nl, dropout=0.3,
                                  epochs=args.max_epochs, patience=80, seed=seed, use_node_features=True,
                                  **extra)
                res = Trainer(cfg).train_generic(
                    data=copy.deepcopy(data),
                    train_pairs=to_idx([p for p in pairs if p.split == "train"]),
                    val_pairs=to_idx([p for p in pairs if p.split == "val"]),
                    test_pairs=to_idx([p for p in pairs if p.split == "test"]),
                    src_type="cv", dst_type="job", num_src=nCV, num_dst=nJ, eval_at_k=KS)
                m = gnn_full_eval(res.model, data_eval_src, nCV, nJ, train_seen, test_pos)
                per[name].append(m)
                log.info("seed %d | %-20s | ndcg@20=%.4f recall@20=%.4f mrr=%.4f",
                         seed, name, m["ndcg@20"], m["recall@20"], m["mrr"])
            except Exception as e:
                log.warning("seed %d | %-20s | FAILED: %s", seed, name, e)

    agg = {name: {c: {"mean": float(np.mean([r[c] for r in per[name]])) if per[name] else 0.0,
                      "std": float(np.std([r[c] for r in per[name]])) if per[name] else 0.0} for c in COLS}
           for name in per}
    Path("results/gnn_variant").mkdir(parents=True, exist_ok=True)
    out = {"dataset": "resume-JD warm-start full-space", "seeds": seeds,
           "protocol": "full-space, content node features, patience=80",
           "results_mean_std": agg, "per_seed": per}
    Path("results/gnn_variant/sweep3_3seed.json").write_text(json.dumps(out, indent=2))

    base = agg["sage gốc (mean 2L)"]["ndcg@20"]["mean"]
    rows = sorted(per.keys(), key=lambda n: -(agg[n]["ndcg@20"]["mean"]))
    print("\n=== SWEEP CÁC HƯỚNG CẢI TIẾN GNN (resume-JD warm full-space, %d seed) ===" % len(seeds))
    print(f"{'Biến thể':22s} {'NDCG@20':>9s} {'±std':>7s} {'R@20':>8s} {'MRR':>8s} {'ΔNDCG vs gốc':>14s}")
    print("-" * 78)
    for n in rows:
        a = agg[n]
        d = a["ndcg@20"]["mean"] - base
        print(f"{n:22s} {a['ndcg@20']['mean']:9.4f} {a['ndcg@20']['std']:7.4f} "
              f"{a['recall@20']['mean']:8.4f} {a['mrr']['mean']:8.4f} {d:+14.4f}")
    print("\nwrote results/gnn_variant/sweep3_3seed.json")


if __name__ == "__main__":
    main()
