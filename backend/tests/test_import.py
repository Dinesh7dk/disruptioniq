"""
backend/tests/test_import.py

Tests for POST /import/shipments/csv, /import/shipments/json,
and /import/orders/json.

Uses shipments_dirty.csv (4 bad rows + 1 duplicate = 4 rejected, 1 imported
after the first valid SH-D04), and orders_import.json (3 valid orders).
Each test re-seeds the DB so it always starts clean.
"""
import sys
import json
from pathlib import Path
from fastapi.testclient import TestClient

from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Re-seed before tests so refs don't collide with prior runs
from backend.seed.seed import seed as _do_seed
_do_seed()

from backend.main import app  # noqa: E402

SEED_DIR = ROOT / "backend" / "seed"
DIRTY_CSV  = SEED_DIR / "shipments_dirty.csv"
CLEAN_CSV  = SEED_DIR / "shipments_clean.csv"
ORDERS_JSON = SEED_DIR / "orders_import.json"

# ── helpers ────────────────────────────────────────────────────────────────────

import pytest

@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _token(client, username="alice", password="pass123"):
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════════════════════════════════════
# SHIPMENT CSV  —  clean file
# ══════════════════════════════════════════════════════════════════════════════

class TestShipmentCSVClean:
    def test_clean_csv_imports_all_rows(self, client):
        token = _token(client)
        data = CLEAN_CSV.read_bytes()
        r = client.post(
            "/import/shipments/csv",
            files={"file": ("shipments_clean.csv", data, "text/csv")},
            headers=_auth(token),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["imported"] == 4
        assert body["rejected"] == []

    def test_clean_csv_second_upload_rejects_duplicates(self, client):
        """Same file again — all refs already in DB → 4 rejected."""
        token = _token(client)
        data = CLEAN_CSV.read_bytes()
        r = client.post(
            "/import/shipments/csv",
            files={"file": ("shipments_clean.csv", data, "text/csv")},
            headers=_auth(token),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["imported"] == 0
        assert len(body["rejected"]) == 4
        for rej in body["rejected"]:
            assert "already exists" in rej["reason"]


# ══════════════════════════════════════════════════════════════════════════════
# SHIPMENT CSV  —  dirty file
# ══════════════════════════════════════════════════════════════════════════════

class TestShipmentCSVDirty:
    """
    Dirty file rows:
      row 1: SH-D01  qty=-50          → rejected (qty <= 0)
      row 2: SH-D02  SUP-ZZZZ         → rejected (unknown supplier)
      row 3: SH-D03  date=not-a-date  → rejected (bad date)
      row 4: SH-D04  valid            → imported
      row 5: SH-D04  duplicate ref    → rejected (dup within batch)
    Expected: imported=1, rejected=4
    """

    def test_dirty_csv_imported_count(self, client):
        token = _token(client)
        data = DIRTY_CSV.read_bytes()
        r = client.post(
            "/import/shipments/csv",
            files={"file": ("shipments_dirty.csv", data, "text/csv")},
            headers=_auth(token),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["imported"] == 1, f"Expected 1 imported, got: {body}"
        assert len(body["rejected"]) == 4, f"Expected 4 rejected, got: {body['rejected']}"

    def test_dirty_csv_negative_qty_rejected(self, client):
        _do_seed()          # reset so SH-D04 is gone again
        token = _token(client)
        data = DIRTY_CSV.read_bytes()
        r = client.post(
            "/import/shipments/csv",
            files={"file": ("shipments_dirty.csv", data, "text/csv")},
            headers=_auth(token),
        )
        body = r.json()
        reasons = [rej["reason"] for rej in body["rejected"]]
        assert any("qty" in reason.lower() or "quantity" in reason.lower()
                   for reason in reasons), reasons

    def test_dirty_csv_unknown_supplier_rejected(self, client):
        _do_seed()
        token = _token(client)
        data = DIRTY_CSV.read_bytes()
        r = client.post(
            "/import/shipments/csv",
            files={"file": ("shipments_dirty.csv", data, "text/csv")},
            headers=_auth(token),
        )
        body = r.json()
        reasons = [rej["reason"] for rej in body["rejected"]]
        assert any("SUP-ZZZZ" in reason for reason in reasons), reasons

    def test_dirty_csv_bad_date_rejected(self, client):
        _do_seed()
        token = _token(client)
        data = DIRTY_CSV.read_bytes()
        r = client.post(
            "/import/shipments/csv",
            files={"file": ("shipments_dirty.csv", data, "text/csv")},
            headers=_auth(token),
        )
        body = r.json()
        reasons = [rej["reason"] for rej in body["rejected"]]
        assert any("not-a-date" in reason or "date" in reason.lower()
                   for reason in reasons), reasons

    def test_dirty_csv_duplicate_ref_rejected(self, client):
        _do_seed()
        token = _token(client)
        data = DIRTY_CSV.read_bytes()
        r = client.post(
            "/import/shipments/csv",
            files={"file": ("shipments_dirty.csv", data, "text/csv")},
            headers=_auth(token),
        )
        body = r.json()
        reasons = [rej["reason"] for rej in body["rejected"]]
        assert any("Duplicate" in reason or "duplicate" in reason
                   for reason in reasons), reasons


# ══════════════════════════════════════════════════════════════════════════════
# SHIPMENT JSON
# ══════════════════════════════════════════════════════════════════════════════

class TestShipmentJSON:
    def test_valid_json_imports(self, client):
        _do_seed()
        token = _token(client)
        payload = [
            {"ref": "SH-J01", "supplier_code": "SUP-A", "product_code": "P2",
             "dest_city": "Chennai", "quantity": 100, "expected_arrival": "2026-11-10"},
            {"ref": "SH-J02", "supplier_code": "SUP-B", "product_code": "P3",
             "dest_city": "Hyderabad", "quantity": 50, "expected_arrival": "2026-11-12"},
        ]
        r = client.post("/import/shipments/json", json=payload, headers=_auth(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["imported"] == 2
        assert body["rejected"] == []

    def test_json_rejects_zero_qty(self, client):
        token = _token(client)
        payload = [
            {"ref": "SH-BAD-1", "supplier_code": "SUP-A", "product_code": "P1",
             "dest_city": "Chennai", "quantity": 0, "expected_arrival": "2026-11-10"},
        ]
        r = client.post("/import/shipments/json", json=payload, headers=_auth(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["imported"] == 0
        assert len(body["rejected"]) == 1
        assert "quantity" in body["rejected"][0]["reason"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# ORDERS JSON
# ══════════════════════════════════════════════════════════════════════════════

class TestOrdersJSON:
    def test_orders_import_json_all_valid(self, client):
        _do_seed()
        token = _token(client)
        data = json.loads(ORDERS_JSON.read_text(encoding="utf-8"))
        r = client.post("/import/orders/json", json=data, headers=_auth(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["imported"] == 3, body
        assert body["rejected"] == []

    def test_orders_import_second_run_rejects_duplicates(self, client):
        """Re-importing same codes → all 3 rejected as duplicates."""
        token = _token(client)
        data = json.loads(ORDERS_JSON.read_text(encoding="utf-8"))
        r = client.post("/import/orders/json", json=data, headers=_auth(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["imported"] == 0
        assert len(body["rejected"]) == 3

    def test_orders_bad_priority_rejected(self, client):
        token = _token(client)
        payload = [{"code": "O-BAD-1", "customer": "X", "priority": "URGENT",
                    "due_date": "2026-11-10",
                    "lines": [{"product_code": "P3", "warehouse_code": "WH-CHN", "quantity": 10}]}]
        r = client.post("/import/orders/json", json=payload, headers=_auth(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["imported"] == 0
        assert "priority" in body["rejected"][0]["reason"].lower()

    def test_orders_bad_line_product_rejected(self, client):
        token = _token(client)
        payload = [{"code": "O-BAD-2", "customer": "Y", "priority": "LOW",
                    "due_date": "2026-11-10",
                    "lines": [{"product_code": "P-UNKNOWN", "warehouse_code": "WH-CHN", "quantity": 5}]}]
        r = client.post("/import/orders/json", json=payload, headers=_auth(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["imported"] == 0
        assert "P-UNKNOWN" in body["rejected"][0]["reason"]

    def test_orders_zero_line_qty_rejected(self, client):
        token = _token(client)
        payload = [{"code": "O-BAD-3", "customer": "Z", "priority": "HIGH",
                    "due_date": "2026-11-10",
                    "lines": [{"product_code": "P3", "warehouse_code": "WH-CHN", "quantity": 0}]}]
        r = client.post("/import/orders/json", json=payload, headers=_auth(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["imported"] == 0
        assert "quantity" in body["rejected"][0]["reason"].lower()

    def test_orders_empty_lines_rejected(self, client):
        token = _token(client)
        payload = [{"code": "O-BAD-4", "customer": "Z", "priority": "HIGH",
                    "due_date": "2026-11-10", "lines": []}]
        r = client.post("/import/orders/json", json=payload, headers=_auth(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["imported"] == 0
        assert "lines" in body["rejected"][0]["reason"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# ROLE ENFORCEMENT
# ══════════════════════════════════════════════════════════════════════════════

class TestImportRoles:
    def test_supply_chain_manager_gets_403(self, client):
        """carol is Supply Chain Manager — not in allowed roles."""
        token = _token(client, "carol")
        data = CLEAN_CSV.read_bytes()
        r = client.post(
            "/import/shipments/csv",
            files={"file": ("f.csv", data, "text/csv")},
            headers=_auth(token),
        )
        assert r.status_code == 403

    def test_warehouse_operator_gets_403(self, client):
        token = _token(client, "dave")
        r = client.post("/import/orders/json", json=[], headers=_auth(token))
        assert r.status_code == 403

    def test_admin_can_import(self, client):
        _do_seed()
        token = _token(client, "admin", "admin123")
        data = CLEAN_CSV.read_bytes()
        r = client.post(
            "/import/shipments/csv",
            files={"file": ("f.csv", data, "text/csv")},
            headers=_auth(token),
        )
        assert r.status_code == 200

    def test_unauthenticated_gets_401(self, client):
        r = client.post("/import/orders/json", json=[])
        assert r.status_code == 401
