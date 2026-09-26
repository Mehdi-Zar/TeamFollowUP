"""Password hashing and stateless session tokens.

Two security primitives used across the auth layer:

  * Passwords are hashed with Argon2 (memory-hard, resistant to GPU cracking);
    only the hash is ever stored.
  * Sessions are carried in a signed JWT (HS256) rather than server-side state,
    so the token itself proves identity. The signing key is ``secret_key``;
    tokens expire after ``session_max_age_seconds``.

Revocation: every token carries the account's ``session_version`` ("sv"). The
version moves on logout, on a password, role or status change (see
``models._bump_session_on_sensitive_change``), and a token whose "sv" differs
is refused. A token issued before this existed has no "sv" and reads as 0.
"""
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .config import settings

# One reusable Argon2 hasher with library-default parameters.
_ph = PasswordHasher()

# An impersonation ("view as") session lasts one hour at most.
IMPERSONATION_MAX_AGE_SECONDS = 60 * 60

# Minimum length of a password set in the app (local accounts).
MIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    """Hash a plaintext password with Argon2 for storage.

    The returned string embeds the algorithm, parameters and salt, so it is
    self-describing and safe to store as-is.
    """
    return _ph.hash(password)


# Checked when the account is unknown or has no password, so a failed login
# takes the same time whether the email exists or not (no enumeration by timing).
_DUMMY_HASH = _ph.hash("dummy-password-for-constant-time-login")


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


def burn_verify_time(password: str) -> None:
    """Spend the time of a real password check, for the paths that have none."""
    verify_password(password or "", _DUMMY_HASH)


def validate_password(password: str) -> None:
    """Refuse a password too short to set on an account (HTTP 422)."""
    from fastapi import HTTPException
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=422, detail="Le mot de passe doit faire au moins 12 caractères")


def bump_session(user) -> None:
    """Invalidate every session of ``user`` issued so far (its tokens carry the
    old version). Password, role and status changes do it by themselves (a flush
    listener, see models.py); call this for anything else (logout)."""
    user.session_version = int(getattr(user, "session_version", 0) or 0) + 1


def create_session_token(user_id: int, impersonator_id: int | None = None,
                         session_version: int = 0, impersonator_version: int = 0) -> str:
    """Mint a signed JWT session token identifying ``user_id``.

    The token carries issued-at (iat), expiry (exp) and the account's session
    version (sv). When set, ``impersonator_id`` is embedded as the "imp" claim
    (with the admin's own version as "isv") to record that an admin is acting as
    this user; ``sub`` remains the impersonated user so the app behaves as them.
    An impersonation token lasts one hour at most.
    """
    now = datetime.now(timezone.utc)
    max_age = settings.session_max_age_seconds
    if impersonator_id is not None:
        max_age = min(max_age, IMPERSONATION_MAX_AGE_SECONDS)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=max_age)).timestamp()),
        "sv": int(session_version or 0),
    }
    if impersonator_id is not None:
        payload["imp"] = str(impersonator_id)
        payload["isv"] = int(impersonator_version or 0)
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


def decode_session_claims(token: str) -> dict | None:
    """Verify a session token and return its claims (sub, imp, sv, isv as ints),
    or None on any failure. Missing "sv"/"isv" read as 0 (tokens issued before
    session versions existed stay valid once)."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        imp = payload.get("imp")
        return {"sub": int(payload["sub"]),
                "imp": int(imp) if imp is not None else None,
                "sv": int(payload.get("sv", 0) or 0),
                "isv": int(payload.get("isv", 0) or 0)}
    except Exception:
        return None


def decode_session(token: str) -> tuple[int | None, int | None]:
    """Return (user_id, impersonator_id). impersonator_id is set when an admin is
    viewing the app as another user.

    Like :func:`decode_session_token` but also surfaces the "imp" claim so the
    caller can tell whether the session is an impersonation and by whom. Returns
    ``(None, None)`` on any verification failure.
    """
    claims = decode_session_claims(token)
    if claims is None:
        return None, None
    return claims["sub"], claims["imp"]
