
import hashlib
import os
import secrets
import uuid

from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash


password_hasher = PasswordHash.recommended()

# A dummy hash makes failed login attempts perform password
# verification even when the submitted email does not exist.
DUMMY_PASSWORD_HASH = password_hasher.hash(
    "agora-dummy-password-not-used"
)

JWT_ALGORITHM = "HS256"


def get_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY")

    if not secret or len(secret) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY is missing or too short. "
            "Configure a strong secret in backend/.env."
        )

    return secret


def get_access_token_expiry_minutes() -> int:
    return int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
    )


def get_refresh_token_expiry_days() -> int:
    return int(
        os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "14")
    )


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    try:
        return password_hasher.verify(
            plain_password,
            hashed_password,
        )
    except Exception:
        return False


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def create_access_token(
    user_id: uuid.UUID,
    session_id: uuid.UUID,
) -> str:
    now = datetime.now(timezone.utc)

    expires_at = now + timedelta(
        minutes=get_access_token_expiry_minutes()
    )

    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": str(uuid.uuid4()),
    }

    return jwt.encode(
        payload,
        get_jwt_secret(),
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        get_jwt_secret(),
        algorithms=[JWT_ALGORITHM],
        options={
            "require": [
                "sub",
                "sid",
                "type",
                "iat",
                "exp",
            ]
        },
    )
