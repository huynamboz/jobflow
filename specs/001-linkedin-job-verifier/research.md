# Phase 0 — Research & Decisions: LinkedIn Job Verifier

**Date**: 2026-05-13

This document records design decisions made before writing data-model and contracts. Each decision answers a question that, left unresolved, would block implementation.

---

## Decision 1 — Lifecycle lives on `Job`, not `JDExtractionRecord`

**Decision**: Add the lifecycle, `last_seen_at`, `last_verified_at`, `verification_attempts`, and `verification_backoff_until` fields to `apps/jobs/models.py:Job`.

**Rationale**:
- `Job` is the canonical record returned to the matching API and already carries `is_active`, `source_url`, `date_posted`, and a `(platform, fingerprint)` unique constraint.
- `JDExtractionRecord` is per-LLM-attempt; its existing `status` field already means "extraction pending/processing/done/error". Overloading it would be confusing and would tie job lifecycle to extraction batches.

**Alternatives considered**:
- *New `JobLifecycle` 1:1 table*: cleaner separation but adds an extra JOIN on every matching request and a join cost the runtime filter shouldn't pay. Rejected.
- *Adding to `JDExtractionRecord`*: see rationale above.

---

## Decision 2 — Runtime filter in matching service, not pre-baked into the GNN checkpoint

**Decision**: The matching service queries `Job` for `lifecycle__in=['active','stale','unverified']` after the engine returns top-K candidates and drops the rest. Ranking order of remaining jobs is preserved.

**Rationale**:
- The engine reads jobs from a baked checkpoint (`gnn_v2/jobs.json`). Re-baking on every lifecycle change is expensive and unnecessary for production filtering.
- One indexed `WHERE id IN (...) AND lifecycle IN (...)` adds <5ms to a request that already takes seconds (engine cold-start ~2 min, warm ~1-2s).
- When the GNN is retrained, the checkpoint will naturally be built from active jobs only — a free win without coupling.

**Alternatives considered**:
- *Pre-bake lifecycle into checkpoint*: clean separation of concerns but blocks lifecycle changes from taking effect until next retrain (days/weeks). Rejected.
- *Add lifecycle to the engine's job table in memory*: requires engine changes and breaks the "filter is matching's concern, not engine's" invariant. Rejected.

---

## Decision 3 — DI via constructor injection + a registry factory (no DI framework)

**Decision**: `StatusCheckService` accepts `verifier_registry`, `repository`, and `clock` via constructor. Verifier auto-discovery uses the same pattern as `ml_service/crawler/factory.py` — scan `providers/` package, register subclasses.

**Rationale**:
- The project has no existing DI container (`django-injector`, `dependency-injector`, etc.). Introducing one is gratuitous for one service.
- Constructor injection makes the test seam obvious: pass `FakeVerifier()` + `FakeRepository()`.
- The crawler module already uses auto-discovery; mirroring it keeps the codebase consistent and lets engineers transfer mental model.

**Alternatives considered**:
- *Service locator (global singleton)*: hides dependencies, hostile to tests. Rejected.
- *Pass verifier instance directly*: works for v1 but breaks once Indeed/RemoteOK are added because the management command needs to know all available verifiers. Registry indirection is paid for by extensibility. Accepted.
- *`dependency-injector` library*: pulls in extra runtime, configuration overhead, and a learning curve for one service. Rejected as premature.

---

## Decision 4 — One Chromium context per batch, not per URL

**Decision**: `LinkedInVerifier.verify_batch(urls)` opens one Playwright context, iterates URLs inside it, refreshes the storage state on context exit. `LinkedInVerifier.verify(url)` is implemented in terms of `verify_batch([url])`.

**Rationale**:
- Chromium launch is ~3-4s on macOS; a per-URL launch dominates batch time. Pooling cuts a 100-URL batch from ~15+5*100=515s + ~5s overhead each from launch (worst case) to ~5*100 + 5 = 505s + 5s launch (best case): saves roughly 5 minutes per 100 URLs.
- The existing crawler already does this inside `linkedin_provider.py:fetch()`. Reusing the same pattern in a shared `browser_pool.py` is straightforward.
- Storage state must be refreshed on exit to keep cookies fresh — this is how the existing provider does it.

**Alternatives considered**:
- *One context per URL*: simpler but quadruples wall-clock. Rejected.
- *Long-lived browser daemon (out of band)*: too much infrastructure for v1. Could be a v2 optimization.

---

## Decision 5 — Detection priority: session → expired → active → unknown

**Decision**: For each LinkedIn job URL, the verifier checks in this fixed order and returns at the first match:
1. Final URL matches `auth_check.expired_url_patterns` from `linkedin_selectors.json` → `SESSION_EXPIRED`.
2. Any selector in `expired_markers` matches → `EXPIRED`.
3. Any selector in `active_markers` matches → `ACTIVE`.
4. Otherwise → `UNKNOWN`.

