"""Password hashing and stateless session tokens.

Two security primitives used across the auth layer:

  * Passwords are hashed with Argon2 (memory-hard, resistant to GPU cracking);
    only the hash is ever stored.
  * Sessions are carried in a signed JWT (HS256) rather than server-side state,
    so the token itself proves identity. The signing key is ``secret_key``;
    tokens expire after ``session_max_age_seconds``.
"""
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .config import settings

# One reusable Argon2 hasher with library-default parameters.
_ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a plaintext password with Argon2 for storage.

    The returned string embeds the algorithm, parameters and salt, so it is
    self-describing and safe to store as-is.
    """
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return True iff ``password`` matches the stored Argon2 ``password_hash``.

    Fails closed: a mismatch, or any unexpected error (e.g. a malformed/legacy
    hash), returns False rather than raising, so a broken hash can never be
    mistaken for a successful authentication.
    """
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        # Any other failure (corrupt hash, unsupported format) is treated as a
        # non-match on purpose - never leak the reason and never let it through.
        return False


def create_session_token(user_id: int, impersonator_id: int | None = None) -> str:
    """Mint a signed JWT session token identifying ``user_id``.

    The token carries issued-at (iat) and expiry (exp) claims. When set,
    ``impersonator_id`` is embedded as the "imp" claim to record that an admin
    is acting as this user (admin "view as" feature), while ``sub`` remains the
    impersonated user so the app behaves as them.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.session_max_age_seconds)).timestamp()),
    }
    if impersonator_id is not None:
        payload["imp"] = str(impersonator_id)
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_session_token(token: str) -> int | None:
    """Verify a session token and return its user id, or None if invalid.

    Returns None on any failure (bad signature, expired, malformed) so callers
    treat every non-authentic token as "not logged in".
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return int(payload["sub"])
    except Exception:
        return None


def decode_session(token: str) -> tuple[int | None, int | None]:
    """Return (user_id, impersonator_id). impersonator_id is set when an admin is
    viewing the app as another user.

    Like :func:`decode_session_token` but also surfaces the "imp" claim so the
    caller can tell whether the session is an impersonation and by whom. Returns
    ``(None, None)`` on any verification failure.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        imp = payload.get("imp")
        return int(payload["sub"]), (int(imp) if imp is not None else None)
    except Exception:
        return None, None
