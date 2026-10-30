"""
scripts/self_approval_blocked.py

Demonstrates Hard Rule 4:
"No self-approval: approver must differ from proposer."

Covers:
1. Recovery Plan workflow: Alice proposes plan, self-approval is blocked (403), Carol approves.
2. Message Draft workflow: Alice creates draft, self-approval is blocked (403), Bob approves.

Usage:
    python scripts/self_approval_blocked.py
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
    if username == "admin":
        password = "admin123"
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def main():
    print("=" * 72)
    print(" HARD RULE 4: SELF-APPROVAL PREVENTION TEST")
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
    print(f"[OK] Disruption #{disruption_id} created.")

    # ── PART 1: RECOVERY PLAN APPROVAL WORKFLOW ───────────────────────────────
    print("\n" + "-" * 72)
    print(" PART 1: RECOVERY PLAN SELF-APPROVAL")
    print("-" * 72)

    # Step 2: Alice proposes a recovery plan
    print("\n[Step 2] Alice (Operations Analyst) proposes a recovery plan...")
    token_alice = _token(client, "alice")
    auth_alice = {"Authorization": f"Bearer {token_alice}"}

    prop_res = client.post(
        f"/disruptions/{disruption_id}/plans",
        json={
            "title": "Stock Reallocation from Hyderabad",
            "action_type": "REALLOCATE_STOCK",
            "description": "Transfer 200 units of P1 to prevent O-001 breach",
            "plan_payload": {
                "source_warehouse_id": 3,
                "product_code": "P1",
                "quantity": 200,
            },
        },
        headers=auth_alice,
    )
    assert prop_res.status_code == 200, prop_res.text
    plan_data = prop_res.json()
    plan_id = plan_data["id"]
    print(f"[OK] Plan #{plan_id} proposed by Alice. Status: '{plan_data['status']}'.")

    # Step 3: Alice attempts to approve her own recovery plan
    print("\n[Step 3] Alice attempts to approve her own proposed plan...")
    self_app_res = client.post(
        f"/plans/{plan_id}/approve",
        json={"note": "Self-approving my own proposal"},
        headers=auth_alice,
    )
    print(f"Response status: {self_app_res.status_code}")
    print(f"Response body: {self_app_res.json()}")

    assert self_app_res.status_code == 403
    print("[OK] Self-approval blocked by backend with HTTP 403 Forbidden.")

    # Step 4: Carol (Supply Chain Manager) approves the plan
    print("\n[Step 4] Carol (Supply Chain Manager) reviews and approves the plan...")
    token_carol = _token(client, "carol")
    auth_carol = {"Authorization": f"Bearer {token_carol}"}

    carol_app_res = client.post(
        f"/plans/{plan_id}/approve",
        json={"note": "Approved by Supply Chain Manager after feasibility check"},
        headers=auth_carol,
    )
    assert carol_app_res.status_code == 200
    assert carol_app_res.json()["status"] == "APPROVED"
    print(f"[OK] Plan successfully approved by Carol (approver != proposer). Status: {carol_app_res.json()['status']}")

    # ── PART 2: MESSAGE DRAFT APPROVAL WORKFLOW ───────────────────────────────
    print("\n" + "-" * 72)
    print(" PART 2: DRAFTED MESSAGE SEPARATION OF DUTY")
    print("-" * 72)

    # Step 5: Alice generates a customer message draft for Order 1
    print("\n[Step 5] Alice generates customer message draft for Order #1...")
    draft_res = client.post(
        "/orders/1/drafts",
        json={"audience": "CUSTOMER"},
        headers=auth_alice,
    )
    assert draft_res.status_code == 200, draft_res.text
    draft_id = draft_res.json()["id"]
    print(f"[OK] Draft #{draft_id} created by Alice. Status: 'DRAFT'.")

    # Step 6: Alice attempts to approve her own message draft
    print("\n[Step 6] Alice attempts to approve her own message draft...")
    draft_self_res = client.post(
        f"/drafts/{draft_id}/approve",
        headers=auth_alice,
    )
    print(f"Response status: {draft_self_res.status_code}")
    print(f"Response body: {draft_self_res.json()}")

    assert draft_self_res.status_code == 403
    detail = draft_self_res.json().get("detail", "")
    assert "separation of duty" in detail.lower()
    print(f"[OK] Draft self-approval blocked by backend (HTTP 403 Forbidden).")
    print(f"Rejection detail: '{detail}'")

    # Step 7: Bob (second Operations Analyst) approves Alice's draft
    print("\n[Step 7] Bob (peer Operations Analyst) reviews and approves Alice's draft...")
    token_bob = _token(client, "bob")
    auth_bob = {"Authorization": f"Bearer {token_bob}"}

    bob_app_res = client.post(
        f"/drafts/{draft_id}/approve",
        headers=auth_bob,
    )
    assert bob_app_res.status_code == 200
    assert bob_app_res.json()["status"] == "APPROVED"
    print(f"[OK] Draft successfully approved by Bob. Status: '{bob_app_res.json()['status']}'.")

    print("\n" + "=" * 72)
    print(" HARD RULE 4 (NO SELF-APPROVAL) VERIFICATION PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
