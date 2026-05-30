"""Password hashing via the bcrypt library directly.

passlib 1.7.4's backend self-test is incompatible with bcrypt >= 4.1 and
raises at import time, so we call bcrypt directly. bcrypt enforces a 72-byte
input cap, which we apply defensively.
"""
from __future__ import annotations

import bcrypt

_MAX_BCRYPT_BYTES = 72


def _to_bytes(plain: str) -> bytes:
    return plain.encode("utf-8")[:_MAX_BCRYPT_BYTES]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_to_bytes(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bytes(plain), hashed.encode("utf-8"))
    except ValueError:
        return False
