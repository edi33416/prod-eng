import secrets
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from bookshelf.auth import github
from bookshelf.auth import service as auth_service
from bookshelf.auth.config import get_settings
from bookshelf.auth.dependencies import AuthenticatedUser
from bookshelf.auth.passwords import hash_password, verify_password
from bookshelf.auth.rate_limit import login_rate_limit
from bookshelf.auth.service import UserRecord
from bookshelf.auth.tokens import create_access_token
from bookshelf.database import get_connection
from bookshelf.models import (
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_STATE_COOKIE = "oauth_state"


def _issue_tokens(conn: Connection, user: UserRecord) -> TokenResponse:
    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(user.as_current_user()),
        refresh_token=auth_service.issue_refresh_token(
            conn, user.id, settings.refresh_token_days
        ),
        expires_in=settings.access_token_minutes * 60,
    )


@router.post("/register", response_model=UserResponse, status_code=201)
def register(body: UserCreate) -> UserResponse:
    with get_connection() as conn:
        try:
            user = auth_service.create_user(
                conn, body.username, hash_password(body.password.get_secret_value())
            )
        except IntegrityError:
            raise HTTPException(
                status_code=409, detail="Username already taken"
            ) from None
    return UserResponse(id=user.id, username=user.username, role=user.role)


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(login_rate_limit)],
)
def login(body: LoginRequest) -> TokenResponse:
    with get_connection() as conn:
        user = auth_service.get_user_by_username(conn, body.username)
        # Same message, and the same amount of hashing work, whether the user
        # does not exist or the password is wrong.
        password_hash = user.password_hash if user else None
        password = body.password.get_secret_value()
        if not verify_password(password, password_hash) or user is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return _issue_tokens(conn, user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest) -> TokenResponse:
    settings = get_settings()
    with get_connection() as conn:
        rotated = auth_service.rotate_refresh_token(
            conn, body.refresh_token, settings.refresh_token_days
        )
        if rotated is None:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        user, new_refresh = rotated
        # The user is re-read from the database, so a role change or a
        # deleted account takes effect here, at the latest one access-token
        # lifetime after it happened.
        return TokenResponse(
            access_token=create_access_token(user.as_current_user()),
            refresh_token=new_refresh,
            expires_in=settings.access_token_minutes * 60,
        )


@router.post("/logout", status_code=204)
def logout(body: RefreshRequest) -> None:
    with get_connection() as conn:
        auth_service.revoke_refresh_token(conn, body.refresh_token)


@router.get("/me", response_model=UserResponse)
def me(user: AuthenticatedUser) -> UserResponse:
    return UserResponse(id=user.id, username=user.username, role=user.role)


# ---------------------------------------------------------------------------
# GitHub OAuth 2.0 (authorization code flow)
# ---------------------------------------------------------------------------


@router.get("/github")
def github_login() -> RedirectResponse:
    settings = get_settings()
    if not settings.github_client_id:
        raise HTTPException(status_code=503, detail="GitHub login is not configured")
    state = secrets.token_urlsafe(32)
    response = RedirectResponse(
        github.authorization_url(
            settings.github_client_id, settings.github_redirect_uri, state
        )
    )
    # The browser keeps the state in a cookie only our site can read; the
    # callback checks that GitHub sent the same value back.
    response.set_cookie(
        _STATE_COOKIE,
        state,
        max_age=600,
        path="/auth/github",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return response


@router.get("/github/callback", response_model=TokenResponse)
def github_callback(
    code: str,
    state: str,
    response: Response,
    oauth_state: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    settings = get_settings()
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(status_code=503, detail="GitHub login is not configured")
    if oauth_state is None or not secrets.compare_digest(state, oauth_state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    response.delete_cookie(_STATE_COOKIE, path="/auth/github")

    try:
        gh_user = github.exchange_code(
            code,
            settings.github_client_id,
            settings.github_client_secret,
            settings.github_redirect_uri,
        )
    except github.GitHubOAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    with get_connection() as conn:
        user = auth_service.get_or_create_github_user(
            conn, gh_user.id, gh_user.login, gh_user.email
        )
        return _issue_tokens(conn, user)
