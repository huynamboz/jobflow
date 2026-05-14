# Feature Specification: Verify Schedule Dashboard

**Branch**: `005-verify-schedule-dashboard` · **Created**: 2026-05-14

## Goal

Give the operator a UI to (1) configure when `verify_job_status` /
`extract_job_dates` run automatically each day, (2) start/stop runs on
demand, (3) follow live logs, and (4) review history — without touching
cron or terminal.

## User stories

**US1 (P1) — Configure the daily schedule.** Operator opens
`/admin/schedule/verify`, sets batch size, batches-per-day (or explicit
UTC hours), toggles enabled, saves. The in-process `schedule_runner`
daemon picks the new config up within ≤60s on its next tick.

**US2 (P1) — Run now / kill.** Operator clicks "Run now"; backend spawns
the management command in a subprocess, surfaces PID + start time.
Clicking "Stop" sends SIGTERM, the PID exits, history row reflects the
truncated run.

**US3 (P1) — Live log.** Subprocess stdout is captured to
`backend/logs/runs/<run_id>.log`. Frontend polls the live-log endpoint
every 2s while a run is active and appends new bytes to a scrollable
panel.

**US4 (P2) — History.** A table shows the last N `VerifierRunLog` rows
for the selected command with start time, wall clock, outcome counts.

## Functional requirements

- `VerifierSchedule` model is keyed by `command` (unique). Fields:
  `enabled`, `batch_size`, `batches_per_day`, `hours_utc[]`,
  `use_no_auth_check`, plus the active-run trio
  (`current_run_pid`, `current_run_started_at`, `current_run_log_path`).
- `schedule_runner` management command loops every 60s, scans rows with
  `enabled=true`, and triggers a subprocess at the first matching hour
  it hasn't yet run today. Tracks PID/log path on the row.
- Manual "Run now" performs the same subprocess spawn, ignoring the
  hour gate.
- "Stop" sends SIGTERM to the recorded PID; the row clears its active
  fields on observed exit (or on the next runner tick).
- Live log endpoint takes `?since=<bytes>` and returns the slice from
  that offset to EOF.
- All endpoints require `IsAuthenticated`.

## Out of scope (v1)

- Per-batch retry policy / catch-up after missed hour.
- Multi-platform schedule (v1 fixes to the LinkedIn invocation; the
  command itself is platform-aware, the schedule row stores a default).
- SSE / WebSocket — polling only.
- Authorization beyond logged-in admin.

## Success criteria

- Config save → daemon picks up within ≤60s of next tick.
- Live log latency ≤2s.
- Stopping a running batch terminates the PID within ≤5s on macOS / Linux.
- Existing tests stay green; new model migration is additive.
