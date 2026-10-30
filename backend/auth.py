"""
backend/auth.py
JWT authentication + role-based access control.

Tokens are HS256 JWTs signed with JWT_SECRET from the environment.
Payload: { "sub": str(user_id), "role": role, "username": username, "exp": ... }
"""
import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from backend.db import get_conn

# ── Config ─────────────────────────────────────────────────────────────────────

ALGORITHM       = "HS256"
TOKEN_EXPIRE_H  = 12          # hours

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def _secret() -> str:
    secret = os.getenv("JWT_SECRET", "").strip()
    if not secret:
        raise RuntimeError(
            "JWT_SECRET is not set. Add it to your .env file and restart."
        )
    return secret


# ── Password helpers ────────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── Token helpers ───────────────────────────────────────────────────────────────

def create_access_token(user_id: int, username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_H)
    payload = {
        "sub":      str(user_id),
        "username": username,
        "role":     role,
        "exp":      expire,
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Raises HTTPException 401 on any decode / expiry failure."""
    try:
        return jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── FastAPI dependencies ────────────────────────────────────────────────────────

VALID_ROLES = {
    "Operations Analyst",
    "Supply Chain Manager",
    "Warehouse Operator",
    "Procurement Approver",
    "Administrator",
}


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """
    Validates the Bearer token and returns the decoded payload dict:
      {"sub": "1", "username": "alice", "role": "Operations Analyst", ...}
    Raises 401 if token is missing or invalid.
    Raises 403 if user role is not in VALID_ROLES (Hard Rule 3).
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = decode_token(credentials.credentials)
    if user.get("role") not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{user.get('role')}' is not authorized. Must be one of: {sorted(VALID_ROLES)}",
        )
    return user


def require_role(*roles: str):
    """
    Dependency factory.  Usage:

        @router.get("/admin-only")
        def admin_only(user=Depends(require_role("Administrator"))):
            ...

    Returns 403 if the authenticated user's role is not in the allowed set.
    """
    def _check(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user['role']}' is not authorised for this endpoint. "
                       f"Required: {list(roles)}",
            )
        return user
    return _check


# ── Login logic (used by the /auth/login route) ─────────────────────────────────

def authenticate_user(username: str, password: str) -> dict:
    """
    Looks up the user by username, verifies the bcrypt password.
    Returns the DB row as a dict on success.
    Raises 401 on failure (deliberately vague message to prevent enumeration).
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, username, email, password_hash, role, is_active "
            "FROM users WHERE username = ? OR email = ?",
            (username, username),
        ).fetchone()
    finally:
        conn.close()

    if row is None or not verify_password(password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled.",
        )
    return dict(row)
