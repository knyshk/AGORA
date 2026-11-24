"""Minimal authentication for collaborative sessions: email + password (argon2), JWT bearer tokens.

JWT_SECRET must be set in backend/.env for anything beyond local development; without it a
development-only secret is used and a warning is printed.
"""
import os
import re
import time

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from db.database import SessionLocal
from db.models import User

JWT_ALGORITHM = "HS256"
TOKEN_TTL_S = 12 * 3600
MIN_PASSWORD = 8
_DEV_SECRET = "agora-development-only-secret-change-me-in-env"  # 32+ bytes
_hasher = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)


_warned = []


def jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        if not _warned:
            print("[AUTH] JWT_SECRET not set; using the development secret (do not deploy like this)")
            _warned.append(True)
        return _DEV_SECRET
    return secret


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerificationError:
        return False


def create_token(user_id: str, ttl_s: int = TOKEN_TTL_S) -> str:
    now = int(time.time())
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + ttl_s}, jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> str:
    try:
        return jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])["sub"]
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {type(e).__name__}")


def public_user(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name}


def register(email: str, password: str, name: str) -> User:
    email = (email or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    if len(password or "") < MIN_PASSWORD:
        raise HTTPException(status_code=422, detail=f"Password must be at least {MIN_PASSWORD} characters")
    with SessionLocal() as s:
        if s.scalar(select(User).where(User.email == email)):
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        user = User(email=email, name=(name or email.split("@")[0]).strip()[:80], password_hash=hash_password(password))
        s.add(user)
        s.commit()
        return user


def login(email: str, password: str) -> User:
    with SessionLocal() as s:
        user = s.scalar(select(User).where(User.email == (email or "").strip().lower()))
    if not user or not verify_password(user.password_hash, password or ""):
        raise HTTPException(status_code=401, detail="Wrong email or password")
    return user


def user_from_token(token: str) -> User:
    user_id = decode_token(token)
    with SessionLocal() as s:
        user = s.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user


def current_user(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> User:
    if creds is None:
        raise HTTPException(status_code=401, detail="Log in first (missing bearer token)")
    return user_from_token(creds.credentials)
