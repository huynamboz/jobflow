"""GNN v2/E1 — self-supervised pretraining (no labels needed).

Link prediction on the structural edges the whole graph has in abundance
(requires_skill: 6.2k jobs × skills; has_skill: CVs × skills): drop a fraction
of edges from message passing, predict dropped+kept edges vs random negatives
via dot-product, BCE loss. The backbone then starts BPR fine-tuning already
knowing "which skills belong together / what a role needs" — structure first,
supervision after (the Round-1 lesson).

    python run_pretrain.py --data data/processed/v4_relabel --epochs 120 \
        --out checkpoints/pretrain_v2/backbone.pt
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import torch

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger("pretrain")


def main(data_dir: Path, out: Path, epochs: int, drop: float, lr: float, seed: int) -> None:
    from run_train_save import load_dataset
    from ml_service.embedding import get_provider
    from ml_service.graph.builder import GraphBuilder
    from ml_service.models.gnn import HeteroGraphSAGE, prepare_data_for_gnn
    from ml_service.training.trainer import _strip_label_edges

    torch.manual_seed(seed)
    rng = np.random.RandomState(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    cvs, jobs, all_pairs, dataset, catalog = load_dataset(data_dir)
    logger.info("Building graph (%d cvs, %d jobs)…", len(cvs), len(jobs))
    data = GraphBuilder(get_provider()).build(cvs, jobs, catalog, all_pairs)
    data = prepare_data_for_gnn(_strip_label_edges(data)).to(device)

    node_dims = {nt: data[nt].x.shape[1] for nt in data.node_types}
    model = HeteroGraphSAGE(metadata=data.metadata(), hidden_channels=256,
                            num_layers=3, node_dims=node_dims).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    bce = torch.nn.BCEWithLogitsLoss()

    TARGETS = [("job", "requires_skill", "skill"), ("cv", "has_skill", "skill")]
    full_ei = {et: data[et].edge_index.clone() for et in TARGETS}
    n_skills = data["skill"].x.shape[0]

    for epoch in range(epochs):
        model.train()
        # drop a fraction of target edges from message passing this epoch
        view = data.clone()
        batch_pos = {}
        for et in TARGETS:
            ei = full_ei[et]
            m = ei.shape[1]
            keep = torch.from_numpy(rng.rand(m) > drop).to(device)
            view[et].edge_index = ei[:, keep]
            # predict a sample of ALL edges (dropped ones are the hard part)
            sample = torch.from_numpy(rng.choice(m, size=min(4096, m), replace=False)).to(device)
            batch_pos[et] = ei[:, sample]

        z = model.encode(view)
        loss = 0.0
        for et, pos in batch_pos.items():
            src_t = et[0]
            z_src, z_skill = z[src_t], z["skill"]
            pos_logit = (z_src[pos[0]] * z_skill[pos[1]]).sum(-1)
            neg_dst = torch.from_numpy(rng.randint(0, n_skills, size=pos.shape[1])).to(device)
            neg_logit = (z_src[pos[0]] * z_skill[neg_dst]).sum(-1)
            loss = loss + bce(pos_logit, torch.ones_like(pos_logit)) \
                        + bce(neg_logit, torch.zeros_like(neg_logit))

        opt.zero_grad(); loss.backward(); opt.step()
        if epoch % 10 == 0 or epoch == epochs - 1:
            with torch.no_grad():
                acc = ((pos_logit > 0).float().mean() + (neg_logit < 0).float().mean()) / 2
            logger.info("epoch %d — loss=%.4f link-acc=%.3f", epoch, float(loss), float(acc))

    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), out)
    logger.info("Pretrained backbone saved → %s", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/processed/v4_relabel")
    ap.add_argument("--out", default="checkpoints/pretrain_v2/backbone.pt")
    ap.add_argument("--epochs", type=int, default=120)
    ap.add_argument("--drop", type=float, default=0.3)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=500)
    a = ap.parse_args()
    main(Path(a.data), Path(a.out), a.epochs, a.drop, a.lr, a.seed)
