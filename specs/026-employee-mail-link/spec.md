# Feature Specification: Employee Mail Link — in-system apply email + reply tracking

**Feature Branch**: `026-employee-mail-link`

**Created**: 2026-06-12

**Status**: Draft

**Input**: User description: "HR links each employee's Gmail to their profile, sends application emails from the employee's own address directly inside the system (CV attached automatically), and gets notified in-app when recruiters reply."

## Problem Statement

Today the apply flow stops at the system's edge: HR composes an application
email in the app, then the app opens Gmail in a new browser tab where HR must
(1) be logged into the right account, (2) manually attach the employee's CV
(the hand-off cannot carry attachments), and (3) remember to come back and mark
the match as applied. After sending, the system is blind: nobody knows whether
a recruiter replied unless HR manually checks an inbox.

Three losses: outgoing mail is untracked, the CV-attachment step is error-prone,
and recruiter replies — the single most important signal in the pipeline —
never reach the system.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Link an employee's email account (Priority: P1)

As HR, I can connect an employee's Gmail to their profile (with the employee's
consent and an app-specific password they provide), so the system can send and
track application mail on their behalf.

**Why this priority**: every other capability depends on a linked, verified
account. Verification at link time prevents silent failures later.

**Independent Test**: link a real test account → status shows "active"; attempt
a wrong password → clear rejection, nothing stored.

**Acceptance Scenarios**:

1. **Given** an employee profile and a valid address + app password, **When**
   HR links it, **Then** the system verifies the credentials by actually
   signing in (both send and read channels) before saving, and shows "linked /
   active" with the address.
2. **Given** an invalid password, **When** HR attempts to link, **Then** the
   system rejects with a clear reason and stores nothing.
3. **Given** a linked account, **When** HR unlinks it, **Then** the stored
   credential is permanently deleted and the profile returns to "not linked".
4. **At all times**: the password is never displayed, never returned by any
   API, and never written to logs.

### User Story 2 - Send the application email from the system (Priority: P1)

As HR, on the existing compose page I can press "Send" and the email goes out
from the employee's own Gmail address with their CV attached automatically —
and the match is marked applied in the same action.

**Why this priority**: this is the core workflow improvement — one click
replaces the open-Gmail / attach-CV / come-back-and-mark dance.

**Independent Test**: send to the test inbox; the received mail shows the
employee's address as sender and carries the CV file; the match flips to
applied; an outgoing-mail record exists.

**Acceptance Scenarios**:

1. **Given** a linked employee and a composed email, **When** HR presses Send,
   **Then** the mail is delivered from the employee's address with the CV
   attached, an outgoing record (recipient, subject, body, time) is stored, and
   the match status becomes applied (existing duplicate-application safeguards
   still apply).
2. **Given** an employee without a linked account, **When** HR opens the
   compose page, **Then** Send is unavailable with a hint to link first, and
   the legacy "Open in Gmail" path remains usable.
3. **Given** a send failure (e.g., revoked password), **When** it occurs,
   **Then** HR sees the error immediately, the failure is recorded, the match
   is NOT marked applied, and the account status flags the problem.

### User Story 3 - Know when a recruiter replies (Priority: P2)

As HR, when a recruiter replies to an application email the system sent, I see
a notification (bell in the header) and the reply's full content in the match's
detail view — without anyone watching an inbox.

**Why this priority**: closes the loop; depends on US1+US2 existing.

**Independent Test**: send an application to the test inbox, then send a reply
to it; within one polling cycle the system shows a notification and the reply
content appears under the match.

**Acceptance Scenarios**:

1. **Given** a sent application, **When** a reply to that specific mail arrives
   in the employee's inbox, **Then** within one polling interval the system
   records the reply (full content: sender, subject, body, time), creates a
   notification, and shows the thread (sent + reply) in the match detail.
2. **Given** unrelated mail in the employee's inbox, **Then** the system never
   reads, stores, or surfaces it — only replies to mail the system itself sent.
3. **Given** a delivery failure bounce, **Then** it is detected the same way
   and surfaced as a "delivery failed" notification.
4. Polling must not alter the employee's mailbox state (messages stay unread).

### User Story 4 - Notification bell + dashboard block (Priority: P2)

As HR, I have a bell icon in the header showing an unread count; clicking it
opens a popover listing recent notifications (click an item → navigate to the
employee/match and mark it read). The dashboard shows a "Mail replies" block
with recent replies.

**Why this priority**: the delivery surface for US3; minimal by design (a
full notification center page is deferred).

**Acceptance Scenarios**:

1. **Given** unread notifications, **Then** the bell shows their count; opening
   the popover lists them newest-first; clicking one navigates to the linked
   employee/match and marks it read, decrementing the badge.
2. **Given** recent mail replies, **Then** the dashboard block lists them
   (employee, job, snippet, time) with links.

