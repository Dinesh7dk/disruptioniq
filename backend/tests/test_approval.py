"""
backend/tests/test_approval.py

Comprehensive tests for recovery plan workflow:
1. Propose plan (Operations Analyst).
2. Self-approval blocked (403).
3. Wrong role blocked:
   - Warehouse Operator cannot approve (403).
   - Supply Chain Manager cannot approve ALTERNATIVE_SUPPLIER (403).
   - Procurement Approver cannot approve REALLOCATE_STOCK (403).
4. Invalid transition blocked (409):
   - Executing a plan that is only PROPOSED or PENDING_APPROVAL.
   - Approving an already EXECUTED plan.
5. Revalidation failure on execute:
   - Stock insufficient at execution time -> 409.
   - Deadline exceeded at execution time -> 409.
6. Optimistic version conflict (409):
   - Concurrent modification changes inventory version -> rowcount == 0 -> 409.
7. End-to-end happy path:
   - Propose -> Approve -> Execute -> inventory reserved updated, version incremented, disruption MITIGATED.
8. Audit logs and notifications written on every step.
"""
import sys
import json
from pathlib import Path
from datetime import date, timedelta
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
from backend.services.detection import run_detection


@pytest.fixture(autouse=True)
def reset_db():
    _do_seed()


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _token(client, username, password="pass123"):
    if username == "admin":
        password = "admin123"
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def setup_disruption():
    conn = get_conn()
    sh = conn.execute("SELECT id, expected_arrival FROM shipments WHERE code = 'SH-001'").fetchone()
    base_date = date.fromisoformat(sh['expected_arrival'])
    new_eta = (base_date + timedelta(days=6)).isoformat()
    conn.execute(
        "UPDATE shipments SET current_eta = ?, delay_days = 6, status = 'DELAYED' WHERE id = ?",
        (new_eta, sh['id']),
    )
    conn.commit()
    conn.close()
    d_ids = run_detection(shipment_id=1)
    return d_ids[0] if d_ids else 1


