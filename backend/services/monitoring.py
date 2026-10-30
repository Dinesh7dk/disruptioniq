"""
backend/services/monitoring.py
Pure SQL & service functions for dashboard, disruptions, orders, audit logs,
notifications, and live event feed.
Strictly complies with parameterized SQL (? placeholders, no ORM) and hard rules.
"""
import json
from typing import Any
from fastapi import HTTPException, status
from backend.db import get_conn
from backend.services.recovery import generate_options


def get_dashboard_summary() -> dict[str, int]:
    """
    Returns counts of:
    - active_disruptions
    - affected_orders
    - pending_approvals
    - executed_plans
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        active_disruptions = cur.execute(
            "SELECT COUNT(*) FROM disruptions WHERE status = 'OPEN'"
        ).fetchone()[0]

        affected_orders = cur.execute(
            """SELECT COUNT(DISTINCT di.order_id)
               FROM disruption_impacts di
               JOIN disruptions d ON d.id = di.disruption_id
               WHERE d.status = 'OPEN'"""
        ).fetchone()[0]

        pending_approvals = cur.execute(
            "SELECT COUNT(*) FROM recovery_plans WHERE status = 'PENDING_APPROVAL'"
        ).fetchone()[0]

        executed_plans = cur.execute(
            "SELECT COUNT(*) FROM recovery_plans WHERE status = 'EXECUTED'"
        ).fetchone()[0]

        return {
            "active_disruptions": int(active_disruptions),
            "affected_orders": int(affected_orders),
            "pending_approvals": int(pending_approvals),
            "executed_plans": int(executed_plans),
        }
    finally:
        conn.close()


def get_all_disruptions() -> list[dict[str, Any]]:
    """
    Returns all disruptions with related shipment, warehouse, and impact stats.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        rows = cur.execute(
            """SELECT 
                 d.id, d.type, d.status, d.description, d.ai_summary, d.ai_source,
                 d.detected_at, d.resolved_at,
                 d.shipment_id, s.code AS shipment_code, s.status AS shipment_status,
                 s.expected_arrival, s.current_eta, s.delay_days,
                 d.warehouse_id, w.code AS warehouse_code, w.name AS warehouse_name, w.city AS warehouse_city,
                 d.product_id, p.code AS product_code, p.name AS product_name,
                 COUNT(di.id) AS affected_orders_count,
                 COALESCE(MAX(di.risk_score), 0.0) AS max_risk_score
               FROM disruptions d
               LEFT JOIN shipments s ON s.id = d.shipment_id
               LEFT JOIN warehouses w ON w.id = d.warehouse_id
               LEFT JOIN products p ON p.id = d.product_id
               LEFT JOIN disruption_impacts di ON di.disruption_id = d.id
               GROUP BY d.id
               ORDER BY d.id DESC"""
        ).fetchall()

        result = []
        for r in rows:
            item = {
                "id": r["id"],
                "type": r["type"],
                "status": r["status"],
                "description": r["description"],
                "ai_summary": r["ai_summary"],
                "ai_source": r["ai_source"],
                "detected_at": r["detected_at"],
                "resolved_at": r["resolved_at"],
                "affected_orders_count": r["affected_orders_count"],
                "max_risk_score": round(float(r["max_risk_score"]), 1),
                "shipment": (
                    {
                        "id": r["shipment_id"],
                        "code": r["shipment_code"],
                        "status": r["shipment_status"],
                        "expected_arrival": r["expected_arrival"],
                        "current_eta": r["current_eta"],
                        "delay_days": r["delay_days"],
                    }
                    if r["shipment_id"]
                    else None
                ),
                "warehouse": (
                    {
                        "id": r["warehouse_id"],
                        "code": r["warehouse_code"],
                        "name": r["warehouse_name"],
                        "city": r["warehouse_city"],
                    }
                    if r["warehouse_id"]
                    else None
                ),
                "product": (
                    {
                        "id": r["product_id"],
                        "code": r["product_code"],
                        "name": r["product_name"],
                    }
                    if r["product_id"]
                    else None
                ),
            }
            result.append(item)
        return result
    finally:
        conn.close()


