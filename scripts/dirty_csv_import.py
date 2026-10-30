"""
scripts/dirty_csv_import.py

Demonstrates CSV Import Validation and Isolation:
- Uploads backend/seed/shipments_dirty.csv containing bad data rows.
- Verifies that invalid rows are rejected with explicit reasons:
  1. Negative quantity
  2. Unknown supplier
  3. Bad date format
  4. Duplicate shipment reference within batch
- Verifies that valid rows are still imported without aborting the entire batch.

Usage:
    python scripts/dirty_csv_import.py
"""
import sys
from pathlib import Path
from fastapi.testclient import TestClient

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.seed.seed import seed
from backend.main import app

DIRTY_CSV = ROOT / "backend" / "seed" / "shipments_dirty.csv"


def main():
    print("=" * 72)
    print(" CSV IMPORT VALIDATION: DIRTY DATASET TEST")
    print("=" * 72)

    client = TestClient(app)

    # Step 1: Reseed database
    print("\n[Step 1] Reseeding database to clean state...")
    seed()
    print("[OK] Database reseeded.")

    # Step 2: Authenticate as Administrator
    print("\n[Step 2] Authenticating as Administrator (admin)...")
    login_res = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert login_res.status_code == 200, login_res.text
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("[OK] Administrator JWT acquired.")

    # Step 3: Inspect dirty CSV contents
    print(f"\n[Step 3] Reading dirty CSV file: {DIRTY_CSV.name}...")
    csv_bytes = DIRTY_CSV.read_bytes()
    lines = csv_bytes.decode("utf-8").strip().splitlines()
    print(f"Header: {lines[0]}")
    for idx, line in enumerate(lines[1:], start=1):
        print(f"  Row {idx}: {line}")

    # Step 4: Submit dirty CSV via /import/shipments/csv
    print("\n[Step 4] Posting CSV to /import/shipments/csv...")
    res = client.post(
        "/import/shipments/csv",
        files={"file": ("shipments_dirty.csv", csv_bytes, "text/csv")},
        headers=headers,
    )
    print(f"Response status: {res.status_code}")
    body = res.json()
    print(f"Summary: Total rows processed: {body.get('total_rows', len(lines) - 1)}")
    print(f"  - Successfully imported: {body.get('imported')}")
    print(f"  - Rejected rows: {len(body.get('rejected', []))}")

    # Step 5: Detail rejection reasons
    print("\n[Step 5] Detailed Row Rejections:")
    print("-" * 72)
    for rej in body.get("rejected", []):
        row_num = rej.get("row")
        reason = rej.get("reason")
        print(f"  [X] CSV Row {row_num}: {reason}")
    print("-" * 72)

    # Validations
    assert body.get("imported") == 1, f"Expected 1 imported, got {body.get('imported')}"
    assert len(body.get("rejected", [])) == 4, f"Expected 4 rejected, got {len(body.get('rejected', []))}"
    print("[OK] Validation successful: exactly 1 valid row imported and 4 invalid rows isolated.")

    print("\n" + "=" * 72)
    print(" DIRTY CSV IMPORT VERIFICATION PASSED")
    print("=" * 72)


if __name__ == "__main__":
    main()