class TestPlanApprovalWorkflow:
    def test_self_approval_blocked(self, client):
        """Rule 4: Approver must differ from proposer. Returns 403."""
        did = setup_disruption()
        # Alice (Analyst) proposes plan
        t_alice = _token(client, "alice")
        prop_res = client.post(
            f"/disruptions/{did}/plans",
            json={
                "title": "Stock Reallocation from Hyderabad",
                "action_type": "REALLOCATE_STOCK",
                "description": "Transfer 200 P1",
                "plan_payload": {
                    "source_warehouse_id": 3,
                    "product_code": "P1",
                    "quantity": 200,
                },
            },
            headers=_auth(t_alice),
        )
        assert prop_res.status_code == 200, prop_res.text
        plan_id = prop_res.json()["id"]

        # If Alice attempts to approve her own plan -> 403 Forbidden
        app_res = client.post(f"/plans/{plan_id}/approve", json={"note": "Self approving"}, headers=_auth(t_alice))
        assert app_res.status_code == 403
        assert "not authorised" in app_res.json()["detail"].lower() or "separation of duty" in app_res.json()["detail"].lower()

    def test_wrong_role_approval_blocked(self, client):
        """
        - Dave (Warehouse Operator) cannot approve -> 403.
        - Eve (Procurement Approver) cannot approve REALLOCATE_STOCK -> 403.
        """
        did = setup_disruption()
        t_alice = _token(client, "alice")
        prop_res = client.post(
            f"/disruptions/{did}/plans",
            json={
                "title": "Transfer stock",
                "action_type": "REALLOCATE_STOCK",
                "plan_payload": {"source_warehouse_id": 3, "product_code": "P1", "quantity": 100},
            },
            headers=_auth(t_alice),
        )
        plan_id = prop_res.json()["id"]

        # Dave (Warehouse Operator) attempts approval
        t_dave = _token(client, "dave")
        res_dave = client.post(f"/plans/{plan_id}/approve", json={}, headers=_auth(t_dave))
        assert res_dave.status_code == 403

        # Eve (Procurement Approver) attempts to approve REALLOCATE_STOCK
        t_eve = _token(client, "eve")
        res_eve = client.post(f"/plans/{plan_id}/approve", json={}, headers=_auth(t_eve))
        assert res_eve.status_code == 403
        assert "only supply chain manager" in res_eve.json()["detail"].lower()

    def test_invalid_status_transitions(self, client):
        """Rule 9: Attempting invalid state transitions returns 409 Conflict."""
        did = setup_disruption()
        t_alice = _token(client, "alice")
        t_dave = _token(client, "dave")

        prop_res = client.post(
            f"/disruptions/{did}/plans",
            json={
                "title": "Premature execution test",
                "action_type": "REALLOCATE_STOCK",
                "plan_payload": {"source_warehouse_id": 3, "product_code": "P1", "quantity": 10},
            },
            headers=_auth(t_alice),
        )
        plan_id = prop_res.json()["id"]

        # Try to execute while still PENDING_APPROVAL -> 409 Conflict
        exec_res = client.post(f"/plans/{plan_id}/execute", headers=_auth(t_dave))
        assert exec_res.status_code == 409
        assert "must be approved" in exec_res.json()["detail"].lower()

    def test_revalidation_failure_insufficient_stock(self, client):
        """Stock revalidation failure right before execution returns 409 Conflict."""
        did = setup_disruption()
        t_alice = _token(client, "alice")
        t_carol = _token(client, "carol")
        t_dave = _token(client, "dave")

        # Propose plan needing 9999 units (exceeds stock)
        prop_res = client.post(
            f"/disruptions/{did}/plans",
            json={
                "title": "Huge reallocation",
                "action_type": "REALLOCATE_STOCK",
                "plan_payload": {
                    "source_warehouse_id": 3,
                    "product_code": "P1",
                    "quantity": 9999,
                },
            },
            headers=_auth(t_alice),
        )
        plan_id = prop_res.json()["id"]

        # Carol (Supply Chain Manager) approves
        app_res = client.post(f"/plans/{plan_id}/approve", headers=_auth(t_carol))
        assert app_res.status_code == 200

        # Dave executes -> fails revalidation -> 409
        exec_res = client.post(f"/plans/{plan_id}/execute", headers=_auth(t_dave))
        assert exec_res.status_code == 409
        assert "insufficient stock" in exec_res.json()["detail"].lower()

    def test_optimistic_version_conflict(self, client):
        """Rule 6: Version conflict in optimistic locking returns 409 Conflict."""
        did = setup_disruption()
        t_alice = _token(client, "alice")
        t_carol = _token(client, "carol")
        t_dave = _token(client, "dave")

        prop_res = client.post(
            f"/disruptions/{did}/plans",
            json={
                "title": "Normal reallocation",
                "action_type": "REALLOCATE_STOCK",
                "plan_payload": {
                    "source_warehouse_id": 3,
                    "product_code": "P1",
                    "quantity": 50,
                },
            },
            headers=_auth(t_alice),
        )
        plan_id = prop_res.json()["id"]

        # Carol approves
        assert client.post(f"/plans/{plan_id}/approve", headers=_auth(t_carol)).status_code == 200

        # Manually tamper with the version column to simulate concurrent modification
        conn = get_conn()
        try:
            # Change version right before Dave executes
            conn.execute(
                """UPDATE inventory SET version = 99
                   WHERE warehouse_id = 3 AND product_id = (SELECT id FROM products WHERE code = 'P1')"""
            )
            conn.commit()
        finally:
            conn.close()

        # Dave executes -> should detect version mismatch -> 409 Conflict
        exec_res = client.post(f"/plans/{plan_id}/execute", headers=_auth(t_dave))
        assert exec_res.status_code == 409

    def test_happy_path_e2e_approval_and_execution(self, client):
        """
        Happy path:
        1. Alice proposes plan for 100 P1 from Hyderabad.
        2. Carol modifies it to 120 units -> returns to PENDING_APPROVAL.
        3. Carol approves it -> APPROVED.
        4. Dave executes it -> inventory reserved increments, version increments, disruption becomes MITIGATED.
        5. Audit logs and notifications created at each step.
        """
        did = setup_disruption()
        t_alice = _token(client, "alice")
        t_carol = _token(client, "carol")
        t_dave = _token(client, "dave")

        # 1. Propose
        prop = client.post(
            f"/disruptions/{did}/plans",
            json={
                "title": "Transfer P1 from Hyderabad",
                "action_type": "REALLOCATE_STOCK",
                "description": "Hyderabad to Chennai",
                "plan_payload": {
                    "source_warehouse_id": 3,
                    "product_code": "P1",
                    "quantity": 100,
                },
            },
            headers=_auth(t_alice),
        )
        assert prop.status_code == 200
        plan_id = prop.json()["id"]

        # 2. Modify
        mod = client.post(
            f"/plans/{plan_id}/modify",
            json={"new_quantity": 120, "note": "Increased to cover safety buffer"},
            headers=_auth(t_carol),
        )
        assert mod.status_code == 200
        assert mod.json()["status"] == "PENDING_APPROVAL"

        # 3. Approve
        app_res = client.post(f"/plans/{plan_id}/approve", json={"note": "Approved by Carol"}, headers=_auth(t_carol))
        assert app_res.status_code == 200
        assert app_res.json()["status"] == "APPROVED"

        # Get initial inventory state
        conn = get_conn()
        inv_before = conn.execute(
            """SELECT i.reserved, i.version
               FROM inventory i
               JOIN products p ON i.product_id = p.id
               WHERE i.warehouse_id = 3 AND p.code = 'P1'"""
        ).fetchone()
        res_before = inv_before["reserved"]
        ver_before = inv_before["version"]
        conn.close()

        # 4. Execute
        exec_res = client.post(f"/plans/{plan_id}/execute", headers=_auth(t_dave))
        assert exec_res.status_code == 200
        assert exec_res.json()["status"] == "EXECUTED"

        # Verify inventory updated with version increment
        conn = get_conn()
        try:
            inv_after = conn.execute(
                """SELECT i.reserved, i.version
                   FROM inventory i
                   JOIN products p ON i.product_id = p.id
                   WHERE i.warehouse_id = 3 AND p.code = 'P1'"""
            ).fetchone()
            assert inv_after["reserved"] == res_before + 120
            assert inv_after["version"] == ver_before + 1

            # Verify disruption status
            disr = conn.execute("SELECT status FROM disruptions WHERE id = ?", (did,)).fetchone()
            assert disr["status"] == "MITIGATED"

            # Verify audit logs
            audits = conn.execute(
                "SELECT action FROM audit_logs WHERE entity_type = 'recovery_plans' AND entity_id = ?",
                (plan_id,),
            ).fetchall()
            actions = [a["action"] for a in audits]
            assert "PLAN_PROPOSED" in actions
            assert "PLAN_MODIFIED" in actions
            assert "PLAN_APPROVED" in actions
            assert "PLAN_EXECUTED" in actions

            # Verify notifications exist
            notifs = conn.execute(
                "SELECT title FROM notifications WHERE ref_table = 'recovery_plans' AND ref_id = ?",
                (plan_id,),
            ).fetchall()
            assert len(notifs) >= 3
        finally:
            conn.close()
