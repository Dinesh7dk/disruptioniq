"""
scripts/run_scenario2.py

Scenario 2: Stock Shortage
- Bangalore warehouse P2 inventory has on_hand=40, reserved=35 (available=5 units).
- Open orders O-004 (40 units) and O-005 (20 units) require 60 units total.
- Net shortfall of 55 units triggers a STOCK_SHORTAGE disruption.
- Hyderabad warehouse has spare P2 (300 available); stock reallocation is recommended.

Usage:
    python scripts/run_scenario2.py
"""
import sys
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.seed.seed import seed
from backend.db import get_conn
from backend.services.detection import detect_stock_shortages, analyze_impact
from backend.services.ai import generate_ai_summary
from backend.services.recovery import generate_options


def main():
    print("=" * 72)
    print(" SCENARIO 2: STOCK SHORTAGE (BANGALORE P2)")
    print("=" * 72)

    # Step 1: Reset & reseed
    print("\n[Step 1] Resetting and reseeding database to clean state...")
    seed()
    print("[OK] Database successfully reseeded.")

    # Step 2: Check current inventory and demand
    print("\n[Step 2] Inspecting inventory and open order demand at Bangalore for P2...")
    conn = get_conn()
    try:
        inv = conn.execute(
            """SELECT i.on_hand, i.reserved, (i.on_hand - i.reserved) as available,
                      w.city, p.code, p.name
               FROM inventory i
               JOIN warehouses w ON i.warehouse_id = w.id
               JOIN products p ON i.product_id = p.id
               WHERE w.city = 'Bangalore' AND p.code = 'P2'"""
        ).fetchone()

        demand_rows = conn.execute(
            """SELECT o.code, o.customer, ol.quantity, o.priority, o.due_date
               FROM order_lines ol
               JOIN orders o ON ol.order_id = o.id
               JOIN warehouses w ON ol.warehouse_id = w.id
               JOIN products p ON ol.product_id = p.id
               WHERE w.city = 'Bangalore' AND p.code = 'P2' AND o.status = 'OPEN'"""
        ).fetchall()

        total_demand = sum(r["quantity"] for r in demand_rows)
        shortfall = total_demand - inv["available"]

        print(f"[OK] Inventory: on_hand={inv['on_hand']}, reserved={inv['reserved']} => available={inv['available']} units.")
        print(f"[OK] Open orders requiring P2 at Bangalore: {len(demand_rows)} orders, total demand={total_demand} units.")
        for r in demand_rows:
            print(f"   - {r['code']} ({r['customer']}): {r['quantity']} units, Priority {r['priority']}, Due {r['due_date']}")
        print(f"[OK] Calculated shortfall: {total_demand} - {inv['available']} = {shortfall} units.")

        # Step 3: Trigger Stock Shortage Detection
        print("\n[Step 3] Running stock shortage detection engine...")
        disruption_ids = detect_stock_shortages()
        print(f"[OK] Detection run: detected {len(disruption_ids)} shortage(s). IDs: {disruption_ids}")

        for did in disruption_ids:
            analyze_impact(did)
            generate_ai_summary(did)

        # Locate the Bangalore P2 disruption
        disr = conn.execute(
            """SELECT d.*, p.code as pcode, w.city as wcity
               FROM disruptions d
               JOIN products p ON d.product_id = p.id
               JOIN warehouses w ON d.warehouse_id = w.id
               WHERE d.type = 'STOCK_SHORTAGE' AND p.code = 'P2' AND w.city = 'Bangalore' AND d.status = 'OPEN'"""
        ).fetchone()

        print(f"\n[Step 4] Disruption Profile #{disr['id']}:")
        print(f"  - Type: {disr['type']}")
        print(f"  - Target: {disr['pcode']} at {disr['wcity']} warehouse")
        print(f"  - Description: {disr['description']}")
        if disr["ai_summary"]:
            print(f"  - AI Summary: {disr['ai_summary']}")

        # Step 5: Query Impacts
        impacts = conn.execute(
            """SELECT di.order_id, di.risk_score, di.risk_level, di.units_at_risk,
                      o.code as order_code, o.customer, o.priority, o.due_date
               FROM disruption_impacts di
               JOIN orders o ON di.order_id = o.id
               WHERE di.disruption_id = ?
               ORDER BY di.risk_score DESC""",
            (disr["id"],),
        ).fetchall()

        print(f"\n[Step 5] Impacted Orders (Total: {len(impacts)}):")
        print("-" * 72)
        for r in impacts:
            print(f"  * {r['order_code']} ({r['customer']}): Risk Score {r['risk_score']} ({r['risk_level']}) | Units at risk: {r['units_at_risk']}")

        # Step 6: Generate Recovery Options
        print("\n[Step 6] Generating recovery recommendations...")
        options = generate_options(disruption_id=disr["id"])
        print(f"[OK] Generated {len(options)} recovery options across affected orders.")

        hyd_options = [
            opt for opt in options
            if opt["type"] == "REALLOCATE_STOCK" and opt.get("details", {}).get("source_warehouse_city") == "Hyderabad"
        ]
        print(f"[OK] Feasible Hyderabad reallocations found: {len(hyd_options)}")
        for opt in hyd_options:
            order_info = opt.get("order", {})
            details = opt.get("details", {})
            print(f"  - Reallocate {details.get('quantity')} P2 from Hyderabad to Bangalore for {order_info.get('code')} ({order_info.get('customer')})")
            print(f"    Estimated cost: ${opt['cost']:.2f} | Delivery: {opt['new_delivery_date']} | Meets deadline: {opt['meets_deadline']}")
    finally:
        conn.close()

    print("\n" + "=" * 72)
    print(" SCENARIO 2 EXECUTION COMPLETE")
    print("=" * 72)


if __name__ == "__main__":
    main()
