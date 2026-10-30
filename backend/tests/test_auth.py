"""
backend/tests/test_auth.py
Pytest tests for authentication and role-based access control.
Uses httpx.AsyncClient via FastAPI's built-in TestClient (sync).
"""
import os
import sys
import pytest
from fastapi.testclient import TestClient

# ── ensure .env is loaded before importing app ─────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

# ── ensure repo root is on sys.path ───────────────────────────────────────────
from pathlib import Path
ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import app   # noqa: E402 – must be after path fix

# ── Fixture: TestClient ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── Helper ─────────────────────────────────────────────────────────────────────

def login(client, username, password):
    return client.post("/auth/login", json={"username": username, "password": password})


# ══════════════════════════════════════════════════════════════════════════════
# AUTH TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestLogin:
    def test_valid_login_returns_token(self, client):
        r = login(client, "alice", "pass123")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["username"] == "alice"
        assert body["role"] == "Operations Analyst"

    def test_valid_admin_login(self, client):
        r = login(client, "admin", "admin123")
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "Administrator"

    def test_wrong_password_returns_401(self, client):
        r = login(client, "alice", "wrongpassword")
        assert r.status_code == 401
        assert "Incorrect" in r.json()["detail"]

    def test_unknown_user_returns_401(self, client):
        r = login(client, "nobody", "pass123")
        assert r.status_code == 401

    def test_empty_password_returns_401(self, client):
        r = login(client, "alice", "")
        assert r.status_code == 401


class TestGetMe:
    def test_me_returns_identity(self, client):
        token = login(client, "carol", "pass123").json()["access_token"]
        r = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["username"] == "carol"
        assert body["role"] == "Supply Chain Manager"
        assert isinstance(body["id"], int)

    def test_me_without_token_returns_401(self, client):
        r = client.get("/me")
        assert r.status_code == 401

    def test_me_with_invalid_token_returns_401(self, client):
        r = client.get("/me", headers={"Authorization": "Bearer not.a.real.token"})
        assert r.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# ROLE TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestRoleRestriction:
    def _token(self, client, username, password="pass123"):
        return login(client, username, password).json()["access_token"]

    # --- /admin/ping: Administrator only ---

    def test_admin_can_reach_admin_endpoint(self, client):
        token = login(client, "admin", "admin123").json()["access_token"]
        r = client.get("/admin/ping", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text

    def test_non_admin_gets_403_on_admin_endpoint(self, client):
        """Operations Analyst must not reach Administrator-only endpoint."""
        token = self._token(client, "alice")
        r = client.get("/admin/ping", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403
        assert "not authorised" in r.json()["detail"].lower()

    def test_warehouse_operator_gets_403_on_admin_endpoint(self, client):
        token = self._token(client, "dave")
        r = client.get("/admin/ping", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403

    def test_procurement_approver_gets_403_on_admin_endpoint(self, client):
        token = self._token(client, "eve")
        r = client.get("/admin/ping", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403

    # --- /analyst/ping: Operations Analyst + Supply Chain Manager ---

    def test_operations_analyst_can_reach_analyst_endpoint(self, client):
        token = self._token(client, "alice")
        r = client.get("/analyst/ping", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_supply_chain_manager_can_reach_analyst_endpoint(self, client):
        token = self._token(client, "carol")
        r = client.get("/analyst/ping", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_warehouse_operator_gets_403_on_analyst_endpoint(self, client):
        token = self._token(client, "dave")
        r = client.get("/analyst/ping", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403

    def test_no_token_gets_401_on_restricted_endpoint(self, client):
        r = client.get("/admin/ping")
        assert r.status_code == 401
