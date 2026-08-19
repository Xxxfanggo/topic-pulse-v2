"""SMTP email provider for notification delivery."""

from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage


@dataclass(slots=True)
class SMTPEmailProvider:
    host: str
    port: int = 587
    username: str | None = None
    password: str | None = None
    from_email: str | None = None
    from_name: str = "Topic Pulse"
    use_tls: bool = True
    use_ssl: bool = False
    timeout: float = 10.0

    @classmethod
    def from_env(cls) -> "SMTPEmailProvider | None":
        host = os.getenv("SMTP_HOST")
        if not host:
            return None
        use_ssl = _env_bool("SMTP_USE_SSL", False)
        default_port = 465 if use_ssl else 587
        return cls(
            host=host,
            port=int(os.getenv("SMTP_PORT") or default_port),
            username=os.getenv("SMTP_USERNAME") or None,
            password=os.getenv("SMTP_PASSWORD") or None,
            from_email=os.getenv("SMTP_FROM_EMAIL") or os.getenv("SMTP_USERNAME") or None,
            from_name=os.getenv("SMTP_FROM_NAME") or "Topic Pulse",
            use_tls=_env_bool("SMTP_USE_TLS", True),
            use_ssl=use_ssl,
            timeout=float(os.getenv("SMTP_TIMEOUT") or 10),
        )

    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str = "",
    ) -> str:
        if not self.from_email:
            raise RuntimeError("SMTP_FROM_EMAIL or SMTP_USERNAME must be configured.")
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = f"{self.from_name} <{self.from_email}>"
        message["To"] = to_email
        message.set_content(text_body)
        if html_body:
            message.add_alternative(html_body, subtype="html")

        if self.use_ssl:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout) as smtp:
                self._send(smtp, message)
            return "smtp_ssl"
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
            if self.use_tls:
                smtp.starttls()
            self._send(smtp, message)
        return "smtp"

    def _send(self, smtp, message: EmailMessage) -> None:
        if self.username:
            smtp.login(self.username, self.password or "")
        smtp.send_message(message)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

