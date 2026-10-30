import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import json
from fastapi.testclient import TestClient
from backend.main import app
from backend.db import get_conn

def run_flow():
    client = TestClient(app)
    
    print("=================================================================")
    print("STEP 1: Log in as Anita (Operations Analyst)")
    print("=================================================================")
    resp = client.post("/auth/login", json={"username": "anita", "password": "pass123"})
    assert resp.status_code == 200, resp.text
    anita_token = resp.json()["access_token"]
    print(f"Anita Logged In: Role = {resp.json()['role']}")
    print(f"Token: {anita_token[:25]}...")
    
    print("\n=================================================================")
    print("STEP 2: Log in as Meera (Supply Chain Manager)")
    print("=================================================================")
    resp = client.post("/auth/login", json={"username": "meera", "password": "pass123"})
    assert resp.status_code == 200, resp.text
    meera_token = resp.json()["access_token"]
    print(f"Meera Logged In: Role = {resp.json()['role']}")
    
    print("\n=================================================================")
    print("STEP 3: Log in as Ravi (Warehouse Operator)")
    print("=================================================================")
    resp = client.post("/auth/login", json={"username": "ravi", "password": "pass123"})
    assert resp.status_code == 200, resp.text
    ravi_token = resp.json()["access_token"]
    print(f"Ravi Logged In: Role = {resp.json()['role']}")

    print("\n=================================================================")
    print("STEP 4: Anita proposes a recovery plan for Disruption 1")
    print("=================================================================")
    plan_body = {
        "title": "Transfer P1 from Hyderabad to Chennai for O-001",
        "action_type": "REALLOCATE_STOCK",
        "description": "Transfer 200 units of P1 from Hyderabad warehouse to Chennai warehouse to fulfill order O-001 on time.",
        "plan_payload": {
            "order_id": 1,
            "order_code": "O-001",
            "source_warehouse_id": 3,
            "product_code": "P1",
            "quantity": 200,
            "cost": 1500.0,
            "new_delivery_date": "2026-11-02",
            "meets_deadline": True
        }
    }
    resp = client.post(
        "/disruptions/1/plans",
        json=plan_body,
        headers={"Authorization": f"Bearer {anita_token}"}
    )
    print(f"Propose Status Code: {resp.status_code}")
    plan = resp.json()
    print("Proposed Plan Response:")
    print(json.dumps(plan, indent=2))
    assert resp.status_code == 200
    plan_id = plan["id"]

    print("\n=================================================================")
    print("STEP 5: Anita attempts to approve her OWN plan (Self-Approval Check)")
    print("=================================================================")
    resp = client.post(
        f"/plans/{plan_id}/approve",
        json={"note": "Self approving my own plan"},
        headers={"Authorization": f"Bearer {anita_token}"}
    )
    print(f"Self-Approval Status Code: {resp.status_code} (Expected 403)")
    print(f"Response: {resp.text}")
    assert resp.status_code == 403

    print("\n=================================================================")
    print("STEP 6: Meera (Supply Chain Manager) approves Anita's plan")
    print("=================================================================")
    resp = client.post(
        f"/plans/{plan_id}/approve",
        json={"note": "Approved reallocation from Hyderabad. Cost Rs. 1500 verified."},
        headers={"Authorization": f"Bearer {meera_token}"}
    )
    print(f"Approval Status Code: {resp.status_code} (Expected 200)")
    print("Approved Plan:")
    print(json.dumps(resp.json(), indent=2))
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"

    print("\n=================================================================")
    print("STEP 7: Ravi (Warehouse Operator) executes the approved plan")
    print("=================================================================")
    resp = client.post(
        f"/plans/{plan_id}/execute",
        headers={"Authorization": f"Bearer {ravi_token}"}
    )
    print(f"Execute Status Code: {resp.status_code} (Expected 200)")
    print("Executed Plan:")
    print(json.dumps(resp.json(), indent=2))
    assert resp.status_code == 200
    assert resp.json()["status"] == "EXECUTED"

    print("\n=================================================================")
    print("STEP 8: Verify Inventory and Audit Logs")
    print("=================================================================")
    conn = get_conn()
    try:
        inv = conn.execute(
            "SELECT i.id, w.name, p.code, i.on_hand, i.reserved, i.version "
            "FROM inventory i "
            "JOIN warehouses w ON w.id = i.warehouse_id "
            "JOIN products p ON p.id = i.product_id "
            "WHERE i.warehouse_id = 3 AND p.code = 'P1'"
        ).fetchone()
        print(f"Updated Hyderabad P1 Inventory: on_hand={inv['on_hand']}, reserved={inv['reserved']}, version={inv['version']}")

        audits = conn.execute(
            "SELECT action, entity_type, actor_id, created_at, old_value, new_value "
            "FROM audit_logs WHERE entity_type = 'recovery_plans' AND entity_id = ? "
            "ORDER BY id ASC",
            (plan_id,)
        ).fetchall()
        print(f"Audit log entries recorded: {len(audits)}")
        for a in audits:
            print(f" - [{a['created_at']}] Action: {a['action']} by actor_id {a['actor_id']}")
    finally:
        conn.close()

    print("\nSUCCESS: Complete workflow verified!")

if __name__ == "__main__":
    run_flow()
