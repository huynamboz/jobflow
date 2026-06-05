# Phase 0 — Research: LightGCN Baseline

**Date**: 2026-05-21

Verified bằng kiểm tra trực tiếp PyG 2.7.0 API trên server.

## R1. LightGCN source

### Decision

`torch_geometric.nn.models.LightGCN` (PyG built-in, 2.7.0 confirmed).

### Constructor

```python
LightGCN(num_nodes: int, embedding_dim: int, num_layers: int, alpha: Union[float, torch.Tensor, None] = None, **kwargs)
```

- `num_nodes` = total = N_users + N_items
- `embedding_dim` = 64 (paper)
- `num_layers` = 3 (paper §4.3)
- `alpha` = None → uniform 1/(K+1) layer aggregation (chuẩn paper)

### Key methods

```python
forward(edge_index, edge_label_index=None, edge_weight=None) -> Tensor
# Returns scores for (src, dst) pairs in edge_label_index

get_embedding(edge_index, edge_weight=None) -> Tensor[num_nodes, embedding_dim]
# Returns full embedding after K layers of GCN aggregation

recommend(edge_index, edge_weight=None, src_index=None, dst_index=None, k=1, sorted=True) -> Tensor
# Top-K recommendation for src nodes; convenient but we use manual scoring for fine control

recommendation_loss(pos_edge_rank, neg_edge_rank, node_id=None, lambda_reg=1e-4) -> Tensor
# BPR loss + L2 regularization on embeddings of node_id
```

## R2. ID space mapping

### Decision

Single namespace, item IDs shifted by `num_users`:

```python
shifted_pairs = [(u, item_idx + num_users) for u, item_idx in train_pairs]
edge_index = torch.tensor(shifted_pairs).T   # [2, num_edges]
# LightGCN treats both as node indices in [0, num_nodes)
```

### Rationale

PyG LightGCN không phân biệt user vs item node — homogeneous bipartite. Shift item IDs là convention chuẩn (LightGCN paper code, NGCF code).

## R3. Training loop — write fresh

### Decision

Viết `scripts/train_lightgcn.py` chứa training loop riêng (~150 lines). KHÔNG cố gắng squeeze vào `Trainer.train_generic()`.

### Skeleton

```python
def main():
    # 1. Load dataset (movielens or careerbuilder)
    if args.dataset == "movielens":
        ds = load_movielens_1m(...)
    else:
        ds = load_careerbuilder_12(...)
    
    num_users, num_items = ds.split.num_users, ds.split.num_movies/num_jobs
    num_nodes = num_users + num_items
    
    # 2. Build shifted edge_index (train edges only)
    train_arr = np.asarray(ds.split.train_pairs, dtype=np.int64)
    train_arr[:, 1] += num_users    # shift item IDs
    edge_index = torch.from_numpy(train_arr.T).long().to(device)
    
    # 3. Build LightGCN model
    model = LightGCN(num_nodes=num_nodes, embedding_dim=64, num_layers=3).to(device)
    optimizer = Adam(model.parameters(), lr=1e-3)
    
    # 4. Training loop with early stopping
    train_pos_by_src = build_per_user_train_set(...)
    train_src = torch.tensor(train_arr[:, 0], device=device)
    train_pos = torch.tensor(train_arr[:, 1], device=device)
    
    for epoch in range(max_epochs):
        # Sample negative: random item shifted into [num_users, num_nodes)
        neg = torch.randint(num_users, num_nodes, (n_train,), device=device)
        
        # Forward: compute scores for (src, pos) and (src, neg) edges
        pos_label = torch.stack([train_src, train_pos])
        neg_label = torch.stack([train_src, neg])
        pos_rank = model(edge_index, pos_label)
        neg_rank = model(edge_index, neg_label)
        
        # Loss: BPR + L2 on user + pos_item + neg_item embeddings
        node_id = torch.cat([train_src, train_pos, neg])
        loss = model.recommendation_loss(pos_rank, neg_rank, node_id=node_id, lambda_reg=1e-4)
        
        optimizer.zero_grad(); loss.backward(); optimizer.step()
        
        # Eval: per-user full ranking
        with torch.no_grad():
            val_metrics = evaluate_lightgcn(model, edge_index, ds.split.val_pairs, ...)
        
        # Early stopping check
        ...
    
    # 5. Final test eval + write result JSON
```

### Eval helper

Adapt `_evaluate_full_ranking` từ trainer.py — nhưng LightGCN có embedding khác way (single namespace):

```python
def evaluate_lightgcn(model, edge_index, eval_pairs, train_pos_by_src, num_users, num_items, eval_at_k):
    embed = model.get_embedding(edge_index)   # [num_nodes, d]
    user_emb = embed[:num_users]              # [num_users, d]
    item_emb = embed[num_users:]              # [num_items, d]
    
    eval_by_src = group by src...
    
    # Chunk users for memory
    for chunk_users in chunks(...):
        z_u = user_emb[chunk_users]   # [chunk, d]
        scores = z_u @ item_emb.T     # [chunk, num_items]  ← dot product (chuẩn LightGCN)
        
        # Mask train-seen + topk + compute metrics (same logic as Phase 2 GPU eval)
        ...
```

## R4. Loss function

### Decision

`model.recommendation_loss(pos_rank, neg_rank, node_id=node_id, lambda_reg=1e-4)`.

### Rationale

- Built-in BPR + L2 (chuẩn LightGCN paper §3.3)
- `lambda_reg=1e-4` = paper default
- `node_id` cho phép L2 chỉ trên embedding của nodes participating (efficient)

## R5. Eval — chuẩn LightGCN paper

Per-user full ranking với train-seen mask, NDCG/Recall/HR/MRR@20. Cùng methodology Phase 2/3 — bảo đảm apples-to-apples.

## R6. Hyperparameters (paper §4.3)

| Param | Value | Source |
|---|---|---|
| hidden_channels | 64 | Paper Table 4 |
| num_layers | 3 | Paper §4.3 — 3 layers best on ML-1M |
| lr | 1e-3 | Paper §4.3 |
| weight_decay (lambda_reg) | 1e-4 | Paper §3.3 (BPR L2) |
| BPR negative sampling | 1 random per positive | Paper §3.3 |
| alpha (layer combination) | None → uniform 1/(K+1) | PyG default = paper formula |
| max_epochs | 500 | Paper used 1000, our budget |
| early_stopping patience | 50 | Paper |

KHÔNG tune per-dataset → fair compare.

## R7-R8. Multi-seed + dataset switch

Reuse `benchmark_compare.py` đã có `--train-script` arg (từ Phase 3). Pattern:

```bash
python scripts/benchmark_compare.py \
  --train-script scripts/train_lightgcn.py \
  --seeds 42 123 2024 \
  --output results/lightgcn/movielens_summary.json \
  --extra --dataset movielens

# Repeat for --dataset careerbuilder
```

`train_lightgcn.py` forwards `--dataset` flag từ `--extra` đến script.

## Tổng kết

All decisions chốt từ verified API. Ready Phase 1.
