import pytest
from sqlalchemy.engine import Connection, Engine

from bookshelf import manage
from bookshelf.auth import service


@pytest.fixture
def app_db(db_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("bookshelf.database._engine", db_engine)


def test_promote(app_db: None, db_conn: Connection, capsys) -> None:  # type: ignore[no-untyped-def]
    service.create_user(db_conn, "alice", "hash")
    assert manage.main(["promote", "alice"]) == 0
    assert "alice is now admin" in capsys.readouterr().out
    user = service.get_user_by_username(db_conn, "alice")
    assert user is not None and user.role == "admin"


def test_promote_unknown_user(app_db: None, capsys) -> None:  # type: ignore[no-untyped-def]
    assert manage.main(["promote", "nobody"]) == 1
    assert "no user named 'nobody'" in capsys.readouterr().err