def get_disruption_by_id(disruption_id: int) -> dict[str, Any] | None:
    """
    Returns full disruption details:
    - Base info
    - Impacts (with customer, order, buffer days, risk score, reasons, and breakdown)
    - Verified feasible recovery options (no DB writes, no hallucinations)
    - Recovery plans proposed/decided for this disruption
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        d = cur.execute(
            """SELECT 
                 d.id, d.type, d.status, d.description, d.ai_summary, d.ai_source,
                 d.detected_at, d.resolved_at,
                 d.shipment_id, s.code AS shipment_code, s.status AS shipment_status,
                 s.expected_arrival, s.current_eta, s.delay_days,
                 d.warehouse_id, w.code AS warehouse_code, w.name AS warehouse_name, w.city AS warehouse_city,
                 d.product_id, p.code AS product_code, p.name AS product_name
               FROM disruptions d
               LEFT JOIN shipments s ON s.id = d.shipment_id
               LEFT JOIN warehouses w ON w.id = d.warehouse_id
               LEFT JOIN products p ON p.id = d.product_id
               WHERE d.id = ?""",
            (disruption_id,),
        ).fetchone()

        if d is None:
            return None

        # Fetch impacts
        imp_rows = cur.execute(
            """SELECT 
                 di.id, di.order_id, di.risk_score, di.risk_level, di.risk_breakdown,
                 di.risk_reasons, di.units_at_risk, di.computed_at,
                 o.code AS order_code, o.customer, o.priority, o.due_date, o.status AS order_status
               FROM disruption_impacts di
               JOIN orders o ON o.id = di.order_id
               WHERE di.disruption_id = ?
               ORDER BY di.risk_score DESC, o.due_date ASC""",
            (disruption_id,),
        ).fetchall()

        impacts = []
        for imp in imp_rows:
            try:
                reasons = json.loads(imp["risk_reasons"]) if imp["risk_reasons"] else []
            except Exception:
                reasons = []

            try:
                breakdown = json.loads(imp["risk_breakdown"]) if imp["risk_breakdown"] else {}
            except Exception:
                breakdown = {}

            impacts.append({
                "id": imp["id"],
                "order_id": imp["order_id"],
                "order_code": imp["order_code"],
                "customer": imp["customer"],
                "priority": imp["priority"],
                "due_date": imp["due_date"],
                "order_status": imp["order_status"],
                "units_at_risk": imp["units_at_risk"],
                "risk_score": round(float(imp["risk_score"]), 1),
                "risk_level": imp["risk_level"],
                "reasons": reasons,
                "breakdown": breakdown,
                "computed_at": imp["computed_at"],
            })

        # Fetch existing plans
        plan_rows = cur.execute(
            """SELECT 
                 p.id, p.disruption_id, p.title, p.description, p.action_type,
                 p.status, p.plan_payload, p.proposed_by, p.decided_by, p.decision_note,
                 p.proposed_at, p.decided_at, p.executed_at,
                 u1.username AS proposer_username,
                 u2.username AS decider_username
               FROM recovery_plans p
               LEFT JOIN users u1 ON u1.id = p.proposed_by
               LEFT JOIN users u2 ON u2.id = p.decided_by
               WHERE p.disruption_id = ?
               ORDER BY p.id DESC""",
            (disruption_id,),
        ).fetchall()

        plans = []
        for p in plan_rows:
            payload = p["plan_payload"]
            try:
                payload = json.loads(payload) if payload else {}
            except Exception:
                pass
            plans.append({
                "id": p["id"],
                "disruption_id": p["disruption_id"],
                "title": p["title"],
                "description": p["description"],
                "action_type": p["action_type"],
                "status": p["status"],
                "plan_payload": payload,
                "proposed_by": p["proposed_by"],
                "proposer_username": p["proposer_username"],
                "decided_by": p["decided_by"],
                "decider_username": p["decider_username"],
                "decision_note": p["decision_note"],
                "proposed_at": p["proposed_at"],
                "decided_at": p["decided_at"],
                "executed_at": p["executed_at"],
            })

    finally:
        conn.close()

    # Generate feasible options (pure function, no DB locks)
    options = generate_options(disruption_id=disruption_id)

    return {
        "id": d["id"],
        "type": d["type"],
        "status": d["status"],
        "description": d["description"],
        "ai_summary": d["ai_summary"],
        "ai_source": d["ai_source"],
        "detected_at": d["detected_at"],
        "resolved_at": d["resolved_at"],
        "shipment": (
            {
                "id": d["shipment_id"],
                "code": d["shipment_code"],
                "status": d["shipment_status"],
                "expected_arrival": d["expected_arrival"],
                "current_eta": d["current_eta"],
                "delay_days": d["delay_days"],
            }
            if d["shipment_id"]
            else None
        ),
        "warehouse": (
            {
                "id": d["warehouse_id"],
                "code": d["warehouse_code"],
                "name": d["warehouse_name"],
                "city": d["warehouse_city"],
            }
            if d["warehouse_id"]
            else None
        ),
        "product": (
            {
                "id": d["product_id"],
                "code": d["product_code"],
                "name": d["product_name"],
            }
            if d["product_id"]
            else None
        ),
        "impacts": impacts,
        "options": options,
        "plans": plans,
    }


def get_orders(sort_by: str = "risk") -> list[dict[str, Any]]:
    """
    Returns all orders. When sort_by='risk', orders are sorted by highest risk
    score descending, then due date ascending.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        order_query = """
        SELECT 
            o.id,
            o.code,
            o.customer,
            o.priority,
            o.due_date,
            o.status,
            COALESCE(MAX(di.risk_score), 0.0) AS risk_score,
            (
                SELECT di2.risk_level FROM disruption_impacts di2
                JOIN disruptions d2 ON d2.id = di2.disruption_id AND d2.status = 'OPEN'
                WHERE di2.order_id = o.id
                ORDER BY di2.risk_score DESC LIMIT 1
            ) AS risk_level,
            (
                SELECT di2.risk_reasons FROM disruption_impacts di2
                JOIN disruptions d2 ON d2.id = di2.disruption_id AND d2.status = 'OPEN'
                WHERE di2.order_id = o.id
                ORDER BY di2.risk_score DESC LIMIT 1
            ) AS risk_reasons,
            (
                SELECT di2.risk_breakdown FROM disruption_impacts di2
                JOIN disruptions d2 ON d2.id = di2.disruption_id AND d2.status = 'OPEN'
                WHERE di2.order_id = o.id
                ORDER BY di2.risk_score DESC LIMIT 1
            ) AS risk_breakdown,
            (
                SELECT di2.units_at_risk FROM disruption_impacts di2
                JOIN disruptions d2 ON d2.id = di2.disruption_id AND d2.status = 'OPEN'
                WHERE di2.order_id = o.id
                ORDER BY di2.risk_score DESC LIMIT 1
            ) AS units_at_risk,
            (
                SELECT di2.disruption_id FROM disruption_impacts di2
                JOIN disruptions d2 ON d2.id = di2.disruption_id AND d2.status = 'OPEN'
                WHERE di2.order_id = o.id
                ORDER BY di2.risk_score DESC LIMIT 1
            ) AS disruption_id
        FROM orders o
        LEFT JOIN disruption_impacts di ON di.order_id = o.id
        LEFT JOIN disruptions d ON d.id = di.disruption_id AND d.status = 'OPEN'
        GROUP BY o.id
        """

        if sort_by == "risk":
            order_query += " ORDER BY risk_score DESC, o.due_date ASC"
        else:
            order_query += " ORDER BY o.id ASC"

        rows = cur.execute(order_query).fetchall()

        # Fetch lines for each order
        lines_rows = cur.execute(
            """SELECT ol.order_id, p.code AS product_code, p.name AS product_name,
                      ol.quantity, ol.fulfilled, w.city AS warehouse_city
               FROM order_lines ol
               JOIN products p ON p.id = ol.product_id
               JOIN warehouses w ON w.id = ol.warehouse_id
               ORDER BY ol.id ASC"""
        ).fetchall()

        lines_by_order: dict[int, list] = {}
        for l in lines_rows:
            lines_by_order.setdefault(l["order_id"], []).append({
                "product_code": l["product_code"],
                "product_name": l["product_name"],
                "quantity": l["quantity"],
                "fulfilled": l["fulfilled"],
                "warehouse_city": l["warehouse_city"],
            })

        orders = []
        for r in rows:
            try:
                reasons = json.loads(r["risk_reasons"]) if r["risk_reasons"] else []
            except Exception:
                reasons = []

            try:
                breakdown = json.loads(r["risk_breakdown"]) if r["risk_breakdown"] else {}
            except Exception:
                breakdown = {}

            orders.append({
                "id": r["id"],
                "code": r["code"],
                "customer": r["customer"],
                "priority": r["priority"],
                "due_date": r["due_date"],
                "status": r["status"],
                "risk_score": round(float(r["risk_score"]), 1),
                "risk_level": r["risk_level"] or "NONE",
                "units_at_risk": r["units_at_risk"] or 0,
                "disruption_id": r["disruption_id"],
                "reasons": reasons,
                "breakdown": breakdown,
                "lines": lines_by_order.get(r["id"], []),
            })

        return orders
    finally:
        conn.close()


