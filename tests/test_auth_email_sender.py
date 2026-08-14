import os
import unittest
from unittest.mock import Mock, patch

from topic_pulse_v2.auth import SMTPEmailCodeSender
from topic_pulse_v2.auth.service import default_email_code_sender


class SMTPEmailCodeSenderTests(unittest.TestCase):
    def test_smtp_sender_sends_verification_code_message(self):
        smtp_instance = Mock()
        smtp_context = Mock()
        smtp_context.__enter__ = Mock(return_value=smtp_instance)
        smtp_context.__exit__ = Mock(return_value=None)

        sender = SMTPEmailCodeSender(
            host="smtp.example.com",
            port=587,
            username="mailer@example.com",
            password="secret",
            from_email="noreply@example.com",
            use_tls=True,
        )

        with patch("topic_pulse_v2.auth.service.smtplib.SMTP", return_value=smtp_context) as smtp_class:
            sender.send_verification_code(email="user@example.com", code="123456", purpose="register")

        smtp_class.assert_called_once_with("smtp.example.com", 587, timeout=10.0)
        smtp_instance.starttls.assert_called_once()
        smtp_instance.login.assert_called_once_with("mailer@example.com", "secret")
        smtp_instance.send_message.assert_called_once()
        message = smtp_instance.send_message.call_args.args[0]
        self.assertEqual(message["To"], "user@example.com")
        self.assertEqual(message["From"], "Topic Pulse <noreply@example.com>")
        self.assertIn("123456", message.get_content())

    def test_default_sender_uses_smtp_when_env_is_configured(self):
        env = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "2525",
            "SMTP_USERNAME": "mailer@example.com",
            "SMTP_PASSWORD": "secret",
            "SMTP_FROM_EMAIL": "noreply@example.com",
            "SMTP_USE_TLS": "false",
        }
        with patch.dict(os.environ, env, clear=False):
            sender = default_email_code_sender()

        self.assertIsInstance(sender, SMTPEmailCodeSender)
        self.assertEqual(sender.host, "smtp.example.com")
        self.assertEqual(sender.port, 2525)
        self.assertFalse(sender.use_tls)


if __name__ == "__main__":
    unittest.main()
