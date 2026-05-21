"""LightGCN baseline wrapper (feature 010).

Thin wrapper around `torch_geometric.nn.models.LightGCN` for use in our
benchmark pipeline. LightGCN treats user and item as a single homogeneous
node space — user IDs are [0, num_users), item IDs are shifted to
[num_users, num_users + num_items).

Reference: He et al., SIGIR 2020, "LightGCN: Simplifying and Powering
Graph Convolution Network for Recommendation".
"""

from __future__ import annotations

import torch
import torch.nn as nn
from torch import Tensor
from torch_geometric.nn.models import LightGCN


class LightGCNScorer(nn.Module):
    """Wrap PyG LightGCN with helpers for single-namespace bipartite recsys.

    Usage:
        scorer = LightGCNScorer(num_users=Nu, num_items=Ni, embedding_dim=64, num_layers=3)
        edge_index = torch.stack([src_user_idx, shift_items(dst_item_idx, Nu)])
        loss = scorer.bpr_step(edge_index, pos_pairs, neg_items)
        z_user, z_item = scorer.get_user_item_embeddings(edge_index)
    """

    def __init__(
        self,
        num_users: int,
        num_items: int,
        embedding_dim: int = 64,
        num_layers: int = 3,
        alpha: float | None = None,
    ) -> None:
        super().__init__()
        self.num_users = num_users
        self.num_items = num_items
        self.num_nodes = num_users + num_items
        self.model = LightGCN(
            num_nodes=self.num_nodes,
            embedding_dim=embedding_dim,
            num_layers=num_layers,
            alpha=alpha,
        )

    def shift_items(self, item_indices: Tensor) -> Tensor:
        """Shift item indices into the [num_users, num_nodes) namespace."""
        return item_indices + self.num_users

    def get_user_item_embeddings(self, edge_index: Tensor) -> tuple[Tensor, Tensor]:
        """Run the K-layer propagation, then split into per-type embeddings."""
        embed = self.model.get_embedding(edge_index)
        return embed[: self.num_users], embed[self.num_users :]

    def score_edges(self, edge_index: Tensor, src: Tensor, dst_shifted: Tensor) -> Tensor:
        """Return rank scores for (src, dst) pairs. dst expected already shifted."""
        edge_label_index = torch.stack([src, dst_shifted])
        return self.model(edge_index, edge_label_index)

    def recommendation_loss(
        self,
        pos_rank: Tensor,
        neg_rank: Tensor,
        node_id: Tensor,
        lambda_reg: float = 1e-4,
    ) -> Tensor:
        return self.model.recommendation_loss(
            pos_rank, neg_rank, node_id=node_id, lambda_reg=lambda_reg
        )
