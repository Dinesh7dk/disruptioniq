"""
backend/tests/test_demo.py

Tests for Demo-only endpoints:
- POST /demo/reset
- POST /demo/scenario/{scenario_id}
- GET /demo/status

Enforces Hard Rule 13:
- Works ONLY when DEMO_MODE=true in .env / environment.
- Works ONLY for Administrator role.
- All other roles and states return 401/403.
"""
import sys
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import app
from backend.seed.seed import seed as _do_seed
from backend.db import get_conn


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _token(client, username="admin", password=None):
    if password is None:
        password = "admin123" if username == "admin" else "pass123"
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestDemoEndpoints:
    def test_demo_status_endpoint(self, client):
        token_admin = _token(client, "admin")
        res = client.get("/demo/status", headers=_auth(token_admin))
        assert res.status_code == 200
        data = res.json()
        assert "demo_mode" in data
        assert data["is_admin"] is True

        token_alice = _token(client, "alice")
        res2 = client.get("/demo/status", headers=_auth(token_alice))
        assert res2.status_code == 200
        assert res2.json()["is_admin"] is False

    def test_demo_reset_success_for_admin(self, client, monkeypatch):
        monkeypatch.setenv("DEMO_MODE", "true")
        token = _token(client, "admin")
        res = client.post("/demo/reset", headers=_auth(token))
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "reseeded" in data["message"].lower()

        # Check audit log recorded
        conn = get_conn()
        try:
            log = conn.execute(
                "SELECT * FROM audit_logs WHERE action = 'DEMO_RESET_DATABASE'"
            ).fetchone()
            assert log is not None
        finally:
            conn.close()

    def test_demo_reset_blocked_for_non_admin(self, client, monkeypatch):
        monkeypatch.setenv("DEMO_MODE", "true")
        token_alice = _token(client, "alice")
        res = client.post("/demo/reset", headers=_auth(token_alice))
        assert res.status_code == 403

    def test_demo_reset_blocked_when_demo_mode_false(self, client, monkeypatch):
        monkeypatch.setenv("DEMO_MODE", "false")
        token = _token(client, "admin")
        res = client.post("/demo/reset", headers=_auth(token))
        assert res.status_code == 403
        assert "demo_mode" in res.json()["detail"].lower()

    def test_demo_scenario_1_success(self, client, monkeypatch):
        monkeypatch.setenv("DEMO_MODE", "true")
        token = _token(client, "admin")

        # Reset first
        client.post("/demo/reset", headers=_auth(token))

        res = client.post("/demo/scenario/1", headers=_auth(token))
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "ok"
        assert data["scenario"] == 1
        assert data["disruption"] is not None
        assert len(data["impacts"]) > 0

        # Verify O-001 is top affected
        codes = [i["order_code"] for i in data["impacts"]]
        assert "O-001" in codes
        assert codes[0] == "O-001"

    def test_demo_scenario_2_success(self, client, monkeypatch):
        monkeypatch.setenv("DEMO_MODE", "true")
        token = _token(client, "admin")

        # Reset first
        client.post("/demo/reset", headers=_auth(token))

        res = client.post("/demo/scenario/2", headers=_auth(token))
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "ok"
        assert data["scenario"] == 2
        assert data["disruption"] is not None
        assert data["disruption"]["type"] == "STOCK_SHORTAGE"

    def test_demo_scenario_invalid_id(self, client, monkeypatch):
        monkeypatch.setenv("DEMO_MODE", "true")
        token = _token(client, "admin")
        res = client.post("/demo/scenario/99", headers=_auth(token))
        assert res.status_code == 400
        assert "unsupported" in res.json()["detail"].lower()
