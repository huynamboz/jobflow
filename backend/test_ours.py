"""Standalone test of ONLY the proposed model (HeteroGraphSAGE) on the
resume-JD-fit dataset, with full diagnostics to explain why combined-script
test metrics were 0. Trains the content GNN, then evaluates test per-CV TWO ways
(decoder score vs embedding cosine) with rank diagnostics.
"""
from __future__ import annotations
import argparse, copy, logging, numpy as np, torch, torch.nn.functional as F

import bench_resume_jd as B  # reuse data builders
from ml_benchmark.graph.builder import GraphBuilder
from ml_benchmark.training.trainer import TrainConfig, Trainer, _strip_label_edges
from ml_benchmark.models.gnn import prepare_data_for_gnn
from ml_benchmark.evaluation.metrics import recall_at_k, ndcg_at_k, mrr

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s")
log = logging.getLogger("test_ours")
KS = B.KS


def per_cv_metrics(score_mat_fn, cvs, jobs, train_seen, test_pos, tag):
    """score_mat_fn(ci)-> np.ndarray[n_jobs]. Returns metrics + rank diagnostics."""
    nJ = len(jobs)
    acc = {f"recall@{k}": [] for k in KS}
    acc.update({f"ndcg@{k}": [] for k in KS})
    acc["mrr"] = []
    pos_ranks = []
    excluded_pos = 0
    for ci, posset in test_pos.items():
        s = score_mat_fn(ci).astype(np.float64).copy()
        seen = train_seen.get(ci, set())
        # count test positives that collide with train-seen (would be masked = bug source)
        excluded_pos += len(posset & seen)
        if seen:
            s[list(seen)] = -np.inf
        y = np.zeros(nJ);
        valid_pos = [j for j in posset if j not in seen]
        if not valid_pos:
            continue
        for j in valid_pos: y[j] = 1.0
        order = np.argsort(-s)
        rank_of = {int(j): int(p) for p, j in enumerate(order)}
        for j in valid_pos: pos_ranks.append(rank_of[j])
        for k in KS:
            acc[f"recall@{k}"].append(recall_at_k(y, s, k))
            acc[f"ndcg@{k}"].append(ndcg_at_k(y, s, k))
        acc["mrr"].append(mrr(y, s))
    out = {m: float(np.mean(v)) if v else 0.0 for m, v in acc.items()}
    pr = np.array(pos_ranks) if pos_ranks else np.array([nJ])
    log.info("[%s] n_eval_cv=%d  test_pos_collide_train_seen=%d  pos rank median=%.0f mean=%.0f (of %d jobs)",
             tag, len(acc["mrr"]), excluded_pos, np.median(pr), np.mean(pr), nJ)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--embedding", default="english")
    ap.add_argument("--max-epochs", type=int, default=300)
    ap.add_argument("--hidden", type=int, default=128)
    ap.add_argument("--layers", type=int, default=2)
    ap.add_argument("--dropout", type=float, default=0.3)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    embed = B.make_embedding_provider(args.embedding)
    alias, patterns = B._build_skill_engine()
    rows = B.load_resume_jd_rows(args.smoke, args.seed)
    cvs, jobs, pairs, skill_catalog, stats = B.build_schema_objects(rows, alias, patterns)
    log.info("cvs=%d jobs=%d skills=%d pairs=%d", len(cvs), len(jobs), len(skill_catalog), len(pairs))

    cv_id2idx = {c.cv_id: i for i, c in enumerate(cvs)}
    job_id2idx = {j.job_id: i for i, j in enumerate(jobs)}
    train_pos = [p for p in pairs if p.split == "train" and p.label == 1]
    test_pos_pairs = [p for p in pairs if p.split == "test" and p.label == 1]

    # val carve
    rng = np.random.default_rng(args.seed)
    idx = rng.permutation(len(train_pos)); ncut = max(1, int(0.1 * len(train_pos)))
    val_pos = [train_pos[i] for i in idx[:ncut]]
    graph_train = [train_pos[i] for i in idx[ncut:]]

    builder = GraphBuilder(embed)
    data = builder.build(cvs, jobs, skill_catalog, graph_train)
    data_eval_src = copy.deepcopy(data)  # keep clean copy; train_generic mutates `data` in place

    to_idx = lambda L: [(cv_id2idx[p.cv_id], job_id2idx[p.job_id]) for p in L
                        if p.cv_id in cv_id2idx and p.job_id in job_id2idx]
    cfg = TrainConfig(model_type="graphsage", hidden_channels=args.hidden, num_layers=args.layers,
                      dropout=args.dropout, epochs=args.max_epochs, patience=30, seed=args.seed,
                      use_node_features=True)  # content-aware: use SBERT node features, not learnable IDs
    res = Trainer(cfg).train_generic(
        data=data, train_pairs=to_idx(graph_train), val_pairs=to_idx(val_pos),
        test_pairs=to_idx(test_pos_pairs), src_type="cv", dst_type="job",
        num_src=len(cvs), num_dst=len(jobs), eval_at_k=KS)
    log.info("train_generic test_metrics (built-in): %s", {k: round(v, 4) for k, v in (res.test_metrics or {}).items() if "hr@" not in k})

    # --- custom diagnostic eval with the trained model ---
    model = res.model; model.eval()
    dev = next(model.parameters()).device
    data_clean = prepare_data_for_gnn(data_eval_src).to(dev)  # match trainer: keep all edges (incl match)
    with torch.no_grad():
        z = model.encode(data_clean)
    z_cv, z_job = z["cv"], z["job"]
    z_cv_n = F.normalize(z_cv, dim=-1); z_job_n = F.normalize(z_job, dim=-1)
    nJ = len(jobs)

    train_seen = {}
    for p in graph_train + val_pos:
        train_seen.setdefault(cv_id2idx[p.cv_id], set()).add(job_id2idx[p.job_id])
    test_pos = {}
    for p in test_pos_pairs:
        test_pos.setdefault(cv_id2idx[p.cv_id], set()).add(job_id2idx[p.job_id])

    def decoder_scores(ci):
        with torch.no_grad():
            zc = z_cv[ci].unsqueeze(0).expand(nJ, -1)
            return model.decoder(zc, z_job).squeeze(-1).detach().cpu().numpy()
    def cosine_scores(ci):
        return (z_cv_n[ci].unsqueeze(0) @ z_job_n.T).squeeze(0).detach().cpu().numpy()

    dec = per_cv_metrics(decoder_scores, cvs, jobs, train_seen, test_pos, "decoder")
    cos = per_cv_metrics(cosine_scores, cvs, jobs, train_seen, test_pos, "cosine-emb")
    print("\n=== OURS (HeteroGraphSAGE) test, 2 scoring signals ===")
    for tag, m in [("decoder", dec), ("cosine-emb", cos)]:
        print(f"{tag:12s} " + "  ".join(f"{c}={m[c]:.4f}" for c in B.METRIC_COLS))


if __name__ == "__main__":
    main()
