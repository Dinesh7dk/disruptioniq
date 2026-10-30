"""
scripts/duplicate_webhook.py

Demonstrates Hard Rule 5:
"Duplicate webhook events are ignored via unique event_id."

Usage:
    python scripts/duplicate_webhook.py
"""
import sys
import json
from pathlib import Path
from fastapi.testclient import TestClient

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.seed.seed import seed
from backend.main import app
from backend.db import get_conn


def main():
    print("=" * 72)
    print(" HARD RULE 5: DUPLICATE WEBHOOK IDEMPOTENCY TEST")
    print("=" * 72)

    client = TestClient(app)

    # Step 1: Reset database
    print("\n[Step 1] Reseeding database to clean state...")
    seed()
    print("[OK] Database reseeded.")

    # Step 2: Send first webhook event
    event_id = "EVT-CARRIER-TEST-999"
    payload1 = {
        "event_id": event_id,
        "shipment_ref": "SH-001",
        "status": "DELAYED",
        "new_eta": "2026-11-10",
    }
    print(f"\n[Step 2] Sending initial carrier webhook with event_id='{event_id}'...")
    print(f"Payload: {json.dumps(payload1, indent=2)}")

    res1 = client.post("/webhooks/carrier", json=payload1)
    print(f"Response status: {res1.status_code}")
    print(f"Response body: {res1.json()}")
    assert res1.status_code == 200
    assert res1.json()["status"] == "processed"
    print("[OK] Initial webhook successfully processed.")

    # Verify DB update
    conn = get_conn()
    try:
        sh1 = conn.execute("SELECT status, current_eta FROM shipments WHERE code = 'SH-001'").fetchone()
        evt_cnt1 = conn.execute(
            "SELECT COUNT(*) as cnt FROM webhook_events WHERE event_id = ?", (event_id,)
        ).fetchone()["cnt"]
        print(f"Shipment SH-001 status in DB: {sh1['status']}, current_eta: {sh1['current_eta']}")
        print(f"Events recorded with this ID: {evt_cnt1}")
    finally:
        conn.close()

    # Step 3: Send duplicate webhook event with modified payload
    payload2 = {
        "event_id": event_id,  # Same event ID!
        "shipment_ref": "SH-001",
        "status": "ARRIVED",    # Different status attempt
        "new_eta": "2026-11-01",
    }
    print(f"\n[Step 3] Sending duplicate webhook with the same event_id='{event_id}'...")
    print(f"Payload: {json.dumps(payload2, indent=2)}")

    res2 = client.post("/webhooks/carrier", json=payload2)
    print(f"Response status: {res2.status_code}")
    print(f"Response body: {res2.json()}")
    assert res2.status_code == 200
    assert res2.json() == {"status": "duplicate, ignored"}
    print("[OK] Duplicate webhook was ignored by backend as expected.")

    # Step 4: Verify database was NOT corrupted or altered
    print("\n[Step 4] Verifying database integrity...")
    conn = get_conn()
    try:
        sh2 = conn.execute("SELECT status, current_eta FROM shipments WHERE code = 'SH-001'").fetchone()
        evt_cnt2 = conn.execute(
            "SELECT COUNT(*) as cnt FROM webhook_events WHERE event_id = ?", (event_id,)
        ).fetchone()["cnt"]

        print(f"Shipment SH-001 status in DB remains: '{sh2['status']}' (not changed to ARRIVED)")
        print(f"Shipment SH-001 ETA in DB remains: '{sh2['current_eta']}' (not changed to 2026-11-01)")
        print(f"Event records in webhook_events table: {evt_cnt2} (no duplicate row added)")

        assert sh2["status"] == "DELAYED"
        assert sh2["current_eta"] == "2026-11-10"
        assert evt_cnt2 == 1
    finally:
        conn.close()

    print("\n" + "=" * 72)
    print(" DUPLICATE WEBHOOK VERIFICATION PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
