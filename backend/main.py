"""
backend/main.py
FastAPI application entry point.
"""
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load .env before any module reads os.getenv
load_dotenv()

from backend.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    require_role,
)

# ── App setup ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast at startup if JWT_SECRET is missing
    from backend.auth import _secret
    _secret()
    yield

app = FastAPI(
    title="DisruptionIQ API",
    description="Logistics disruption detection and recovery platform.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # tighten for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class MeResponse(BaseModel):
    id: int
    username: str
    role: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def login(body: LoginRequest):
    """
    Authenticate with username + password.
    Returns a signed JWT valid for 12 hours.
    """
    user  = authenticate_user(body.username, body.password)
    token = create_access_token(user["id"], user["username"], user["role"])
    return TokenResponse(
        access_token=token,
        username=user["username"],
        role=user["role"],
    )


@app.get("/me", response_model=MeResponse, tags=["auth"])
def me(user: dict = Depends(get_current_user)):
    """Return the currently authenticated user's identity."""
    return MeResponse(id=int(user["sub"]), username=user["username"], role=user["role"])


# ── Role-restricted example endpoints (used in tests) ─────────────────────────

@app.get("/admin/ping", tags=["admin"])
def admin_ping(user: dict = Depends(require_role("Administrator"))):
    """Reachable only by Administrator role."""
    return {"message": f"Hello, {user['username']}! Admin area."}


@app.get("/analyst/ping", tags=["analyst"])
def analyst_ping(
    user: dict = Depends(require_role("Operations Analyst", "Supply Chain Manager"))
):
    """Reachable by Operations Analyst or Supply Chain Manager."""
    return {"message": f"Hello, {user['username']}!"}
