from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field

import numpy as np
import torch
from torch_geometric.data import HeteroData

from ml_benchmark.baselines.skill_overlap import SkillOverlapScorer
from ml_benchmark.evaluation.metrics import (
    compute_all_metrics,
    hit_rate_at_k,
    mrr,
    ndcg_at_k,
    recall_at_k,
)
from ml_benchmark.graph.schema import (
    EDGE_TRIPLETS,
    CVData,
    DatasetSplit,
    EdgeType,
    JobData,
    LabeledPair,
)
from ml_benchmark.models.gnn import HeteroGraphSAGE, HeteroRGCN, prepare_data_for_gnn
from ml_benchmark.models.losses import bpr_loss

logger = logging.getLogger(__name__)


def _get_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    # MPS (Apple Silicon) is slower than CPU for small heterogeneous graphs
    # due to op overhead — skip it and fall through to CPU.
    return torch.device("cpu")


@dataclass
class TrainConfig:
    model_type: str = "graphsage"  # "graphsage" or "rgcn"
    hidden_channels: int = 128
    num_layers: int = 2
    lr: float = 1e-3
    weight_decay: float = 1e-5
    epochs: int = 50
    patience: int = 10
    dropout: float = 0.0          # dropout on GNN layers
    drop_edge_rate: float = 0.0  # DropEdge (ICLR 2020): fraction of edges to drop per train iter
    full_space_neg: bool = True  # BPR standard: sample negatives from full job space, not just labeled
    warmup_epochs: int = 0       # skip early stopping for first N epochs (avoids curriculum transition dip)
    hybrid_alpha: float = 0.6
    hybrid_beta: float = 0.3
    hybrid_gamma: float = 0.1
    seed: int = 42


@dataclass
class TrainResult:
    best_epoch: int = 0
    train_losses: list[float] = field(default_factory=list)
    val_metrics_history: list[dict[str, float]] = field(default_factory=list)
    test_metrics: dict[str, float] = field(default_factory=dict)
    model: HeteroGraphSAGE | None = None  # trained model (best checkpoint)
    data_clean: HeteroData | None = None  # graph data (label edges stripped)


def _strip_label_edges(data: HeteroData) -> HeteroData:
    """Remove match/no_match edges to prevent label leakage during GNN message passing."""
    data = copy.copy(data)
    for etype in (EdgeType.MATCH, EdgeType.NO_MATCH):
        triplet = EDGE_TRIPLETS[etype]
        if triplet in data.edge_types:
            del data[triplet]
    return data


