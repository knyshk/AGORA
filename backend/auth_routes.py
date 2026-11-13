
import os
import uuid

from datetime import datetime, timedelta, timezone

import jwt

from email_validator import EmailNotValidError
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import JSONResponse
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from pydantic import BaseModel, EmailStr, Field

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db

from models import (
    AuthSession,
    Conversation,
    Message,
    User,
    Workspace,
    WorkspaceMember,
)

from security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    get_access_token_expiry_minutes,
    get_refresh_token_expiry_days,
    hash_password,
    hash_refresh_token,
    verify_password,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

bearer_scheme = HTTPBearer(auto_error=False)

REFRESH_COOKIE_NAME = "agora_refresh"


# ---------------------------------------------------------
# Request and response schemas
# ---------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr

    password: str = Field(
        min_length=12,
        max_length=128,
    )

    full_name: str | None = Field(
        default=None,
        max_length=120,
    )


class LoginRequest(BaseModel):
    email: EmailStr

    password: str = Field(
        min_length=1,
        max_length=128,
    )


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_verified: bool
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
    workspace: WorkspaceResponse


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ---------------------------------------------------------
# Cookie configuration
# ---------------------------------------------------------


def cookie_secure() -> bool:
    return (
        os.getenv("AUTH_COOKIE_SECURE", "false").lower()
        == "true"
    )


def set_refresh_cookie(
    response: Response,
    token: str,
):
    max_age = (
        get_refresh_token_expiry_days()
        * 24
        * 60
        * 60
    )

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )


def clear_refresh_cookie(response: Response):
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
    )


def refresh_error(detail: str) -> JSONResponse:
    response = JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": detail},
    )

    clear_refresh_cookie(response)
    return response


# ---------------------------------------------------------
# Session helpers
# ---------------------------------------------------------


def create_refresh_session(
    db: Session,
    user_id: uuid.UUID,
    family_id: uuid.UUID | None = None,
):
    raw_token = generate_refresh_token()

    session = AuthSession(
        user_id=user_id,
        family_id=family_id or uuid.uuid4(),
        token_hash=hash_refresh_token(raw_token),
        expires_at=(
            datetime.now(timezone.utc)
            + timedelta(
                days=get_refresh_token_expiry_days()
            )
        ),
    )

    db.add(session)
    db.flush()

    return raw_token, session


def create_auth_response(
    user: User,
    workspace: Workspace,
    session: AuthSession,
    raw_refresh_token: str,
    response: Response,
) -> AuthResponse:
    set_refresh_cookie(
        response,
        raw_refresh_token,
    )

    access_token = create_access_token(
        user.id,
        session.id,
    )

    return AuthResponse(
        access_token=access_token,
        expires_in=(
            get_access_token_expiry_minutes() * 60
        ),
        user=UserResponse.model_validate(user),
        workspace=WorkspaceResponse.model_validate(
            workspace
        ),
    )


# ---------------------------------------------------------
# Current user dependency
# ---------------------------------------------------------


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme.",
        )

    try:
        payload = decode_access_token(
            credentials.credentials
        )

        if payload.get("type") != "access":
            raise ValueError("Invalid token type.")

        user_id = uuid.UUID(payload["sub"])
        session_id = uuid.UUID(payload["sid"])

    except (
        jwt.InvalidTokenError,
        ValueError,
        KeyError,
        TypeError,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_session = db.get(
        AuthSession,
        session_id,
    )

    now = datetime.now(timezone.utc)

    if (
        auth_session is None
        or auth_session.user_id != user_id
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is invalid or expired.",
        )

    user = db.get(User, user_id)

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is unavailable.",
        )

    return user


# ---------------------------------------------------------
# Registration
# ---------------------------------------------------------


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    email = str(payload.email).strip().lower()

    existing_user = db.scalar(
        select(User).where(
            func.lower(User.email) == email
        )
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    full_name = (
        payload.full_name.strip()
        if payload.full_name
        else None
    )

    if full_name == "":
        full_name = None

    user = User(
        email=email,
        password_hash=hash_password(
            payload.password
        ),
        full_name=full_name,
        is_active=True,
        is_verified=False,
    )

    try:
        db.add(user)
        db.flush()

        workspace_name = (
            f"{full_name}'s workspace"
            if full_name
            else f"{email.split('@')[0]}'s workspace"
        )

        workspace = Workspace(
            name=workspace_name,
            owner_id=user.id,
        )

        db.add(workspace)
        db.flush()

        membership = WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role="owner",
        )

        db.add(membership)

        raw_refresh_token, session = (
            create_refresh_session(
                db,
                user.id,
            )
        )

        db.commit()

        db.refresh(user)
        db.refresh(workspace)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    except Exception:
        db.rollback()
        raise

    return create_auth_response(
        user,
        workspace,
        session,
        raw_refresh_token,
        response,
    )


