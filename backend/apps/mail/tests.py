"""Mail-link tests (026). Unit (no network) + matching logic."""
from unittest import mock

from django.test import TestCase

from apps.employees.models import Employee
from apps.mail import crypto
from apps.mail.models import EmailLog, EmployeeMailCredential, Notification


def _emp(**kw):
    return Employee.objects.create(full_name=kw.get("name", "Test"), skills=["python"], **{k: v for k, v in kw.items() if k != "name"})


class CryptoTests(TestCase):
    def test_roundtrip(self):
        t = crypto.encrypt("srno zwia cmny qqay")
        self.assertNotIn("srno", t)
        self.assertEqual(crypto.decrypt(t), "srno zwia cmny qqay")

    def test_key_missing_fails_loud(self):
        import os
        crypto._fernet.cache_clear()
        with mock.patch.dict(os.environ, {"MAIL_CRED_KEY": ""}, clear=False):
            with self.assertRaises(RuntimeError):
                crypto.encrypt("x")
        crypto._fernet.cache_clear()


class CredentialSecurityTests(TestCase):
    def test_password_never_in_serializer_or_repr(self):
        from apps.mail.serializers import CredentialStatusSerializer
        e = _emp()
        c = EmployeeMailCredential(employee=e, gmail_address="x@gmail.com")
        c.set_password("super-secret-pw")
        c.save()
        data = CredentialStatusSerializer(c).data
        self.assertNotIn("password_encrypted", data)
        self.assertNotIn("super-secret-pw", str(data))
        self.assertNotIn("super-secret-pw", repr(c))
        self.assertEqual(c.get_password(), "super-secret-pw")


class SendTests(TestCase):
    def _setup(self):
        e = _emp()
        c = EmployeeMailCredential(employee=e, gmail_address="x@gmail.com")
        c.set_password("pw"); c.save()
        from apps.jobs.models import Job
        from apps.employees.models import EmployeeJobMatch
        j = Job.objects.create(title="FE", source_url="http://x")
        m = EmployeeJobMatch.objects.create(employee=e, job=j, status="suggested")
        return e, c, m

    def test_send_success_marks_applied(self):
        e, c, m = self._setup()
        with mock.patch("apps.mail.services.send.smtplib.SMTP") as S:
            S.return_value.__enter__.return_value = mock.MagicMock()
            from apps.mail.services.send import send_apply_email
            log = send_apply_email(credential=c, employee=e, match=m,
                                   to_addr="r@co.com", subject="s", body="b")
        self.assertEqual(log.status, EmailLog.SENT)
        self.assertTrue(log.message_id.endswith("@jobflow.local>"))

    def test_send_failure_records_failed(self):
        e, c, m = self._setup()
        with mock.patch("apps.mail.services.send.smtplib.SMTP", side_effect=OSError("smtp down")):
            from apps.mail.services.send import send_apply_email
            with self.assertRaises(OSError):
                send_apply_email(credential=c, employee=e, match=m, to_addr="r@co.com", subject="s", body="b")
        log = EmailLog.objects.get(employee=e, direction="out")
        self.assertEqual(log.status, EmailLog.FAILED)


class PollerMatchTests(TestCase):
    """Header-matching logic without a live IMAP server."""

    def _imap_with(self, messages):
        """messages: list of raw bytes (full RFC822)."""
        m = mock.MagicMock()
        m.search.return_value = ("OK", [b" ".join(str(i).encode() for i in range(1, len(messages) + 1))])
        def _fetch(uid, what):
            idx = int(uid) - 1
            return ("OK", [(b"x", messages[idx])])
        m.fetch.side_effect = _fetch
        return m

    def _cred(self):
        e = _emp()
        c = EmployeeMailCredential(employee=e, gmail_address="x@gmail.com"); c.set_password("pw"); c.save()
        EmailLog.objects.create(employee=e, direction="out", from_addr="x@gmail.com", to_addr="r@co.com",
                                subject="Apply", body_text="hi", message_id="<sent123@jobflow.local>", status="sent")
        return c

    def test_reply_matched_creates_log_and_notification(self):
        c = self._cred()
        reply = (b"From: recruiter@co.com\r\nSubject: Re: Apply\r\nMessage-ID: <r1@co.com>\r\n"
                 b"In-Reply-To: <sent123@jobflow.local>\r\n\r\nThanks, interested!\r\n")
        with mock.patch("apps.mail.services.imap_poll.imaplib.IMAP4_SSL", return_value=self._imap_with([reply])):
            from apps.mail.services.imap_poll import poll_credential
            n = poll_credential(c)
        self.assertEqual(n, 1)
        log = EmailLog.objects.get(direction="in")
        self.assertIn("interested", log.body_text)
        self.assertFalse(log.is_bounce)
        self.assertEqual(Notification.objects.filter(type="mail_reply").count(), 1)

    def test_unrelated_mail_ignored(self):
        c = self._cred()
        junk = b"From: spam@x.com\r\nSubject: Buy now\r\nMessage-ID: <j@x>\r\n\r\nspam\r\n"
        with mock.patch("apps.mail.services.imap_poll.imaplib.IMAP4_SSL", return_value=self._imap_with([junk])):
            from apps.mail.services.imap_poll import poll_credential
            n = poll_credential(c)
        self.assertEqual(n, 0)
        self.assertEqual(EmailLog.objects.filter(direction="in").count(), 0)

    def test_bounce_detected(self):
        c = self._cred()
        bounce = (b"From: mailer-daemon@googlemail.com\r\nSubject: Delivery failed\r\nMessage-ID: <b@g>\r\n"
                  b"References: <sent123@jobflow.local>\r\n\r\nundelivered\r\n")
        with mock.patch("apps.mail.services.imap_poll.imaplib.IMAP4_SSL", return_value=self._imap_with([bounce])):
            from apps.mail.services.imap_poll import poll_credential
            n = poll_credential(c)
        self.assertEqual(n, 1)
        self.assertTrue(EmailLog.objects.get(direction="in").is_bounce)
        self.assertEqual(Notification.objects.filter(type="mail_bounce").count(), 1)

    def test_peek_used_no_seen_flag(self):
        c = self._cred()
        reply = b"From: r@co.com\r\nMessage-ID: <r2@co>\r\nIn-Reply-To: <sent123@jobflow.local>\r\n\r\nok\r\n"
        imap = self._imap_with([reply])
        with mock.patch("apps.mail.services.imap_poll.imaplib.IMAP4_SSL", return_value=imap):
            from apps.mail.services.imap_poll import poll_credential
            poll_credential(c)
        fetches = [str(call) for call in imap.fetch.call_args_list]
        self.assertTrue(all("PEEK" in f for f in fetches))  # never plain BODY[]
        imap.select.assert_called_with("INBOX", readonly=True)
