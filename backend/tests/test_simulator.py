"""
backend/tests/test_simulator.py

Tests for What-If Simulator endpoints:
- POST /disruptions/{id}/simulate
- POST /plans/{id}/simulate
- Verification that database state (row counts across all tables and exact inventory values)
  is 100% identical before and after simulations.
- Role-based access control:
  - Allowed: Operations Analyst, Supply Chain Manager, Procurement Approver, Administrator.
  - Denied (403): Warehouse Operator.
  - Unauthenticated (401): Missing token.
"""
import sys
from datetime import date, timedelta
from pathlib import Path
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import app
from backend.seed.seed import seed
from backend.services.detection import run_detection
from backend.services.approval import propose_plan
from backend.db import get_conn


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(scope="module", autouse=True)
def setup_scenario():
    """Seed DB and trigger Scenario 1 disruption."""
    seed()
    conn = get_conn()
    sh = conn.execute("SELECT id, expected_arrival FROM shipments WHERE code = 'SH-001'").fetchone()
    base_date = date.fromisoformat(sh["expected_arrival"])
    new_eta = (base_date + timedelta(days=6)).isoformat()
    conn.execute(
        "UPDATE shipments SET current_eta = ?, delay_days = 6, status = 'DELAYED' WHERE id = ?",
        (new_eta, sh["id"]),
    )
    conn.commit()
    conn.close()

    # Detect disruption and generate impacts
    run_detection(shipment_id=1)


@pytest.fixture(scope="module")
def tokens(client):
    users = {
        "analyst": ("anita", "pass123"),
        "manager": ("meera", "pass123"),
        "operator": ("ravi", "pass123"),
        "procurement": ("priya", "pass123"),
        "admin": ("admin", "admin123"),
    }
    toks = {}
    for role, (user, pwd) in users.items():
        res = client.post("/auth/login", json={"username": user, "password": pwd})
        assert res.status_code == 200, f"Login failed for {user}: {res.text}"
        toks[role] = res.json()["access_token"]
    return toks


def get_db_snapshot():
    """Capture row counts and complete inventory values to prove zero mutations occur."""
    conn = get_conn()
    try:
        tables = [
            ("inventory", "SELECT COUNT(*) as c FROM inventory"),
            ("orders", "SELECT COUNT(*) as c FROM orders"),
            ("order_lines", "SELECT COUNT(*) as c FROM order_lines"),
            ("shipments", "SELECT COUNT(*) as c FROM shipments"),
            ("disruptions", "SELECT COUNT(*) as c FROM disruptions"),
            ("disruption_impacts", "SELECT COUNT(*) as c FROM disruption_impacts"),
            ("recovery_plans", "SELECT COUNT(*) as c FROM recovery_plans"),
            ("audit_logs", "SELECT COUNT(*) as c FROM audit_logs"),
            ("notifications", "SELECT COUNT(*) as c FROM notifications"),
        ]
        counts = {}
        for tbl, count_sql in tables:
            r = conn.execute(count_sql).fetchone()
            counts[tbl] = r["c"]

        inv_rows = conn.execute(
            "SELECT id, warehouse_id, product_id, on_hand, reserved, version FROM inventory ORDER BY id"
        ).fetchall()
        inventory_state = [tuple(row) for row in inv_rows]

        return {"counts": counts, "inventory": inventory_state}
    finally:
        conn.close()


def test_simulation_data_integrity_unmodified(client, tokens):
    """
    CRITICAL TEST: Proves that row counts across all database tables and exact
    inventory values (on_hand, reserved, version) remain 100% IDENTICAL before and after simulations.
    Hard rules 11 & 14: Simulator runs inside a transaction that is ALWAYS rolled back.
    """
    auth = {"Authorization": f"Bearer {tokens['analyst']}"}

    # 1. Capture snapshot before
    snapshot_before = get_db_snapshot()

    # 2. Run simulation on disruption (REALLOCATE_STOCK)
    res_disruption = client.post(
        "/disruptions/1/simulate",
        headers=auth,
        json={
            "action_type": "REALLOCATE_STOCK",
            "parameters": {
                "source_warehouse_id": 3,
                "quantity": 200,
            },
        },
    )
    assert res_disruption.status_code == 200
    data_d = res_disruption.json()
    assert data_d["action_type"] == "REALLOCATE_STOCK"
    assert data_d["cost"] == 1500.0  # 500 flat + 5*200
    assert len(data_d["affected_orders"]) > 0
    assert "collateral_orders_affected" in data_d

    # 3. Propose a plan first so we can simulate it
    propose_res = client.post(
        "/disruptions/1/plans",
        headers=auth,
        json={
            "title": "Reallocate 200 units from Hyderabad",
            "action_type": "REALLOCATE_STOCK",
            "description": "Transfer 200 units from Hyderabad to Chennai",
            "plan_payload": {
                "source_warehouse_id": 3,
                "quantity": 200,
                "product_code": "P1",
            },
        },
    )
    assert propose_res.status_code == 200
    plan_id = propose_res.json()["id"]

    # Capture snapshot after proposal (the proposal itself writes a plan, but simulation must not write anything)
    snapshot_after_proposal = get_db_snapshot()

    # 4. Run simulation on plan
    res_plan = client.post(
        f"/plans/{plan_id}/simulate",
        headers=auth,
        json={},
    )
    assert res_plan.status_code == 200
    data_p = res_plan.json()
    assert data_p["plan_id"] == plan_id
    assert data_p["action_type"] == "REALLOCATE_STOCK"
    assert data_p["cost"] == 1500.0

    # 5. Capture snapshot after simulations
    snapshot_after = get_db_snapshot()

    # ASSERT IDENTICAL TABLE ROW COUNTS
    for table_name, count_before in snapshot_after_proposal["counts"].items():
        count_after = snapshot_after["counts"][table_name]
        assert count_after == count_before, (
            f"Row count mutation detected in table '{table_name}'! "
            f"Before: {count_before}, After: {count_after}"
        )

    # ASSERT IDENTICAL INVENTORY ON_HAND, RESERVED, VERSION VALUES
    assert snapshot_after["inventory"] == snapshot_after_proposal["inventory"], (
        "Inventory values (on_hand, reserved, version) changed after simulation!"
    )


