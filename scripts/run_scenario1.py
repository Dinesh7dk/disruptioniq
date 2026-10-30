"""
scripts/run_scenario1.py

Scenario 1: Supplier Delay
- Shipment SH-001 (Supplier A to Chennai, 500 x P1) is delayed by 6 days.
- Orders O-001 (HIGH, due day 3, 200 units), O-002 (MEDIUM, day 5, 150 units),
  and O-003 (LOW, day 9, 50 units) are affected.
- Hyderabad warehouse has spare P1 stock available for reallocation.

Usage:
    python scripts/run_scenario1.py
"""
import sys
import json
from pathlib import Path
from datetime import date, timedelta

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.seed.seed import seed
from backend.db import get_conn
from backend.services.detection import run_detection
from backend.services.recovery import generate_options


def main():
    print("=" * 72)
    print(" SCENARIO 1: SUPPLIER DELAY (SH-001 -> CHENNAI)")
    print("=" * 72)

    # Step 1: Reset & reseed
    print("\n[Step 1] Resetting and reseeding database to clean state...")
    seed()
    print("[OK] Database successfully reseeded.")

    # Step 2: Trigger shipment delay event
    print("\n[Step 2] Triggering carrier delay update on shipment SH-001...")
    conn = get_conn()
    try:
        sh = conn.execute(
            "SELECT id, code, expected_arrival FROM shipments WHERE code = 'SH-001'"
        ).fetchone()
        base_date = date.fromisoformat(sh["expected_arrival"])
        new_eta = (base_date + timedelta(days=6)).isoformat()
        shipment_id = sh["id"]

        conn.execute(
            "UPDATE shipments SET current_eta = ?, delay_days = 6, status = 'DELAYED' WHERE id = ?",
            (new_eta, shipment_id),
        )
        conn.execute(
            """INSERT INTO webhook_events (event_id, source, event_type, payload, status, processed_at)
               VALUES ('EVT-SCENARIO-1', 'carrier', 'CARRIER_UPDATE', ?, 'PROCESSED', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))""",
            (json.dumps({"shipment_ref": "SH-001", "status": "DELAYED", "delay_days": 6, "new_eta": new_eta}),),
        )
        conn.commit()
    finally:
        conn.close()
    print(f"[OK] Shipment SH-001 updated: Expected arrival={sh['expected_arrival']}, New ETA={new_eta} (+6 days delay).")

    # Step 3: Run Disruption Detection
    print("\n[Step 3] Running deterministic detection engine (run_detection)...")
    d_ids = run_detection(shipment_id=shipment_id)
    print(f"[OK] Disruption detected and registered: Disruption ID(s) = {d_ids}")

    conn = get_conn()
    try:
        disr = conn.execute(
            "SELECT id, type, status, description, ai_summary FROM disruptions WHERE id = ?",
            (d_ids[0],),
        ).fetchone()
        print(f"  - Type: {disr['type']}")
        print(f"  - Status: {disr['status']}")
        print(f"  - Description: {disr['description']}")
        if disr["ai_summary"]:
            print(f"  - AI Summary: {disr['ai_summary']}")

        # Step 4: Display Impact Analysis & Risk Scoring
        print("\n[Step 4] Querying affected orders ranked by composite risk score...")
        impacts = conn.execute(
            """SELECT di.order_id, di.risk_score, di.risk_level, di.units_at_risk,
                      di.risk_breakdown, di.risk_reasons,
                      o.code as order_code, o.customer, o.priority, o.due_date
               FROM disruption_impacts di
               JOIN orders o ON di.order_id = o.id
               WHERE di.disruption_id = ?
               ORDER BY di.risk_score DESC""",
            (d_ids[0],),
        ).fetchall()

        print(f"[OK] Total affected orders: {len(impacts)}")
        print("-" * 72)
        print(f"{'Order':<8} {'Customer':<20} {'Priority':<8} {'Due Date':<12} {'Risk Score':<10} {'Level'}")
        print("-" * 72)
        for r in impacts:
            print(f"{r['order_code']:<8} {r['customer']:<20} {r['priority']:<8} {r['due_date']:<12} {r['risk_score']:<10.1f} {r['risk_level']}")
            breakdown = json.loads(r["risk_breakdown"]) if r["risk_breakdown"] else {}
            reasons = json.loads(r["risk_reasons"]) if r["risk_reasons"] else []
            print(f"   -> Breakdown weights: {breakdown}")
            print(f"   -> Top risk reason: {reasons[0] if reasons else 'N/A'}")
        print("-" * 72)

        # Step 5: Generate Recovery Options
        print("\n[Step 5] Generating recovery options for top-risk order O-001...")
        o001 = conn.execute("SELECT id FROM orders WHERE code = 'O-001'").fetchone()
        options = generate_options(disruption_id=d_ids[0], order_id=o001["id"])

        print(f"[OK] Feasible options generated: {len(options)}")
        for idx, opt in enumerate(options, start=1):
            details = opt.get("details", {})
            src = details.get("source_warehouse_city", "Local")
            tgt = details.get("target_warehouse_city", "Chennai")
            qty = details.get("quantity", 0)
            desc = details.get("description", opt["type"])
            print(f"  [{idx}] {opt['type']} - {desc}")
            print(f"      Estimated cost: ${opt['cost']:.2f} | Delivery: {opt['new_delivery_date']} | Meets deadline: {opt['meets_deadline']}")
    finally:
        conn.close()

    print("\n" + "=" * 72)
    print(" SCENARIO 1 EXECUTION COMPLETE")
    print("=" * 72)


if __name__ == "__main__":
    main()
