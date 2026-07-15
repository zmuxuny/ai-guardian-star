"""Small, dependency-free security helpers used by the ECS account service."""

import base64
import hashlib
import hmac
import secrets


_SCHEME = "scrypt"
_N = 1 << 14
_R = 8
_P = 1
_DKLEN = 32
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Return a versioned, salted scrypt password verifier."""
    if not isinstance(password, str) or not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN
    )
    salt_text = base64.b64encode(salt).decode("ascii")
    digest_text = base64.b64encode(digest).decode("ascii")
    return f"{_SCHEME}${_N}${_R}${_P}${salt_text}${digest_text}"


def verify_password(stored: str, candidate: str) -> bool:
    """Verify current scrypt values and legacy plaintext values during migration."""
    if not isinstance(stored, str) or not isinstance(candidate, str) or not stored or not candidate:
        return False
    if not stored.startswith(f"{_SCHEME}$"):
        return hmac.compare_digest(stored.encode("utf-8"), candidate.encode("utf-8"))

    try:
        scheme, n_text, r_text, p_text, salt_text, digest_text = stored.split("$", 5)
        n, r, p = int(n_text), int(r_text), int(p_text)
        if scheme != _SCHEME or n < 2 or n > (1 << 20) or r < 1 or r > 32 or p < 1 or p > 16:
            return False
        salt = base64.b64decode(salt_text, validate=True)
        expected = base64.b64decode(digest_text, validate=True)
        if not salt or not expected:
            return False
        actual = hashlib.scrypt(
            candidate.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(expected)
        )
        return hmac.compare_digest(expected, actual)
    except (ValueError, TypeError, MemoryError):
        return False


def password_needs_rehash(stored: str) -> bool:
    """Tell the login path when a legacy or outdated verifier should be replaced."""
    prefix = f"{_SCHEME}${_N}${_R}${_P}$"
    return not isinstance(stored, str) or not stored.startswith(prefix)
