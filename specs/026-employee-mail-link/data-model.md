# Data Model — Employee Mail Link

All in new app `apps/mail`. HR-only access (admin/recruiter).

## EmployeeMailCredential

| Field | Type | Notes |
|---|---|---|
| employee | OneToOne(Employee) | cascade delete |
| gmail_address | Email, unique | one address across all credentials |
| password_encrypted | Text | Fernet ciphertext — **never serialized/logged** |
| status | choices: active / error | error when probe/send/poll auth fails |
| last_error | Text, blank | provider message on error |
| linked_at | datetime | |
| updated_at | datetime | |

Unlink = row `delete()` (hard). `decrypt_password()` decrypts on demand; no
plaintext column ever.

## EmailLog

| Field | Type | Notes |
|---|---|---|
| employee | FK(Employee) | |
| match | FK(EmployeeJobMatch), null | the application this mail belongs to |
| direction | out / in | |
| from_addr / to_addr | Email | |
| subject | Text | |
| body_text | Text | full content (FR-010, decision #3) |
| message_id | Text, indexed | self-generated for `out`; sender's for `in` |
| in_reply_to | Text, blank, indexed | for `in`: the matched out message_id |
| is_bounce | bool | `in` + mailer-daemon |
| status | sent / failed (out) · received (in) | |
| error | Text, blank | send failure reason |
| created_at | datetime | sent_at / received_at |

Thread of a match = `EmailLog.filter(match=…).order_by(created_at)`.

## Notification

| Field | Type | Notes |
|---|---|---|
| type | mail_reply / mail_bounce | extensible |
| title | Text | e.g. "Reply from recruiter" |
| body_preview | Text | snippet of the reply |
| link_url | Text | deep-link, e.g. `/admin/employees/20?match=642` |
| employee | FK(Employee), null | for the dashboard block |
| read_at | datetime, null | null = unread |
| created_at | datetime | |

## Invariants

1. Password plaintext exists only transiently in memory (probe/send/poll);
   never persisted, serialized, or logged.
2. An `EmailLog(in)` is created ONLY when a header reference matches an existing
   `EmailLog.message_id` — no unmatched mail is stored.
3. Send marks the match applied only on `status=sent`; on `failed` the match is
   untouched.
4. Poller never sets `\Seen` (BODY.PEEK + readonly SELECT).

## Schedule registration

`VerifierSchedule.COMMAND_CHOICES += ('poll_mail_replies', 'poll_mail_replies')`
(migration). Default cadence 15 min via existing `schedule_runner`.
