# API Contract — Employee Mail Link

All under `/api/admin/mail/`, HR-only (admin/recruiter). Password never appears
in any response.

## Credential

### POST /api/admin/mail/credentials/   — link
```json
req:  { "employee": 20, "gmail_address": "x@gmail.com", "app_password": "abcd efgh ijkl mnop" }
200:  { "employee": 20, "gmail_address": "x@gmail.com", "status": "active", "linked_at": "..." }
400:  { "success": false, "error": { "code": "PROBE_FAILED", "message": "<provider text>" } }
```
Validates by real SMTP + IMAP login BEFORE saving. No password echoed.

### GET /api/admin/mail/credentials/?employee=20   — status
```json
200: { "linked": true, "gmail_address": "x@gmail.com", "status": "active", "last_error": "" }
     | { "linked": false }
```

### DELETE /api/admin/mail/credentials/{employee}/   — unlink
`204` — credential row hard-deleted.

## Send

### POST /api/admin/mail/send-apply/
```json
req:  { "match": 642, "to": "recruiter@co.com", "subject": "...", "body": "..." }
200:  { "ok": true, "email_log": 11, "match_status": "applied", "cv_attached": true }
400:  PROBE/SEND failure → { "error": { "code": "SEND_FAILED", "message": "..." } }  (match NOT applied)
409:  duplicate-apply frontman (existing guard) → returns frontman, needs confirm_duplicate
```

## Mail thread (per match)

### GET /api/admin/mail/thread/?match=642
```json
200: [ { "direction": "out", "to_addr": "...", "subject": "...", "body_text": "...", "created_at": "..." },
       { "direction": "in",  "from_addr": "...", "subject": "Re: ...", "body_text": "...", "is_bounce": false, "created_at": "..." } ]
```

## Notifications

### GET /api/admin/mail/notifications/?page=1   — newest first, unread first
```json
200: { "count": 7, "unread": 3, "results": [ { "id": 5, "type": "mail_reply",
       "title": "Reply from recruiter", "body_preview": "Thanks, we'd like...",
       "link_url": "/admin/employees/20?match=642", "employee": 20, "read_at": null, "created_at": "..." } ] }
```

### GET /api/admin/mail/notifications/unread-count/
```json
200: { "unread": 3 }
```

### POST /api/admin/mail/notifications/{id}/read/
`200: { "id": 5, "read_at": "..." }`

### GET /api/admin/mail/notifications/recent-replies/   — dashboard block
```json
200: [ { "employee": {"id":20,"name":"..."}, "job_title": "...", "snippet": "...", "created_at": "...", "link_url": "..." } ]
```

## Permissions

All endpoints: authenticated + role ∈ {admin, recruiter} (same guard as the
match endpoints). 403 otherwise. Serializers exclude `password_encrypted`
entirely.
