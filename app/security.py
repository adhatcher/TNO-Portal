"""Security and validation helpers."""

from __future__ import annotations

import re
import secrets

from flask import session
from werkzeug.security import check_password_hash, generate_password_hash

from app.instrumentation import instrument

PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$")


@instrument("validate_password")
def validate_password(password: str) -> bool:
    """Validate password complexity requirements."""

    return bool(PASSWORD_PATTERN.match(password or ""))


@instrument("hash_password")
def hash_password(password: str) -> str:
    """Securely hash a password."""

    return generate_password_hash(password)


@instrument("verify_password")
def verify_password(password_hash: str, password: str) -> bool:
    """Verify a password against a stored hash."""

    return check_password_hash(password_hash, password)


@instrument("get_csrf_token")
def get_csrf_token() -> str:
    """Return a stable CSRF token for the current session."""

    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


@instrument("validate_csrf")
def validate_csrf(token: str | None) -> bool:
    """Check whether a submitted token matches the session token."""

    return bool(token and token == session.get("csrf_token"))