def get_notifications(user_id: int, role: str, limit: int = 50) -> list[dict[str, Any]]:
    """
    Returns in-app notifications for the authenticated user / role.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        if role == "Administrator":
            rows = cur.execute(
                """SELECT n.id, n.user_id, u.username, n.title, n.body, n.type,
                          n.is_read, n.ref_table, n.ref_id, n.created_at
                   FROM notifications n
                   LEFT JOIN users u ON u.id = n.user_id
                   ORDER BY n.id DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        else:
            rows = cur.execute(
                """SELECT n.id, n.user_id, u.username, n.title, n.body, n.type,
                          n.is_read, n.ref_table, n.ref_id, n.created_at
                   FROM notifications n
                   LEFT JOIN users u ON u.id = n.user_id
                   WHERE n.user_id = ?
                   ORDER BY n.id DESC
                   LIMIT ?""",
                (user_id, limit),
            ).fetchall()

        return [
            {
                "id": r["id"],
                "user_id": r["user_id"],
                "username": r["username"],
                "title": r["title"],
                "body": r["body"],
                "type": r["type"],
                "is_read": bool(r["is_read"]),
                "ref_table": r["ref_table"],
                "ref_id": r["ref_id"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_audit_logs(limit: int = 100) -> list[dict[str, Any]]:
    """
    Returns audit logs (append-only) with before & after state parsed.
    Restricted to Administrator and Supply Chain Manager.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        rows = cur.execute(
            """SELECT 
                 a.id, a.actor_id, u.username AS actor_username, u.role AS actor_role,
                 a.action, a.entity_type, a.entity_id, a.old_value, a.new_value,
                 a.note, a.created_at
               FROM audit_logs a
               LEFT JOIN users u ON u.id = a.actor_id
               ORDER BY a.id DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

        result = []
        for r in rows:
            old_val = r["old_value"]
            new_val = r["new_value"]
            try:
                old_val = json.loads(old_val) if old_val else None
            except Exception:
                pass
            try:
                new_val = json.loads(new_val) if new_val else None
            except Exception:
                pass

            result.append({
                "id": r["id"],
                "actor_id": r["actor_id"],
                "actor_username": r["actor_username"],
                "actor_role": r["actor_role"],
                "action": r["action"],
                "entity_type": r["entity_type"],
                "entity_id": r["entity_id"],
                "old_value": old_val,
                "new_value": new_val,
                "note": r["note"],
                "created_at": r["created_at"],
            })
        return result
    finally:
        conn.close()


def get_recent_events(limit: int = 50) -> list[dict[str, Any]]:
    """
    Returns the last 50 audit and webhook events combined for a live feed,
    sorted by timestamp descending.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        query = """
        SELECT * FROM (
            SELECT 
                'audit' AS category,
                CAST(a.id AS TEXT) AS id,
                a.action AS title,
                COALESCE(a.note, a.action || ' on ' || a.entity_type || ' #' || a.entity_id) AS details,
                COALESCE(u.username, 'System') AS actor,
                a.entity_type,
                a.entity_id,
                a.created_at AS timestamp
            FROM audit_logs a
            LEFT JOIN users u ON u.id = a.actor_id
            UNION ALL
            SELECT 
                'webhook' AS category,
                w.event_id AS id,
                ('Webhook: ' || w.source || ' ' || w.event_type) AS title,
                w.payload AS details,
                w.source AS actor,
                'webhook' AS entity_type,
                NULL AS entity_id,
                w.received_at AS timestamp
            FROM webhook_events w
        )
        ORDER BY timestamp DESC
        LIMIT ?
        """
        rows = cur.execute(query, (limit,)).fetchall()

        result = []
        for r in rows:
            details = r["details"]
            try:
                # If details is JSON (e.g. from webhook payload), parse to dict
                details = json.loads(details) if (details and details.startswith("{")) else details
            except Exception:
                pass

            result.append({
                "category": r["category"],
                "id": r["id"],
                "title": r["title"],
                "details": details,
                "actor": r["actor"],
                "entity_type": r["entity_type"],
                "entity_id": r["entity_id"],
                "timestamp": r["timestamp"],
            })
        return result
    finally:
        conn.close()


def get_disruption_graph(disruption_id: int) -> dict[str, Any]:
    """
    Returns graph representation {nodes, edges} for the supply chain cascade:
    Supplier -> Shipment -> Warehouse -> Orders -> Customers
    Each order node includes risk_level ("HIGH" | "MEDIUM" | "LOW"), risk_score,
    and risk_breakdown.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        query = """
        SELECT 
            d.id AS disruption_id,
            d.type AS disruption_type,
            d.status AS disruption_status,
            d.description AS disruption_description,
            d.product_id AS d_product_id,
            d.warehouse_id AS d_warehouse_id,
            s.id AS shipment_id,
            s.code AS shipment_code,
            s.status AS shipment_status,
            s.current_eta,
            s.expected_arrival,
            s.delay_days,
            s.quantity AS shipment_quantity,
            s.product_id AS s_product_id,
            s.dest_warehouse_id AS s_warehouse_id,
            sup.id AS supplier_id,
            sup.code AS supplier_code,
            sup.name AS supplier_name,
            sup.contact AS supplier_contact,
            w.id AS warehouse_id,
            w.code AS warehouse_code,
            w.name AS warehouse_name,
            w.city AS warehouse_city,
            p.id AS product_id,
            p.code AS product_code,
            p.name AS product_name
        FROM disruptions d
        LEFT JOIN shipments s ON d.shipment_id = s.id
        LEFT JOIN suppliers sup ON s.supplier_id = sup.id
        LEFT JOIN warehouses w ON (d.warehouse_id = w.id OR s.dest_warehouse_id = w.id)
        LEFT JOIN products p ON (d.product_id = p.id OR s.product_id = p.id)
        WHERE d.id = ?
        """
        d = cur.execute(query, (disruption_id,)).fetchone()
        if not d:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Disruption #{disruption_id} not found."
            )

        # Fallback for supplier if not linked via shipment
        supplier_id = d["supplier_id"]
        supplier_name = d["supplier_name"]
        supplier_contact = d["supplier_contact"]
        supplier_code = d["supplier_code"]
        if not supplier_id:
            sup_row = cur.execute("SELECT * FROM suppliers ORDER BY reliability_score DESC LIMIT 1").fetchone()
            if sup_row:
                supplier_id = sup_row["id"]
                supplier_name = sup_row["name"]
                supplier_contact = sup_row["contact"]
                supplier_code = sup_row["code"]
            else:
                supplier_id = 1
                supplier_name = "Primary Supplier"
                supplier_contact = "Primary Contact"
                supplier_code = "SUP-001"

        # Fallback for warehouse
        warehouse_id = d["warehouse_id"]
        warehouse_name = d["warehouse_name"]
        warehouse_city = d["warehouse_city"]
        warehouse_code = d["warehouse_code"]
        if not warehouse_id:
            wh_row = cur.execute("SELECT * FROM warehouses LIMIT 1").fetchone()
            if wh_row:
                warehouse_id = wh_row["id"]
                warehouse_name = wh_row["name"]
                warehouse_city = wh_row["city"]
                warehouse_code = wh_row["code"]
            else:
                warehouse_id = 1
                warehouse_name = "Regional WH"
                warehouse_city = "Hub"
                warehouse_code = "WH-01"

        # Fetch affected orders from disruption_impacts
        impact_rows = cur.execute(
            """SELECT 
                 di.risk_score, di.risk_level, di.risk_breakdown, di.risk_reasons, di.units_at_risk,
                 o.id AS order_id, o.code AS order_code, o.customer, o.priority, o.due_date, o.status AS order_status
               FROM disruption_impacts di
               JOIN orders o ON di.order_id = o.id
               WHERE di.disruption_id = ?
               ORDER BY di.risk_score DESC""",
            (disruption_id,),
        ).fetchall()

        # If impacts not yet computed, compute them dynamically
        if not impact_rows:
            conn.close()
            from backend.services.impact import analyze_impact
            analyze_impact(disruption_id)
            conn = get_conn()
            cur = conn.cursor()
            impact_rows = cur.execute(
                """SELECT 
                     di.risk_score, di.risk_level, di.risk_breakdown, di.risk_reasons, di.units_at_risk,
                     o.id AS order_id, o.code AS order_code, o.customer, o.priority, o.due_date, o.status AS order_status
                   FROM disruption_impacts di
                   JOIN orders o ON di.order_id = o.id
                   WHERE di.disruption_id = ?
                   ORDER BY di.risk_score DESC""",
                (disruption_id,),
            ).fetchall()

        num_orders = max(1, len(impact_rows))
        center_y = max(80, (num_orders * 110) // 2)

        nodes = []
        edges = []

        # 1. Supplier Node
        sup_node_id = f"supplier-{supplier_id}"
        nodes.append({
            "id": sup_node_id,
            "type": "default",
            "position": {"x": 50, "y": center_y},
            "data": {
                "label": f"{supplier_name} ({supplier_code})",
                "entity_type": "supplier",
                "code": supplier_code,
                "name": supplier_name,
                "contact": supplier_contact,
            },
        })

        # 2. Shipment Node
        shipment_id = d["shipment_id"]
        ship_node_id = f"shipment-{shipment_id or 'none'}"
        ship_label = f"{d['shipment_code'] or 'Inbound Transport'}"
        if d["delay_days"]:
            ship_label += f" (+{d['delay_days']}d delay)"
        nodes.append({
            "id": ship_node_id,
            "type": "default",
            "position": {"x": 280, "y": center_y},
            "data": {
                "label": ship_label,
                "entity_type": "shipment",
                "code": d["shipment_code"],
                "status": d["shipment_status"],
                "delay_days": d["delay_days"] or 0,
                "current_eta": d["current_eta"],
                "expected_arrival": d["expected_arrival"],
            },
        })
        edges.append({
            "id": f"e-{sup_node_id}-{ship_node_id}",
            "source": sup_node_id,
            "target": ship_node_id,
            "animated": True,
        })

        # 3. Warehouse Node
        wh_node_id = f"warehouse-{warehouse_id}"
        nodes.append({
            "id": wh_node_id,
            "type": "default",
            "position": {"x": 510, "y": center_y},
            "data": {
                "label": f"{warehouse_city} ({warehouse_code})",
                "entity_type": "warehouse",
                "code": warehouse_code,
                "city": warehouse_city,
                "name": warehouse_name,
            },
        })
        edges.append({
            "id": f"e-{ship_node_id}-{wh_node_id}",
            "source": ship_node_id,
            "target": wh_node_id,
            "animated": True,
        })

        # 4. Orders and Customers
        for i, imp in enumerate(impact_rows):
            y_pos = 40 + i * 110

            breakdown = {}
            if imp["risk_breakdown"]:
                try:
                    breakdown = json.loads(imp["risk_breakdown"]) if isinstance(imp["risk_breakdown"], str) else imp["risk_breakdown"]
                except Exception:
                    breakdown = {}

            reasons = []
            if imp["risk_reasons"]:
                try:
                    reasons = json.loads(imp["risk_reasons"]) if isinstance(imp["risk_reasons"], str) else imp["risk_reasons"]
                except Exception:
                    reasons = []

            ord_node_id = f"order-{imp['order_id']}"
            nodes.append({
                "id": ord_node_id,
                "type": "default",
                "position": {"x": 740, "y": y_pos},
                "data": {
                    "label": f"{imp['order_code']} ({imp['risk_level']})",
                    "entity_type": "order",
                    "order_id": imp["order_id"],
                    "order_code": imp["order_code"],
                    "customer": imp["customer"],
                    "priority": imp["priority"],
                    "due_date": imp["due_date"],
                    "risk_level": imp["risk_level"],
                    "risk_score": float(imp["risk_score"]),
                    "units_at_risk": imp["units_at_risk"],
                    "risk_breakdown": breakdown,
                    "risk_reasons": reasons,
                },
            })
            edges.append({
                "id": f"e-{wh_node_id}-{ord_node_id}",
                "source": wh_node_id,
                "target": ord_node_id,
            })

            # 5. Customer Node
            cust_node_id = f"customer-{imp['order_id']}"
            nodes.append({
                "id": cust_node_id,
                "type": "default",
                "position": {"x": 970, "y": y_pos},
                "data": {
                    "label": imp["customer"],
                    "entity_type": "customer",
                    "customer_name": imp["customer"],
                    "order_id": imp["order_id"],
                    "order_code": imp["order_code"],
                },
            })
            edges.append({
                "id": f"e-{ord_node_id}-{cust_node_id}",
                "source": ord_node_id,
                "target": cust_node_id,
            })

        return {
            "disruption_id": disruption_id,
            "nodes": nodes,
            "edges": edges,
        }
    finally:
        conn.close()

