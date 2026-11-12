from datetime import UTC, datetime, timedelta

import jwt
import pytest

from bookshelf.auth.tokens import (
    CurrentUser,
    create_access_token,
    decode_access_token,
    hash_refresh_token,
    new_refresh_token,
)
from tests.conftest import TEST_JWT_SECRET

ALICE = CurrentUser(id=42, username="alice", role="user")


def test_round_trip() -> None:
    token = create_access_token(ALICE)
    assert decode_access_token(token) == ALICE


def test_payload_contains_standard_claims() -> None:
    token = create_access_token(ALICE)
    # Anyone can read the payload without the key: signed, not encrypted.
    payload = jwt.decode(token, options={"verify_signature": False})
    assert payload["sub"] == "42"
    assert payload["iss"] == "bookshelf"
    assert payload["aud"] == "bookshelf-api"
    assert payload["exp"] - payload["iat"] == 15 * 60


def test_expired_token_rejected() -> None:
    token = create_access_token(ALICE, expires_delta=timedelta(seconds=-1))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_wrong_secret_rejected() -> None:
    token = jwt.encode(
        {"sub": "42", "username": "alice", "role": "admin"},
        "an-attacker-chosen-secret-of-32-chars!!",
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token)


def test_tampered_payload_rejected() -> None:
    header, _payload, signature = create_access_token(ALICE).split(".")
    forged_payload = jwt.utils.base64url_encode(
        b'{"sub":"42","username":"alice","role":"admin"}'
    ).decode()
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(f"{header}.{forged_payload}.{signature}")


def test_alg_none_rejected() -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "42",
            "username": "alice",
            "role": "admin",
            "iss": "bookshelf",
            "aud": "bookshelf-api",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        key=None,
        algorithm="none",
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)


def test_wrong_audience_rejected() -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "42",
            "username": "alice",
            "role": "user",
            "iss": "bookshelf",
            "aud": "some-other-service",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidAudienceError):
        decode_access_token(token)


def test_missing_exp_rejected() -> None:
    token = jwt.encode(
        {
            "sub": "42",
            "username": "alice",
            "role": "user",
            "iss": "bookshelf",
            "aud": "bookshelf-api",
            "iat": datetime.now(UTC),
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_access_token(token)


def test_refresh_token_hash() -> None:
    token, digest = new_refresh_token()
    assert len(token) >= 43
    assert digest == hash_refresh_token(token)
    assert token not in digest
