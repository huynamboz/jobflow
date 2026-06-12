# Quickstart — Employee Mail Link (E2E runbook)

Uses the real test inbox in `backend/.env` (`TEST_GMAIL_ADDRESS`,
`TEST_GMAIL_APP_PASSWORD`, `MAIL_CRED_KEY`). All from `backend/`.

```bash
# 0. migrate
python manage.py migrate mail schedule

# 1. unit tests (no network)
python manage.py test apps.mail
#    crypto roundtrip + key-missing fail · send (mocked SMTP) · poller match/
#    no-match/bounce (synthetic IMAP) · serializer hides password · permissions

# 2. E2E (real network) — one script does the whole loop:
python specs/026-employee-mail-link/e2e_mail.py
#    a. link TEST_GMAIL to a test employee via the service (SMTP+IMAP probe)
#    b. send-apply To: TEST_GMAIL (mail lands in its own inbox), CV attached
#    c. simulate recruiter reply: SMTP-send a 2nd mail with
#       In-Reply-To = <step-b Message-ID> to TEST_GMAIL
#    d. poll_mail_replies → assert: EmailLog(in) with full body, Notification
#       created, unread-count API = 1, recent-replies block non-empty
#    e. negatives: wrong password link → rejected, nothing stored;
#       a non-threaded mail in the inbox → no EmailLog row; unlink → row gone

# 3. manual UI smoke
#    employee detail → "Email account" card → link → status active
#    apply a job → compose → Send → received from employee addr + CV attached →
#    match = applied → reply to it → within 15 min: bell badge +1, thread shows reply
```

Done-when: unit suite green · E2E asserts all pass against the real inbox ·
password absent from every API/log · CLAUDE.md notes MAIL_CRED_KEY + poller.