def test_simulation_before_after_comparison(client, tokens):
    """
    Verify detailed before/after comparison fields:
    - affected orders: due date, delivery date before vs after, risk score before vs after
    - collateral orders sharing same stock at source warehouse
    """
    auth = {"Authorization": f"Bearer {tokens['manager']}"}

    res = client.post(
        "/disruptions/1/simulate",
        headers=auth,
        json={
            "action_type": "REALLOCATE_STOCK",
            "parameters": {
                "source_warehouse_id": 3,
                "quantity": 200,
            },
        },
    )
    assert res.status_code == 200
    data = res.json()

    assert data["meets_deadline"] is True
    assert data["cost"] == 1500.0
    assert len(data["affected_orders"]) >= 1

    first_ord = data["affected_orders"][0]
    assert "before" in first_ord
    assert "after" in first_ord
    assert first_ord["before"]["meets_deadline"] is False
    assert first_ord["after"]["meets_deadline"] is True
    assert first_ord["risk_score_delta"] < 0  # Risk improved
    assert first_ord["status"] == "IMPROVED"

    # Overall metrics
    assert data["overall_before"]["avg_risk_score"] > data["overall_after"]["avg_risk_score"]
    assert data["overall_after"]["risk_reduction"] > 0

    # Collateral orders sharing stock at warehouse 3 (Hyderabad)
    assert isinstance(data["collateral_orders_affected"], list)
    for col in data["collateral_orders_affected"]:
        assert "order_id" in col
        assert "stock_before" in col
        assert "stock_after" in col
        assert "impact_note" in col


