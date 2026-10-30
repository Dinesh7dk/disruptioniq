"""
backend/services/detection.py

Deterministic Disruption Detection Engine.
NO LLM CALLS.

Rules:
1. Late shipment: current_eta > expected_arrival
2. Supplier delay: supplier has 3 or more delayed/late shipments
3. Stock shortage: on_hand - reserved < open order demand for a product at a warehouse

Rule constraint:
- Never create a second ACTIVE (status='OPEN') disruption for the same target!
  Update existing disruption if already open.
"""
from typing import Any
from backend.db import get_conn
from backend.services.impact import analyze_impact
from backend.services.ai import generate_ai_summary


def detect_late_shipments(target_shipment_id: int | None = None) -> list[int]:
    """
    Checks shipments where current_eta > expected_arrival.
    Creates or updates OPEN disruption of type 'SUPPLIER_DELAY' or 'TRANSPORT'.
    """
    conn = get_conn()
    disruption_ids = []
    try:
        query = """
            SELECT s.id, s.code, s.supplier_id, s.product_id, s.dest_warehouse_id,
                   s.expected_arrival, s.current_eta, s.status, s.delay_days
            FROM shipments s
            WHERE (s.current_eta IS NOT NULL AND s.expected_arrival IS NOT NULL
                   AND s.current_eta > s.expected_arrival)
               OR s.status = 'DELAYED'
        """
        params = []
        if target_shipment_id is not None:
            query += " AND s.id = ?"
            params.append(target_shipment_id)

        rows = conn.execute(query, params).fetchall()

        for s in rows:
            shipment_id = s["id"]
            product_id = s["product_id"]
            warehouse_id = s["dest_warehouse_id"]
            desc = f"Shipment {s['code']} delayed: expected {s['expected_arrival']}, current ETA {s['current_eta']}"

            # Check for existing ACTIVE (OPEN) disruption for this shipment
            existing = conn.execute(
                "SELECT id FROM disruptions WHERE shipment_id = ? AND status = 'OPEN'",
                (shipment_id,),
            ).fetchone()

            if existing:
                disruption_id = existing["id"]
                conn.execute(
                    """UPDATE disruptions
                       SET description = ?, product_id = ?, warehouse_id = ?
                       WHERE id = ?""",
                    (desc, product_id, warehouse_id, disruption_id),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO disruptions (type, status, shipment_id, warehouse_id, product_id, description)
                       VALUES ('SUPPLIER_DELAY', 'OPEN', ?, ?, ?, ?)""",
                    (shipment_id, warehouse_id, product_id, desc),
                )
                disruption_id = cur.lastrowid

            disruption_ids.append(disruption_id)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return disruption_ids


def detect_supplier_delays() -> list[int]:
    """
    Checks if any supplier has 3 or more delayed shipments.
    Creates or updates OPEN disruption for that supplier.
    """
    conn = get_conn()
    disruption_ids = []
    try:
        rows = conn.execute(
            """SELECT s.supplier_id, sup.name, COUNT(*) as delay_count
               FROM shipments s
               JOIN suppliers sup ON s.supplier_id = sup.id
               WHERE (s.current_eta > s.expected_arrival OR s.status = 'DELAYED')
               GROUP BY s.supplier_id
               HAVING COUNT(*) >= 3"""
        ).fetchall()

        for r in rows:
            sup_id = r["supplier_id"]
            sup_name = r["name"]
            desc = f"Supplier '{sup_name}' has chronic delay: {r['delay_count']} delayed shipments"

            # Check existing OPEN disruption for this supplier
            existing = conn.execute(
                "SELECT id FROM disruptions WHERE type = 'SUPPLIER_DELAY' AND description LIKE ? AND status = 'OPEN'",
                (f"%{sup_name}%",),
            ).fetchone()

            if existing:
                disruption_id = existing["id"]
                conn.execute(
                    "UPDATE disruptions SET description = ? WHERE id = ?",
                    (desc, disruption_id),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO disruptions (type, status, description)
                       VALUES ('SUPPLIER_DELAY', 'OPEN', ?)""",
                    (desc,),
                )
                disruption_id = cur.lastrowid

            disruption_ids.append(disruption_id)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return disruption_ids


def detect_stock_shortages() -> list[int]:
    """
    Checks if (on_hand - reserved) < total open order demand for any (product, warehouse).
    Creates or updates OPEN disruption of type 'STOCK_SHORTAGE'.
    """
    conn = get_conn()
    disruption_ids = []
    try:
        rows = conn.execute(
            """SELECT ol.warehouse_id, ol.product_id,
                      p.code as pcode, p.name as pname,
                      w.code as wcode, w.city as wcity,
                      SUM(ol.quantity) as total_demand,
                      MAX(i.on_hand) as on_hand,
                      MAX(i.reserved) as reserved,
                      (MAX(i.on_hand) - MAX(i.reserved)) as available_stock
               FROM order_lines ol
               JOIN orders o ON ol.order_id = o.id
               JOIN products p ON ol.product_id = p.id
               JOIN warehouses w ON ol.warehouse_id = w.id
               LEFT JOIN inventory i ON (ol.warehouse_id = i.warehouse_id AND ol.product_id = i.product_id)
               WHERE o.status = 'OPEN'
               GROUP BY ol.warehouse_id, ol.product_id
               HAVING (COALESCE(MAX(i.on_hand), 0) - COALESCE(MAX(i.reserved), 0)) < SUM(ol.quantity)"""
        ).fetchall()

        for r in rows:
            wh_id = r["warehouse_id"]
            prod_id = r["product_id"]
            avail = r["available_stock"] or 0
            demand = r["total_demand"]
            shortfall = demand - avail
            desc = f"Stock shortage for {r['pcode']} at {r['wcity']}: demand is {demand}, available is {avail} (shortfall {shortfall})"

            existing = conn.execute(
                """SELECT id FROM disruptions
                   WHERE type = 'STOCK_SHORTAGE' AND warehouse_id = ? AND product_id = ? AND status = 'OPEN'""",
                (wh_id, prod_id),
            ).fetchone()

            if existing:
                disruption_id = existing["id"]
                conn.execute(
                    "UPDATE disruptions SET description = ? WHERE id = ?",
                    (desc, disruption_id),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO disruptions (type, status, warehouse_id, product_id, description)
                       VALUES ('STOCK_SHORTAGE', 'OPEN', ?, ?, ?)""",
                    (wh_id, prod_id, desc),
                )
                disruption_id = cur.lastrowid

            disruption_ids.append(disruption_id)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return disruption_ids


def run_detection(shipment_id: int | None = None) -> list[int]:
    """
    Main detection entrypoint.
    Runs detection rules, then triggers impact analysis for each resulting disruption.
    Never creates duplicate active disruptions.
    """
    created_disruptions = set()

    # 1. Late shipments
    for did in detect_late_shipments(shipment_id):
        created_disruptions.add(did)

    # 2. Supplier delays
    for did in detect_supplier_delays():
        created_disruptions.add(did)

    # 3. Stock shortages
    for did in detect_stock_shortages():
        created_disruptions.add(did)

    # Run impact analysis and AI summary generation on all active disruptions
    for did in created_disruptions:
        analyze_impact(did)
        generate_ai_summary(did)

    return list(created_disruptions)

