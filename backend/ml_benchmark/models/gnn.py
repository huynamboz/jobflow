from __future__ import annotations

import torch
import torch.nn as nn
from torch_geometric.data import HeteroData
from torch_geometric.nn import GraphSAGE, RGCNConv, to_hetero
from torch_geometric.transforms import ToUndirected


class MLPDecoder(nn.Module):
    """MLP decoder: concatenate (cv, job) embeddings -> scalar score."""

    def __init__(self, hidden_channels: int) -> None:
        super().__init__()
        self.lin1 = nn.Linear(2 * hidden_channels, hidden_channels)
        self.lin2 = nn.Linear(hidden_channels, 1)

    def forward(self, z_cv: torch.Tensor, z_job: torch.Tensor) -> torch.Tensor:
        z = torch.cat([z_cv, z_job], dim=-1)
        z = torch.relu(self.lin1(z))
        return self.lin2(z).squeeze(-1)


def prepare_data_for_gnn(data: HeteroData) -> HeteroData:
    """Add reverse edges so every node type is a message destination."""
    return ToUndirected()(data)


# ---------------------------------------------------------------------------
# GraphSAGE backbone (original)
# ---------------------------------------------------------------------------


class HeteroGraphSAGE(nn.Module):
    """Heterogeneous GNN using GraphSAGE backbone.

    Architecture:
    1. Per-type linear projections to common ``hidden_channels``
    2. PyG ``GraphSAGE`` wrapped with ``to_hetero()`` for message passing
    3. ``MLPDecoder`` to produce (cv, job) match scores
    """

    def __init__(
        self,
        metadata: tuple[list[str], list[tuple[str, str, str]]],
        hidden_channels: int = 128,
        num_layers: int = 2,
        dropout: float = 0.0,
        node_dims: dict[str, int] | None = None,
    ) -> None:
        super().__init__()
        if node_dims is None:
            node_dims = {"cv": 386, "job": 386, "skill": 385, "seniority": 6}

        self.projections = nn.ModuleDict(
            {ntype: nn.Linear(dim, hidden_channels) for ntype, dim in node_dims.items()}
        )

        backbone = GraphSAGE(
            in_channels=hidden_channels,
            hidden_channels=hidden_channels,
            num_layers=num_layers,
            out_channels=hidden_channels,
            dropout=dropout,
        )
        self.gnn = to_hetero(backbone, metadata, aggr="mean")
        self.decoder = MLPDecoder(hidden_channels)

    def encode(self, data: HeteroData) -> dict[str, torch.Tensor]:
        x_dict = {ntype: proj(data[ntype].x) for ntype, proj in self.projections.items()}
        return self.gnn(x_dict, data.edge_index_dict)

    def decode(self, z_dict: dict[str, torch.Tensor], cv_indices: torch.Tensor, job_indices: torch.Tensor) -> torch.Tensor:
        return self.decoder(z_dict["cv"][cv_indices], z_dict["job"][job_indices])

    def forward(self, data: HeteroData, cv_indices: torch.Tensor, job_indices: torch.Tensor) -> torch.Tensor:
        return self.decode(self.encode(data), cv_indices, job_indices)


# ---------------------------------------------------------------------------
# RGCN backbone (relation-aware, distinguishes edge types)
# ---------------------------------------------------------------------------


class HeteroRGCN(nn.Module):
    """Heterogeneous GNN using RGCN backbone.

    Unlike GraphSAGE, RGCN uses **relation-specific weight matrices** for each
    edge type, better distinguishing has_skill vs requires_skill vs seniority edges.

    Architecture:
    1. Per-type linear projections
    2. Stacked RGCNConv layers (one per edge type, with basis decomposition)
    3. MLPDecoder for scoring
    """

    def __init__(
        self,
        metadata: tuple[list[str], list[tuple[str, str, str]]],
        hidden_channels: int = 128,
        num_layers: int = 2,
        node_dims: dict[str, int] | None = None,
        num_bases: int | None = None,
    ) -> None:
        super().__init__()
        if node_dims is None:
            node_dims = {"cv": 386, "job": 386, "skill": 385, "seniority": 6}

        self._node_types = metadata[0]
        self._edge_types = metadata[1]
        num_relations = len(self._edge_types)

        # Per-type projection
        self.projections = nn.ModuleDict(
            {ntype: nn.Linear(dim, hidden_channels) for ntype, dim in node_dims.items()}
        )

        # Stacked RGCN layers
        self.convs = nn.ModuleList()
        for _ in range(num_layers):
            self.convs.append(
                RGCNConv(
                    in_channels=hidden_channels,
                    out_channels=hidden_channels,
                    num_relations=num_relations,
                    num_bases=num_bases,
                )
            )

        self.decoder = MLPDecoder(hidden_channels)

        # Build edge_type → relation_id mapping
        self._rel_map: dict[tuple[str, str, str], int] = {
            et: i for i, et in enumerate(self._edge_types)
        }

    def encode(self, data: HeteroData) -> dict[str, torch.Tensor]:
        # Project all nodes to common dim, stack into one tensor
        node_offsets: dict[str, int] = {}
        node_slices: dict[str, tuple[int, int]] = {}
        x_parts = []
        offset = 0
        for ntype in self._node_types:
            proj = self.projections[ntype]
            x_n = proj(data[ntype].x)
            n = x_n.size(0)
            node_offsets[ntype] = offset
            node_slices[ntype] = (offset, offset + n)
            x_parts.append(x_n)
            offset += n

        x = torch.cat(x_parts, dim=0)  # [total_nodes, hidden]

        # Build unified edge_index + edge_type tensor
        edge_indices = []
        edge_types = []
        for et in self._edge_types:
            if et not in data.edge_types:
                continue
            ei = data[et].edge_index.clone()
            src_type, _, dst_type = et
            ei[0] += node_offsets[src_type]
            ei[1] += node_offsets[dst_type]
            edge_indices.append(ei)
            edge_types.append(torch.full((ei.size(1),), self._rel_map[et], dtype=torch.long))

        if not edge_indices:
            # No edges — return projected features
            z_dict = {}
            for ntype in self._node_types:
                s, e = node_slices[ntype]
                z_dict[ntype] = x[s:e]
            return z_dict

        edge_index = torch.cat(edge_indices, dim=1)
        edge_type = torch.cat(edge_types)

        # Message passing
        for conv in self.convs:
            x = torch.relu(conv(x, edge_index, edge_type))

        # Split back to per-type
        z_dict = {}
        for ntype in self._node_types:
            s, e = node_slices[ntype]
            z_dict[ntype] = x[s:e]

        return z_dict

    def decode(self, z_dict: dict[str, torch.Tensor], cv_indices: torch.Tensor, job_indices: torch.Tensor) -> torch.Tensor:
        return self.decoder(z_dict["cv"][cv_indices], z_dict["job"][job_indices])

    def forward(self, data: HeteroData, cv_indices: torch.Tensor, job_indices: torch.Tensor) -> torch.Tensor:
        return self.decode(self.encode(data), cv_indices, job_indices)
