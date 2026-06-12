# Research — Employee Mail Link

## R1. Credential encryption — Fernet (symmetric)

**Decision**: `cryptography.fernet.Fernet` with a single key in env
`MAIL_CRED_KEY`. `crypto.encrypt(plaintext) -> token`, `crypto.decrypt(token)
-> plaintext`. Key load fails loud at first use if `MAIL_CRED_KEY` missing/invalid.

**Rationale**: one service both encrypts (at link) and decrypts (at send/poll) →
symmetric is correct; asymmetric adds nothing. Fernet = AES-128-CBC + HMAC,
authenticated, URL-safe token, already in venv. Key rotation is out of scope
(documented); if needed later, MultiFernet supports it without schema change.

**Alternatives**: Django `SECRET_KEY`-derived (couples mail secrets to the app
secret's blast radius — rejected); plaintext + DB-level encryption (weaker,
ops-dependent — rejected).

## R2. Reply matching — threading headers only

**Decision**: every outgoing mail gets a self-generated RFC 5322 Message-ID
`<{uuid4}@jobflow.local>` stored on `EmailLog.message_id`. The poller reads each
candidate's `In-Reply-To` + `References` headers and matches if either contains
a known `message_id`. No subject/sender heuristic.

**Rationale**: standards-compliant clients echo the original Message-ID in
`In-Reply-To`/`References` — exact, zero false positives, and the privacy
guarantee (only touch mail referencing what we sent). Subject matching would
read unrelated mail and mis-fire — rejected (documented limitation: a client
that drops these headers won't be tracked).

## R3. IMAP fetch discipline

**Decision**: `imaplib`, `SELECT INBOX` (readonly via `select(readonly=True)`),
`SEARCH SINCE <last_poll_date>` to bound the window, then for each UID
`FETCH (BODY.PEEK[HEADER])` first; only on a header match do `FETCH
(BODY.PEEK[])` the full body. `BODY.PEEK` never sets `\Seen`. Track a
per-credential `last_polled_at`/`last_uid` to avoid resc· re-scan.

**Rationale**: header-first keeps non-matching mail unread AND unfetched-in-full
(privacy + bandwidth). readonly SELECT is belt-and-suspenders against accidental
flag writes.

## R4. Send path

**Decision**: `smtplib.SMTP(smtp.gmail.com, 587)` + `starttls()` +
`login(address, app_password)`; `EmailMessage` with From = employee address,
To = recruiter, the composed body, and the CV attached from `Employee.cv_file`
(guess MIME by extension; pdf/docx). Set the self Message-ID header before send;
store `EmailLog(out, status=sent)` on success, `status=failed` + error on
exception (match NOT marked applied in that case).

**Rationale**: Gmail SMTP relays "as" the authenticated address — From shows the
employee. STARTTLS:587 is Gmail's documented submission path. Reusing
`EmailMessage` keeps headers correct.

## R5. Probe at link time

**Decision**: before saving a credential, run BOTH `SMTP.login()` and
`IMAP.login()` with the supplied address+password; any failure → reject with the
provider's error text, store nothing. On success → encrypt + save status=active.

**Rationale**: a credential that can't send OR can't be polled is useless;
validating both at link time turns a future silent runtime failure into an
immediate, actionable link-time rejection (project's fail-loud principle).

## R6. Bounce detection

**Decision**: a polled message qualifies as a bounce if its From contains
`mailer-daemon@` or `postmaster@` AND its `References`/body contains a known
`message_id`. Store as `EmailLog(in)` flagged bounce + Notification type
`mail_bounce`.

**Rationale**: bounces are just auto-replies that already thread to the original;
the same matching path catches them — surfaces "delivery failed" for free.

## R7. Notification ownership

**Decision**: the new `Notification` model lives in `apps/mail` (the only
producer for now), with an extensible `type` field. `apps/notifications` stays
the HR-digest app.

**Rationale**: avoids confusing two "notification" concepts; keeps the
mail-driven surface cohesive. If notifications later get many producers, promote
the model to a shared app — non-breaking (type field already generic).
