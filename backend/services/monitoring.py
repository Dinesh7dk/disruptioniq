"""
backend/services/monitoring.py
Pure SQL & service functions for dashboard, disruptions, orders, audit logs,
notifications, and live event feed.
Strictly complies with parameterized SQL (? placeholders, no ORM) and hard rules.
"""
import json
from typing import Any
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
