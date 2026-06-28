"""Non-trained baselines on CareerBuilder12 (same split as the neural models):
Random and Popularity (Rule-Based). Per-user full-ranking eval at @5/10/20 + MRR,
matching trainer._evaluate_full_ranking protocol (exclude train+val seen items).

Run with the SAME load config as the neural train scripts so the split is identical:
    --subsample-users 50000 --k-core 10 --seed 42
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np

from ml_benchmark.data.careerbuilder_loader import load_careerbuilder_12
from ml_benchmark.evaluation.metrics import recall_at_k, ndcg_at_k, mrr


def per_user_eval(score_fn, split, ks=(5, 10, 20)):
    nU, nJ = split.num_users, split.num_jobs
    seen = [set() for _ in range(nU)]
    for u, j in list(split.train_pairs) + list(split.val_pairs):
        seen[u].add(j)
    testpos: dict[int, list[int]] = {}
    for u, j in split.test_pairs:
        testpos.setdefault(u, []).append(j)

    acc = {f"recall@{k}": 0.0 for k in ks}
    acc.update({f"ndcg@{k}": 0.0 for k in ks})
    acc["mrr"] = 0.0
    n = 0
    for u, pos in testpos.items():
        s = np.asarray(score_fn(u), dtype=np.float64).copy()
        if seen[u]:
            s[list(seen[u])] = -np.inf  # exclude already-seen jobs from ranking
        y = np.zeros(nJ, dtype=np.float64)
        y[pos] = 1.0
        for k in ks:
            acc[f"recall@{k}"] += recall_at_k(y, s, k)
            acc[f"ndcg@{k}"] += ndcg_at_k(y, s, k)
        acc["mrr"] += mrr(y, s)
        n += 1
    return {m: v / n for m, v in acc.items()}, n


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--subsample-users", type=int, default=50_000)
    p.add_argument("--k-core", type=int, default=10)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output", type=Path, default=Path("results/careerbuilder/baselines_seed42.json"))
    args = p.parse_args()

    ds = load_careerbuilder_12(subsample_users=args.subsample_users, k_core=args.k_core, seed=args.seed)
    sp = ds.split
    nU, nJ = sp.num_users, sp.num_jobs
    print(f"CB12: users={nU} jobs={nJ} train={len(sp.train_pairs)} val={len(sp.val_pairs)} test={len(sp.test_pairs)}", flush=True)

    # --- Popularity (Rule-Based): score each job by its application count in TRAIN ---
    pop = np.zeros(nJ, dtype=np.float64)
    for _u, j in sp.train_pairs:
        pop[j] += 1.0
    pop_metrics, n = per_user_eval(lambda u: pop, sp)
    print(f"[Popularity] eval users={n}: {pop_metrics}", flush=True)

    # --- Random: fixed-seed random score per (user, job) ---
    rng = np.random.default_rng(args.seed)
    rand_mat = rng.random((nU, nJ))
    rand_metrics, _ = per_user_eval(lambda u: rand_mat[u], sp)
    print(f"[Random] {rand_metrics}", flush=True)

    out = {
        "feature": "009-careerbuilder-benchmark / baselines",
        "dataset": "careerbuilder12",
        "config": {"subsample_users": args.subsample_users, "k_core": args.k_core, "seed": args.seed,
                   "num_users": nU, "num_jobs": nJ, "num_test": len(sp.test_pairs)},
        "results": {"Random": rand_metrics, "Popularity": pop_metrics},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2))
    print(f"[done] wrote {args.output}", flush=True)


if __name__ == "__main__":
    main()