**Rationale**:
- Session checks must come first; a logged-out browser will land on a login redirect that may render generic content, leading to false `UNKNOWN`/`ACTIVE` classifications. Detecting session first prevents this whole class of false outcomes.
- Expired markers come before active markers because a closed-job page often still includes a stub of the original job description and could accidentally match an active-marker pattern (e.g., "Save job" button stays visible on LinkedIn closed listings). Bias toward `EXPIRED` when both could plausibly match.
- `UNKNOWN` is a deliberate non-outcome; lifecycle is not changed, only retry state is.

**Alternatives considered**:
- *Active first*: causes false `ACTIVE` on closed pages that still render the save/share buttons. Rejected.
- *Confidence-weighted multi-marker scoring*: over-engineered for v1. The selector lists give us simple deterministic precedence; we can revisit if false-positive rate is high.

---

## Decision 6 — Exponential backoff with hard cap

**Decision**: On `ERROR` or `UNKNOWN`, `verification_backoff_until = now + min(2^attempts * 1h, 7d)`, where `attempts` is incremented before computing. `ACTIVE` / `EXPIRED` reset `attempts` to 0 and clear `verification_backoff_until`.

**Rationale**:
- Doubling backoff is the standard pattern for transient failures and avoids hammering a downed source.
- Cap of 7 days prevents a permanently broken job from blocking the queue indefinitely while keeping the queue manageable.
- Reset on success ensures recovered jobs do not carry stale backoff into future runs.

**Alternatives considered**:
- *Fixed retry interval*: doesn't differentiate transient vs persistent failure. Rejected.
- *Drop the job after N failures*: loses jobs that were genuinely temporary outages. Rejected.

---

## Decision 7 — Identity by `(platform, fingerprint)`, no new column

**Decision**: Use the existing `Job.fingerprint` (already indexed and unique per platform) as the row identity for re-verification. LinkedIn URLs are normalized via a helper `linkedin_clean_url(url)` to a canonical `linkedin.com/jobs/view/<id>/` form for verifier input; this helper is a pure function and doesn't change the DB.

**Rationale**:
- `unique_together = ('platform', 'fingerprint')` already enforces job identity at the DB level.
- Adding a `linkedin_job_id` column duplicates information already encoded in `fingerprint` and `source_url`.

**Alternatives considered**:
- *Add `external_id` column*: would simplify some queries but doesn't enable any new capability. Rejected as premature.

---

## Decision 8 — Operator entry point: Django management command + cron, not Celery

**Decision**: A single Django management command `python manage.py verify_job_status --platform linkedin --batch 100 [--dry-run]`. Cron entries are documented in `quickstart.md` but not auto-installed.

**Rationale**:
- The project has no Celery, Redis, or RQ. Adding async infrastructure for one job is disproportionate.
- A synchronous command on cron is enough for v1 (≤500 jobs/day at ~5s each ≈ 40 min/day total).
- `StatusCheckService` is stateless, so wrapping it in a Celery task later is mechanical.

**Alternatives considered**:
- *Celery task + Redis broker*: significant infra change for marginal v1 benefit. Rejected.
- *Background thread inside Django*: fragile, no observability, hard to bound runtime. Rejected.

---

## Decision 9 — Stale transition is age-based and recomputed at batch time

**Decision**: Within the verifier batch entry point, before picking the candidate set, run a quick UPDATE:
```sql
UPDATE jobs SET lifecycle='stale'
WHERE lifecycle='active'
  AND date_posted < (NOW() - INTERVAL '14 days');
```
This is the only path that produces `stale`. The candidate selection then picks `lifecycle='stale'` (preferred) before `lifecycle='active'`.

**Rationale**:
- One bulk update is cheaper than a per-row check at request time, and centralizes the rule.
- Putting it inside the batch entry point guarantees that every verification run sees an up-to-date stale set without a separate cron job.

**Alternatives considered**:
- *Separate "age tick" cron*: works but adds another cron entry. Rejected for simplicity.
- *Computing `stale` as a view rather than a stored value*: makes index usage harder for the candidate selection query. Rejected.

---

## Decision 10 — Test strategy: unit for service + dispatch; smoke for LinkedIn

**Decision**:
- **Unit (`pytest`, no Django DB, no Playwright)**: cover state transitions, backoff math, factory dispatch by URL, session-expired alerting, batch result accumulation, empty-batch behaviour. Use `FakeVerifier` and `FakeRepository`.
- **Integration smoke (manual)**: run `verify_job_status --batch 5 --dry-run` against the real LinkedIn provider with 5 hand-picked URLs (3 active, 2 expired) and assert the printed report. Document the URLs in `quickstart.md`.

**Rationale**:
- 100% of branch logic is reachable with fakes.
- An automated Playwright integration test in CI requires LinkedIn credentials and a stable URL set — fragile. A documented manual smoke is more reliable for v1.

**Alternatives considered**:
- *Mock Playwright responses with recorded HTML*: improves repeatability but bloats the test bundle. Defer to v2 if false-positive rate becomes a concern.

---

## Open items

None. All NEEDS CLARIFICATION items from the spec (zero) are resolved; no further blockers before Phase 1.
