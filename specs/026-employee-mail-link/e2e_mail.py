"""E2E for 026 against the REAL test inbox (env TEST_GMAIL_*).

link → send-apply (to self) → simulate threaded reply → poll → assert
EmailLog(in) + Notification. Run: python specs/026-employee-mail-link/e2e_mail.py
"""
import sys, os, time, smtplib, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings"); django.setup()
import logging; logging.disable(logging.WARNING)

from django.conf import settings
ADDR = os.environ["TEST_GMAIL_ADDRESS"]; PW = os.environ["TEST_GMAIL_APP_PASSWORD"]

from apps.employees.models import Employee, EmployeeJobMatch
from apps.jobs.models import Job
from apps.mail.models import EmployeeMailCredential, EmailLog, Notification
from apps.mail.services.probe import probe, ProbeError
from apps.mail.services.send import send_apply_email
from apps.mail.services.imap_poll import poll_credential

def step(msg): print(f"\n=== {msg} ===")

# 0. clean test fixtures
Employee.objects.filter(full_name="E2E Mail Tester").delete()
emp = Employee.objects.create(full_name="E2E Mail Tester", skills=["python"])
job = Job.objects.create(title="E2E Backend Role", source_url=f"http://e2e/{uuid.uuid4().hex}")
match = EmployeeJobMatch.objects.create(employee=emp, job=job, status="suggested")

step("1. PROBE + LINK (real SMTP+IMAP login)")
probe(ADDR, PW.replace(" ", ""))
cred = EmployeeMailCredential(employee=emp, gmail_address=ADDR); cred.set_password(PW.replace(" ", "")); cred.save()
print(f"  linked {ADDR} · status={cred.status}")

step("1b. NEGATIVE: wrong password rejected")
try:
    probe(ADDR, "wrong-password-xyz"); print("  ✗ should have failed")
except ProbeError as e: print(f"  ✓ rejected: {str(e)[:60]}")

step("2. SEND-APPLY to self (CV attach path; no CV file → cv_attached False ok)")
out = send_apply_email(credential=cred, employee=emp, match=match,
                       to_addr=ADDR, subject="E2E application", body="Hello, applying for the role.")
print(f"  sent · message_id={out.message_id} · cv_attached={out.cv_attached}")
SENT_MID = out.message_id

step("3. SIMULATE recruiter reply (SMTP send w/ In-Reply-To = sent message id)")
from email.message import EmailMessage
reply = EmailMessage()
reply["From"] = ADDR; reply["To"] = ADDR
reply["Subject"] = "Re: E2E application"
reply["Message-ID"] = f"<reply-{uuid.uuid4().hex}@co.com>"
reply["In-Reply-To"] = SENT_MID
reply["References"] = SENT_MID
reply.set_content("Thanks for applying — we'd like to schedule an interview.")
with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
    s.starttls(); s.login(ADDR, PW.replace(" ", "")); s.send_message(reply)
print("  reply sent; waiting for Gmail delivery...")

step("4. POLL (retry a few cycles for delivery latency)")
found = 0
for attempt in range(8):
    time.sleep(8)
    found = poll_credential(cred)
    print(f"  poll attempt {attempt+1}: {found} new")
    if found: break

step("5. ASSERT")
in_logs = EmailLog.objects.filter(employee=emp, direction="in")
notifs = Notification.objects.filter(employee=emp, type="mail_reply")
print(f"  EmailLog(in): {in_logs.count()} · Notification(reply): {notifs.count()}")
if in_logs.exists():
    print(f"  reply body: {in_logs.first().body_text[:80]!r}")
ok = in_logs.exists() and notifs.exists() and "interview" in (in_logs.first().body_text or "")
print(f"\n  E2E RESULT: {'PASS ✓' if ok else 'INCOMPLETE (delivery latency? rerun poll)'}")

step("6. NEGATIVE: unlink removes the row")
EmployeeMailCredential.objects.filter(employee=emp).delete()
print(f"  credential rows after unlink: {EmployeeMailCredential.objects.filter(employee=emp).count()}")
sys.exit(0 if ok else 1)
