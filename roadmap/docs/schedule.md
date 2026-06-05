# Schedule Subsystem — Kiến trúc & Flow

> Tài liệu này mô tả cách hệ thống schedule quản lý hai management command chạy nền:
> `verify_job_status` và `extract_job_dates`.
>
> Mục đích: operator có thể bật/tắt, cấu hình giờ chạy, quan sát live log, và kill từ
> admin UI mà không cần SSH vào server. Mọi state đều nằm trong DB nên restart-safe.
>
> Spec liên quan: [specs/005-verify-schedule-dashboard/spec.md](../../specs/005-verify-schedule-dashboard/spec.md)
>
> Cập nhật: 2026-05-14

---

## Bài toán

Hai job dài đang chạy thủ công, mỗi cái 30–60 phút:
- `verify_job_status` — duyệt Job, cập nhật lifecycle (active/expired)
- `extract_job_dates` — backfill `Job.date_posted` + bundled verify

Operator cần:
1. Bật/tắt theo lịch (vài lần / ngày, theo giờ UTC)
2. Kích "Run now" tức thì
3. Xem live log đang chạy
4. Stop nửa chừng nếu thấy session hết hạn
5. Xem history các lần chạy trước (counts, wall-clock)

→ Không dùng Celery/Redis vì hai job này I/O-bound, chạy tuần tự, không cần queue.
Chọn **in-process daemon + subprocess.Popen** cho đơn giản và trong suốt.

---

## Component map

