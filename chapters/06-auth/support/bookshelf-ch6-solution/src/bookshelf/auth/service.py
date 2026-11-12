import time
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Connection

from bookshelf.auth.tokens import CurrentUser, hash_refresh_token, new_refresh_token


@dataclass(frozen=True)
class UserRecord:
    id: int
    username: str
    password_hash: str | None
    role: str
    github_id: int | None
    email: str | None

    def as_current_user(self) -> CurrentUser:
        return CurrentUser(id=self.id, username=self.username, role=self.role)


_USER_COLUMNS = "id, username, password_hash, role, github_id, email"


def create_user(
    conn: Connection,
    username: str,
    password_hash: str | None,
    *,
    github_id: int | None = None,
    email: str | None = None,
) -> UserRecord:
    # No role parameter: every new account is a "user". Admins are promoted
    # out of band (python -m bookshelf.manage promote <username>).
    row = (
        conn.execute(
            text(
                "INSERT INTO users (username, password_hash, role, github_id, email) "
                "VALUES (:username, :password_hash, 'user', :github_id, :email) "
                "RETURNING id, username, password_hash, role, github_id, email"
            ),
            {
                "username": username,
                "password_hash": password_hash,
                "github_id": github_id,
                "email": email,
            },
        )
        .mappings()
        .one()
    )
    conn.commit()
    return UserRecord(**row)


def _get_user_by(conn: Connection, column: str, value: object) -> UserRecord | None:
    row = (
        conn.execute(
            text(f"SELECT {_USER_COLUMNS} FROM users WHERE {column} = :value"),  # noqa: S608
            {"value": value},
        )
        .mappings()
        .first()
    )
    return UserRecord(**row) if row else None


def get_user_by_id(conn: Connection, user_id: int) -> UserRecord | None:
    return _get_user_by(conn, "id", user_id)


def get_user_by_username(conn: Connection, username: str) -> UserRecord | None:
    return _get_user_by(conn, "username", username)


def get_user_by_github_id(conn: Connection, github_id: int) -> UserRecord | None:
    return _get_user_by(conn, "github_id", github_id)


def set_role(conn: Connection, username: str, role: str) -> bool:
    result = conn.execute(
        text("UPDATE users SET role = :role WHERE username = :username"),
        {"role": role, "username": username},
    )
    conn.commit()
    return result.rowcount > 0


def get_or_create_github_user(
    conn: Connection, github_id: int, login: str, email: str | None
) -> UserRecord:
    user = get_user_by_github_id(conn, github_id)
    if user is not None:
        return user
    # The "github:" prefix cannot collide with a registered username, because
    # registration only allows [a-z0-9_-].
    return create_user(
        conn, f"github:{login.lower()}", None, github_id=github_id, email=email
    )


# ---------------------------------------------------------------------------
# Refresh tokens
# ---------------------------------------------------------------------------


def issue_refresh_token(conn: Connection, user_id: int, ttl_days: int) -> str:
    token, token_hash = new_refresh_token()
    conn.execute(
        text(
            "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) "
            "VALUES (:user_id, :token_hash, :expires_at)"
        ),
        {
            "user_id": user_id,
            "token_hash": token_hash,
            "expires_at": int(time.time()) + ttl_days * 86400,
        },
    )
    conn.commit()
    return token


def rotate_refresh_token(
    conn: Connection, token: str, ttl_days: int
) -> tuple[UserRecord, str] | None:
    """Exchange a refresh token for a new one. The old token stops working.

    Returns None if the token is unknown, expired, or already used. Presenting
    an already-used token revokes every refresh token of that user: either the
    client has a bug or the token was stolen, and we cannot tell which.
    """
    row = (
        conn.execute(
            text(
                "SELECT id, user_id, expires_at, revoked FROM refresh_tokens "
                "WHERE token_hash = :token_hash"
            ),
            {"token_hash": hash_refresh_token(token)},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    if row["revoked"]:
        revoke_all_refresh_tokens(conn, row["user_id"])
        return None
    if row["expires_at"] < time.time():
        return None

    # Conditional UPDATE: of two concurrent requests with the same token,
    # only one can flip revoked from false to true.
    result = conn.execute(
        text(
            "UPDATE refresh_tokens SET revoked = true "
            "WHERE id = :id AND revoked = false"
        ),
        {"id": row["id"]},
    )
    conn.commit()
    if result.rowcount != 1:
        return None

    user = get_user_by_id(conn, row["user_id"])
    if user is None:
        return None
    return user, issue_refresh_token(conn, user.id, ttl_days)


def revoke_refresh_token(conn: Connection, token: str) -> None:
    conn.execute(
        text("UPDATE refresh_tokens SET revoked = true WHERE token_hash = :token_hash"),
        {"token_hash": hash_refresh_token(token)},
    )
    conn.commit()


def revoke_all_refresh_tokens(conn: Connection, user_id: int) -> None:
    conn.execute(
        text("UPDATE refresh_tokens SET revoked = true WHERE user_id = :user_id"),
        {"user_id": user_id},
    )
    conn.commit()
