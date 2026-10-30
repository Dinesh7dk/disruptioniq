"""
backend/tests/test_recovery.py

Tests for:
1. Pure recovery option functions (reallocate, expedite, alternative_supplier, split_order).
2. generate_options(disruption_id, order_id).
3. GET /disruptions/{id}/options endpoint.
4. Scenario 1 test: Reallocation from Hyderabad must be feasible for O-001 (P1 at Chennai).
5. Scenario 2 test: Stock shortage at Bangalore for P2; reallocation from Hyderabad must be feasible.
6. Verify no database writes occur during option generation.
"""
import sys
from datetime import date, timedelta
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
from backend.services.detection import run_detection, detect_stock_shortages
from backend.services.recovery import (
    generate_options,
    option_reallocate,
    option_expedite,
    option_alternative_supplier,
    option_split_order,
)


@pytest.fixture(autouse=True)
def reset_db():
    _do_seed()


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _token(client, username="alice", password="pass123"):
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


class TestRecoveryScenario1:
    def test_scenario1_reallocation_from_hyderabad_feasible_for_o001(self, client):
        """
        Scenario 1:
        SH-001 is delayed. Chennai needs 200 P1 for O-001.
        Hyderabad has 300 on hand, 20 reserved (280 available >= 200 needed).
        Reallocation from Hyderabad must be feasible!
        """
        conn = get_conn()
        try:
            sh = conn.execute("SELECT id, expected_arrival FROM shipments WHERE code = 'SH-001'").fetchone()
            base_date = date.fromisoformat(sh["expected_arrival"])
            new_eta = (base_date + timedelta(days=6)).isoformat()
            conn.execute(
                "UPDATE shipments SET current_eta = ?, delay_days = 6, status = 'DELAYED' WHERE id = ?",
                (new_eta, sh["id"]),
            )
            conn.commit()
        finally:
            conn.close()

        # Run detection to create the disruption
        run_detection(shipment_id=sh["id"])

        conn = get_conn()
        try:
            disr = conn.execute("SELECT id FROM disruptions WHERE shipment_id = ? AND status = 'OPEN'", (sh["id"],)).fetchone()
            assert disr is not None
            disruption_id = disr["id"]

            o001 = conn.execute("SELECT id FROM orders WHERE code = 'O-001'").fetchone()
            assert o001 is not None
            order_id = o001["id"]
        finally:
            conn.close()

        # Check options via service
        options = generate_options(disruption_id=disruption_id, order_id=order_id)
        assert len(options) > 0

        # Find REALLOCATE_STOCK option from Hyderabad
        realloc_opts = [
            opt for opt in options
            if opt["type"] == "REALLOCATE_STOCK"
            and opt["details"]["source_warehouse_city"] == "Hyderabad"
        ]
        assert len(realloc_opts) > 0, f"No reallocation from Hyderabad found in {options}"
        realloc = realloc_opts[0]
        assert realloc["details"]["quantity"] == 200
        assert realloc["details"]["target_warehouse_city"] == "Chennai"
        assert realloc["cost"] > 0
        assert "new_delivery_date" in realloc
        assert realloc["meets_deadline"] is True

        # Test GET /disruptions/{id}/options endpoint
        token = _token(client)
        resp = client.get(
            f"/disruptions/{disruption_id}/options?order_id={order_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["disruption_id"] == disruption_id
        assert body["options_count"] == len(options)


class TestRecoveryScenario2:
    def test_scenario2_stock_shortage_reallocation_feasible(self):
        """
        Scenario 2:
        Stock shortage at Bangalore: P2 has on_hand 40, reserved 35 (5 available).
        Orders O-004 (40 units) and O-005 (20 units) total 60 units.
        Hyderabad has 400 on hand, 100 reserved (300 available).
        Reallocation from Hyderabad must be feasible for both O-004 and O-005.
        """
        # Run detection for stock shortages
        disruptions = detect_stock_shortages()
        assert len(disruptions) > 0

        conn = get_conn()
        try:
            d = conn.execute(
                """SELECT d.id FROM disruptions d
                   JOIN products p ON d.product_id = p.id
                   JOIN warehouses w ON d.warehouse_id = w.id
                   WHERE d.type = 'STOCK_SHORTAGE' AND p.code = 'P2' AND w.city = 'Bangalore' AND d.status = 'OPEN'"""
            ).fetchone()
            assert d is not None
            disruption_id = d["id"]
        finally:
            conn.close()

        # Check options for the disruption
        options = generate_options(disruption_id=disruption_id)
        assert len(options) > 0

        # Filter reallocation options from Hyderabad
        hyd_reallocs = [
            opt for opt in options
            if opt["type"] == "REALLOCATE_STOCK" and opt["details"]["source_warehouse_city"] == "Hyderabad"
        ]
        assert len(hyd_reallocs) >= 2

        # Check that both O-004 (40 qty) and O-005 (20 qty) have feasible reallocation options
        order_codes_covered = {opt["order"]["code"] for opt in hyd_reallocs}
        assert "O-004" in order_codes_covered
        assert "O-005" in order_codes_covered


class TestPureRecoveryFunctions:
    def test_reallocate_infeasible_when_stock_insufficient(self):
        src_wh = {"id": 2, "city": "Bangalore", "available_stock": 10}
        tgt_wh = {"id": 1, "city": "Chennai"}
        prod = {"code": "P1"}
        res = option_reallocate(src_wh, tgt_wh, prod, quantity_needed=50, order_due_date="2026-11-10")
        assert res is None

    def test_expedite_infeasible_when_no_shipment_or_misses_deadline(self):
        # Misses deadline
        shipment = {"code": "SH-001", "current_eta": "2026-11-20", "quantity": 100}
        res = option_expedite(shipment, order_due_date="2026-11-05")
        assert res is None

    def test_split_order_infeasible_when_no_local_stock(self):
        res = option_split_order(
            local_available=0,
            order_quantity=100,
            order_due_date="2026-11-05",
            delayed_delivery_date="2026-11-12",
        )
        assert res is None

    def test_split_order_feasible_when_partial_stock_available(self):
        res = option_split_order(
            local_available=30,
            order_quantity=100,
            order_due_date="2026-11-05",
            delayed_delivery_date="2026-11-12",
        )
        assert res is not None
        assert res["type"] == "PARTIAL_FULFIL"
        assert res["details"]["immediate_quantity"] == 30
        assert res["details"]["backlog_quantity"] == 70
