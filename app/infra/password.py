# Owner: Amer
"""Password hashing for admin authentication.

Uses the `bcrypt` library directly. Passlib 1.7.x was considered but is
incompatible with bcrypt >= 4.0 (depends on a removed `__about__` attribute);
calling bcrypt directly avoids the dependency-pinning trap entirely.

Bcrypt has a hard 72-byte truncation on the password input. Passwords are
encoded to UTF-8 and truncated to 72 bytes BEFORE hashing/verification so the
two paths stay consistent and unicode passwords don't hit the limit
unexpectedly. This is the bcrypt-standard mitigation.
"""

from __future__ import annotations

import bcrypt

_BCRYPT_MAX_BYTES = 72


def _prep(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    """Return a bcrypt hash for the given plaintext password."""
    return bcrypt.hashpw(_prep(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True iff `plain` matches `hashed`.

    Returns False on any verifier error (malformed hash, unknown scheme) so
    callers can treat any failure as an authentication failure without
    branching on exception types.
    """
    try:
        return bcrypt.checkpw(_prep(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
