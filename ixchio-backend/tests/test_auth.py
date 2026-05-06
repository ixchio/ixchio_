"""
Auth module tests.
Runs against the in-memory fallback (no mongo needed).
"""

import pytest
from unittest.mock import patch
from pydantic import ValidationError
from auth import (
    signup, login, _hash_pw, _check_pw, _mint_token, _crack_token,
    _check_rate_limit, _login_attempts, _mem_users,
    SignupRequest, LoginRequest,
)
from fastapi import HTTPException


# ---- password hashing ----

def test_bcrypt_roundtrip():
    hashed = _hash_pw("mypassword123")
    assert _check_pw("mypassword123", hashed) is True
    assert _check_pw("wrongpassword", hashed) is False


def test_hash_is_not_plaintext():
    hashed = _hash_pw("secret")
    assert hashed != "secret"
    assert len(hashed) > 20


# ---- jwt ----

def test_mint_and_crack_token():
    token = _mint_token("test@example.com")
    payload = _crack_token(token)
    assert payload["sub"] == "test@example.com"


def test_bad_token_raises():
    with pytest.raises(HTTPException) as exc:
        _crack_token("not.a.real.token")
    assert exc.value.status_code == 401


# ---- input validation ----

def test_invalid_email_rejected():
    with pytest.raises(ValidationError):
        SignupRequest(email="not-an-email", password="password123", name="Test")


def test_short_password_rejected():
    with pytest.raises(ValidationError):
        SignupRequest(email="test@example.com", password="abc", name="Test")


def test_email_normalized():
    req = LoginRequest(email="  Test@Example.COM  ", password="whatever")
    assert req.email == "test@example.com"


# ---- rate limiting ----

def test_rate_limit_allows_normal_usage():
    _login_attempts.clear()
    for _ in range(4):
        _check_rate_limit("normal@test.com")


def test_rate_limit_blocks_spam():
    _login_attempts.clear()
    with pytest.raises(HTTPException) as exc:
        for _ in range(10):
            _check_rate_limit("spammer@test.com")
    assert exc.value.status_code == 429


# ---- signup/login flows (in-memory mode) ----

@pytest.mark.asyncio
async def test_signup_flow():
    _mem_users.clear()

    with patch("auth.get_db", return_value=None):
        result = await signup(SignupRequest(email="new@test.com", password="pass123", name="Tester"))
        assert result.access_token
        assert result.token_type == "bearer"


@pytest.mark.asyncio
async def test_duplicate_signup_rejected():
    _mem_users.clear()

    with patch("auth.get_db", return_value=None):
        await signup(SignupRequest(email="dupe@test.com", password="pass123", name="A"))

        with pytest.raises(HTTPException) as exc:
            await signup(SignupRequest(email="dupe@test.com", password="pass123", name="B"))
        assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_login_flow():
    _mem_users.clear()
    _login_attempts.clear()

    with patch("auth.get_db", return_value=None):
        await signup(SignupRequest(email="login@test.com", password="mypass1", name="X"))
        result = await login(LoginRequest(email="login@test.com", password="mypass1"))
        assert result.access_token


@pytest.mark.asyncio
async def test_login_wrong_password():
    _mem_users.clear()
    _login_attempts.clear()

    with patch("auth.get_db", return_value=None):
        await signup(SignupRequest(email="wrong@test.com", password="correct1", name="X"))

        with pytest.raises(HTTPException) as exc:
            await login(LoginRequest(email="wrong@test.com", password="incorrect"))
        assert exc.value.status_code == 401