def test_simulation_collateral_order_detection(client, tokens):
    """
    Explicitly test that when another open order shares stock at the source warehouse,
    the simulation detects it, reports stock before/after, and flags when a deficit is created.
    """
    auth = {"Authorization": f"Bearer {tokens['manager']}"}
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO orders (id, code, customer, priority, status, due_date) VALUES (9999, 'O-COLLATERAL', 'Apex Labs', 'MEDIUM', 'OPEN', '2026-11-15')"
        )
        conn.execute(
            "INSERT INTO order_lines (order_id, product_id, warehouse_id, quantity) VALUES (9999, 1, 3, 100)"
        )
        conn.commit()
    finally:
        conn.close()

    try:
        res = client.post(
            "/disruptions/1/simulate",
            headers=auth,
            json={
                "action_type": "REALLOCATE_STOCK",
                "parameters": {"source_warehouse_id": 3, "quantity": 250},
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert len(data["collateral_orders_affected"]) >= 1
        collateral = next(c for c in data["collateral_orders_affected"] if c["order_id"] == 9999)
        assert collateral["order_code"] == "O-COLLATERAL"
        assert collateral["warehouse_id"] == 3
        assert collateral["order_quantity"] == 100
        assert collateral["stock_before"] == 280
        assert collateral["stock_after"] == 30
        assert collateral["deficit"] == 70
        assert collateral["status"] == "SHORTFALL_CREATED"
    finally:
        conn = get_conn()
        conn.execute("DELETE FROM order_lines WHERE order_id = 9999")
        conn.execute("DELETE FROM orders WHERE id = 9999")
        conn.commit()
        conn.close()


def test_simulation_expedite_option(client, tokens):
    """Verify simulation of EXPEDITE_ORDER option."""
    auth = {"Authorization": f"Bearer {tokens['analyst']}"}

    res = client.post(
        "/disruptions/1/simulate",
        headers=auth,
        json={"action_type": "EXPEDITE_ORDER"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["action_type"] == "EXPEDITE_ORDER"
    assert data["cost"] > 0
    assert len(data["affected_orders"]) > 0


def test_expedite_vs_reallocate_different_outcomes_and_database_unchanged(client, tokens):
    """
    Verify:
    1. Simulating 'EXPEDITE_ORDER' instead of 'REALLOCATE_STOCK' produces distinctly different
       operational outcomes (different cost, delivery dates, collateral impact, and action summary).
    2. The database state (row counts in all tables and exact inventory values) is completely unchanged.
    """
    auth = {"Authorization": f"Bearer {tokens['analyst']}"}

    # Step 1: Capture DB state before any simulation
    snapshot_before = get_db_snapshot()

    # Step 2: Simulate REALLOCATE_STOCK
    res_reallocate = client.post(
        "/disruptions/1/simulate",
        headers=auth,
        json={
            "action_type": "REALLOCATE_STOCK",
            "parameters": {"source_warehouse_id": 3, "quantity": 200},
        },
    )
    assert res_reallocate.status_code == 200
    reallocate_out = res_reallocate.json()

    # Verify DB unchanged after reallocation simulation
    snapshot_mid = get_db_snapshot()
    assert snapshot_mid["counts"] == snapshot_before["counts"]
    assert snapshot_mid["inventory"] == snapshot_before["inventory"]

    # Step 3: Simulate EXPEDITE_ORDER
    res_expedite = client.post(
        "/disruptions/1/simulate",
        headers=auth,
        json={"action_type": "EXPEDITE_ORDER"},
    )
    assert res_expedite.status_code == 200
    expedite_out = res_expedite.json()

    # Step 4: Verify DB unchanged after expedite simulation
    snapshot_after = get_db_snapshot()
    assert snapshot_after["counts"] == snapshot_before["counts"], "Table row counts mutated!"
    assert snapshot_after["inventory"] == snapshot_before["inventory"], "Inventory values mutated!"

    # Step 5: Verify distinct outcomes between the two recovery strategies
    # A) Different Action Types
    assert reallocate_out["action_type"] == "REALLOCATE_STOCK"
    assert expedite_out["action_type"] == "EXPEDITE_ORDER"

    # B) Distinct Logistics Cost (Reallocation Rs. 1,500 vs Expedited Air Freight Rs. 7,500)
    assert reallocate_out["cost"] != expedite_out["cost"]
    assert reallocate_out["cost"] == 1500.0  # 500 flat + 5 * 200
    assert expedite_out["cost"] == 7500.0    # 2500 flat + 10 * 500
    assert expedite_out["cost"] > reallocate_out["cost"]

    # C) Distinct Action Summaries
    assert reallocate_out["action_summary"] != expedite_out["action_summary"]
    assert "Hyderabad" in reallocate_out["action_summary"]
    assert "air freight" in expedite_out["action_summary"].lower()

    # D) Both simulate valid order recovery
    assert len(reallocate_out["affected_orders"]) > 0
    assert len(expedite_out["affected_orders"]) > 0



def test_simulation_roles_rbac(client, tokens):
    """
    Role check:
    - Allowed: Operations Analyst, Supply Chain Manager, Procurement Approver, Administrator.
    - Blocked (403): Warehouse Operator.
    - Blocked (401): Unauthenticated.
    """
    payload = {"action_type": "REALLOCATE_STOCK", "parameters": {"source_warehouse_id": 3, "quantity": 100}}

    # 1. Operations Analyst -> 200
    r = client.post("/disruptions/1/simulate", headers={"Authorization": f"Bearer {tokens['analyst']}"}, json=payload)
    assert r.status_code == 200

    # 2. Supply Chain Manager -> 200
    r = client.post("/disruptions/1/simulate", headers={"Authorization": f"Bearer {tokens['manager']}"}, json=payload)
    assert r.status_code == 200

    # 3. Procurement Approver -> 200
    r = client.post("/disruptions/1/simulate", headers={"Authorization": f"Bearer {tokens['procurement']}"}, json=payload)
    assert r.status_code == 200

    # 4. Administrator -> 200
    r = client.post("/disruptions/1/simulate", headers={"Authorization": f"Bearer {tokens['admin']}"}, json=payload)
    assert r.status_code == 200

    # 5. Warehouse Operator -> 403 Forbidden
    r = client.post("/disruptions/1/simulate", headers={"Authorization": f"Bearer {tokens['operator']}"}, json=payload)
    assert r.status_code == 403
    assert "not authorised" in r.json()["detail"].lower()

    # 6. Unauthenticated -> 401 Unauthorized
    r = client.post("/disruptions/1/simulate", json=payload)
    assert r.status_code == 401