```
┌─────────────────────────────────────────────────────────────────────┐
│                          ADMIN UI (React)                            │
│  /admin/schedule/verify     /admin/schedule/extract                  │
│  ──────────────────────────────────────────────                      │
│  _schedule-page.tsx                                                  │
│    • Config card (enabled, batch_size, hours_utc, no-auth-check)     │
│    • Active-run card (pid, started_at, Start/Stop)                   │
│    • Live log <pre> (poll 2s, byte offset)                           │
│    • History table (last 20 VerifierRunLog rows)                     │
│            │                                                         │
│            ▼ scheduleService (axios)                                 │
└────────────┼─────────────────────────────────────────────────────────┘
             │
             │ REST  /api/admin/schedule/<cmd>/...
             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       DJANGO BACKEND                                 │
│                                                                      │
│  apps/schedule/views.py    ←──── stateless REST controllers          │
│         │                                                            │
│         ▼                                                            │
│  apps/schedule/services.py ←──── lifecycle primitives                │
│         │      • start_run(row)          spawn subprocess            │
│         │      • stop_run(row)           SIGTERM process group       │
│         │      • is_active_run(row)      kill(pid, 0) probe          │
│         │      • tail_live_log(...)      seek + read log file        │
│         │      • list_run_logs(...)      glob backend/logs/runs/     │
│         ▼                                                            │
│  apps/schedule/models.py   ←──── DB state                            │
│         • VerifierSchedule (singleton per command)                   │
│         • Active-run trio: current_run_pid / started_at / log_path   │
│         • last_fired_at (daemon idempotency)                         │
│                                                                      │
│  apps/jobs/models.py                                                 │
│         • VerifierRunLog ←──── history; written bởi command khi DONE │
└─────────────────────────────────────────────────────────────────────┘
             ▲
             │ DB read (every tick) + spawn
             │
┌─────────────────────────────────────────────────────────────────────┐
│              schedule_runner DAEMON  (forever loop)                  │
│                                                                      │
│  apps/schedule/management/commands/schedule_runner.py                │
│         while not stop:                                              │
│           for row in VerifierSchedule.filter(enabled=True):          │
│             if now.hour in row.hours_utc and not last_fired_at...:   │
│                 services.start_run(row)                              │
│           sleep(tick)                                                │
│                                                                      │
│  Run trong tmux/systemd:                                             │
│      python manage.py schedule_runner --tick 60                      │
└─────────────────────────────────────────────────────────────────────┘
             │
             │ subprocess.Popen(..., start_new_session=True)
             ▼
┌─────────────────────────────────────────────────────────────────────┐
│             CHILD PROCESS  (one of):                                 │
│   manage.py verify_job_status --platform linkedin --batch 100        │
│   manage.py extract_job_dates --platform linkedin --batch 100        │
│                                                                      │
│   stdout+stderr → backend/logs/runs/<cmd>_<TS>.log                   │
│   on exit       → VerifierRunLog.objects.create(...)                 │
│                   (PID dies, but log file persists)                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data model

### `VerifierSchedule` — `backend/apps/schedule/models.py`

Một row per command. Đóng vai trò cả **config** lẫn **active-run pointer**:

| Field | Mục đích |
|---|---|
| `command` | `"verify_job_status"` hoặc `"extract_job_dates"` (unique) |
| `enabled` | Daemon có quyền fire không |
| `batch_size` | `--batch N` truyền cho subprocess (1..1000) |
| `hours_utc` | List giờ UTC daemon sẽ fire, vd `[2, 14]` |
| `use_no_auth_check` | Truyền `--no-auth-check` cho subprocess (ad-hoc only) |
| `platform` | v1 chỉ `"linkedin"` |
| `current_run_pid` | PID của subprocess đang chạy, hoặc NULL |
| `current_run_started_at` | Khi nào spawn |
| `current_run_log_path` | Absolute path tới `backend/logs/runs/<cmd>_<TS>.log` |
| `last_fired_at` | Daemon bookkeeping — chống fire 2 lần trong cùng giờ |

### `VerifierRunLog` — `backend/apps/jobs/models.py`

History bảng append-only. Command tự write 1 row sau khi finish:

| Field | Ghi chú |
|---|---|
| `command`, `platform`, `started_at`, `finished_at` | Identity |
| `batch_size_requested`, `total_examined` | Scope |
| `counts_by_outcome` | JSON `{populated, expired_marked, none, error, session_expired}` |
| `dry_run` | Có ghi DB hay không |

---

## Lifecycle: spawn → observe → exit

### 1. Spawn — `services.start_run(row)`

```python
log_fp = open("backend/logs/runs/verify_job_status_20260514_021500.log", "wb")
proc = subprocess.Popen(
    [sys.executable, "manage.py", row.command,
     "--platform", row.platform, "--batch", str(row.batch_size)],
    cwd=settings.BASE_DIR,
    stdout=log_fp,
    stderr=subprocess.STDOUT,
    start_new_session=True,   # detach từ daemon — SIGTERM của daemon
                              # không kill child
)
row.current_run_pid = proc.pid
row.current_run_log_path = str(log_path)
row.save()
```

**Lý do `start_new_session=True`:** Tạo process group mới. Khi daemon (parent)
nhận SIGTERM, default behaviour kernel sẽ tìm cách kill cả child — nhưng ở đây
operator có thể muốn child tiếp tục. New session ⇒ child tự lập đầu group, độc lập.

Cũng cho phép `services.stop_run` dùng `os.killpg(getpgid(pid), SIGTERM)` để
kill toàn bộ Playwright + Chromium subprocess tree, không chỉ Python parent.

### 2. Observe

**Liveness probe** — `services.is_active_run(row)`:
```python
os.kill(pid, 0)   # signal 0 = "does this PID exist?", không gửi signal thật
```
Không touch DB nếu PID còn sống. Nếu `ProcessLookupError` ⇒ subprocess đã exit,
clear `current_run_pid`.

**Live log tail** — `services.tail_live_log(row, since_bytes)`:
- Frontend gọi 2s/lần, gửi `since=<bytes>` (offset đã đọc)
- Backend mở log file, `seek(since_bytes)`, đọc tới EOF, trả `(text, new_offset)`
- Frontend append `text` vào `<pre>`, nhớ `new_offset` cho lần tới
- Không stream, không SSE, không WebSocket — đơn giản và stateless

### 3. Exit

Subprocess tự ghi `VerifierRunLog` row vào DB ở cuối `handle()`. Khi PID chết:
- Lần `refresh_active_run_state` kế tiếp ⇒ clear `current_run_pid` về NULL
- Log file vẫn nằm ở `backend/logs/runs/` (gitignored), pickup bằng `list_run_logs`
- History table có row mới với counts đầy đủ

---

## Daemon scan loop

`schedule_runner` (forever loop):

```
mỗi --tick giây (default 60s):
  for row in VerifierSchedule.objects.filter(enabled=True):
    refresh_active_run_state(row)
    if is_active_run(row):     skip  # đang chạy rồi
    if now.hour not in row.hours_utc: skip
    if last_fired_at.date == now.date and last_fired_at.hour == now.hour:
        skip                          # đã fire trong giờ này rồi
    start_run(row)
    row.last_fired_at = now
    row.save()
