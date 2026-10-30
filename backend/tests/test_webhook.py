"""
backend/tests/test_webhook.py

Tests for POST /webhooks/carrier.
Verifies idempotency, atomic update of current_eta and status, 404 on unknown shipment,
and 422 on invalid payload.
"""
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.seed.seed import seed as _do_seed
from backend.main import app
from backend.db import get_conn


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


class TestCarrierWebhook:
    def test_carrier_webhook_updates_shipment(self, client):
        _do_seed()
        payload = {
            "event_id": "EVT-TEST-001",
            "shipment_ref": "SH-001",
            "status": "DELAYED",
            "new_eta": "2026-11-10",
        }
        res = client.post("/webhooks/carrier", json=payload)
        assert res.status_code == 200, res.text
        assert res.json() == {"status": "processed", "shipment_id": 1}

        # Verify shipment updated in DB
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT status, current_eta FROM shipments WHERE code = 'SH-001'"
            ).fetchone()
            assert row["status"] == "DELAYED"
            assert row["current_eta"] == "2026-11-10"

            # Verify webhook event recorded
            evt = conn.execute(
                "SELECT event_id, status FROM webhook_events WHERE event_id = 'EVT-TEST-001'"
            ).fetchone()
            assert evt is not None
            assert evt["status"] == "PROCESSED"
        finally:
            conn.close()

    def test_duplicate_webhook_event_ignored(self, client):
        payload = {
            "event_id": "EVT-TEST-001",
            "shipment_ref": "SH-001",
            "status": "ARRIVED",
            "new_eta": "2026-11-12",
        }
        # Second time with same event_id
        res = client.post("/webhooks/carrier", json=payload)
        assert res.status_code == 200, res.text
        assert res.json() == {"status": "duplicate, ignored"}

        # Verify shipment was NOT modified by the duplicate event
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT status, current_eta FROM shipments WHERE code = 'SH-001'"
            ).fetchone()
            assert row["status"] == "DELAYED"
            assert row["current_eta"] == "2026-11-10"
        finally:
            conn.close()

    def test_unknown_shipment_returns_404(self, client):
        payload = {
            "event_id": "EVT-TEST-UNKNOWN",
            "shipment_ref": "SH-999-DOESNOTEXIST",
            "status": "DELAYED",
            "new_eta": "2026-11-10",
        }
        res = client.post("/webhooks/carrier", json=payload)
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()

    def test_invalid_payload_returns_422(self, client):
        # Missing required fields
        payload = {
            "event_id": "EVT-TEST-BAD",
        }
        res = client.post("/webhooks/carrier", json=payload)
        assert res.status_code == 422
