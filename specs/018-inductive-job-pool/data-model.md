# Phase 1 Data Model: Inductive Live-Catalog Job Ranking

No database schema changes. This feature adds an on-disk artifact (the job-pool snapshot) and a deterministic mapping from existing DB rows into the engine's in-memory `JobData`.

## Entity 1 — `JobData` built from the live catalog

In-memory dataclass consumed by the engine (`ml_service/graph/schema.py::JobData`). Built by `build_jobdata_from_db()`.

| JobData field | Source (DB) | Mapping rule |
|---|---|---|
| `job_id` | `Job.id` | direct (becomes the single match identifier) |
| `seniority` | `Job.seniority` | `SeniorityLevel(int)` |
| `skills` | `JobSkill.skill.name` for the job | normalized skill names (same normalizer the checkpoint used) |
| `skill_importances` | `JobSkill.importance` | 1–5, aligned 1:1 with `skills` |
| `salary_min` / `salary_max` | `Job.salary_min` / `Job.salary_max` | int; 0 when absent (most rows) |
| `text` | `Job.title` + `Job.description` | join title + description (same text used for the embedding) |
| `role_category` | `Job.role_category` | string; default `"other"` |
| `experience_min` / `experience_max` | not stored on `Job` | default `0.0` / `None` (reranker treats 0 as "neutral") |

**Validation / rules**:
- Only include jobs with ≥1 skill that maps into the checkpoint skill catalog; jobs whose skills are entirely unknown still load but rank on text only (R8). After cleanup all current jobs qualify.
- Skill names MUST pass through the same `SkillNormalizer` used at training so they key into `skill_to_idx`.
- Ordering within the pool is the build order; `job_id` is the stable key (used by Stage-1 context + persistence). No positional coupling outside the 3 parallel arrays.

## Entity 2 — Job-Pool Snapshot (new on-disk artifact)

Directory `checkpoints/job_pool/`, written atomically (temp dir + `os.replace`).

| File | Content | Notes |
|---|---|---|
| `jobs.json` | list of JobData dicts | same serialization as `checkpoint.py::_job_to_dict` |
| `job_embeddings.pt` | `torch.Tensor [N, H]` | GNN `z_dict["job"]` rows, order matches `jobs.json` |
| `job_text_vecs.npy` | `np.ndarray [N, 384]` | sentence-embeddings of each job `text` |
| `meta.json` | `{count, built_at, source:"live", model_sig, skill_skipped_edges}` | `model_sig` = fingerprint of the checkpoint used, to refuse loading a snapshot built against a different model |

**Invariants**:
- `len(jobs.json) == job_embeddings.pt.shape[0] == job_text_vecs.npy.shape[0]`.
- `model_sig` MUST match the loaded checkpoint; mismatch → ignore snapshot, fall back to checkpoint jobs + warn.
- Atomic replace guarantees readers never see a partial set.

## Entity 3 — In-engine pool state (mutated by `rebuild_job_pool`)

The engine's three parallel structures, replaced atomically under `self._inductive_lock`:

| State | Type | Replaced from |
|---|---|---|
| `self._jobs` | `list[JobData]` | new live JobData |
| `self._job_embeddings` | `torch.Tensor [N, H]` | inductive `z_dict["job"]` |
| `self._job_text_vecs` | `np.ndarray [N, 384]` | `embed([j.text for j in jobs])` |

`match_cv` iterates `self._jobs` by index and reads the two arrays by the same index — keeping them length-aligned is the only correctness invariant. Reranker reads JobData fields + `job_id` (no index), so it needs nothing further.

## Entity 4 — `EmployeeJobMatch` (existing, unchanged schema)

Behavioural change only: the engine `job_id` now equals `Job.id`, so `_persist_matches` resolves by primary key (drop the `source_url` fallback). Unique `(employee, job)` + `update_or_create` continue to guarantee idempotency and status preservation (FR-007, SC-006). No migration.

## Mapping flow (build → snapshot → serve)

```text
Job + JobSkill (DB)
   │  build_jobdata_from_db()        ← normalize skills, join title+description
   ▼
list[JobData]  (job_id = Job.id)
   │  engine.rebuild_job_pool(jobs)  ← 397-dim job nodes + requires_skill/requires_seniority
   │                                   onto frozen checkpoint graph copy → model.encode()
   ▼
self._jobs / self._job_embeddings / self._job_text_vecs   (in-process)
   │  job_pool_snapshot.save()       ← atomic write checkpoints/job_pool/
   ▼
snapshot on disk
   │  _get_engine() mtime check → engine reload     (live server, realtime)
   ▼
match_cv ranks CV against the live catalog → EmployeeJobMatch (job_id = Job.id)
```