# ---------------------------------------------------------
# Login
# ---------------------------------------------------------


@router.post(
    "/login",
    response_model=AuthResponse,
)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    email = str(payload.email).strip().lower()

    user = db.scalar(
        select(User).where(
            func.lower(User.email) == email
        )
    )

    password_to_check = (
        user.password_hash
        if user is not None
        else DUMMY_PASSWORD_HASH
    )

    password_valid = verify_password(
        payload.password,
        password_to_check,
    )

    if (
        user is None
        or not password_valid
        or not user.is_active
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    workspace = db.scalar(
        select(Workspace)
        .where(Workspace.owner_id == user.id)
        .order_by(Workspace.created_at)
        .limit(1)
    )

    # Supports accounts created before workspace onboarding.
    if workspace is None:
        workspace = Workspace(
            name=f"{email.split('@')[0]}'s workspace",
            owner_id=user.id,
        )

        db.add(workspace)
        db.flush()

        db.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                role="owner",
            )
        )

    raw_refresh_token, session = (
        create_refresh_session(
            db,
            user.id,
        )
    )

    db.commit()
    db.refresh(user)
    db.refresh(workspace)

    return create_auth_response(
        user,
        workspace,
        session,
        raw_refresh_token,
        response,
    )


# ---------------------------------------------------------
# Refresh token rotation
# ---------------------------------------------------------


@router.post(
    "/refresh",
    response_model=TokenResponse,
)
def refresh_access_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    raw_token = request.cookies.get(
        REFRESH_COOKIE_NAME
    )

    if not raw_token:
        return refresh_error(
            "Refresh token is missing."
        )

    token_hash = hash_refresh_token(raw_token)

    session = db.scalar(
        select(AuthSession)
        .where(
            AuthSession.token_hash == token_hash
        )
        .with_for_update()
    )

    if session is None:
        return refresh_error(
            "Refresh token is invalid."
        )

    now = datetime.now(timezone.utc)

    # Reuse of a revoked refresh token is treated as
    # a possible token theft. Revoke the whole family.
    if session.revoked_at is not None:
        db.execute(
            update(AuthSession)
            .where(
                AuthSession.family_id == session.family_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

        db.commit()

        return refresh_error(
            "Refresh token reuse detected. Please log in again."
        )

    if session.expires_at <= now:
        session.revoked_at = now
        db.commit()

        return refresh_error(
            "Refresh token has expired."
        )

    user = db.get(
        User,
        session.user_id,
    )

    if user is None or not user.is_active:
        session.revoked_at = now
        db.commit()

        return refresh_error(
            "User account is unavailable."
        )

    old_family_id = session.family_id

    session.revoked_at = now
    session.last_used_at = now

    new_raw_token, new_session = (
        create_refresh_session(
            db,
            user.id,
            family_id=old_family_id,
        )
    )

    db.commit()

    set_refresh_cookie(
        response,
        new_raw_token,
    )

    access_token = create_access_token(
        user.id,
        new_session.id,
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=(
            get_access_token_expiry_minutes() * 60
        ),
    )


# ---------------------------------------------------------
# Logout
# ---------------------------------------------------------


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    raw_token = request.cookies.get(
        REFRESH_COOKIE_NAME
    )

    if raw_token:
        token_hash = hash_refresh_token(raw_token)

        session = db.scalar(
            select(AuthSession)
            .where(
                AuthSession.token_hash == token_hash
            )
            .with_for_update()
        )

        if session is not None:
            if session.revoked_at is None:
                session.revoked_at = datetime.now(
                    timezone.utc
                )

            db.commit()

    clear_refresh_cookie(response)

    return {
        "status": "logged_out",
    }


# ---------------------------------------------------------
# Current authenticated user
# ---------------------------------------------------------


@router.get(
    "/me",
    response_model=UserResponse,
)
def read_current_user(
    current_user: User = Depends(get_current_user),
):
    return current_user

