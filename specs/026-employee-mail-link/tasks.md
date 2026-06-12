# Tasks: Employee Mail Link

**Input**: spec.md, plan.md, research.md, data-model.md, contracts/api.md, quickstart.md
**Tests**: requested (SC-001..008 are gates) → test tasks included.
Backend paths under `backend/`, FE under `admin/`.

## Phase 1: Setup

- [x] T001 Create app `backend/apps/mail/` (apps.py, __init__, migrations/, management/commands/, services/, tests.py); add `apps.mail` to INSTALLED_APPS in `backend/config/settings.py`
- [x] T002 `backend/apps/mail/crypto.py`: Fernet encrypt/decrypt using `MAIL_CRED_KEY` env; fail-loud (RuntimeError) if key missing/invalid on first use

## Phase 2: Foundational (blocking — models + permission shared by all stories)

- [x] T003 Models in `backend/apps/mail/models.py`: `EmployeeMailCredential` (OneToOne, encrypted password column, status, last_error), `EmailLog` (out/in, message_id indexed, in_reply_to indexed, is_bounce, status), `Notification` (type, title, body_preview, link_url, employee FK, read_at) — per data-model.md
- [x] T004 Migration `python manage.py makemigrations mail`
- [x] T005 HR-only permission + base viewset wiring in `backend/apps/mail/views.py` + `backend/apps/mail/urls.py` mounted at `/api/admin/mail/` in `backend/config/urls.py` (mirror employees admin mount + role guard)

## Phase 3: User Story 1 — Link an email account (P1) 🎯 MVP-foundation

**Goal**: link/verify/unlink credential; password never exposed.
**Independent test**: valid creds → active; wrong password → rejected, nothing stored; unlink → row gone.

- [x] T006 [US1] `backend/apps/mail/services/probe.py`: `probe(address, app_password)` runs real SMTP login (smtp.gmail.com:587 STARTTLS) AND IMAP login (imap.gmail.com:993) — returns ok / raises with provider message
- [x] T007 [US1] Credential API in `backend/apps/mail/views.py` + serializer (EXCLUDES password): POST link (probe→encrypt→save active; probe fail→400 PROBE_FAILED, store nothing), GET status (?employee=), DELETE unlink (hard delete) — per contracts/api.md
- [x] T008 [P] [US1] Tests `CredentialTests` in `backend/apps/mail/tests.py`: Fernet roundtrip + key-missing fail-loud; serializer/`repr` never contain password; link with bad probe (mock) → 400 + 0 rows; unlink deletes row; permissions HR-only
- [x] T009 [US1] FE `admin/src/services/mail.service.ts` (link/status/unlink) + "Email account" card in `admin/src/pages/admin/employees/detail.tsx`: status badge, link form (address + app password + how-to-create-app-password hint + consent text), unlink button; `tsc --noEmit` clean

## Phase 4: User Story 2 — Send from the system (P1)

**Goal**: one-click Send from employee address with CV attached + mark applied.
**Independent test**: mail received from employee addr w/ CV; match=applied; EmailLog(out) exists; failure leaves match un-applied.

- [x] T010 [US2] `backend/apps/mail/services/send.py`: smtplib STARTTLS as employee, EmailMessage From=employee, attach `Employee.cv_file`, set self Message-ID `<uuid4@jobflow.local>`; write EmailLog(out, sent) on success / (failed,error) on exception
- [x] T011 [US2] `POST /api/admin/mail/send-apply/` {match,to,subject,body}: require linked active credential, send, on success mark match applied via existing flow (preserve duplicate-apply frontman 409); on send failure 400 SEND_FAILED + match NOT applied + flag credential status=error
- [x] T012 [P] [US2] Tests `SendTests` in `backend/apps/mail/tests.py`: mocked SMTP — success path (EmailLog out + match applied + cv_attached flag), failure path (match untouched + credential error), no-credential → blocked
- [x] T013 [US2] FE `admin/src/pages/admin/apply-email.tsx`: primary "Send" button (enabled iff linked) → send-apply API → run existing applied flow incl. frontman; keep "Open in Gmail" as fallback; show From=linked address + "CV will be attached" indicator

