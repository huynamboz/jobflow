# Implementation Plan: Employee Mail Link

**Branch**: `026-employee-mail-link` | **Date**: 2026-06-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/026-employee-mail-link/spec.md`

## Summary

Add a new Django app `apps/mail` that lets HR link an employee's Gmail
(app-password, encrypted at rest), send the application email from the
employee's own address with the CV attached (replacing the open-Gmail hand-off),
and poll IMAP for recruiter replies — matched strictly by threading headers
against system-generated Message-IDs — surfacing them as in-app notifications
(header bell popover + dashboard block) and a per-match mail thread. Verified
end-to-end against a real test Gmail.

## Technical Context

**Stack**: Django 5.2 + DRF (backend), React 18 + Vite + HeroUI (admin).
**Verified facts (2026-06-12)**:
- `Employee.email` + `Employee.cv_file` exist; matches carry an applied flow +
  duplicate-apply frontman guard (`matchService.update status=applied`).
- `apps/notifications` has NO model (digest-only) → in-app Notification is new.
- `apps/schedule`: `VerifierSchedule.COMMAND_CHOICES` + `schedule_runner` daemon
  exist → register `poll_mail_replies` there (small migration).
- `cryptography`/Fernet present in venv. `EMAIL_*` SMTP config exists (console
  backend default). `.env` (gitignored) now holds `MAIL_CRED_KEY` (Fernet) +
  `TEST_GMAIL_ADDRESS` + `TEST_GMAIL_APP_PASSWORD`.
- FE header `admin-header.tsx` already renders a `Bell` (lucide) in the right
  slot — wire popover + badge there. Apply button → `apply-email.tsx`
  (compose, AI draft stream, then opens Gmail tab — replace with Send).

**New app**: `backend/apps/mail/` — models, services (crypto, smtp_send,
imap_poll), serializers, views, urls, management command, migrations, tests.
Notification model also lives here (single owner of the mail-driven surface;
`apps/notifications` stays the digest app to avoid confusion).

### Components

| # | Component | Where |
|---|---|---|
| A | `EmployeeMailCredential` (OneToOne) + Fernet crypto helper | apps/mail/models.py, apps/mail/crypto.py |
| A | link/unlink/status API + SMTP&IMAP probe | apps/mail/views.py, services/probe.py |
| A | "Email account" card on employee detail | FE employees/detail.tsx + mail.service.ts |
| B | `EmailLog` (out/in) + send service (smtplib STARTTLS, attach CV, self Message-ID) | apps/mail/models.py, services/send.py |
| B | `POST /api/admin/mail/send-apply/` → send + applied flow | apps/mail/views.py |
| B | apply-email page: "Send" (primary if linked) + Gmail fallback | FE apply-email.tsx |
| C | `poll_mail_replies` command (IMAP BODY.PEEK, header match, bounce) | apps/mail/management/commands/ |
| C | register in VerifierSchedule.COMMAND_CHOICES | apps/schedule migration |
| D | `Notification` model + list/mark-read/unread-count API | apps/mail/models.py, views.py |
| D | header bell popover + badge; dashboard "Mail replies" block | FE admin-header.tsx, dashboard.tsx |
| D/B | match detail mail thread | FE employees/detail.tsx |

### Security design (FR-002/006, SC-005/006)

- Password column stores Fernet ciphertext; `crypto.encrypt/decrypt` with
  `MAIL_CRED_KEY` from env — **fail-loud if key missing** (project convention).
  Serializer NEVER includes the password field; `__repr__`/logs redacted.
  Unlink = `credential.delete()` (row gone).
- Poller filter is the privacy guarantee: it pulls headers, computes the
  In-Reply-To/References set, and only `BODY.PEEK`s + stores a message whose
  reference intersects known `EmailLog.message_id`. Anything else: not fetched
  beyond envelope, not stored. `BODY.PEEK` (not BODY) keeps \Seen off.

## Constitution Check

`.specify/memory/constitution.md` = unfilled template (as in 018–025). Generic
gates honored: new app is self-contained; fail-loud on missing key / probe
failure / send failure (no silent success); secrets never serialized; tests
incl. a real E2E. **PASS** (pre- and post-design).

## Phase 0 — Research

→ [research.md](research.md). Key decisions: Fernet symmetric (single service
encrypts+decrypts); self-generated RFC-compliant Message-ID `<uuid@jobflow>`;
IMAP `SINCE last_poll` + header match (not full-body scan); probe = SMTP
`login()` AND IMAP `login()`, fail → reject; bounce = sender contains
`mailer-daemon`/`postmaster` AND references a known id.

## Phase 1 — Design

→ [data-model.md](data-model.md) · [contracts/api.md](contracts/api.md) ·
[quickstart.md](quickstart.md) (E2E runbook with the real test inbox).

### Implementation order (informs tasks)

```
1. crypto + EmployeeMailCredential + probe + link/unlink/status API + tests
2. FE email-account card
3. EmailLog + send service (CV attach) + send-apply API + applied flow + tests
4. FE apply-email Send button + thread view
5. Notification model + API (list/mark-read/unread) + tests
6. FE bell popover + dashboard block
7. poll_mail_replies command + schedule registration + matching tests
8. E2E with real test gmail (link→send→reply→poll→notify) + negatives
9. docs (CLAUDE.md gotcha: MAIL_CRED_KEY, app-password, poller must run)
```

### Riskiest pieces & mitigation

- **Real-network E2E flakiness** (Gmail throttling/challenges): probe + send
  surface the provider's exact message; E2E retries the poll a few cycles; if
  Gmail blocks the CI IP, the matching-logic unit tests (synthetic IMAP) still
  prove correctness and the E2E is documented as environment-dependent.
- **Secret leakage**: a dedicated test asserts the password is absent from the
  serializer output and the credential's `repr`.

## Phase 2 — Tasks

→ [tasks.md](tasks.md) via `/speckit-tasks`.
