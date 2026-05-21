# Contract — LightGCN Baseline API

**Date**: 2026-05-21

## 1. New module

```python
from ml_benchmark.baselines.lightgcn import LightGCNScorer
```

## 2. LightGCNScorer class

```python
class LightGCNScorer(nn.Module):
    def __init__(
        self,
        num_users: int,
        num_items: int,
        embedding_dim: int = 64,
        num_layers: int = 3,
    ) -> None: ...
    
    def get_user_item_embeddings(self, edge_index: Tensor) -> tuple[Tensor, Tensor]:
        """Return (user_emb [Nu, d], item_emb [Ni, d])."""
    
    def score_edges(self, edge_index: Tensor, src: Tensor, dst: Tensor) -> Tensor:
        """Return scores for given (src, dst) edges. dst expected in shifted ID space."""
    
    def recommendation_loss(self, pos_rank: Tensor, neg_rank: Tensor, node_id: Tensor, lambda_reg: float = 1e-4) -> Tensor:
        """BPR loss + L2 reg on participating node embeddings."""
```

## 3. CLI

```bash
# Single seed
python backend/scripts/train_lightgcn.py \
    --dataset {movielens, careerbuilder} \
    --seed 42 \
    --output results/lightgcn/{dataset}_seed42.json

# Multi-seed via existing benchmark_compare:
python backend/scripts/benchmark_compare.py \
    --train-script scripts/train_lightgcn.py \
    --seeds 42 123 2024 \
    --output results/lightgcn/{dataset}_summary.json \
    --extra --dataset {dataset}
```

## 4. Output JSON schema

Identical to Phase 2/3 schema, with `model: "LightGCN"` and dataset-appropriate fields. See [data-model §E3](../data-model.md#e3-output-json-schema).

## 5. Forbidden imports

Inherit from Phase 2/3:
- KHÔNG `from ml_service.*`
- KHÔNG sửa `Trainer` / `HeteroGraphSAGE` classes

## 6. Backward compatibility

Phase 2 + Phase 3 surface untouched. Regression: smoke tests of both phases must still pass.
