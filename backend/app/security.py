from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .config import settings

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def create_session_token(user_id: int, impersonator_id: int | None = None) -> str:
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
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return int(payload["sub"])
    except Exception:
        return None


def decode_session(token: str) -> tuple[int | None, int | None]:
    """Return (user_id, impersonator_id). impersonator_id is set when an admin is
    viewing the app as another user."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        imp = payload.get("imp")
        return int(payload["sub"]), (int(imp) if imp is not None else None)
    except Exception:
        return None, None
