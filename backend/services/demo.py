"""
backend/services/demo.py

Service functions for Demo-only capabilities:
- Hard rule 13: Demo-only endpoints work only when DEMO_MODE=true in .env and only for Administrator.
- Resets and reseeds the database.
- Scenario 1: Supplier delay on SH-001 (affecting O-001, O-002, O-003; Hyderabad has spare P1).
- Scenario 2: Stock shortage for Bangalore P2 (affecting O-004, O-005; Hyderabad has spare P2).
"""
import os
import json
from datetime import date, timedelta, datetime
from typing import Any
from fastapi import HTTPException, status

from backend.db import get_conn
from backend.seed.seed import seed as _do_seed
from backend.services.detection import run_detection, detect_stock_shortages, analyze_impact
from backend.services.ai import generate_ai_summary
from backend.services.recovery import generate_options


def check_demo_mode():
    """Verify DEMO_MODE=true in environment."""
    if os.getenv("DEMO_MODE", "false").lower() != "true":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo endpoints are disabled. DEMO_MODE must be set to 'true'.",
        )


def reset_demo_database(actor_id: int | None = None) -> dict[str, Any]:
    """
    Reseeds the database to clean demo state and records audit log.
    """
    check_demo_mode()
    _do_seed()

    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO audit_logs (actor_id, action, entity_type, entity_id, note)
               VALUES (?, 'DEMO_RESET_DATABASE', 'system', 0, 'Database reset and reseeded to clean demo state')""",
            (actor_id,),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "status": "ok",
        "message": "Database reset and reseeded successfully",
    }


def trigger_scenario_1(actor_id: int | None = None) -> dict[str, Any]:
    """
    Triggers Demo Scenario 1:
    - Supplier delay: shipment SH-001 (Supplier A to Chennai, 500 x P1) is delayed by 6 days.
    - Orders O-001 (HIGH, due day 3, 200), O-002 (MEDIUM, day 5, 150),
      O-003 (LOW, day 9, 50) are affected.
    - Hyderabad warehouse has spare P1 available for reallocation.
    """
    check_demo_mode()

    conn = get_conn()
    try:
        sh = conn.execute(
            "SELECT id, code, expected_arrival FROM shipments WHERE code = 'SH-001'"
        ).fetchone()
        if not sh:
            raise HTTPException(status_code=404, detail="Shipment SH-001 not found")

        shipment_id = sh["id"]
        base_date = date.fromisoformat(sh["expected_arrival"])
        new_eta = (base_date + timedelta(days=6)).isoformat()

        # Update shipment to DELAYED with new ETA
        conn.execute(
            "UPDATE shipments SET current_eta = ?, delay_days = 6, status = 'DELAYED' WHERE id = ?",
            (new_eta, shipment_id),
        )

        # Log simulated carrier webhook event
        evt_id = f"EVT-SCENARIO-1-{int(datetime.now().timestamp())}"
        conn.execute(
            """INSERT INTO webhook_events (event_id, source, event_type, payload, status, processed_at)
               VALUES (?, 'carrier', 'CARRIER_UPDATE', ?, 'PROCESSED', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))""",
            (
                evt_id,
                json.dumps({
                    "shipment_ref": "SH-001",
                    "status": "DELAYED",
                    "delay_days": 6,
                    "new_eta": new_eta,
                }),
            ),
        )

        # Audit log entry
        conn.execute(
            """INSERT INTO audit_logs (actor_id, action, entity_type, entity_id, note)
               VALUES (?, 'DEMO_SCENARIO_1_TRIGGERED', 'shipments', ?, 'Carrier webhook reported SH-001 delayed by 6 days')""",
            (actor_id, shipment_id),
        )
        conn.commit()
    finally:
        conn.close()

    # Run detection, impact scoring, and AI summary
    created_disruptions = run_detection(shipment_id=shipment_id)

    # Fetch created disruption details
    conn = get_conn()
    try:
        disr = conn.execute(
            "SELECT * FROM disruptions WHERE shipment_id = ? AND status = 'OPEN'",
            (shipment_id,),
        ).fetchone()
        if not disr:
            disruption_id = created_disruptions[0] if created_disruptions else None
            disr = conn.execute("SELECT * FROM disruptions WHERE id = ?", (disruption_id,)).fetchone()
        else:
            disruption_id = disr["id"]

        impacts = conn.execute(
            """SELECT di.*, o.code as order_code, o.customer, o.priority, o.due_date
               FROM disruption_impacts di
               JOIN orders o ON di.order_id = o.id
               WHERE di.disruption_id = ?
               ORDER BY di.risk_score DESC""",
            (disruption_id,),
        ).fetchall()
    finally:
        conn.close()

    # Generate feasible options for first order
    options = []
    if disruption_id:
        options = generate_options(disruption_id=disruption_id)

    return {
        "status": "ok",
        "scenario": 1,
        "name": "Supplier Delay (SH-001)",
        "disruption": dict(disr) if disr else None,
        "impacts": [dict(i) for i in impacts],
        "options_count": len(options),
        "message": f"Scenario 1 triggered: Disruption #{disruption_id} created with {len(impacts)} affected orders.",
    }


def trigger_scenario_2(actor_id: int | None = None) -> dict[str, Any]:
    """
    Triggers Demo Scenario 2:
    - Stock shortage: Bangalore P2 on_hand 40, reserved 35 (available 5).
    - Orders O-004 and O-005 need 60 units total (shortfall 55).
    - Hyderabad warehouse has spare P2 (300 available); reallocation recommended.
    """
    check_demo_mode()

    # Detect stock shortages
    shortage_ids = detect_stock_shortages()
    for did in shortage_ids:
        analyze_impact(did)
        generate_ai_summary(did)

    conn = get_conn()
    try:
        # Find Bangalore P2 disruption
        disr = conn.execute(
            """SELECT d.*, p.code as pcode, w.city as wcity
               FROM disruptions d
               JOIN products p ON d.product_id = p.id
               JOIN warehouses w ON d.warehouse_id = w.id
               WHERE d.type = 'STOCK_SHORTAGE' AND p.code = 'P2' AND w.city = 'Bangalore' AND d.status = 'OPEN'"""
        ).fetchone()

        if not disr and shortage_ids:
            disr = conn.execute("SELECT * FROM disruptions WHERE id = ?", (shortage_ids[0],)).fetchone()

        disruption_id = disr["id"] if disr else None

        impacts = []
        if disruption_id:
            impacts = conn.execute(
                """SELECT di.*, o.code as order_code, o.customer, o.priority, o.due_date
                   FROM disruption_impacts di
                   JOIN orders o ON di.order_id = o.id
                   WHERE di.disruption_id = ?
                   ORDER BY di.risk_score DESC""",
                (disruption_id,),
            ).fetchall()

        # Audit log entry
        conn.execute(
            """INSERT INTO audit_logs (actor_id, action, entity_type, entity_id, note)
               VALUES (?, 'DEMO_SCENARIO_2_TRIGGERED', 'disruptions', ?, 'Detected stock shortage for P2 at Bangalore warehouse')""",
            (actor_id, disruption_id if disruption_id is not None else 0),
        )
        conn.commit()
    finally:
        conn.close()

    options = []
    if disruption_id:
        options = generate_options(disruption_id=disruption_id)

    return {
        "status": "ok",
        "scenario": 2,
        "name": "Stock Shortage (Bangalore P2)",
        "disruption": dict(disr) if disr else None,
        "impacts": [dict(i) for i in impacts],
        "options_count": len(options),
        "message": f"Scenario 2 triggered: Stock shortage disruption #{disruption_id} with {len(impacts)} affected orders.",
    }