def _sample_bpr_pairs(
    pairs: list[LabeledPair],
    rng: np.random.RandomState,
    cv_id_to_idx: dict[int, int],
    job_id_to_idx: dict[int, int],
    num_jobs: int,
    *,
    hard_neg_ratio: float = 0.7,
    full_space_neg: bool = True,
    cvs: list[CVData] | None = None,
    jobs: list[JobData] | None = None,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Sample (cv, pos_job, neg_job) BPR triplets with hard negative priority.

    Hard negatives (same role, similar skills, wrong match) are sampled
    with probability `hard_neg_ratio`. This forces GNN to learn subtle
    differences like Flask vs React, not just Frontend vs DevOps.
    """
    pos_by_cv: dict[int, list[int]] = {}
    neg_by_cv: dict[int, list[int]] = {}
    for p in pairs:
        if p.cv_id not in cv_id_to_idx or p.job_id not in job_id_to_idx:
            continue
        if p.label == 1:
            pos_by_cv.setdefault(p.cv_id, []).append(job_id_to_idx[p.job_id])
        else:
            neg_by_cv.setdefault(p.cv_id, []).append(job_id_to_idx[p.job_id])

    # Split negatives into hard vs easy (if CV/job data available)
    hard_neg_by_cv: dict[int, list[int]] = {}
    easy_neg_by_cv: dict[int, list[int]] = {}

    if cvs and jobs:
        cv_idx_to_data = {cv_id_to_idx.get(cv.cv_id): cv for cv in cvs if cv.cv_id in cv_id_to_idx}
        job_idx_to_data = {job_id_to_idx.get(j.job_id): j for j in jobs if j.job_id in job_id_to_idx}

        for cv_id, neg_jobs in neg_by_cv.items():
            cv_idx = cv_id_to_idx[cv_id]
            cv_data = cv_idx_to_data.get(cv_idx)
            if not cv_data:
                easy_neg_by_cv[cv_id] = neg_jobs
                continue

            cv_skills = set(cv_data.skills)
            hard, easy = [], []
            for job_idx in neg_jobs:
                job_data = job_idx_to_data.get(job_idx)
                if job_data:
                    job_skills = set(job_data.skills)
                    union = cv_skills | job_skills
                    overlap = len(cv_skills & job_skills) / len(union) if union else 0
                    sen_dist = abs(int(cv_data.seniority) - int(job_data.seniority))
                    # Hard: some overlap + similar seniority (subtle mismatch)
                    if overlap >= 0.15 and sen_dist <= 1:
                        hard.append(job_idx)
                    else:
                        easy.append(job_idx)
                else:
                    easy.append(job_idx)

            hard_neg_by_cv[cv_id] = hard
            easy_neg_by_cv[cv_id] = easy
    else:
        for cv_id, neg_jobs in neg_by_cv.items():
            easy_neg_by_cv[cv_id] = neg_jobs

    cv_indices, pos_indices, neg_indices = [], [], []
    for cv_id, pos_jobs in pos_by_cv.items():
        cv_idx = cv_id_to_idx[cv_id]
        hard_negs = hard_neg_by_cv.get(cv_id, [])
        easy_negs = easy_neg_by_cv.get(cv_id, [])
        all_negs = hard_negs + easy_negs
        pos_job_set = set(pos_jobs)  # known positive job indices for this CV

        for pos_job in pos_jobs:
            if hard_negs and rng.random() < hard_neg_ratio:
                # Hard neg: domain-specific difficult cases from labeled set
                neg_job = hard_negs[rng.randint(0, len(hard_negs))]
            elif full_space_neg:
                # BPR standard: sample uniformly from entire job catalog.
                # This trains the model to rank positives above ALL jobs,
                # not just the 0.44% that were labeled — directly optimizes
                # the per-CV full-ranking objective.
                for _ in range(10):
                    neg_job = rng.randint(0, num_jobs)
                    if neg_job not in pos_job_set:
                        break
            elif all_negs:
                neg_job = all_negs[rng.randint(0, len(all_negs))]
            else:
                neg_job = rng.randint(0, num_jobs)

            cv_indices.append(cv_idx)
            pos_indices.append(pos_job)
            neg_indices.append(neg_job)

    return (
        torch.tensor(cv_indices, dtype=torch.long),
        torch.tensor(pos_indices, dtype=torch.long),
        torch.tensor(neg_indices, dtype=torch.long),
    )


def _seniority_match_score(cv: CVData, job: JobData) -> float:
    """1.0 if seniority matches, decaying by distance."""
    dist = abs(int(cv.seniority) - int(job.seniority))
    return max(0.0, 1.0 - dist * 0.25)


def _apply_drop_edge(data: HeteroData, rate: float, rng: np.random.RandomState) -> HeteroData:
    """Randomly drop edges per training iteration (DropEdge, ICLR 2020)."""
    if rate <= 0.0:
        return data
    data = copy.copy(data)
    for edge_type in data.edge_types:
        ei = data[edge_type].edge_index
        num_edges = ei.shape[1]
        if num_edges == 0:
            continue
        keep = torch.from_numpy(rng.random(num_edges) >= rate)
        data[edge_type].edge_index = ei[:, keep]
        ea = getattr(data[edge_type], "edge_attr", None)
        if ea is not None:
            data[edge_type].edge_attr = ea[keep]
    return data


def _curriculum_hard_neg_ratio(epoch: int) -> float:
    """Curriculum schedule: start easy, ramp up hard negatives over training."""
    if epoch < 5:
        return 0.0
    elif epoch < 20:
        return 0.3
    else:
        return 0.7


class Trainer:
    """BPR training loop with early stopping and hybrid scoring evaluation."""

    def __init__(self, config: TrainConfig | None = None) -> None:
        self.config = config or TrainConfig()
        self._device = _get_device()
        logger.info("Device: %s", self._device)

    def train(
        self,
        data: HeteroData,
        dataset: DatasetSplit,
        cvs: list[CVData],
        jobs: list[JobData],
    ) -> TrainResult:
        """Train the GNN model and return results."""
        cfg = self.config
        seed = getattr(cfg, "seed", 42)
        rng = np.random.RandomState(seed)
        torch.manual_seed(seed)
        np.random.seed(seed)

        cv_id_to_idx = {cv.cv_id: i for i, cv in enumerate(cvs)}
        job_id_to_idx = {job.job_id: i for i, job in enumerate(jobs)}

        device = self._device

        # Strip label edges and prepare data for GNN
        data_clean = _strip_label_edges(data)
        data_clean = prepare_data_for_gnn(data_clean)
        data_clean = data_clean.to(device)

        # Build model
        metadata = data_clean.metadata()
        if cfg.model_type == "rgcn":
            model = HeteroRGCN(
                metadata=metadata,
                hidden_channels=cfg.hidden_channels,
                num_layers=cfg.num_layers,
            )
        else:
            node_dims = {
                ntype: data_clean[ntype].x.shape[1]
                for ntype in data_clean.node_types
                if hasattr(data_clean[ntype], "x") and data_clean[ntype].x is not None
            }
            model = HeteroGraphSAGE(
                metadata=metadata,
                hidden_channels=cfg.hidden_channels,
                num_layers=cfg.num_layers,
                dropout=cfg.dropout,
                node_dims=node_dims,
            )
        model = model.to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)

        result = TrainResult()
        best_val_signal = -float("inf")
        patience_counter = 0
        best_state = None

        # Pre-generate val BPR negatives once — fixed across all epochs so val_bpr
        # is deterministic (no noise from re-sampling different negatives each epoch).
        val_rng = np.random.RandomState(99)
        val_cv_idx_fixed, val_pos_idx_fixed, val_neg_idx_fixed = _sample_bpr_pairs(
            dataset.val, val_rng, cv_id_to_idx, job_id_to_idx, len(jobs),
            hard_neg_ratio=0.0, full_space_neg=cfg.full_space_neg,
            cvs=None, jobs=None,
        )
        val_cv_idx_fixed = val_cv_idx_fixed.to(device)
        val_pos_idx_fixed = val_pos_idx_fixed.to(device)
        val_neg_idx_fixed = val_neg_idx_fixed.to(device)

        for epoch in range(cfg.epochs):
            # --- Train ---
            model.train()
            hard_neg_ratio = _curriculum_hard_neg_ratio(epoch)
            cv_idx, pos_idx, neg_idx = _sample_bpr_pairs(
                dataset.train, rng, cv_id_to_idx, job_id_to_idx, len(jobs),
                hard_neg_ratio=hard_neg_ratio,
                full_space_neg=cfg.full_space_neg,
                cvs=cvs, jobs=jobs,
            )
            if len(cv_idx) == 0:
                logger.warning("No BPR pairs sampled for epoch %d", epoch)
                result.train_losses.append(0.0)
                result.val_metrics_history.append({})
                continue

            cv_idx = cv_idx.to(device)
            pos_idx = pos_idx.to(device)
            neg_idx = neg_idx.to(device)

            train_data = _apply_drop_edge(data_clean, cfg.drop_edge_rate, rng)
            z_dict = model.encode(train_data)
            pos_scores = model.decode(z_dict, cv_idx, pos_idx)
            neg_scores = model.decode(z_dict, cv_idx, neg_idx)
            loss = bpr_loss(pos_scores, neg_scores)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            loss_val = loss.item()
            result.train_losses.append(loss_val)

            # --- Validate ---
            model.eval()
            with torch.no_grad():
                # Val BPR loss with fixed negatives (pre-generated before training loop).
                # Fixed negatives make val_bpr deterministic across epochs — no noise
                # from re-sampling different random negatives each epoch.
                if len(val_cv_idx_fixed) > 0:
                    z_val = model.encode(data_clean)
                    val_pos_s = model.decode(z_val, val_cv_idx_fixed, val_pos_idx_fixed)
                    val_neg_s = model.decode(z_val, val_cv_idx_fixed, val_neg_idx_fixed)
                    val_bpr = bpr_loss(val_pos_s, val_neg_s).item()
                else:
                    val_bpr = float("inf")

                val_metrics = self._evaluate_split(
                    model, data_clean, dataset.val, cvs, jobs, cv_id_to_idx, job_id_to_idx
                )
            result.val_metrics_history.append(val_metrics)

            val_auc = val_metrics.get("auc_roc", 0.0)
            val_ndcg = val_metrics.get("ndcg@10", 0.0)
            # val_bpr logged for diagnostics; val_auc used as early stopping signal.
            # warmup_epochs skips patience counting during curriculum transition
            # (epoch 5-20 often shows a temporary val_auc dip when hard negs kick in).
            val_signal = val_auc
            logger.info(
                "Epoch %d — loss=%.4f, val_bpr=%.4f, val_auc=%.4f, val_ndcg@10=%.4f",
                epoch, loss_val, val_bpr, val_auc, val_ndcg,
            )

            if val_signal > best_val_signal:
                best_val_signal = val_signal
                best_state = copy.deepcopy(model.state_dict())
                result.best_epoch = epoch
                patience_counter = 0
            elif epoch >= cfg.warmup_epochs:
                patience_counter += 1
                if patience_counter >= cfg.patience:
                    logger.info("Early stopping at epoch %d", epoch)
                    break

        # Restore best model and evaluate on test
        if best_state is not None:
            model.load_state_dict(best_state)
        model.eval()
        with torch.no_grad():
            result.test_metrics = self._evaluate_split(
                model, data_clean, dataset.test, cvs, jobs, cv_id_to_idx, job_id_to_idx
            )

        # Store model and data for downstream use (e.g. per-CV evaluation)
        result.model = model
        result.data_clean = data_clean

        return result

    def _evaluate_split(
        self,
        model: HeteroGraphSAGE,
        data: HeteroData,
        pairs: list[LabeledPair],
        cvs: list[CVData],
        jobs: list[JobData],
        cv_id_to_idx: dict[int, int],
        job_id_to_idx: dict[int, int],
    ) -> dict[str, float]:
        """Evaluate using hybrid scoring: alpha*GNN + beta*skill_overlap + gamma*seniority."""
        if not pairs:
            return {}

        cfg = self.config
        skill_scorer = SkillOverlapScorer()

        cv_indices = []
        job_indices = []
        valid_pairs = []
        for p in pairs:
            ci = cv_id_to_idx.get(p.cv_id)
            ji = job_id_to_idx.get(p.job_id)
            if ci is not None and ji is not None:
                cv_indices.append(ci)
                job_indices.append(ji)
                valid_pairs.append(p)

        if not valid_pairs:
            return {}

        device = self._device
        cv_idx_t = torch.tensor(cv_indices, dtype=torch.long).to(device)
        job_idx_t = torch.tensor(job_indices, dtype=torch.long).to(device)

        # GNN scores (min-max normalized to [0, 1])
        z_dict = model.encode(data)
        gnn_scores = model.decode(z_dict, cv_idx_t, job_idx_t).cpu().numpy()
        gnn_min, gnn_max = gnn_scores.min(), gnn_scores.max()
        if gnn_max - gnn_min > 1e-8:
            gnn_norm = (gnn_scores - gnn_min) / (gnn_max - gnn_min)
        else:
            gnn_norm = np.full_like(gnn_scores, 0.5)

        # Feature-based scores
        skill_scores = np.array(
            [skill_scorer.score(cvs[ci], jobs[ji]) for ci, ji in zip(cv_indices, job_indices)]
        )
        seniority_scores = np.array(
            [_seniority_match_score(cvs[ci], jobs[ji]) for ci, ji in zip(cv_indices, job_indices)]
        )

        # Hybrid combination
        hybrid = (
            cfg.hybrid_alpha * gnn_norm
            + cfg.hybrid_beta * skill_scores
            + cfg.hybrid_gamma * seniority_scores
        )

        y_true = np.array([p.label for p in valid_pairs])
        return compute_all_metrics(y_true, hybrid)

    # ------------------------------------------------------------------
    # Generic training loop for datasets without CV/Job schema (e.g. MovieLens).
    # Pure BPR + random negative + per-user full-ranking evaluation, matching
    # the LightGCN paper convention. Does NOT use hybrid scoring or hard negatives.
    # ------------------------------------------------------------------

    def train_generic(
        self,
        data: HeteroData,
        train_pairs: list[tuple[int, int]],
        val_pairs: list[tuple[int, int]],
        test_pairs: list[tuple[int, int]],
        *,
        src_type: str = "user",
        dst_type: str = "movie",
        num_src: int,
        num_dst: int,
        eval_at_k: tuple[int, ...] = (20,),
    ) -> TrainResult:
        cfg = self.config
        seed = getattr(cfg, "seed", 42)
        rng = np.random.RandomState(seed)
        torch.manual_seed(seed)
        np.random.seed(seed)

        device = self._device

        # Per-user positive set for train (used to mask seen items at eval time)
        train_pos_by_src: dict[int, set[int]] = {}
        for s, d in train_pairs:
            train_pos_by_src.setdefault(s, set()).add(d)

        data_clean = prepare_data_for_gnn(data).to(device)
        metadata = data_clean.metadata()
        node_dims = {
            ntype: data_clean[ntype].x.shape[1]
            for ntype in data_clean.node_types
            if hasattr(data_clean[ntype], "x") and data_clean[ntype].x is not None
        }
        model = HeteroGraphSAGE(
            metadata=metadata,
            hidden_channels=cfg.hidden_channels,
            num_layers=cfg.num_layers,
            dropout=cfg.dropout,
            node_dims=node_dims,
        ).to(device)

        # Learnable embedding tables per node type — replace the frozen Xavier
        # tensors that the loader puts on data[ntype].x. Without this, only the
        # projection layer learns and signal per-user/item is essentially fixed
        # (verified empirically: frozen embeddings give NDCG@20 ≈ 0.006 vs paper 0.22).
        node_embeddings = torch.nn.ModuleDict()
        for ntype in data_clean.node_types:
            x = getattr(data_clean[ntype], "x", None)
            if x is None:
                continue
            num_nodes, emb_dim = x.shape
            emb = torch.nn.Embedding(num_nodes, emb_dim).to(device)
            torch.nn.init.xavier_uniform_(emb.weight)
            node_embeddings[ntype] = emb

        optimizer = torch.optim.Adam(
            list(model.parameters()) + list(node_embeddings.parameters()),
            lr=cfg.lr,
            weight_decay=cfg.weight_decay,
        )

        # Helper to refresh data.x → embedding.weight before each encode call
        def _refresh_features():
            for ntype, emb in node_embeddings.items():
                data_clean[ntype].x = emb.weight

        _refresh_features()

        train_arr = np.asarray(train_pairs, dtype=np.int64)
        train_src = torch.from_numpy(train_arr[:, 0]).long().to(device)
        train_pos = torch.from_numpy(train_arr[:, 1]).long().to(device)
        n_train = len(train_pairs)

        result = TrainResult()
        best_val_signal = -float("inf")
        patience_counter = 0
        best_state = None
        primary_k = eval_at_k[0]

        for epoch in range(cfg.epochs):
            model.train()
            # BPR: 1 random negative per positive (LightGCN convention)
            neg_np = rng.randint(0, num_dst, size=n_train).astype(np.int64)
            neg = torch.from_numpy(neg_np).long().to(device)

            z_dict = model.encode(data_clean)
            pos_s = model.decode_generic(z_dict, train_src, train_pos, src_type, dst_type)
            neg_s = model.decode_generic(z_dict, train_src, neg, src_type, dst_type)
            loss = bpr_loss(pos_s, neg_s)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            result.train_losses.append(loss.item())

            # Validate
            model.eval()
            with torch.no_grad():
                val_metrics = self._evaluate_full_ranking(
                    model, data_clean, val_pairs, train_pos_by_src,
                    src_type=src_type, dst_type=dst_type,
                    num_dst=num_dst, eval_at_k=eval_at_k,
                )
            result.val_metrics_history.append(val_metrics)

            val_signal = val_metrics.get(f"ndcg@{primary_k}", 0.0)
            logger.info(
                "Epoch %d — loss=%.4f val_ndcg@%d=%.4f val_recall@%d=%.4f val_hr@%d=%.4f",
                epoch, loss.item(),
                primary_k, val_signal,
                primary_k, val_metrics.get(f"recall@{primary_k}", 0.0),
                primary_k, val_metrics.get(f"hr@{primary_k}", 0.0),
            )

            if val_signal > best_val_signal:
                best_val_signal = val_signal
                best_state = {
                    "model": copy.deepcopy(model.state_dict()),
                    "embeddings": copy.deepcopy(node_embeddings.state_dict()),
                }
                result.best_epoch = epoch
                patience_counter = 0
            elif epoch >= cfg.warmup_epochs:
                patience_counter += 1
                if patience_counter >= cfg.patience:
                    logger.info("Early stopping at epoch %d (patience=%d)", epoch, cfg.patience)
                    break

        if best_state is not None:
            model.load_state_dict(best_state["model"])
            node_embeddings.load_state_dict(best_state["embeddings"])
            _refresh_features()
        model.eval()
        with torch.no_grad():
            result.test_metrics = self._evaluate_full_ranking(
                model, data_clean, test_pairs, train_pos_by_src,
                src_type=src_type, dst_type=dst_type,
                num_dst=num_dst, eval_at_k=eval_at_k,
            )

        result.model = model
        result.data_clean = data_clean
        return result

    def _evaluate_full_ranking(
        self,
        model: HeteroGraphSAGE,
        data: HeteroData,
        eval_pairs: list[tuple[int, int]],
        train_pos_by_src: dict[int, set[int]],
        *,
        src_type: str,
        dst_type: str,
        num_dst: int,
        eval_at_k: tuple[int, ...],
        chunk_size: int = 1024,
    ) -> dict[str, float]:
        # Per-user full-ranking eval, chuẩn LightGCN paper §4.2:
        # for each user, score ALL items except those seen in TRAIN,
        # then compute Recall/NDCG/HR@k + MRR on whether the user's eval items rank high.
        #
        # Vectorized GPU implementation: chunks of `chunk_size` users at a time,
        # scores all items in one batched MLP forward, sorts + computes metrics on GPU.
        # ~5-10x faster than the per-user Python loop.
        if not eval_pairs:
            return {}

        device = self._device

        # Group eval pairs by src user
        eval_by_src: dict[int, list[int]] = {}
        for s, d in eval_pairs:
            eval_by_src.setdefault(s, []).append(d)

        eval_users = sorted(eval_by_src.keys())
        n_eval = len(eval_users)
        if n_eval == 0:
            return {}

        # Encode once
        z_dict = model.encode(data)
        z_src_full = z_dict[src_type]   # [num_src, hidden]
        z_dst_full = z_dict[dst_type]   # [num_dst, hidden]
        decoder = model.decoder
        max_k = max(eval_at_k)
        log2_idx = torch.log2(torch.arange(2, num_dst + 2, dtype=torch.float32, device=device))
        discount_topk = 1.0 / log2_idx[:max_k]

        accum: dict[str, float] = {}
        for k in eval_at_k:
            accum[f"recall@{k}"] = 0.0
            accum[f"ndcg@{k}"] = 0.0
            accum[f"hr@{k}"] = 0.0
        accum["mrr"] = 0.0

        for start in range(0, n_eval, chunk_size):
            end = min(start + chunk_size, n_eval)
            chunk = end - start
            chunk_users = eval_users[start:end]
            user_idx = torch.tensor(chunk_users, dtype=torch.long, device=device)
            z_u = z_src_full[user_idx]                                   # [chunk, hidden]

            # Build (chunk * num_dst, 2*hidden) input for MLP decoder
            z_u_exp = z_u.unsqueeze(1).expand(-1, num_dst, -1)            # [chunk, num_dst, hidden]
            z_m_exp = z_dst_full.unsqueeze(0).expand(chunk, -1, -1)        # [chunk, num_dst, hidden]
            z_cat = torch.cat([z_u_exp, z_m_exp], dim=-1)                 # [chunk, num_dst, 2*hidden]
            z_flat = z_cat.reshape(-1, z_cat.shape[-1])
            scores = decoder.lin2(torch.relu(decoder.lin1(z_flat))).squeeze(-1)
            scores = scores.view(chunk, num_dst)                          # [chunk, num_dst]

            # Mask: -inf at items seen in train (so they don't appear in top-K)
            train_mask = torch.zeros(chunk, num_dst, dtype=torch.bool, device=device)
            eval_pos = torch.zeros(chunk, num_dst, dtype=torch.bool, device=device)
            for i, u in enumerate(chunk_users):
                seen = train_pos_by_src.get(u, set())
                if seen:
                    train_mask[i, list(seen)] = True
                eval_pos[i, eval_by_src[u]] = True

            scores = scores.masked_fill(train_mask, float("-inf"))

            # Sort scores descending → ranking per user
            sorted_idx = scores.argsort(dim=-1, descending=True)           # [chunk, num_dst]
            is_pos_full = eval_pos.gather(1, sorted_idx)                   # [chunk, num_dst]
            is_pos_topk = is_pos_full[:, :max_k].float()                   # [chunk, max_k]

            n_pos_per_user = eval_pos.sum(dim=-1).clamp(min=1).float()     # [chunk]

            for k in eval_at_k:
                hits_at_k = is_pos_topk[:, :k]                              # [chunk, k]
                recall_per_user = hits_at_k.sum(dim=-1) / n_pos_per_user
                accum[f"recall@{k}"] += recall_per_user.sum().item()

                dcg = (hits_at_k * discount_topk[:k]).sum(dim=-1)
                # Ideal DCG: cap positives to k, then sum top-k of discount
                n_ideal_per_user = eval_pos.sum(dim=-1).clamp(max=k)        # [chunk]
                positions = torch.arange(k, device=device).unsqueeze(0)     # [1, k]
                ideal_mask = positions < n_ideal_per_user.unsqueeze(1)      # [chunk, k]
                idcg = (ideal_mask.float() * discount_topk[:k]).sum(dim=-1).clamp(min=1e-10)
                ndcg_per_user = dcg / idcg
                accum[f"ndcg@{k}"] += ndcg_per_user.sum().item()

                hr_per_user = (hits_at_k.sum(dim=-1) > 0).float()
                accum[f"hr@{k}"] += hr_per_user.sum().item()

            # MRR over full ranking: 1 / rank_of_first_positive (1-indexed)
            first_pos = is_pos_full.float().argmax(dim=-1)                 # [chunk]
            has_any_pos = is_pos_full.any(dim=-1).float()
            mrr_per_user = has_any_pos / (first_pos.float() + 1.0)
            accum["mrr"] += mrr_per_user.sum().item()

        for key in accum:
            accum[key] /= n_eval
        return accum


def make_gnn_hybrid_scorer(
    model: HeteroGraphSAGE,
    data_clean: HeteroData,
    cvs: list[CVData],
    jobs: list[JobData],
    config: TrainConfig,
):
    """Create batch and single scoring functions using GNN hybrid scoring.

    Pre-computes GNN embeddings once, then each call only does:
      decode (MLP forward) + skill overlap + seniority match.

    Returns:
        batch_score_fn: (cv: CVData, jobs: list[JobData]) -> np.ndarray
            Scores all jobs for one CV with per-CV min-max normalization.
        score_fn: (cv: CVData, job: JobData) -> float
            Single-pair scoring with sigmoid normalization (for compatibility).

    Args:
        model: Trained GNN model.
        data_clean: Graph data with label edges already stripped and prepared
                    (as returned by TrainResult.data_clean).
    """
    cv_id_to_idx = {cv.cv_id: i for i, cv in enumerate(cvs)}
    job_id_to_idx = {job.job_id: i for i, job in enumerate(jobs)}

    device = next(model.parameters()).device
    model.eval()
    with torch.no_grad():
        z_dict = model.encode(data_clean)

    skill_scorer = SkillOverlapScorer()

    def batch_score_fn(cv: CVData, candidate_jobs: list[JobData]) -> np.ndarray:
        """Score all candidate jobs for one CV with min-max normalization."""
        ci = cv_id_to_idx.get(cv.cv_id)
        if ci is None:
            return np.zeros(len(candidate_jobs))

        # Batch GNN decode
        job_indices = []
        valid_mask = []
        for j in candidate_jobs:
            ji = job_id_to_idx.get(j.job_id)
            if ji is not None:
                job_indices.append(ji)
                valid_mask.append(True)
            else:
                job_indices.append(0)  # placeholder
                valid_mask.append(False)

        with torch.no_grad():
            cv_idx_t = torch.full((len(job_indices),), ci, dtype=torch.long, device=device)
            job_idx_t = torch.tensor(job_indices, dtype=torch.long, device=device)
            gnn_raw = model.decode(z_dict, cv_idx_t, job_idx_t).cpu().numpy()

        # Min-max normalize GNN scores per-CV (same as training evaluation)
        valid_scores = gnn_raw[valid_mask] if any(valid_mask) else gnn_raw
        gnn_min, gnn_max = valid_scores.min(), valid_scores.max()
        if gnn_max - gnn_min > 1e-8:
            gnn_norm = (gnn_raw - gnn_min) / (gnn_max - gnn_min)
        else:
            gnn_norm = np.full_like(gnn_raw, 0.5)

        # Skill overlap and seniority scores
        skill_scores = np.array([skill_scorer.score(cv, j) for j in candidate_jobs])
        seniority_scores = np.array([_seniority_match_score(cv, j) for j in candidate_jobs])

        # Hybrid combination
        hybrid = (
            config.hybrid_alpha * gnn_norm
            + config.hybrid_beta * skill_scores
            + config.hybrid_gamma * seniority_scores
        )

        # Zero out invalid jobs
        for i, valid in enumerate(valid_mask):
            if not valid:
                hybrid[i] = 0.0

        return hybrid

    def score_fn(cv: CVData, job: JobData) -> float:
        """Single-pair scoring (uses sigmoid normalization)."""
        ci = cv_id_to_idx.get(cv.cv_id)
        ji = job_id_to_idx.get(job.job_id)
        if ci is None or ji is None:
            return 0.0

        with torch.no_grad():
            raw = model.decode(
                z_dict,
                torch.tensor([ci], dtype=torch.long, device=device),
                torch.tensor([ji], dtype=torch.long, device=device),
            )
            gnn_score = torch.sigmoid(raw).item()

        skill_score = skill_scorer.score(cv, job)
        seniority_score = _seniority_match_score(cv, job)

        return (
            config.hybrid_alpha * gnn_score
            + config.hybrid_beta * skill_score
            + config.hybrid_gamma * seniority_score
        )

    return batch_score_fn, score_fn
