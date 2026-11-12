import time

import pytest
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from bookshelf.auth import service


def test_create_user_defaults_to_user_role(db_conn: Connection) -> None:
    user = service.create_user(db_conn, "alice", "hash")
    assert user.role == "user"
    assert service.get_user_by_username(db_conn, "alice") == user


def test_duplicate_username_rejected(db_conn: Connection) -> None:
    service.create_user(db_conn, "alice", "hash")
    with pytest.raises(IntegrityError):
        service.create_user(db_conn, "alice", "other-hash")


def test_set_role(db_conn: Connection) -> None:
    service.create_user(db_conn, "alice", "hash")
    assert service.set_role(db_conn, "alice", "admin") is True
    user = service.get_user_by_username(db_conn, "alice")
    assert user is not None and user.role == "admin"


def test_set_role_unknown_user(db_conn: Connection) -> None:
    assert service.set_role(db_conn, "nobody", "admin") is False


def test_github_user_created_once(db_conn: Connection) -> None:
    first = service.get_or_create_github_user(db_conn, 583231, "Octocat", None)
    second = service.get_or_create_github_user(db_conn, 583231, "octocat", None)
    assert first == second
    assert first.username == "github:octocat"
    assert first.password_hash is None


def test_refresh_rotation(db_conn: Connection) -> None:
    user = service.create_user(db_conn, "alice", "hash")
    token = service.issue_refresh_token(db_conn, user.id, ttl_days=7)

    rotated = service.rotate_refresh_token(db_conn, token, ttl_days=7)

    assert rotated is not None
    rotated_user, new_token = rotated
    assert rotated_user.id == user.id
    assert new_token != token


def test_unknown_refresh_token(db_conn: Connection) -> None:
    assert service.rotate_refresh_token(db_conn, "not-a-token", ttl_days=7) is None


def test_expired_refresh_token(db_conn: Connection) -> None:
    user = service.create_user(db_conn, "alice", "hash")
    token = service.issue_refresh_token(db_conn, user.id, ttl_days=-1)
    assert service.rotate_refresh_token(db_conn, token, ttl_days=7) is None


def test_reuse_revokes_whole_family(db_conn: Connection) -> None:
    user = service.create_user(db_conn, "alice", "hash")
    stolen = service.issue_refresh_token(db_conn, user.id, ttl_days=7)
    rotated = service.rotate_refresh_token(db_conn, stolen, ttl_days=7)
    assert rotated is not None
    _, legit = rotated

    # The old token is presented again (by the thief, or by the user).
    assert service.rotate_refresh_token(db_conn, stolen, ttl_days=7) is None
    # Every token of the user is now dead, including the legitimate one.
    assert service.rotate_refresh_token(db_conn, legit, ttl_days=7) is None


def test_revoke_refresh_token(db_conn: Connection) -> None:
    user = service.create_user(db_conn, "alice", "hash")
    token = service.issue_refresh_token(db_conn, user.id, ttl_days=7)
    service.revoke_refresh_token(db_conn, token)
    assert service.rotate_refresh_token(db_conn, token, ttl_days=7) is None


def test_refresh_token_stored_hashed(db_conn: Connection) -> None:
    user = service.create_user(db_conn, "alice", "hash")
    token = service.issue_refresh_token(db_conn, user.id, ttl_days=7)
    rows = db_conn.exec_driver_sql("SELECT token_hash, expires_at FROM refresh_tokens")
    token_hash, expires_at = rows.one()
    assert token_hash != token
    assert abs(expires_at - (time.time() + 7 * 86400)) < 5