### Edge Cases

- **Password revoked after linking** (employee changes Google password): next
  send or poll fails → account status becomes "error" with the reason, visible
  on the profile; HR re-links.
- **Reply without threading headers** (rare mail clients): not matched — the
  system does not guess by subject; documented limitation.
- **Provider challenges sign-in from a new location**: link/send surfaces the
  provider's message clearly rather than a generic failure.
- **Two employees linked to the same address**: rejected (address unique across
  credentials).
- **CV file missing** on send: send proceeds without attachment only after an
  explicit warning; the record notes "no attachment".

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: HR can link exactly one email account per employee (address +
  app-specific password); the system MUST verify both send and read access by
  actually authenticating at link time, and store nothing on failure.
- **FR-002**: The stored password MUST be encrypted at rest, never returned by
  any API, never logged, and hard-deleted on unlink.
- **FR-003**: The link UI MUST show consent wording (what the system will do
  with the account: send applications, read only replies to them) and a hint
  for creating an app-specific password.
- **FR-004**: Sending an application email MUST deliver from the employee's
  linked address with the employee's CV attached automatically, record the
  outgoing mail in full, and mark the match applied (existing duplicate-apply
  safeguards preserved).
- **FR-005**: Each outgoing mail MUST carry a system-generated message
  identifier stored with the record — the basis for reply matching.
- **FR-006**: A periodic poller MUST detect inbox messages that are replies to
  system-sent mail (by threading headers only), store them in full, and create
  a notification; non-matching mail MUST never be read or stored; polling MUST
  NOT mark the employee's messages as read.
- **FR-007**: Bounce/delivery-failure messages for system-sent mail MUST be
  detected and surfaced as "delivery failed" notifications.
- **FR-008**: In-app notifications MUST be listable (newest first, unread
  count), markable as read, and deep-link to the related employee/match.
- **FR-009**: The header bell MUST show the unread count and a popover of
  recent notifications; the dashboard MUST show a recent-mail-replies block.
- **FR-010**: The match detail MUST show the mail thread for that match (sent
  application + any replies, full content).
- **FR-011**: The poller MUST be schedulable via the existing job scheduler
  (registered command, default 15-minute cadence).
- **FR-012**: All mail features MUST be restricted to HR roles (admin/recruiter),
  consistent with existing permissions.

### Key Entities

- **Employee mail credential**: one per employee; address, encrypted secret,
  status (active/error + reason), linked time. Deleted entirely on unlink.
- **Mail record**: every system-sent application and every detected reply/
  bounce; direction, addresses, subject, full body, message identifier,
  reply-reference, timestamps, send status; linked to employee and (when
  applicable) the match.
- **Notification**: type (reply/bounce — extensible), title, preview, deep
  link, read state, created time.

## Success Criteria *(mandatory)*

- **SC-001**: Linking with valid credentials succeeds with "active" status;
  linking with invalid credentials is rejected with a clear reason and zero
  stored data (verified against a real account).
- **SC-002**: A sent application arrives at the recipient showing the
  employee's address as sender and the CV attached (verified end-to-end with
  the real test inbox).
- **SC-003**: Send + mark-applied is one action: after Send, the match is
  applied and the outgoing record exists — no manual follow-up steps.
- **SC-004**: A reply to a sent application is detected within one polling
  cycle, stored in full, and produces a notification (verified end-to-end by
  sending a real reply-threaded message).
- **SC-005**: Unrelated mail in the linked inbox is never stored (verified: a
  non-reply message present in the inbox produces no records).
- **SC-006**: The password never appears in any API response, page, or log
  (verified by tests + API inspection).
- **SC-007**: Bell badge count, popover list, mark-read, and dashboard block
  reflect notification state correctly via the API.
- **SC-008**: A failed send leaves the match un-applied, records the failure,
  and flags the credential.

## Assumptions

- Employees are company staff who consent to the company sending applications
  from their address and tracking replies to those applications; consent
  wording shown at link time. If the tool is ever opened to external
  candidates, this approach must be revisited (scoped OAuth) — documented.
- Gmail-only for now (app-password mechanism is Google-specific).
- 15-minute polling latency is acceptable for recruiter-reply notifications.
- Replies lacking threading headers are out of scope (no subject-based
  guessing) — accepted limitation.
- The existing schedule daemon must be running for polling (operational
  prerequisite, already true for other scheduled jobs).
- One real test account (provided, stored outside version control) is used for
  end-to-end verification; sends during verification go to that same inbox.

## Out of Scope

- OAuth / Gmail API integration; other mail providers.
- A full notification-center page (bell popover only, detail page deferred).
- Sending arbitrary non-application emails; bulk/mass mailing.
- Real-time push notification (polling only).
- Open/click tracking of sent mail.
- Multi-account per employee.
