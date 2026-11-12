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
    # TODO(ch6): Hash the password, create the user, 409 on duplicate username.
    raise NotImplementedError


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(login_rate_limit)],
)
def login(body: LoginRequest) -> TokenResponse:
    # TODO(ch6): Look up the user, verify the password (same 401 for unknown
    # user and wrong password), return _issue_tokens(conn, user).
    raise NotImplementedError


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest) -> TokenResponse:
    # TODO(ch6): rotate_refresh_token; 401 "Invalid refresh token" on None;
    # return a new access token AND the new refresh token.
    raise NotImplementedError


@router.post("/logout", status_code=204)
def logout(body: RefreshRequest) -> None:
    # TODO(ch6): Revoke the refresh token.
    raise NotImplementedError


@router.get("/me", response_model=UserResponse)
def me(user: AuthenticatedUser) -> UserResponse:
    return UserResponse(id=user.id, username=user.username, role=user.role)


# ---------------------------------------------------------------------------
# GitHub OAuth 2.0 (authorization code flow)
# ---------------------------------------------------------------------------


@router.get("/github")
def github_login() -> RedirectResponse:
    # TODO(ch6): Random state -> HttpOnly, SameSite=Lax cookie; redirect to
    # github.authorization_url(...).
    raise NotImplementedError


@router.get("/github/callback", response_model=TokenResponse)
def github_callback(
    code: str,
    state: str,
    response: Response,
    oauth_state: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    # TODO(ch6): Compare the state parameter with the cookie
    # (secrets.compare_digest), exchange the code, get_or_create_github_user,
    # return _issue_tokens(conn, user).
    raise NotImplementedError
