"""
scripts/send_fake_event.py

Sends a simulated carrier webhook event twice to http://localhost:8000/webhooks/carrier
to demonstrate idempotent deduplication.
"""
import sys
import time
import requests

API_URL = "http://localhost:8000/webhooks/carrier"

fake_event = {
    "event_id": f"EVT-DEMO-{int(time.time())}",
    "shipment_ref": "SH-001",
    "status": "DELAYED",
    "new_eta": "2026-11-08",
}

def main():
    print("=" * 60)
    print("Carrier Webhook Deduplication Demo")
    print("=" * 60)
    print(f"Target URL: {API_URL}")
    print(f"Payload:\n  {fake_event}\n")

    # Send 1
    print("--- [1] Sending first event ---")
    try:
        r1 = requests.post(API_URL, json=fake_event, timeout=5)
        print(f"Status Code: {r1.status_code}")
        print(f"Response:    {r1.text}\n")
    except Exception as e:
        print(f"Error connecting to backend: {e}")
        print("Make sure the backend is running (run scripts/start.bat or scripts/start.ps1)")
        sys.exit(1)

    # Send 2 (duplicate)
    print("--- [2] Sending duplicate event (same event_id) ---")
    r2 = requests.post(API_URL, json=fake_event, timeout=5)
    print(f"Status Code: {r2.status_code}")
    print(f"Response:    {r2.text}\n")

    if r1.status_code == 200 and r2.status_code == 200:
        if "duplicate" in r2.text.lower():
            print("[SUCCESS] First event was processed, second event was detected as duplicate and ignored!")
        else:
            print("[WARNING] Expected duplicate response on second call.")

if __name__ == "__main__":
    main()
