"""GNN-only on CB12-content (warm-start + text node features). Skips the slow
per-pair baselines; gets the Ours number fast via the GPU-vectorized train_generic.
"""
import argparse, logging
import bench_cb12_content as C
import bench_resume_jd as B

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s")
log = logging.getLogger("test_ours_cb12")

ap = argparse.ArgumentParser()
ap.add_argument("--subsample-users", type=int, default=50_000)
ap.add_argument("--k-core", type=int, default=10)
ap.add_argument("--seed", type=int, default=42)
ap.add_argument("--embedding", default="english")
ap.add_argument("--max-epochs", type=int, default=300)
args = ap.parse_args()

embed = B.make_embedding_provider(args.embedding)
alias, patterns = B._build_skill_engine()

ds = C.load_careerbuilder_12(cache_dir=C.CACHE_DIR, subsample_users=args.subsample_users, k_core=args.k_core, seed=args.seed)
keep_job_ids = set(ds.idx_to_job_id)
job_text_map = C.load_job_text_map(C.JOBS_FILTERED, keep_job_ids)
cvs, jobs, pairs, skill_catalog, stats = C.build_schema_objects(ds, job_text_map, alias, patterns)
log.info("stats: %s", stats)

res = C.run_gnn_cb12(cvs, jobs, pairs, skill_catalog, embed,
                     seed=args.seed, max_epochs=args.max_epochs,
                     patience=30, hidden=64, num_layers=2, lr=1e-3, weight_decay=1e-4)
print("\n=== HeteroGraphSAGE (Ours, content + warm-start) on CB12 ===")
print("  ".join(f"{k}={res[k]:.4f}" for k in B.METRIC_COLS))
print("\n(LightGCN prior: ndcg@20=0.2746 recall@20=0.6523 mrr=0.1795)")
