# Quickstart: Scalable Job-Pool Retrieval

**Feature**: 027-job-retrieval-scaling · **Date**: 2026-06-13

How to enable, validate, and roll back each stage. The golden rule: **no stage flips its default `RETRIEVAL_MODE` until `eval_matching` passes the quality gate** (on-domain@k ≥ baseline, calibrated-P within tol, recall@shortlist ≈ 1.0).

## 0. Capture the baseline (before any change)

```bash
cd backend
.venv/bin/python manage.py eval_matching            # record on-domain@k
# note the 20-CV calibrated probabilities as the parity reference
```

## Stage A — vectorized recall

```bash
# default after the refactor lands; switch explicitly to A/B:
export RETRIEVAL_MODE=exact     # today's path, parity oracle
export RETRIEVAL_MODE=vector    # Stage A
export RETRIEVE_K=1000          # shortlist size (raise if recall < target)

.venv/bin/python manage.py eval_matching --report-recall   # on-domain@k + recall@shortlist + ΔP
```
- **Pass**: on-domain@k ≥ baseline, |ΔP| ≤ 0.005, recall@shortlist ≈ 1.0 → set `RETRIEVAL_MODE=vector` as default.
- **Fail (low recall / dropped candidate)**: raise `RETRIEVE_K` (1000→2000…) or rebalance `W_GNN`/`W_TEXT`; re-run.
- **Rollback**: `RETRIEVAL_MODE=exact` — instant, no data change.
- **Latency bench**: inflate the pool synthetically (duplicate jobs to ~100k) and time a match in `vector` vs `exact`.

## Stage B — pgvector ANN

```bash
# one-time: enable the extension + create the table/index (migration)
.venv/bin/python manage.py migrate apps.matching

# populate the vector table from the live pool
.venv/bin/python manage.py rebuild_job_pool          # now also upserts job_pool_vec

export RETRIEVAL_MODE=pgvector
export HNSW_EF_SEARCH=64        # raise until recall parity
.venv/bin/python manage.py eval_matching --report-recall
```
- **Pass**: parity with `vector`/`exact` on the gate metrics → default `pgvector`.
- **Tune**: raise `HNSW_EF_SEARCH` for recall (costs latency); record chosen `m`/`ef_search`.
- **Fallback/rollback**: missing extension / fingerprint mismatch / `RETRIEVAL_MODE=vector` → engine serves from memory; no outage.
- **Bench**: inflate to 200k+; confirm sublinear retrieval latency vs `vector`.

## Stage C — incremental refresh

```bash
# normal (incremental): encodes only new/changed jobs
.venv/bin/python manage.py rebuild_job_pool

# force from-scratch (safety net / correctness check)
.venv/bin/python manage.py rebuild_job_pool --full
```
- **Validate**: on an unchanged catalog, `rebuild_job_pool` (incremental) must produce the same pool as `--full` (embedding + order diff = 0).
- **Validate delta**: after crawling N new jobs, the incremental run logs "encoded N" (not the whole catalog).
- **Safety net**: a weekly `--full` runs inside `morning_refresh`.
- **Rollback**: `--full` always reproduces a correct pool; if incremental ever drifts, run `--full`.

## End-to-end gate (per stage, before merge)

1. `eval_matching` on-domain@k ≥ baseline.
2. Calibrated P within ±0.005 on the 20-CV set.
3. recall@shortlist ≈ 1.0 (Stage A/B).
4. Latency bench shows the expected scaling (flat / sublinear).
5. Rollback verified (`RETRIEVAL_MODE=exact` reproduces baseline; `--full` reproduces full pool).

## Key settings (config/settings.py)

| Setting | Default | Stage |
|---|---|---|
| `RETRIEVAL_MODE` | `exact`→`vector`→`pgvector` | all |
| `RETRIEVE_K` | `1000` | A |
| `W_GNN` / `W_TEXT` | GNN-dominant | A |
| `HNSW_M` / `HNSW_EF_SEARCH` | `16` / tuned | B |
