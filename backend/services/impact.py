"""
backend/services/impact.py

Impact Analysis Service.
NO LLM CALLS.

For a detected disruption:
1. Find open order lines requiring the affected product at the affected warehouse.
2. For each line, compute:
   - buffer_days = (order.due_date - new_availability_date - 1 day handling).
   - shortfall = max(0, order_line.quantity - local_available_stock).
3. Compute explainable risk score via backend.services.risk.calculate_risk.
4. Atomically insert or update disruption_impacts records with:
   - risk_score, risk_level, risk_breakdown (JSON), risk_reasons (JSON), units_at_risk.
"""
import json
from datetime import date
from typing import Any
from backend.db import get_conn
from backend.services.risk import calculate_risk


def parse_iso_date(d_str: str) -> date:
    return date.fromisoformat(d_str.split("T")[0])


def analyze_impact(disruption_id: int) -> list[dict[str, Any]]:
    """
    Run impact analysis for the given disruption and save disruption_impacts rows.
    Returns list of evaluated impacts.
    """
    conn = get_conn()
    impacts: list[dict[str, Any]] = []
    try:
        # Load disruption details
        disruption = conn.execute(
            """SELECT d.*, s.current_eta, s.expected_arrival, s.delay_days,
                      s.product_id AS s_product_id, s.dest_warehouse_id AS s_warehouse_id
               FROM disruptions d
               LEFT JOIN shipments s ON d.shipment_id = s.id
               WHERE d.id = ?""",
            (disruption_id,),
        ).fetchone()

        if not disruption:
            return []

        product_id = disruption["product_id"] or disruption["s_product_id"]
        warehouse_id = disruption["warehouse_id"] or disruption["s_warehouse_id"]

        if not product_id or not warehouse_id:
            return []

        # Determine effective new ETA date
        if disruption["current_eta"]:
            new_eta_date = parse_iso_date(disruption["current_eta"])
        elif disruption["expected_arrival"]:
            new_eta_date = parse_iso_date(disruption["expected_arrival"])
        else:
            new_eta_date = date.today()

        # Check local warehouse stock: on_hand - reserved
        local_inv = conn.execute(
            "SELECT on_hand, reserved FROM inventory WHERE warehouse_id = ? AND product_id = ?",
            (warehouse_id, product_id),
        ).fetchone()
        local_available = (local_inv["on_hand"] - local_inv["reserved"]) if local_inv else 0

        # Check alternative stock available in OTHER warehouses
        alt_row = conn.execute(
            """SELECT SUM(MAX(0, on_hand - reserved)) AS alt_avail
               FROM inventory
               WHERE product_id = ? AND warehouse_id <> ?""",
            (product_id, warehouse_id),
        ).fetchone()
        alt_available = alt_row["alt_avail"] if (alt_row and alt_row["alt_avail"] is not None) else 0

        # Calculate delay_days
        delay_days = disruption["delay_days"] or 0
        if disruption["current_eta"] and disruption["expected_arrival"]:
            d1 = parse_iso_date(disruption["expected_arrival"])
            d2 = parse_iso_date(disruption["current_eta"])
            if d2 > d1:
                delay_days = (d2 - d1).days

        # Query open order lines for this product & warehouse
        order_rows = conn.execute(
            """SELECT o.id AS order_id, o.code AS order_code, o.customer, o.priority,
                      o.due_date, ol.quantity AS line_qty
               FROM orders o
               JOIN order_lines ol ON o.id = ol.order_id
               WHERE ol.product_id = ? AND ol.warehouse_id = ? AND o.status = 'OPEN'
               ORDER BY o.due_date ASC""",
            (product_id, warehouse_id),
        ).fetchall()

        # Simulate local stock allocation by due date
        remaining_local = max(0, local_available)

        for row in order_rows:
            order_id = row["order_id"]
            qty = row["line_qty"]
            due_date = parse_iso_date(row["due_date"])

            # buffer_days = due_date - new_eta_date - 1 day handling
            buffer_days = (due_date - new_eta_date).days - 1

            if remaining_local >= qty:
                shortfall = 0
                remaining_local -= qty
            else:
                shortfall = qty - remaining_local
                remaining_local = 0

            units_at_risk = qty if buffer_days < 0 else shortfall

            # Only create impact if order is actually affected (negative buffer OR positive shortfall)
            if buffer_days < 0 or shortfall > 0:
                risk_info = calculate_risk(
                    buffer_days=buffer_days,
                    delay_days=delay_days,
                    priority=row["priority"],
                    shortfall=shortfall,
                    order_quantity=qty,
                    alt_stock_available=alt_available,
                )

                # Upsert into disruption_impacts
                conn.execute(
                    """INSERT INTO disruption_impacts (
                           disruption_id, order_id, risk_score, risk_level,
                           risk_breakdown, risk_reasons, units_at_risk, computed_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                       ON CONFLICT(disruption_id, order_id) DO UPDATE SET
                           risk_score = excluded.risk_score,
                           risk_level = excluded.risk_level,
                           risk_breakdown = excluded.risk_breakdown,
                           risk_reasons = excluded.risk_reasons,
                           units_at_risk = excluded.units_at_risk,
                           computed_at = excluded.computed_at""",
                    (
                        disruption_id,
                        order_id,
                        risk_info["score"],
                        risk_info["level"],
                        json.dumps(risk_info["breakdown"]),
                        json.dumps(risk_info["reasons"]),
                        units_at_risk,
                    ),
                )

                impacts.append({
                    "disruption_id": disruption_id,
                    "order_id": order_id,
                    "order_code": row["order_code"],
                    "customer": row["customer"],
                    "priority": row["priority"],
                    "buffer_days": buffer_days,
                    "shortfall": shortfall,
                    "units_at_risk": units_at_risk,
                    "risk_score": risk_info["score"],
                    "risk_level": risk_info["level"],
                    "risk_reasons": risk_info["reasons"],
                    "risk_breakdown": risk_info["breakdown"],
                })

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Sort impacts descending by risk_score
    impacts.sort(key=lambda x: x["risk_score"], reverse=True)
    return impacts
