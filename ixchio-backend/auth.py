"""
Auth — JWT tokens + bcrypt passwords + mongo persistence.

Sign up, get a token, attach it to every request.
Passwords are bcrypt'd. Tokens expire in 24h. Rate limited to
5 login attempts per minute per email.

Falls back to an in-memory dict when mongo isn't available
so you can still dev locally without docker-compose.
"""

import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from collections import defaultdict
from time import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, field_validator

import jwt
import bcrypt

from core.db import get_db

SECRET_KEY = os.getenv("JWT_SECRET") or secrets.token_hex(32)
ALGORITHM = "HS256"
TOKEN_HOURS = 24
MIN_PASSWORD_LEN = 6

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

security = HTTPBearer()

_mem_users: dict = {}
_login_attempts: dict = defaultdict(list)
MAX_LOGIN_PER_MIN = 5


# ---- models ----

class SignupRequest(BaseModel):
    email: str
    password: str
    name: str = ""

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < MIN_PASSWORD_LEN:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LEN} characters")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = TOKEN_HOURS * 3600


class UserInfo(BaseModel):
    email: str
    name: str
    created_at: str


# ---- password ----

def _hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _check_pw(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


# ---- jwt ----

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _mint_token(email: str) -> str:
    now = _now_utc()
    return jwt.encode(
        {"sub": email, "exp": now + timedelta(hours=TOKEN_HOURS), "iat": now},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def _crack_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired — log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Bad token")


# ---- rate limit ----

def _check_rate_limit(email: str):
    now = time()
    _login_attempts[email] = [t for t in _login_attempts[email] if now - t < 60]
    if len(_login_attempts[email]) >= MAX_LOGIN_PER_MIN:
        raise HTTPException(429, "Too many login attempts. Chill for a minute.")
    _login_attempts[email].append(now)


# ---- auth logic ----

async def signup(req: SignupRequest) -> TokenResponse:
    db = get_db()

    if db is not None:
        existing = await db.users.find_one({"email": req.email})
        if existing:
            raise HTTPException(409, "Email already taken")
        await db.users.insert_one({
            "email": req.email,
            "password_hash": _hash_pw(req.password),
            "name": req.name,
            "created_at": _now_utc(),
        })
    else:
        if req.email in _mem_users:
            raise HTTPException(409, "Email already taken")
        _mem_users[req.email] = {
            "password_hash": _hash_pw(req.password),
            "name": req.name,
            "created_at": _now_utc().isoformat(),
        }

    return TokenResponse(access_token=_mint_token(req.email))


async def login(req: LoginRequest) -> TokenResponse:
    _check_rate_limit(req.email)
    db = get_db()

    if db is not None:
        user = await db.users.find_one({"email": req.email})
        if not user or not _check_pw(req.password, user["password_hash"]):
            raise HTTPException(401, "Wrong email or password")
    else:
        user = _mem_users.get(req.email)
        if not user or not _check_pw(req.password, user["password_hash"]):
            raise HTTPException(401, "Wrong email or password")

    return TokenResponse(access_token=_mint_token(req.email))


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    payload = _crack_token(creds.credentials)
    email = payload.get("sub")
    if not email:
        raise HTTPException(401, "Invalid token payload")

    db = get_db()
    if db is not None:
        user = await db.users.find_one({"email": email})
        if not user:
            raise HTTPException(401, "User not found")
    else:
        if email not in _mem_users:
            raise HTTPException(401, "User not found")

    return email


async def get_user_info(email: str) -> Optional[UserInfo]:
    db = get_db()

    if db is not None:
        user = await db.users.find_one({"email": email})
        if not user:
            return None
        ca = user["created_at"]
        return UserInfo(
            email=email,
            name=user.get("name", ""),
            created_at=ca.isoformat() if isinstance(ca, datetime) else str(ca),
        )
    else:
        user = _mem_users.get(email)
        if not user:
            return None
        return UserInfo(email=email, name=user["name"], created_at=user["created_at"])
