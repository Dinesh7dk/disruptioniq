"""
scripts/stock_version_conflict.py

Demonstrates Hard Rule 6:
"Inventory updates use the version column inside a transaction"
(Optimistic Concurrency Control / Conflict Detection).

Usage:
    python scripts/stock_version_conflict.py
"""
import sys
from pathlib import Path
from datetime import date, timedelta
from fastapi.testclient import TestClient

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.seed.seed import seed
from backend.main import app
from backend.db import get_conn
from backend.services.detection import run_detection


def _token(client, username, password="pass123"):
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def main():
    print("=" * 72)
    print(" HARD RULE 6: INVENTORY OPTIMISTIC CONCURRENCY CONFLICT TEST")
    print("=" * 72)

    client = TestClient(app)

    # Step 1: Reseed and setup disruption
    print("\n[Step 1] Reseeding database and setting up Scenario 1 disruption...")
    seed()
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

    d_ids = run_detection(shipment_id=1)
    disruption_id = d_ids[0]

    # Step 2: Alice proposes and Carol approves
    print("\n[Step 2] Alice proposes recovery plan, Carol approves...")
    token_alice = _token(client, "alice")
    token_carol = _token(client, "carol")

    prop_res = client.post(
        f"/disruptions/{disruption_id}/plans",
        json={
            "title": "Transfer P1 from Hyderabad to Chennai",
            "action_type": "REALLOCATE_STOCK",
            "description": "Stock reallocation under optimistic concurrency control",
            "plan_payload": {
                "source_warehouse_id": 3,
                "product_code": "P1",
                "quantity": 100,
            },
        },
        headers={"Authorization": f"Bearer {token_alice}"},
    )
    assert prop_res.status_code == 200
    plan_id = prop_res.json()["id"]

    app_res = client.post(
        f"/plans/{plan_id}/approve",
        headers={"Authorization": f"Bearer {token_carol}"},
    )
    assert app_res.status_code == 200
    print(f"[OK] Plan #{plan_id} approved. Ready for execution.")

    # Inspect current inventory state before execution
    conn = get_conn()
    try:
        inv_before = conn.execute(
            """SELECT i.on_hand, i.reserved, i.version, w.city, p.code
               FROM inventory i
               JOIN warehouses w ON i.warehouse_id = w.id
               JOIN products p ON i.product_id = p.id
               WHERE w.city = 'Hyderabad' AND p.code = 'P1'"""
        ).fetchone()
        print(f"Current inventory at Hyderabad P1: on_hand={inv_before['on_hand']}, reserved={inv_before['reserved']}, version={inv_before['version']}")

        # Step 3: Simulate concurrent modification by bumping version
        print("\n[Step 3] Simulating concurrent inventory modification by another process...")
        conn.execute(
            """UPDATE inventory SET version = 99
               WHERE warehouse_id = 3 AND product_id = (SELECT id FROM products WHERE code = 'P1')"""
        )
        conn.commit()
        inv_tampered = conn.execute(
            "SELECT version FROM inventory WHERE warehouse_id = 3 AND product_id = (SELECT id FROM products WHERE code = 'P1')"
        ).fetchone()
        print(f"Version tampered to: {inv_tampered['version']} (simulating race condition / prior commit)")
    finally:
        conn.close()

    # Step 4: Dave attempts execution
    print("\n[Step 4] Dave (Warehouse Operator) attempts to execute plan...")
    token_dave = _token(client, "dave")
    exec_res = client.post(
        f"/plans/{plan_id}/execute",
        headers={"Authorization": f"Bearer {token_dave}"},
    )
    print(f"Response status: {exec_res.status_code}")
    print(f"Response body: {exec_res.json()}")

    # Verify HTTP 409 Conflict
    assert exec_res.status_code == 409
    detail = exec_res.json().get("detail", "")
    assert "version" in detail.lower() or "conflict" in detail.lower() or "concurrent" in detail.lower()
    print("[OK] Execution rejected with HTTP 409 Conflict as required by Hard Rule 6.")
    print(f"Conflict detail: {detail}")

    # Step 5: Verify transaction rollback & safety
    print("\n[Step 5] Verifying inventory safety after conflict rollback...")
    conn = get_conn()
    try:
        inv_after = conn.execute(
            """SELECT i.on_hand, i.reserved, i.version
               FROM inventory i
               WHERE warehouse_id = 3 AND product_id = (SELECT id FROM products WHERE code = 'P1')"""
        ).fetchone()
        print(f"Inventory after rollback: on_hand={inv_after['on_hand']}, reserved={inv_after['reserved']}")
        assert inv_after["reserved"] == inv_before["reserved"], "Reserved inventory should NOT have changed on conflict!"
        print("[OK] Inventory reservations were NOT corrupted. Atomic rollback confirmed.")
    finally:
        conn.close()

    print("\n" + "=" * 72)
    print(" OPTIMISTIC CONCURRENCY CONFLICT VERIFICATION PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
