# `ml_service/verifier` — Job liveness verification & date extraction

Checks whether a crawled job posting is still **live or expired**, and extracts its
**posted date** — so the matcher never recommends a dead job.

**Coverage by platform:**

| Platform | Verifier | How | Account risk |
|---|---|---|---|
| **LinkedIn** | `linkedin_verifier` | Playwright, **guest/anonymous** by default | none (no login) |
| **Freelancer** | `freelancer_verifier` | public Projects **API** — reads `status` (frozen/closed/complete → expired) | none |
| **Remotive** | `remotive_verifier` | **HTTP** GET — removed jobs 410 / redirect off the URL | none |
| Indeed | — | not verified (aggressive bot detection) — heuristic age-out | — |
| RemoteOK | — | not verified (page is a catch-all 200; API feed only returns the recent ~100) — heuristic age-out | — |

The API/HTTP verifiers (Freelancer, Remotive) are **pure HTTP, no browser, no auth** —
they plug into the same `verify_job_status` command and lifecycle pipeline.

> **Guest mode by default (no login).** Verification runs **anonymously** — it does
> NOT use the operator's `li_at` session. High-volume status checks from a logged-in
> account get it flagged/locked; LinkedIn still serves the public guest job layout
> and still redirects deleted/closed jobs to a search page with
> `trk=expired_jd_redirect`, the strongest expiry signal. So guest checks reliably
> catch EXPIRED jobs with **zero account risk**. Opt back into auth with `--use-auth`.

---

## What it does

1. **Status check** — navigate to the job URL, classify it `ACTIVE` / `EXPIRED` /
   `UNKNOWN` (and `SESSION_EXPIRED` / `ERROR` for ops), then update `Job.lifecycle`.
2. **Date backfill** — extract `date_posted` (JSON-LD → `<time datetime>` →
   relative text), optionally verifying lifecycle in the same page visit.

A job marked `expired` is also set `is_active=False` (see *Pool integration*), so it
drops out of the GNN match pool on the next `rebuild_job_pool`.

---

## Files

| File | Role |
|---|---|
| `base.py` | `JobStatus` enum (`ACTIVE/EXPIRED/SESSION_EXPIRED/UNKNOWN/ERROR`), `VerifyResult` dataclass, `JobStatusVerifier` ABC (`supports(url)`, `verify(url)`, `verify_batch(urls)`). |
| `factory.py` | Auto-discovery registry — `get_verifier(name)`, `get_verifier_for_url(url)`, `list_verifiers()`. |
| `service.py` | `StatusCheckService` orchestrator + `LifecycleRepository` protocol (DB writes are injected, not done here). Produces a `StatusCheckReport`. |
| `backfill_service.py` | `DateBackfillService` — date extraction + optional bundled lifecycle verify, in one page visit per job. |
| `browser_pool.py` | `open_browser_page(...)` — patchright stealth Chromium via `launch_persistent_context`. **Guest** uses a fresh empty profile; auth uses a disposable copy of the operator profile. |
| `date_extractor.py` | `extract_date_posted(page)` — multi-source date parsing with ±730-day guardrails. |
| `auth_guard.py` | `li_at` cookie invariant — `read_state` / `persist_state` refuse to read/write a session without `li_at`. (Only relevant on the `--use-auth` path.) |
| `providers/linkedin_verifier.py` | `LinkedInVerifier` + `inspect_linkedin_lifecycle(page, selectors)`. **Guest by default** (`require_li_at=False`). |
| `providers/freelancer_verifier.py` | `FreelancerVerifier` — Projects API lookup by seo-url → `status` field. Pure HTTP. |
| `providers/remotive_verifier.py` | `RemotiveVerifier` — thin subclass of `HttpPresenceVerifier`. |
| `http_presence.py` | `HttpPresenceVerifier` base — GET the job URL; 404/410/redirect-off-URL → EXPIRED, 200 → ACTIVE. Reused by HTTP-checkable boards (lives outside `providers/` so the factory only registers concrete subclasses). |
| `selectors/linkedin.json` | DOM/URL selectors for LinkedIn detection. Anchored on `aria-label` / `h2` text / `componentkey` (LinkedIn ships hashed CSS class names). Update when LinkedIn changes its layout. |

