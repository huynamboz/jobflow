from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.data import HeteroData
from torch_geometric.nn import GAT, GraphSAGE, RGCNConv, to_hetero
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
        jk: str | None = None,
        l2_norm: bool = False,
        hetero_aggr: str = "mean",
    ) -> None:
        super().__init__()
        self.l2_norm = l2_norm
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
            jk=jk,
        )
        self.gnn = to_hetero(backbone, metadata, aggr=hetero_aggr)
        self.decoder = MLPDecoder(hidden_channels)

    def encode(self, data: HeteroData) -> dict[str, torch.Tensor]:
        x_dict = {ntype: proj(data[ntype].x) for ntype, proj in self.projections.items()}
        z = self.gnn(x_dict, data.edge_index_dict)
        if getattr(self, "l2_norm", False):
            z = {k: F.normalize(v, p=2, dim=-1) for k, v in z.items()}
        return z

    def decode(self, z_dict: dict[str, torch.Tensor], cv_indices: torch.Tensor, job_indices: torch.Tensor) -> torch.Tensor:
        return self.decoder(z_dict["cv"][cv_indices], z_dict["job"][job_indices])

    def decode_generic(
        self,
        z_dict: dict[str, torch.Tensor],
        src_indices: torch.Tensor,
        dst_indices: torch.Tensor,
        src_type: str,
        dst_type: str,
    ) -> torch.Tensor:
        # Generic decoder for any (src, dst) node-type pair. Used by Trainer.train_generic
        # for datasets that are not CV/Job (e.g. MovieLens user/movie).
        return self.decoder(z_dict[src_type][src_indices], z_dict[dst_type][dst_indices])

    def forward(self, data: HeteroData, cv_indices: torch.Tensor, job_indices: torch.Tensor) -> torch.Tensor:
        return self.decode(self.encode(data), cv_indices, job_indices)


# ---------------------------------------------------------------------------
# GATv2 backbone (improvement: attention instead of mean aggregator)
# ---------------------------------------------------------------------------


class HeteroGAT(HeteroGraphSAGE):
    """Cải tiến: thay backbone GraphSAGE (mean aggregator) bằng GATv2 (attention).

    Trọng số từng lân cận TRONG mỗi loại cạnh được HỌC bằng attention thay vì
    trung bình đều; tổng hợp GIỮA các loại cạnh vẫn là mean. Opt-in qua
    ``model_type='gat'`` — KHÔNG đổi hành vi mặc định, KHÔNG đụng production.
    """

    def __init__(
        self,
        metadata: tuple[list[str], list[tuple[str, str, str]]],
        hidden_channels: int = 128,
        num_layers: int = 2,
        dropout: float = 0.0,
        node_dims: dict[str, int] | None = None,
        heads: int = 4,
        jk: str | None = None,
        l2_norm: bool = False,
        hetero_aggr: str = "mean",
    ) -> None:
        super().__init__(metadata, hidden_channels, num_layers, dropout, node_dims,
                         jk=jk, l2_norm=l2_norm, hetero_aggr=hetero_aggr)
        backbone = GAT(
            in_channels=hidden_channels,
            hidden_channels=hidden_channels,
            num_layers=num_layers,
            out_channels=hidden_channels,
            dropout=dropout,
            v2=True,
            heads=heads,
            jk=jk,
            add_self_loops=False,  # hetero bipartite edges: self-loops invalid
        )
        self.gnn = to_hetero(backbone, metadata, aggr=hetero_aggr)


class HeteroEdgeGAT(HeteroGraphSAGE):
    """Cải tiến: GATv2 dùng TRỌNG SỐ CẠNH (importance kỹ năng / proficiency) trong
    attention (edge_dim=1). Tận dụng edge_attr đang bị bỏ phí. Các cạnh không có
    trọng số được điền 1.0. Opt-in qua model_type='egat'.
    """

    def __init__(
        self,
        metadata,
        hidden_channels: int = 128,
        num_layers: int = 2,
        dropout: float = 0.0,
        node_dims: dict[str, int] | None = None,
        heads: int = 4,
        hetero_aggr: str = "mean",
    ) -> None:
        super().__init__(metadata, hidden_channels, num_layers, dropout, node_dims, hetero_aggr=hetero_aggr)
        backbone = GAT(
            in_channels=hidden_channels, hidden_channels=hidden_channels, num_layers=num_layers,
            out_channels=hidden_channels, dropout=dropout, v2=True, heads=heads,
            edge_dim=1, add_self_loops=False,
        )
        self.gnn = to_hetero(backbone, metadata, aggr=hetero_aggr)

    def encode(self, data: HeteroData) -> dict[str, torch.Tensor]:
        x_dict = {ntype: proj(data[ntype].x) for ntype, proj in self.projections.items()}
        ea_dict = {}
        for et in data.edge_types:
            ei = data[et].edge_index
            ea = getattr(data[et], "edge_attr", None)
            if ea is None:
                ea = torch.ones((ei.shape[1], 1), device=ei.device)
            elif ea.dim() == 1:
                ea = ea.unsqueeze(-1)
            ea_dict[et] = ea.float()
        return self.gnn(x_dict, data.edge_index_dict, ea_dict)


def make_model(kind, metadata, hidden_channels, num_layers, dropout, node_dims):
    """Factory: map a model_type string to a sandbox GNN variant for ablation.
    Default 'graphsage' = mô hình gốc (mean aggregator). Mọi biến thể đều opt-in.
    Cú pháp kind: base ∈ {graphsage, gat, gat8} + hậu tố tùy chọn _jk (jumping
    knowledge), _l2 (chuẩn hóa L2), _sum (tổng hợp giữa các loại cạnh = sum).
    """
    if kind == "rgcn":
        return HeteroRGCN(metadata=metadata, hidden_channels=hidden_channels, num_layers=num_layers)
    jk = "cat" if "jk" in kind else None
    l2 = "l2" in kind
    aggr = "sum" if "sum" in kind else "mean"
    if kind.startswith("egat"):
        return HeteroEdgeGAT(metadata=metadata, hidden_channels=hidden_channels, num_layers=num_layers,
                             dropout=dropout, node_dims=node_dims, heads=4, hetero_aggr=aggr)
    if kind.startswith("gat"):
        heads = 8 if "gat8" in kind else 4
        return HeteroGAT(metadata=metadata, hidden_channels=hidden_channels, num_layers=num_layers,
                         dropout=dropout, node_dims=node_dims, heads=heads, jk=jk, l2_norm=l2, hetero_aggr=aggr)
    return HeteroGraphSAGE(metadata=metadata, hidden_channels=hidden_channels, num_layers=num_layers,
                           dropout=dropout, node_dims=node_dims, jk=jk, l2_norm=l2, hetero_aggr=aggr)


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

    def decode_generic(
        self,
        z_dict: dict[str, torch.Tensor],
        src_indices: torch.Tensor,
        dst_indices: torch.Tensor,
        src_type: str,
        dst_type: str,
    ) -> torch.Tensor:
        return self.decoder(z_dict[src_type][src_indices], z_dict[dst_type][dst_indices])

    def forward(self, data: HeteroData, cv_indices: torch.Tensor, job_indices: torch.Tensor) -> torch.Tensor:
        return self.decode(self.encode(data), cv_indices, job_indices)
