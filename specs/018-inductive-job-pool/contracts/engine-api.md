# Contract: Inference Engine — job-pool rebuild & snapshot

Internal Python contract (ML library). No HTTP surface.

## `InferenceEngine.rebuild_job_pool(jobs: list[JobData]) -> RebuildReport`

Replace the engine's job pool with an inductively-encoded set built from `jobs`.

**Preconditions**:
- Engine loaded (model + CV/skill/seniority graph from checkpoint).
- `jobs` is the full desired pool (full-rebuild semantics; not a delta).

**Behaviour**:
1. Build 397-dim job-node features via the shared recipe helper (text emb + minmax salary over `jobs` + role onehot).
2. Copy the frozen graph (`_strip_label_edges(self._data)`), append all `jobs` as `job` nodes, add `requires_skill` (attr=importance, skills in `skill_to_idx` only) + `requires_seniority` edges.
3. `prepare_data_for_gnn` → one `model.encode()` → take `z_dict["job"][:len(jobs)]` (or the new-node slice).
4. Under `self._inductive_lock`, atomically swap `self._jobs`, `self._job_embeddings`, `self._job_text_vecs = embed([j.text for j in jobs])`.

**Postconditions**:
- `len(self._jobs) == self._job_embeddings.shape[0] == self._job_text_vecs.shape[0]`.
- `num_jobs == len(jobs)`. Subsequent `match_cv` ranks against `jobs`.
- Thread-safe: in-flight `match_cv` either sees the old pool fully or the new pool fully.

**Returns** `RebuildReport`: `{num_jobs, skill_skipped_edges, encode_seconds}`.

**Errors**: raises on dimension mismatch (feature recipe drift) — fail loud, do not serve a bad pool.

## `job_pool_snapshot.save(dir, jobs, embeddings, text_vecs, model_sig)`

Atomically persist the pool to `checkpoints/job_pool/`.

- Write to a temp sibling dir, then `os.replace` onto the target (atomic swap).
- Files: `jobs.json`, `job_embeddings.pt`, `job_text_vecs.npy`, `meta.json` (`count, built_at, source, model_sig, skill_skipped_edges`).
- Invariant: readers never observe a partial set.

## `job_pool_snapshot.load(dir, model_sig) -> (jobs, embeddings, text_vecs) | None`

- Returns the pool if the snapshot exists AND `meta.model_sig == model_sig`; else `None` (caller falls back to checkpoint jobs + warns).
- Validates the three-way length invariant; on mismatch → `None` + warn.

## `InferenceEngine.from_checkpoint(...)` (modified)

- After loading model + graph + CVs + checkpoint jobs, attempt `job_pool_snapshot.load`. If present, the snapshot pool **overrides** the checkpoint jobs (`self._jobs`/embeddings/text_vecs come from the snapshot; `_precompute_embeddings` still computes CV embeddings + `z_dict`).
- If absent, behaviour is unchanged (frozen checkpoint jobs) — backward compatible.

## `_get_engine()` reload (matching_service)

- On each call (cheap), stat `checkpoints/job_pool/meta.json` mtime. If newer than the loaded snapshot's mtime, reload the pool into the existing engine (via `job_pool_snapshot.load` + the same atomic swap as `rebuild_job_pool`) under the engine lock.
- No full engine rebuild; only the 3 pool structures refresh → realtime on the live server (FR-004).