## Phase 5: User Story 3 — Reply tracking (P2)

**Goal**: detect replies to sent mail, store full, notify; never touch other mail.
**Independent test**: reply-threaded mail → EmailLog(in)+Notification within a poll; unrelated mail → nothing.

- [x] T014 [US3] `backend/apps/mail/services/imap_poll.py`: per active credential, IMAP readonly SELECT, SEARCH SINCE last_polled, FETCH BODY.PEEK[HEADER] → match In-Reply-To/References vs known EmailLog.message_id → only then PEEK full body → EmailLog(in) + Notification(mail_reply); bounce (mailer-daemon/postmaster + known ref) → is_bounce + Notification(mail_bounce); advance last_polled; non-match never stored
- [x] T015 [US3] `backend/apps/mail/management/commands/poll_mail_replies.py` (loops active credentials, calls poller, catches per-credential errors → status=error) + register `poll_mail_replies` in `backend/apps/schedule/models.py` COMMAND_CHOICES + migration
- [x] T016 [P] [US3] Tests `PollerTests` in `backend/apps/mail/tests.py`: synthetic IMAP messages — match (creates in+notif), no-match (creates nothing, body never fetched), bounce (is_bounce+notif); BODY.PEEK used (no \Seen)
- [x] T017 [US3] `GET /api/admin/mail/thread/?match=` API + mail-thread view in match detail (`admin/src/pages/admin/employees/detail.tsx`): sent + replies, full body, bounce flag

## Phase 6: User Story 4 — Bell + dashboard (P2)

**Goal**: notification delivery surface.

- [x] T018 [US4] Notification API in `backend/apps/mail/views.py`: list (newest+unread first, paginated), unread-count, mark-read, recent-replies (dashboard) — per contracts/api.md
- [x] T019 [P] [US4] Tests `NotificationApiTests` in `backend/apps/mail/tests.py`: list ordering, unread-count, mark-read decrements, recent-replies shape, HR-only
- [x] T020 [US4] FE bell: `admin/src/services/notification.service.ts` + wire `Bell` in `admin/src/components/admin/admin-header.tsx` — unread badge + popover (newest list, click→navigate link_url + mark read); poll unread-count every ~60s
- [x] T021 [P] [US4] FE dashboard "Mail replies" block in `admin/src/pages/admin/dashboard.tsx` (employee, job, snippet, time, link); `tsc --noEmit` clean

## Phase 7: Verification & Polish

- [x] T022 E2E script `specs/026-employee-mail-link/e2e_mail.py` (real test inbox): link→send-apply→simulate threaded reply→poll→assert EmailLog(in)+Notification+unread-count API+recent-replies; negatives (bad password rejected, non-threaded mail untouched, unlink removes row) — per quickstart.md
- [x] T023 Run `python manage.py test apps.mail` (unit, no network) green + run e2e_mail.py against the real inbox
- [x] T024 Docs: `CLAUDE.md` gotcha (MAIL_CRED_KEY required; app-password per employee; `poll_mail_replies` must be scheduled/running; password never logged) + brief note in docs/codebase-knowledge if architecture doc touched
- [x] T025 Commit with verification evidence

## Dependencies

```
T001→T002→T003→T004→T005 ─┬─ US1 (T006→T007→T008→T009)
                          ├─ US2 (T010→T011→T012→T013)   [needs US1 credential]
                          ├─ US3 (T014→T015→T016→T017)   [needs US2 EmailLog.message_id]
                          └─ US4 (T018→T019→T020→T021)   [needs Notification from US3]
US1..US4 → T022→T023→T024→T025
```

MVP increment: US1+US2 (link + send) already delivers the core workflow win;
US3+US4 close the reply loop. Parallel: the [P] test/FE tasks within a story.

## Implementation Strategy

Build US1→US2 first (immediately useful: in-system send replaces the Gmail
hand-off). US3 reuses US2's stored Message-IDs; US4 is the surface for US3's
notifications. The real-network E2E (T022) is the final gate; the synthetic
poller tests (T016) prove matching logic independent of Gmail availability.
