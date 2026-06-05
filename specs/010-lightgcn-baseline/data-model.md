# Phase 1 — Data Model: LightGCN Baseline

**Date**: 2026-05-21

## E1. LightGCNScorer wrapper class

```python
class LightGCNScorer(nn.Module):
    """Minimal wrapper around torch_geometric.nn.models.LightGCN for our benchmark.
    
    Provides forward/eval methods matching the Phase 2 trainer pattern but
    using LightGCN's single-namespace ID convention (user [0, Nu), item [Nu, Nu+Ni)).
    """
    def __init__(self, num_users: int, num_items: int, embedding_dim: int = 64, num_layers: int = 3):
        super().__init__()
        self.num_users = num_users
        self.num_items = num_items
        self.num_nodes = num_users + num_items
        self.model = LightGCN(num_nodes=self.num_nodes, embedding_dim=embedding_dim, num_layers=num_layers)
    
    def forward(self, edge_index, src, pos, neg):
        """Returns (pos_rank, neg_rank, node_id) for recommendation_loss."""
        ...
    
    def get_user_item_embeddings(self, edge_index):
        embed = self.model.get_embedding(edge_index)
        return embed[:self.num_users], embed[self.num_users:]
    
    def recommendation_loss(self, pos_rank, neg_rank, node_id, lambda_reg=1e-4):
        return self.model.recommendation_loss(pos_rank, neg_rank, node_id=node_id, lambda_reg=lambda_reg)
```

## E2. ID mapping rules

- User IDs từ loader → keep as `user_idx` ∈ [0, Nu)
- Item IDs từ loader (movie or job) → shift to `item_idx + Nu` ∈ [Nu, Nu+Ni)
- edge_index shape `[2, num_edges]` — chỉ chứa train edges (no val/test leak)
- BPR triplets: src ∈ user space, pos/neg ∈ shifted item space

## E3. Output JSON schema

`backend/results/lightgcn/{dataset}_seed{N}.json`:

```json
{
  "feature": "010-lightgcn-baseline",
  "dataset": "MovieLens-1M" | "CareerBuilder12",
  "variant": "bipartite",
  "preprocessing": { ... same as Phase 2/3 ... },
  "model": "LightGCN",
  "config": {
    "embedding_dim": 64,
    "num_layers": 3,
    "lr": 1e-3,
    "weight_decay": 1e-4,
    "lambda_reg": 1e-4,
    "max_epochs": 500,
    "early_stopping_patience": 50,
    "seed": 42
  },
  "stats": { ... },
  "training": { ... },
  "test_metrics": { "ndcg@20": ..., "recall@20": ..., "hr@20": ..., "mrr": ... },
  "versions": { ... }
}
```

## E4. Invariants

| Rule | Check |
|---|---|
| Item indices shifted by Nu | `(edge_index[1] >= num_users).all()` |
| No val/test in train edges | set intersection check |
| Embedding shape `[Nu+Ni, d]` | `model.get_embedding(...).shape == (Nu+Ni, d)` |
| Negative sample in item space | `(neg >= num_users) & (neg < num_nodes)` |
