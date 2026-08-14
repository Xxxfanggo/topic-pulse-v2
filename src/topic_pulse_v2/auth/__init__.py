"""Email authentication primitives."""

from .service import (
    AuthService,
    AuthUser,
    ConsoleEmailCodeSender,
    EmailCodeSender,
    JwtCodec,
    SMTPEmailCodeSender,
)

__all__ = [
    "AuthService",
    "AuthUser",
    "ConsoleEmailCodeSender",
    "EmailCodeSender",
    "JwtCodec",
    "SMTPEmailCodeSender",
]
