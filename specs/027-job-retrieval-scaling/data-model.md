# Data Model: Scalable Job-Pool Retrieval

**Feature**: 027-job-retrieval-scaling · **Date**: 2026-06-13

This feature is retrieval/serving infrastructure; it adds **one persistent table (Stage B)** and **one per-job derived field (Stage C)**. The `Job`/`JobSkill` catalog and the GNN graph are unchanged.

## Entities

### JobPoolVec (Stage B — new table `job_pool_vec`)

Per-eligible-job vector row backing ANN retrieval. One row per job currently in the rankable pool.

| Field | Type | Notes |
|---|---|---|
| `job_id` | bigint PK, FK→`jobs.id` (CASCADE) | 1:1 with a pooled Job |
| `gnn_emb` | `vector(D)` | frozen-model inductive job embedding; D = GNN hidden dim (e.g. 256). HNSW cosine index. |
| `text_vec` | `vector(384)` | MiniLM multilingual text vector (stored; recall ranks on `gnn_emb`) |
| `model_fingerprint` | varchar(64) | sha of the model weights the embedding was produced with; retrieval filters on the live model's fp |
| `content_hash` | varchar(64) | Stage C — hash of encode-affecting JobData fields (see below) |
| `updated_at` | timestamptz | last upsert time |

**Indexes**: HNSW on `gnn_emb` (`vector_cosine_ops`, `m=16`, `ef_construction` default); btree on `model_fingerprint`.

**Validation / rules**:
- A row exists **iff** the job is pool-eligible (active + ≥2 canonical skills). Ineligible/removed jobs are deleted.
- `gnn_emb` dimension MUST equal the live model's job-embedding dim; mismatched-fingerprint rows are ignored at query time (not served), guarding model swaps.
- `text_vec` dim fixed at 384 (MiniLM-L12).

**Lifecycle**: created/updated by `rebuild_job_pool` (full or incremental upsert); deleted when a job leaves the pool; whole table rebuilt on model change (new fingerprint).

### Job content hash (Stage C — derived, not a new table)

`content_hash = sha256(canonical(skills+importances) ‖ seniority ‖ encode_text)` where `encode_text` is exactly the text fed to the MiniLM encoder for that job. Stored:
- `vector` mode: in the snapshot meta as a `{job_id: content_hash}` map.
- `pgvector` mode: in `job_pool_vec.content_hash`.

**Rule**: two JobData that produce identical embeddings MUST produce identical `content_hash`; any field that changes the embedding MUST be in the hash. This is the correctness contract for "encode only changed jobs."

## Transient / in-memory (no persistence)

### Shortlist (per match request)

`list[(job_idx, recall_sim)]` of length ≤ `RETRIEVE_K`, produced by a `Retriever` and consumed by exact scoring. Not stored; defined by the [retriever contract](contracts/retriever.md).

### Unit-norm pool matrices (Stage A — in-memory cache)

`_job_embeddings_unit`, `_job_text_unit`: L2-normalized copies of the existing pool matrices, recomputed at pool load / snapshot reload. Memory ≈ same as existing matrices (N×D float32). Not persisted.

## Configuration (settings / env, not DB)

| Key | Default | Meaning |
|---|---|---|
| `RETRIEVAL_MODE` | `exact` → `vector` → `pgvector` | which Retriever serves; also the rollback switch |
| `RETRIEVE_K` | `1000` | shortlist size handed to exact scoring |
| `W_GNN` / `W_TEXT` | GNN-dominant | recall blend weights (gate recall only, not final score) |
| `HNSW_M` / `HNSW_EF_SEARCH` | `16` / tuned | Stage B index/query params |

## Relationships

```
Job (jobs) 1───1 JobPoolVec (job_pool_vec)        # only for pool-eligible jobs
JobPoolVec.model_fingerprint ── must match ──> live engine model fingerprint
JobData (in-memory, from get_all_job_data) ──hash──> content_hash ──> incremental diff
```

No change to `Job`, `JobSkill`, `CVData`, `EmployeeJobMatch`, or the GNN graph.
