"""LSTM / BiLSTM baseline training on CareerBuilder12 (feature 011).

Uses the same per-user full-ranking evaluation as Phase 2/3/4 so metrics are
directly comparable with HeteroSAGE, LightGCN, etc.

Usage:
    cd backend
    python scripts/train_lstm.py --dataset careerbuilder --seed 42 \
        --output results/lstm/careerbuilder_seed42.json
    python scripts/train_lstm.py --dataset careerbuilder --seed 42 --bilstm \
        --output results/bilstm/careerbuilder_seed42.json
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import math
import os
import platform
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import sklearn.metrics.pairwise  # noqa: F401
import torch_geometric  # noqa: F401

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

from ml_benchmark.baselines.lstm import LSTMScorer, Vocab, build_vocab, tokenize
from ml_benchmark.evaluation.metrics import hit_rate_at_k, mrr, ndcg_at_k, recall_at_k

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("train_lstm")


def _get_device() -> torch.device:
    return torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")


def _load_job_texts(jobs_path: Path, kept_job_ids: set[int]) -> dict[int, str]:
    """Read jobs_filtered.tsv and return {job_id: "title description"} for kept jobs."""
    df = pd.read_csv(
        jobs_path,
        sep="\t",
        encoding="ISO-8859-1",
        usecols=["JobID", "Title", "Description"],
        on_bad_lines="warn",
        low_memory=False,
        dtype={"JobID": "Int64"},
    )
    df = df.dropna(subset=["JobID"])
    df["JobID"] = df["JobID"].astype(int)
    df = df[df["JobID"].isin(kept_job_ids)]
    job_texts: dict[int, str] = {}
    for _, row in df.iterrows():
        title = str(row.get("Title", "") or "")
        desc = str(row.get("Description", "") or "")
        job_texts[int(row["JobID"])] = f"{title} {desc}"
    return job_texts


def _build_user_texts(
    train_pairs: list[tuple[int, int]],
    idx_to_job_id: list[int],
    job_to_skills: dict[int, set[str]],
) -> dict[int, str]:
    """Aggregate each user's TRAIN positives → skill keyword string.

    Important: only uses TRAIN pairs to avoid val/test leakage.
    """
    user_skills: dict[int, list[str]] = defaultdict(list)
    for u_idx, j_idx in train_pairs:
        job_id = idx_to_job_id[j_idx]
        for skill in job_to_skills.get(job_id, ()):
            user_skills[u_idx].append(skill)
    return {u: " ".join(skills) for u, skills in user_skills.items()}


def _extract_skills_per_job(jobs_path: Path, kept_job_ids: set[int]) -> dict[int, set[str]]:
    """Extract canonical skills per job using the same matcher as careerbuilder_loader hetero variant."""
    from ml_benchmark.data.careerbuilder_loader import (
        _build_skill_keyword_index,
        _compile_skill_patterns,
        _extract_skills_from_text,
    )

    skill_alias_path = Path(__file__).resolve().parent.parent / "ml_benchmark" / "data" / "skill-alias.json"
    alias_to_canonical, _ = _build_skill_keyword_index(skill_alias_path)
    patterns = _compile_skill_patterns(alias_to_canonical)

    df = pd.read_csv(
        jobs_path,
        sep="\t",
        encoding="ISO-8859-1",
        usecols=["JobID", "Title", "Description"],
        on_bad_lines="warn",
        low_memory=False,
        dtype={"JobID": "Int64"},
    )
    df = df.dropna(subset=["JobID"])
    df["JobID"] = df["JobID"].astype(int)
    df = df[df["JobID"].isin(kept_job_ids)]

    job_to_skills: dict[int, set[str]] = {}
    for _, row in df.iterrows():
        title = str(row.get("Title", "") or "")
        desc = str(row.get("Description", "") or "")
        skills = _extract_skills_from_text(f"{title} {desc}", alias_to_canonical, patterns)
        if skills:
            job_to_skills[int(row["JobID"])] = skills
    return job_to_skills


def evaluate_lstm(
    model: LSTMScorer,
    user_ids: torch.Tensor,
    user_lens: torch.Tensor,
    job_ids: torch.Tensor,
    job_lens: torch.Tensor,
    eval_pairs: list[tuple[int, int]],
    train_pos_by_src: dict[int, set[int]],
    num_users: int,
    num_jobs: int,
    eval_at_k: tuple[int, ...],
    device: torch.device,
    chunk_size: int = 512,
) -> dict[str, float]:
    """Per-user full ranking eval, dot product on encoded vectors."""
    if not eval_pairs:
        return {}

    eval_by_src: dict[int, list[int]] = {}
    for s, d in eval_pairs:
        eval_by_src.setdefault(s, []).append(d)

    eval_users = sorted(eval_by_src.keys())
    n_eval = len(eval_users)

    with torch.no_grad():
        # Encode all jobs once (job pool is small after k-core ~ 3K)
        job_emb_all = []
        for start in range(0, num_jobs, chunk_size):
            end = min(start + chunk_size, num_jobs)
            j_ids = job_ids[start:end].to(device)
            j_lens = job_lens[start:end].to(device)
            job_emb_all.append(model.encode(j_ids, j_lens))
        job_emb = torch.cat(job_emb_all, dim=0)  # [num_jobs, hidden]

    max_k = max(eval_at_k)
    log2_idx = torch.log2(torch.arange(2, max_k + 2, dtype=torch.float32, device=device))
    discount_topk = 1.0 / log2_idx[:max_k]

    accum: dict[str, float] = {f"recall@{k}": 0.0 for k in eval_at_k}
    accum.update({f"ndcg@{k}": 0.0 for k in eval_at_k})
    accum.update({f"hr@{k}": 0.0 for k in eval_at_k})
    accum["mrr"] = 0.0

    for start in range(0, n_eval, chunk_size):
        end = min(start + chunk_size, n_eval)
        chunk_users = eval_users[start:end]
        chunk = end - start
        u_idx = torch.tensor(chunk_users, dtype=torch.long, device=device)
        with torch.no_grad():
            user_emb = model.encode(user_ids[u_idx], user_lens[u_idx])  # [chunk, hidden]
            scores = user_emb @ job_emb.T  # [chunk, num_jobs]

        train_mask = torch.zeros(chunk, num_jobs, dtype=torch.bool, device=device)
        eval_pos = torch.zeros(chunk, num_jobs, dtype=torch.bool, device=device)
        for i, u in enumerate(chunk_users):
            seen = train_pos_by_src.get(u, set())
            if seen:
                train_mask[i, list(seen)] = True
            eval_pos[i, eval_by_src[u]] = True
        scores = scores.masked_fill(train_mask, float("-inf"))

        sorted_idx = scores.argsort(dim=-1, descending=True)
        is_pos_full = eval_pos.gather(1, sorted_idx)
        is_pos_topk = is_pos_full[:, :max_k].float()
        n_pos_per_user = eval_pos.sum(dim=-1).clamp(min=1).float()

        for k in eval_at_k:
            hits = is_pos_topk[:, :k]
            accum[f"recall@{k}"] += (hits.sum(dim=-1) / n_pos_per_user).sum().item()
            dcg = (hits * discount_topk[:k]).sum(dim=-1)
            n_ideal = eval_pos.sum(dim=-1).clamp(max=k)
            positions = torch.arange(k, device=device).unsqueeze(0)
            ideal_mask = positions < n_ideal.unsqueeze(1)
            idcg = (ideal_mask.float() * discount_topk[:k]).sum(dim=-1).clamp(min=1e-10)
            accum[f"ndcg@{k}"] += (dcg / idcg).sum().item()
            accum[f"hr@{k}"] += (hits.sum(dim=-1) > 0).float().sum().item()

        first_pos = is_pos_full.float().argmax(dim=-1)
        has_any = is_pos_full.any(dim=-1).float()
        accum["mrr"] += (has_any / (first_pos.float() + 1.0)).sum().item()

    for k in accum:
        accum[k] /= n_eval
    return accum


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", choices=["careerbuilder"], required=True)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--bilstm", action="store_true", help="Use BiLSTM (default: LSTM unidirectional)")
    p.add_argument("--max-epochs", type=int, default=100)
    p.add_argument("--patience", type=int, default=20)
    p.add_argument("--embed-dim", type=int, default=64)
    p.add_argument("--hidden-dim", type=int, default=64)
    p.add_argument("--max-seq-len", type=int, default=200)
    p.add_argument("--vocab-size", type=int, default=30_000)
    p.add_argument("--dropout", type=float, default=0.3)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--batch-size", type=int, default=256)
    p.add_argument("--subsample-users", type=int, default=50_000)
    p.add_argument("--k-core", type=int, default=10)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    device = _get_device()
    logger.info("Device: %s, model: %s", device, "BiLSTM" if args.bilstm else "LSTM")

    t_start = time.time()

    # 1. Load CB12 bipartite split (reuse Phase 3 loader)
    from ml_benchmark.data.careerbuilder_loader import load_careerbuilder_12
    ds = load_careerbuilder_12(
        cache_dir=_BACKEND_DIR.parent / "Dataset" / "careerbuilder-12",
        subsample_users=args.subsample_users,
        subsample_seed=args.seed,
        k_core=args.k_core,
        hidden_channels=args.hidden_dim,
        include_hetero=False,
        seed=args.seed,
    )
    sp = ds.split
    num_users, num_jobs = sp.num_users, sp.num_jobs
    logger.info("Dataset: %d users, %d jobs, train=%d val=%d test=%d",
                num_users, num_jobs, len(sp.train_pairs), len(sp.val_pairs), len(sp.test_pairs))

    # 2. Extract skill keywords per job for user-side aggregation + load job text
    jobs_path = _BACKEND_DIR.parent / "Dataset" / "careerbuilder-12" / "jobs_filtered.tsv"
    if not jobs_path.exists():
        raise RuntimeError(f"Missing {jobs_path} — sync from Phase 4c first")
    kept_job_ids = set(ds.idx_to_job_id)
    logger.info("Extracting skills per job for user aggregation ...")
    job_to_skills = _extract_skills_per_job(jobs_path, kept_job_ids)
    logger.info("Loading job text ...")
    job_texts = _load_job_texts(jobs_path, kept_job_ids)

    # 3. Build user side text from TRAIN positives only
    user_texts_dict = _build_user_texts(sp.train_pairs, ds.idx_to_job_id, job_to_skills)
    user_texts = [user_texts_dict.get(u_idx, "") for u_idx in range(num_users)]
    job_texts_list = [job_texts.get(jid, "") for jid in ds.idx_to_job_id]

    # 4. Build vocab from TRAINING job texts (no leak)
    logger.info("Building vocab ...")
    vocab = build_vocab(job_texts_list, max_size=args.vocab_size)

    # 5. Tokenize everything
    logger.info("Tokenizing user texts (%d) and job texts (%d) ...", len(user_texts), len(job_texts_list))
    user_ids_list, user_lens_list = [], []
    for t in user_texts:
        ids, ln = tokenize(t, vocab, args.max_seq_len)
        user_ids_list.append(ids); user_lens_list.append(ln)
    job_ids_list, job_lens_list = [], []
    for t in job_texts_list:
        ids, ln = tokenize(t, vocab, args.max_seq_len)
        job_ids_list.append(ids); job_lens_list.append(ln)
    user_ids_t = torch.tensor(user_ids_list, dtype=torch.long)
    user_lens_t = torch.tensor(user_lens_list, dtype=torch.long)
    job_ids_t = torch.tensor(job_ids_list, dtype=torch.long)
    job_lens_t = torch.tensor(job_lens_list, dtype=torch.long)
    logger.info("avg user seq len = %.1f, avg job seq len = %.1f",
                user_lens_t.float().mean().item(), job_lens_t.float().mean().item())

    # 6. Build per-user train-positive set for eval mask
    train_pos_by_src: dict[int, set[int]] = {}
    for u, j in sp.train_pairs:
        train_pos_by_src.setdefault(u, set()).add(j)

    # 7. Model + optimizer
    model = LSTMScorer(
        vocab_size=vocab.size,
        embed_dim=args.embed_dim,
        hidden_dim=args.hidden_dim,
        bidirectional=args.bilstm,
        dropout=args.dropout,
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)

    user_ids_t = user_ids_t.to(device)
    user_lens_t = user_lens_t.to(device)
    job_ids_t = job_ids_t.to(device)
    job_lens_t = job_lens_t.to(device)

    train_pairs_arr = np.asarray(sp.train_pairs, dtype=np.int64)
    n_train = len(train_pairs_arr)
    src_t = torch.from_numpy(train_pairs_arr[:, 0]).long().to(device)
    pos_t = torch.from_numpy(train_pairs_arr[:, 1]).long().to(device)

    # 8. Training loop (mini-batch BPR)
    best_val = -float("inf"); best_state = None; best_epoch = 0; patience_counter = 0
    train_losses: list[float] = []
    rng = np.random.RandomState(args.seed)

    for epoch in range(args.max_epochs):
        model.train()
        # Shuffle for mini-batch
        perm = rng.permutation(n_train)
        total_loss = 0.0
        n_batch = 0
        for b_start in range(0, n_train, args.batch_size):
            b_end = min(b_start + args.batch_size, n_train)
            b_idx = perm[b_start:b_end]
            b_src = src_t[b_idx]
            b_pos = pos_t[b_idx]
            b_neg = torch.randint(0, num_jobs, (len(b_idx),), device=device)

            u_emb = model.encode(user_ids_t[b_src], user_lens_t[b_src])
            pos_emb = model.encode(job_ids_t[b_pos], job_lens_t[b_pos])
            neg_emb = model.encode(job_ids_t[b_neg], job_lens_t[b_neg])
            pos_score = (u_emb * pos_emb).sum(dim=-1)
            neg_score = (u_emb * neg_emb).sum(dim=-1)
            loss = -F.logsigmoid(pos_score - neg_score).mean()

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item(); n_batch += 1
        avg_loss = total_loss / max(n_batch, 1)
        train_losses.append(avg_loss)

        model.eval()
        val_metrics = evaluate_lstm(
            model, user_ids_t, user_lens_t, job_ids_t, job_lens_t,
            sp.val_pairs, train_pos_by_src, num_users, num_jobs,
            eval_at_k=(20,), device=device,
        )
        val_signal = val_metrics.get("ndcg@20", 0.0)
        logger.info(
            "Epoch %d — loss=%.4f val_ndcg@20=%.4f val_recall@20=%.4f val_hr@20=%.4f",
            epoch, avg_loss, val_signal,
            val_metrics.get("recall@20", 0.0), val_metrics.get("hr@20", 0.0),
        )

        if val_signal > best_val:
            best_val = val_signal
            best_state = copy.deepcopy(model.state_dict())
            best_epoch = epoch
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= args.patience:
                logger.info("Early stopping at epoch %d (patience=%d)", epoch, args.patience)
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    test_metrics = evaluate_lstm(
        model, user_ids_t, user_lens_t, job_ids_t, job_lens_t,
        sp.test_pairs, train_pos_by_src, num_users, num_jobs,
        eval_at_k=(20,), device=device,
    )

    elapsed = time.time() - t_start
    has_nan = any(
        v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))
        for v in test_metrics.values()
    )
    if has_nan:
        logger.error("NaN in test metrics: %s", test_metrics)
        return 1

    output = {
        "feature": "011-thesis-defense-prep",
        "dataset": "CareerBuilder12",
        "variant": "bipartite",
        "preprocessing": {
            "subsample_users": args.subsample_users,
            "subsample_seed": args.seed,
            "k_core": args.k_core,
            "split": "leave-one-out per user (timestamp)",
        },
        "model": "BiLSTM" if args.bilstm else "LSTM",
        "config": {
            "embed_dim": args.embed_dim,
            "hidden_dim": args.hidden_dim,
            "num_layers": 1,
            "bidirectional": args.bilstm,
            "vocab_size": args.vocab_size,
            "vocab_actual_size": vocab.size,
            "max_seq_len": args.max_seq_len,
            "dropout": args.dropout,
            "lr": args.lr,
            "weight_decay": args.weight_decay,
            "batch_size": args.batch_size,
            "max_epochs": args.max_epochs,
            "early_stopping_patience": args.patience,
            "seed": args.seed,
        },
        "stats": {
            "num_users": num_users,
            "num_jobs": num_jobs,
            "num_train_pairs": len(sp.train_pairs),
            "num_val_pairs": len(sp.val_pairs),
            "num_test_pairs": len(sp.test_pairs),
            "avg_user_seq_len": float(user_lens_t.float().mean().item()),
            "avg_job_seq_len": float(job_lens_t.float().mean().item()),
        },
        "training": {
            "best_epoch": best_epoch,
            "epochs_run": len(train_losses),
            "final_train_loss": float(train_losses[-1]) if train_losses else None,
            "wall_time_seconds": round(elapsed, 2),
            "device": "cuda" if torch.cuda.is_available() else "cpu",
        },
        "test_metrics": {k: float(v) for k, v in test_metrics.items()},
        "versions": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "torch_geometric": torch_geometric.__version__,
            "numpy": np.__version__,
        },
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)
    logger.info("Result written to %s", args.output)

    print("\n" + "=" * 60)
    print(f"✓ {'BiLSTM' if args.bilstm else 'LSTM'} training completed ({args.output.name})")
    print(f"  Wall time:    {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"  Best epoch:   {best_epoch}/{len(train_losses)}")
    print(f"  Test NDCG@20: {test_metrics.get('ndcg@20', 0.0):.4f}")
    print(f"  Test Recall@20: {test_metrics.get('recall@20', 0.0):.4f}")
    print(f"  Test HR@20:   {test_metrics.get('hr@20', 0.0):.4f}")
    print(f"  Test MRR:     {test_metrics.get('mrr', 0.0):.4f}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
