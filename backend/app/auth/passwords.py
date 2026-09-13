"""Password hashing with scrypt, which is memory-hard and ships with Python.

Stored as `scrypt$n$r$p$salt$hash`, so the cost can be raised later and old
hashes still verify.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

N, R, P = 2**14, 8, 1
MIN_LENGTH = 12


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=32)
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        # Same work as a real check, so timing does not reveal which emails exist.
        hashlib.scrypt(password.encode(), salt=b"0" * 16, n=N, r=R, p=P, dklen=32)
        return False
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        check = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt),
                               n=int(n), r=int(r), p=int(p), dklen=len(base64.b64decode(digest)))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(check, base64.b64decode(digest))


def password_problem(password: str) -> str | None:
    if len(password) < MIN_LENGTH:
        return f"A password needs at least {MIN_LENGTH} characters."
    return None
