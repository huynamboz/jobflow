"""Multi-seed benchmark for MovieLens-1M: run train_movielens.py with multiple
seeds, aggregate mean ± std for each metric, write a summary JSON.

Usage:
    cd backend
    python scripts/benchmark_compare.py --seeds 42 123 2024 \
        --output results/movielens/summary.json
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent


# LightGCN paper reference (He et al., SIGIR 2020), Table 2 MovieLens-1M.
LIGHTGCN_PAPER_REF = {"ndcg@20": 0.22, "recall@20": 0.26}


def run_one_seed(
    seed: int,
    out_path: Path,
    hetero: bool,
    extra_args: list[str],
    train_script: str = "scripts/train_movielens.py",
) -> dict:
    cmd = [
        sys.executable,
        str(_BACKEND_DIR / train_script),
        "--seed", str(seed),
        "--output", str(out_path),
    ]
    if hetero:
        cmd.append("--hetero")
    cmd.extend(extra_args)
    print(f"[seed={seed}] launching: {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=_BACKEND_DIR)
    if proc.returncode != 0:
        raise RuntimeError(f"{train_script} seed={seed} failed with exit {proc.returncode}")
    with open(out_path) as f:
        return json.load(f)


def aggregate(values: list[float]) -> dict:
    return {
        "mean": statistics.mean(values),
        "std": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "values": values,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seeds", type=int, nargs="+", default=[42, 123, 2024])
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--hetero", action="store_true")
    p.add_argument("--train-script", default="scripts/train_movielens.py",
                   help="Relative train script path (e.g. scripts/train_careerbuilder.py)")
    p.add_argument("--extra", nargs=argparse.REMAINDER, default=[],
                   help="Extra args forwarded to train script (e.g. --max-epochs 200)")
    args = p.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    variant = "hetero" if args.hetero else "bipartite"

    runs = []
    for seed in args.seeds:
        seed_out = args.output.parent / f"seed{seed}{'_hetero' if args.hetero else ''}.json"
        result = run_one_seed(seed, seed_out, args.hetero, args.extra or [], train_script=args.train_script)
        runs.append(result)

    # Aggregate test metrics across seeds
    metric_keys = sorted({k for r in runs for k in r["test_metrics"].keys()})
    aggregated = {}
    for k in metric_keys:
        vals = [r["test_metrics"][k] for r in runs if k in r["test_metrics"]]
        aggregated[k] = aggregate(vals)

    # LightGCN paper comparison flag
    in_oom = True
    notes = []
    for k, ref in LIGHTGCN_PAPER_REF.items():
        if k in aggregated:
            mean = aggregated[k]["mean"]
            ratio = mean / ref if ref else math.inf
            within = 0.1 <= ratio <= 10.0   # within an order of magnitude
            in_oom = in_oom and within
            notes.append(f"{k}: ours={mean:.4f} paper≈{ref:.4f} ratio={ratio:.2f}")

    summary = {
        "feature": "008-movielens-benchmark",
        "variant": variant,
        "seeds": args.seeds,
        "metrics": aggregated,
        "comparison_lightgcn_paper": {
            "in_same_order_of_magnitude": in_oom,
            "notes": notes,
            "reference": LIGHTGCN_PAPER_REF,
        },
        "run_count": len(runs),
    }

    with open(args.output, "w") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 60)
    print(f"✓ Multi-seed benchmark done ({args.output.name})")
    print(f"  Seeds: {args.seeds}")
    for k in ("ndcg@20", "recall@20", "hr@20", "mrr"):
        if k in aggregated:
            a = aggregated[k]
            print(f"  {k:<12} {a['mean']:.4f} ± {a['std']:.4f}")
    print(f"  Order-of-magnitude vs LightGCN: {'OK' if in_oom else 'OUT'}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