---

## Detection priority (`inspect_linkedin_lifecycle`)

1. final URL matches `auth_check.expired_url_patterns` (`login`/`authwall`/`checkpoint`)
   → **SESSION_EXPIRED**. In guest mode this just means LinkedIn gated the page — the
   lifecycle repo treats it as a **no-op**, so a job is never mislabeled.
2. final URL matches `expired_url_patterns` (`trk=expired_jd_redirect`) → **EXPIRED**.
3. any `expired_markers` selector visible (e.g. *"No longer accepting applications"*,
   *"Page not found"*) → **EXPIRED**.
4. any `active_markers` selector visible (guest layout covered:
   `.top-card-layout__title`, `section.description`, *About the job*, Apply button…)
   → **ACTIVE**.
5. otherwise → **UNKNOWN**.

`UNKNOWN` / `SESSION_EXPIRED` / `ERROR` never change a job's lifecycle (no-op) —
only confirmed `ACTIVE` / `EXPIRED` write.

---

## Running

```bash
# Status check (guest, default). --dry-run = no DB writes.
python manage.py verify_job_status --platform linkedin --batch 50 --dry-run
python manage.py verify_job_status --platform linkedin --batch 50          # writes lifecycle

# API/HTTP verifiers (no browser, no auth):
python manage.py verify_job_status --platform freelancer --batch 50
python manage.py verify_job_status --platform remotive   --batch 50

# Date backfill (+ bundled verify by default; --no-verify for extract-only)
python manage.py extract_job_dates --platform linkedin --batch 50 --dry-run

# Opt into the authenticated path (NOT recommended — can lock the account):
python manage.py verify_job_status --platform linkedin --batch 50 --use-auth
#   requires a saved session: python -m ml_service.crawler.providers.linkedin_auth
```

Flags: `--use-auth` (opt into li_at), `--no-auth-check` (deprecated no-op, guest is
default now), `--headed` (visible browser), `--batch N`, `--dry-run`,
`--min-age-hours N` (skip jobs verified within N hours; default **12**, `0` = off —
never-verified jobs are always eligible).

**Scheduling:** `apps/schedule` (`VerifierSchedule` + `schedule_runner`) runs these
on a cadence. With guest as the default, scheduled runs no longer touch the account.

---

## Lifecycle states (`Job.lifecycle`)

`active` · `stale` (not seen recently) · `expired` (verified dead) · `unverified`.
The verifier writes `active` / `expired`. `apply_aging` promotes long-unseen jobs to
`stale`.

## Pool integration (don't reintroduce the leak)

The GNN match pool is built from the live catalog and **must not include expired
jobs**. Two guards keep it clean:

1. `job_lifecycle_repository.apply_result` sets **`is_active=False`** whenever it marks
   a job `expired` (keeps the legacy flag in sync).
2. The pool builders (`apps/jobs/services/job_service.get_all_job_data` and
   `apps/matching/services/matching_service.build_jobdata_from_db`) filter
   `is_active=True` **and** `.exclude(lifecycle='expired')` — belt-and-suspenders.

After a verification run, `rebuild_job_pool` evicts the newly-expired jobs from the
pgvector pool + snapshot.

---

## Extending to a new platform

1. Add `providers/<platform>_verifier.py` implementing `JobStatusVerifier`
   (`name`, `supports(url)`, `verify_batch(urls)`); it's auto-discovered by the factory.
2. Add a `selectors/<platform>.json` if it needs DOM markers.
3. Reuse `browser_pool.open_browser_page` for stealth Chromium, or use plain HTTP if
   the platform exposes status without a browser.

Operator secrets (`backend/auth/linkedin_state.json`, `chromium_profile/`) are
git-ignored and only touched on the `--use-auth` path.
