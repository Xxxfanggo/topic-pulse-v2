"""Email-code registration and token authentication service."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import smtplib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("Invalid email address.")
    return normalized


def _datetime_to_text(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _datetime_from_text(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


@dataclass(slots=True)
class AuthUser:
    id: str
    email: str
    status: str
    email_verified_at: datetime | None = None


class EmailCodeSender(Protocol):
    def send_verification_code(self, *, email: str, code: str, purpose: str) -> None:
        """Send a verification code to the user."""


class ConsoleEmailCodeSender:
    """Development sender that logs verification codes."""

    def send_verification_code(self, *, email: str, code: str, purpose: str) -> None:
        logger.warning("Email verification code for %s (%s): %s", email, purpose, code)


@dataclass(slots=True)
class SMTPEmailCodeSender:
    """SMTP sender for email verification codes."""

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
    def from_env(cls) -> "SMTPEmailCodeSender | None":
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

    def send_verification_code(self, *, email: str, code: str, purpose: str) -> None:
        if not self.from_email:
            raise RuntimeError("SMTP_FROM_EMAIL or SMTP_USERNAME must be configured.")
        message = self._build_message(email=email, code=code, purpose=purpose)
        if self.use_ssl:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout) as smtp:
                self._send(smtp, message)
            return
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
            if self.use_tls:
                smtp.starttls()
            self._send(smtp, message)

    def _send(self, smtp, message: EmailMessage) -> None:
        if self.username:
            smtp.login(self.username, self.password or "")
        smtp.send_message(message)

    def _build_message(self, *, email: str, code: str, purpose: str) -> EmailMessage:
        subject = "Your Topic Pulse verification code"
        if purpose == "register":
            subject = "Verify your Topic Pulse account"
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = f"{self.from_name} <{self.from_email}>"
        message["To"] = email
        message.set_content(
            "\n".join(
                [
                    "Your Topic Pulse verification code is:",
                    "",
                    code,
                    "",
                    "This code expires in 10 minutes. If you did not request it, you can ignore this email.",
                ]
            )
        )
        return message


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def default_email_code_sender() -> EmailCodeSender:
    return SMTPEmailCodeSender.from_env() or ConsoleEmailCodeSender()


class JwtCodec:
    """Small HS256 JWT encoder/decoder."""

    def __init__(self, secret: str | None = None, *, issuer: str = "topic-pulse-v2") -> None:
        self._secret = (secret or os.getenv("TOPIC_PULSE_JWT_SECRET") or "topic-pulse-dev-secret").encode("utf-8")
        self._issuer = issuer

    def encode(self, claims: dict, *, expires_delta: timedelta) -> str:
        now = utc_now()
        payload = {
            **claims,
            "iss": self._issuer,
            "iat": int(now.timestamp()),
            "exp": int((now + expires_delta).timestamp()),
        }
        header = {"alg": "HS256", "typ": "JWT"}
        signing_input = ".".join(
            [
                _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")),
                _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")),
            ]
        )
        signature = hmac.new(self._secret, signing_input.encode("ascii"), hashlib.sha256).digest()
        return f"{signing_input}.{_b64url_encode(signature)}"

    def decode(self, token: str) -> dict:
        try:
            header_b64, payload_b64, signature_b64 = token.split(".", 2)
        except ValueError as exc:
            raise ValueError("Invalid token.") from exc
        signing_input = f"{header_b64}.{payload_b64}"
        expected = hmac.new(self._secret, signing_input.encode("ascii"), hashlib.sha256).digest()
        provided = _b64url_decode(signature_b64)
        if not hmac.compare_digest(expected, provided):
            raise ValueError("Invalid token signature.")
        header = json.loads(_b64url_decode(header_b64))
        if header.get("alg") != "HS256":
            raise ValueError("Unsupported token algorithm.")
        payload = json.loads(_b64url_decode(payload_b64))
        if payload.get("iss") != self._issuer:
            raise ValueError("Invalid token issuer.")
        if int(payload.get("exp") or 0) < int(utc_now().timestamp()):
            raise ValueError("Token expired.")
        return payload


class AuthService:
    """Registration and login service backed by SQLite."""

    def __init__(
        self,
        *,
        path: str | Path = "data/topic_pulse.sqlite3",
        sender: EmailCodeSender | None = None,
        jwt_codec: JwtCodec | None = None,
        code_ttl: timedelta = timedelta(minutes=10),
        token_ttl: timedelta = timedelta(days=7),
        max_code_attempts: int = 5,
        min_code_interval: timedelta = timedelta(seconds=60),
    ) -> None:
        self.path = Path(path)
        self.sender = sender or default_email_code_sender()
        self.jwt_codec = jwt_codec or JwtCodec()
        self.code_ttl = code_ttl
        self.token_ttl = token_ttl
        self.max_code_attempts = max_code_attempts
        self.min_code_interval = min_code_interval

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    email_verified_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS email_verification_codes (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_email_codes_email_purpose
                    ON email_verification_codes(email, purpose, created_at DESC);
                """
            )

    def request_registration_code(self, email: str) -> None:
        email = normalize_email(email)
        self.initialize()
        if self._get_user_by_email(email) is not None:
            raise ValueError("Email is already registered.")
        latest = self._latest_code(email, "register")
        now = utc_now()
        if latest is not None:
            created_at = _datetime_from_text(latest["created_at"]) or now
            if now - created_at < self.min_code_interval:
                raise ValueError("Verification code was sent recently.")
        code = f"{secrets.randbelow(1_000_000):06d}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO email_verification_codes (
                    id, email, code_hash, purpose, expires_at, consumed_at, attempt_count, created_at
                ) VALUES (?, ?, ?, ?, ?, NULL, 0, ?)
                """,
                (
                    secrets.token_urlsafe(18),
                    email,
                    self._hash_code(email, code, "register"),
                    "register",
                    _datetime_to_text(now + self.code_ttl),
                    _datetime_to_text(now),
                ),
            )
        self.sender.send_verification_code(email=email, code=code, purpose="register")

    def register_with_code(self, *, email: str, code: str, password: str) -> tuple[AuthUser, str]:
        email = normalize_email(email)
        self._validate_password(password)
        self.initialize()
        if self._get_user_by_email(email) is not None:
            raise ValueError("Email is already registered.")
        row = self._latest_code(email, "register")
        if row is None:
            raise ValueError("Verification code is invalid.")
        self._verify_code_row(row, email=email, code=code, purpose="register")
        now = utc_now()
        user = AuthUser(
            id=secrets.token_urlsafe(18),
            email=email,
            status="active",
            email_verified_at=now,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO users (
                    id, email, password_hash, status, email_verified_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user.id,
                    user.email,
                    self._hash_password(password),
                    user.status,
                    _datetime_to_text(user.email_verified_at),
                    _datetime_to_text(now),
                    _datetime_to_text(now),
                ),
            )
            connection.execute(
                "UPDATE email_verification_codes SET consumed_at = ? WHERE id = ?",
                (_datetime_to_text(now), row["id"]),
            )
        return user, self.create_access_token(user)

    def login(self, *, email: str, password: str) -> tuple[AuthUser, str]:
        email = normalize_email(email)
        self.initialize()
        row = self._get_user_by_email(email)
        if row is None or not self._verify_password(password, row["password_hash"]):
            raise ValueError("Invalid email or password.")
        if row["status"] != "active" or not row["email_verified_at"]:
            raise ValueError("User is not active.")
        user = self._user_from_row(row)
        return user, self.create_access_token(user)

    def create_access_token(self, user: AuthUser) -> str:
        return self.jwt_codec.encode(
            {"sub": user.id, "email": user.email},
            expires_delta=self.token_ttl,
        )

    def authenticate_token(self, token: str) -> AuthUser:
        self.initialize()
        payload = self.jwt_codec.decode(token)
        user_id = str(payload.get("sub") or "")
        if not user_id:
            raise ValueError("Invalid token subject.")
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise ValueError("User not found.")
        user = self._user_from_row(dict(row))
        if user.status != "active":
            raise ValueError("User is not active.")
        return user

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _get_user_by_email(self, email: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row is not None else None

    def _latest_code(self, email: str, purpose: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM email_verification_codes
                WHERE email = ? AND purpose = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (email, purpose),
            ).fetchone()
        return dict(row) if row is not None else None

    def _verify_code_row(self, row: dict, *, email: str, code: str, purpose: str) -> None:
        now = utc_now()
        if row["consumed_at"]:
            raise ValueError("Verification code is invalid.")
        if (_datetime_from_text(row["expires_at"]) or now) < now:
            raise ValueError("Verification code expired.")
        if int(row["attempt_count"] or 0) >= self.max_code_attempts:
            raise ValueError("Verification code attempts exceeded.")
        expected = self._hash_code(email, code, purpose)
        if not hmac.compare_digest(expected, row["code_hash"]):
            with self._connect() as connection:
                connection.execute(
                    "UPDATE email_verification_codes SET attempt_count = attempt_count + 1 WHERE id = ?",
                    (row["id"],),
                )
            raise ValueError("Verification code is invalid.")

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
        return f"pbkdf2_sha256$260000${_b64url_encode(salt)}${_b64url_encode(digest)}"

    @staticmethod
    def _verify_password(password: str, encoded: str) -> bool:
        try:
            algorithm, iterations, salt_b64, digest_b64 = encoded.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            salt = _b64url_decode(salt_b64)
            expected = _b64url_decode(digest_b64)
            actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
            return hmac.compare_digest(expected, actual)
        except Exception:
            return False

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password or "") < 8:
            raise ValueError("Password must be at least 8 characters.")

    def _hash_code(self, email: str, code: str, purpose: str) -> str:
        payload = f"{purpose}:{email}:{code.strip()}".encode("utf-8")
        return hmac.new(self.jwt_codec._secret, payload, hashlib.sha256).hexdigest()

    @staticmethod
    def _user_from_row(row: dict) -> AuthUser:
        return AuthUser(
            id=row["id"],
            email=row["email"],
            status=row["status"],
            email_verified_at=_datetime_from_text(row.get("email_verified_at")),
        )