```

**Idempotency invariant:** Mỗi `(date, hour)` chỉ fire 1 lần — `last_fired_at`
ngăn tick thứ 2 trong cùng giờ tái-spawn. Restart daemon giữa giờ cũng an toàn.

**Trade-off:** Nếu daemon down lúc 02:00 và up lại lúc 03:30, **bỏ lỡ slot
02:00** — không catch-up. Operator phải bấm "Run now" thủ công. Quyết định
chấp nhận vì verify/extract idempotent ở DB level (date đã có sẽ không overwrite).

---

## REST API

Base: `/api/admin/schedule/<command>/`

| Method | Path | Mục đích |
|---|---|---|
| GET | `/<cmd>/` | Lấy config + active-run snapshot |
| PUT | `/<cmd>/` | Update config (enabled, batch_size, hours_utc, …) |
| POST | `/<cmd>/start/` | "Run now" — spawn ngay, bỏ qua hours_utc |
| POST | `/<cmd>/stop/` | SIGTERM process group |
| GET | `/<cmd>/live-log/?since=N` | Đọc log file từ offset N |
| GET | `/<cmd>/history/?limit=20` | List VerifierRunLog + log files trên disk |
| GET | `/<cmd>/log-file/?name=…` | Đọc 1 file log cũ (path-traversal-safe) |

`<command>` luôn validate ⊆ `{verify_job_status, extract_job_dates}` —
không cho path-traversal qua URL.

---

## Frontend integration

`admin/src/pages/admin/schedule/_schedule-page.tsx` — shared component cho cả
2 trang `verify.tsx` và `extract.tsx`, chỉ khác `command` prop.

Layout (NODE design system):
```
┌──────────────────────────────────────────────────────────┐
│  Config card                                              │
│  ✔ Enabled    [100]/batch    hours_utc [2, 14]            │
│  ☐ --no-auth-check    Save                                │
├──────────────────────────────────────────────────────────┤
│  Active run                                               │
│  pid=12345 · started 2 min ago · backend/logs/runs/…      │
│  [Run now]   [Stop]                                       │
├──────────────────────────────────────────────────────────┤
│  Live log    (poll 2s, append-only)                       │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ [12:00:01] starting verify_job_status …            │ │
│  │ [12:00:03]   url=https://… → active                │ │
│  │ …                                                   │ │
│  └─────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────┤
│  History (last 20)                                        │
│  started_at | examined | populated | error | wall_clock   │
└──────────────────────────────────────────────────────────┘
```

Service: `admin/src/services/schedule.service.ts` — typed axios wrapper cho
6 endpoint trên.

---

## Operational concerns

### Auth state
- `use_no_auth_check=True` chỉ dùng ad-hoc test trên máy operator
- Production cron **phải** giữ `false` để extractor enforce `li_at` cookie
- Khi `false`, subprocess refuse start nếu `linkedin_state.json` thiếu/expired
  (exit code 2)

### File layout
- Log files: `backend/logs/runs/<cmd>_<YYYYMMDD_HHMMSS>.log` — gitignored
- Auth state: `backend/auth/linkedin_state.json` — gitignored
- Chromium profile: `backend/auth/chromium_profile/` — gitignored

### Restart safety
- Daemon down/up không mất state — tất cả nằm trong `VerifierSchedule` row
- Nếu kill -9 daemon trong lúc child đang chạy:
  - Child tiếp tục (`start_new_session=True`)
  - `current_run_pid` vẫn point đúng → UI Stop button vẫn hoạt động
  - Khi child exit, log file đã ghi xong, lần check kế tiếp clear PID

### Cách deploy
```bash
# tmux session
tmux new -s scheduler
cd backend
.venv/bin/python manage.py schedule_runner --tick 60
# Ctrl-B D detach
```

hoặc systemd unit (`scheduler.service`) với `Restart=always`.

---

## Trade-offs đã chọn

| Quyết định | Vì sao |
|---|---|
| In-process daemon (vs Celery beat) | Không có Redis, ít dependency, chạy 2 job/ngày không cần queue |
| `subprocess.Popen` + log file (vs threading) | Crash isolation — Playwright hang không kéo Django backend |
| Poll 2s (vs SSE/WebSocket) | Đủ nhanh cho operator, không cần ASGI infra |
| Singleton-per-command (vs multi-schedule) | v1 đơn giản — operator chỉ cần 1 lịch / command |
| Không catch-up missed hours | Acceptable: command idempotent, operator có "Run now" |
| `start_new_session=True` | Cho phép stop_run kill cả Chromium subprocess tree |

---

## Tương lai (chưa implement)

- Multi-schedule per command (vd vừa `[2, 14]` cho LinkedIn vừa `[6]` cho RemoteOK)
- Catch-up missed hours sau khi daemon restart
- SSE streaming thay polling
- Slack/email alert khi `session_expired_count` tăng
- Per-platform schedule (hiện hardcode `platform=linkedin` ở v1)
