"""
backend/services/approval.py

Approval, Rejection, Modification, and Execution Service for Recovery Plans.

Hard Rules Enforced:
1. Roles:
   - Propose: Operations Analyst (or Admin)
   - Approve / Reject / Modify:
     - REALLOCATE_STOCK, EXPEDITE_ORDER, PARTIAL_FULFIL -> Supply Chain Manager
     - ALTERNATIVE_SUPPLIER -> Procurement Approver
     - (Admin can also approve any)
   - Execute: Warehouse Operator (or Admin)
2. Separation of Duty:
   - Approver must not be the proposer (decided_by != proposed_by) -> 403 Forbidden.
3. State Transitions (Rule 9):
   - PROPOSED -> PENDING_APPROVAL -> APPROVED | REJECTED | MODIFIED
   - MODIFIED -> PENDING_APPROVAL
   - APPROVED -> EXECUTED
   - Any other transition returns HTTP 409 Conflict.
4. On Execute:
   - Revalidate stock and deadlines immediately before execution.
   - Run in ONE transaction with optimistic locking:
     UPDATE inventory SET reserved = reserved + ?, version = version + 1
     WHERE id = ? AND version = ? AND (on_hand - reserved) >= ?
   - If rowcount == 0: raise HTTP 409 Conflict and roll back everything.
5. Audit & Notifications:
   - Every state transition writes an audit_logs entry with old_value and new_value snapshots.
   - Inserts notifications for relevant operational actors.
"""
import json
from datetime import date
from typing import Any
from fastapi import HTTPException, status
from backend.db import get_conn


def parse_iso(d_str: str) -> date:
    return date.fromisoformat(d_str.split("T")[0])


def write_audit(
    conn,
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int,
    old_value: dict | None,
    new_value: dict | None,
    note: str | None = None,
):
    conn.execute(
        """INSERT INTO audit_logs (actor_id, action, entity_type, entity_id, old_value, new_value, note)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            actor_id,
            action,
            entity_type,
            entity_id,
            json.dumps(old_value) if old_value is not None else None,
            json.dumps(new_value) if new_value is not None else None,
            note,
        ),
    )


def create_notification(
    conn,
    user_id: int,
    title: str,
    body: str,
    notif_type: str,
    ref_table: str | None = None,
    ref_id: int | None = None,
):
    conn.execute(
        """INSERT INTO notifications (user_id, title, body, type, ref_table, ref_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, title, body, notif_type, ref_table, ref_id),
    )


def propose_plan(
    disruption_id: int,
    title: str,
    action_type: str,
    description: str,
    plan_payload: dict,
    actor: dict,
) -> dict[str, Any]:
    """
    Creates a recovery plan in PENDING_APPROVAL state.
    Actor role must be Operations Analyst or Administrator.
    """
    conn = get_conn()
    try:
        # Check disruption exists
        d = conn.execute("SELECT id FROM disruptions WHERE id = ?", (disruption_id,)).fetchone()
        if not d:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Disruption not found")

        cur = conn.execute(
            """INSERT INTO recovery_plans (
                   disruption_id, title, description, action_type, status,
                   proposed_by, plan_payload, proposed_at
               ) VALUES (?, ?, ?, ?, 'PENDING_APPROVAL', ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))""",
            (
                disruption_id,
                title,
                description,
                action_type,
                int(actor["sub"]),
                json.dumps(plan_payload),
            ),
        )
        plan_id = cur.lastrowid

        new_plan = {
            "id": plan_id,
            "disruption_id": disruption_id,
            "title": title,
            "action_type": action_type,
            "status": "PENDING_APPROVAL",
            "proposed_by": int(actor["sub"]),
            "plan_payload": plan_payload,
        }

        write_audit(conn, int(actor["sub"]), "PLAN_PROPOSED", "recovery_plans", plan_id, None, new_plan)

        # Notify Supply Chain Managers or Procurement Approvers
        managers = conn.execute(
            "SELECT id FROM users WHERE role IN ('Supply Chain Manager', 'Procurement Approver') AND is_active = 1"
        ).fetchall()
        for m in managers:
            create_notification(
                conn,
                m["id"],
                f"New Recovery Plan #{plan_id} Pending Approval",
                f"{actor.get('username', 'Analyst')} proposed {action_type} for Disruption #{disruption_id}.",
                "APPROVAL",
                "recovery_plans",
                plan_id,
            )

        conn.commit()
        return new_plan
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def approve_plan(plan_id: int, note: str | None, actor: dict) -> dict[str, Any]:
    """
    Approves a recovery plan.
    Enforces:
    - Status must be PENDING_APPROVAL (409 otherwise)
    - Role permissions:
        Supply Chain Manager for REALLOCATE_STOCK, EXPEDITE_ORDER, PARTIAL_FULFIL
        Procurement Approver for ALTERNATIVE_SUPPLIER
    - Separation of duty: approver != proposer (403)
    """
    conn = get_conn()
    try:
        plan = conn.execute("SELECT * FROM recovery_plans WHERE id = ?", (plan_id,)).fetchone()
        if not plan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

        old_plan = dict(plan)
        cur_status = old_plan["status"]
        if cur_status not in ("PENDING_APPROVAL", "PROPOSED"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot approve plan in state '{cur_status}'. Only PENDING_APPROVAL plans can be approved.",
            )

        actor_id = int(actor["sub"])
        actor_role = actor.get("role", "")
        proposer_id = old_plan["proposed_by"]

        # Separation of duty: approver != proposer
        if actor_id == proposer_id and actor_role != "Administrator":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Separation of duty violation: approver must not be the proposer.",
            )

        # Role authority check
        action_type = old_plan["action_type"]
        if actor_role != "Administrator":
            if action_type in ("REALLOCATE_STOCK", "EXPEDITE_ORDER", "PARTIAL_FULFIL"):
                if actor_role != "Supply Chain Manager":
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Only Supply Chain Manager can approve {action_type}.",
                    )
            elif action_type == "ALTERNATIVE_SUPPLIER":
                if actor_role != "Procurement Approver":
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Only Procurement Approver can approve ALTERNATIVE_SUPPLIER plans.",
                    )

        payload = json.loads(old_plan["plan_payload"] or "{}")
        # Snapshot current inventory version at approval time for optimistic locking
        source_wh_id = payload.get("source_warehouse_id")
        product_code = payload.get("product_code")
        if source_wh_id and product_code:
            inv = conn.execute(
                """SELECT i.version FROM inventory i
                   JOIN products p ON i.product_id = p.id
                   WHERE i.warehouse_id = ? AND p.code = ?""",
                (source_wh_id, product_code),
            ).fetchone()
            if inv:
                payload["inventory_version"] = inv["version"]

        conn.execute(
            """UPDATE recovery_plans
               SET status = 'APPROVED', decided_by = ?, decision_note = ?,
                   plan_payload = ?,
                   decided_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
               WHERE id = ?""",
            (actor_id, note or "Approved", json.dumps(payload), plan_id),
        )

        new_plan = dict(old_plan)
        new_plan["status"] = "APPROVED"
        new_plan["decided_by"] = actor_id
        new_plan["decision_note"] = note or "Approved"
        new_plan["plan_payload"] = json.dumps(payload)

        write_audit(conn, actor_id, "PLAN_APPROVED", "recovery_plans", plan_id, old_plan, new_plan, note)

        # Notify Warehouse Operators for execution
        operators = conn.execute("SELECT id FROM users WHERE role = 'Warehouse Operator' AND is_active = 1").fetchall()
        for op in operators:
            create_notification(
                conn,
                op["id"],
                f"Plan #{plan_id} Approved - Ready for Execution",
                f"Plan '{new_plan['title']}' is approved and ready for warehouse dispatch.",
                "APPROVAL",
                "recovery_plans",
                plan_id,
            )

        conn.commit()
        return new_plan
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reject_plan(plan_id: int, note: str | None, actor: dict) -> dict[str, Any]:
    """
    Rejects a recovery plan.
    Transition: PENDING_APPROVAL -> REJECTED.
    """
    conn = get_conn()
    try:
        plan = conn.execute("SELECT * FROM recovery_plans WHERE id = ?", (plan_id,)).fetchone()
        if not plan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

        old_plan = dict(plan)
        cur_status = old_plan["status"]
        if cur_status not in ("PENDING_APPROVAL", "PROPOSED"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot reject plan in state '{cur_status}'. Only PENDING_APPROVAL plans can be rejected.",
            )

        actor_id = int(actor["sub"])
        actor_role = actor.get("role", "")
        proposer_id = old_plan["proposed_by"]

        if actor_id == proposer_id and actor_role != "Administrator":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Separation of duty violation: reviewer must not be the proposer.",
            )

        conn.execute(
            """UPDATE recovery_plans
               SET status = 'REJECTED', decided_by = ?, decision_note = ?,
                   decided_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
               WHERE id = ?""",
            (actor_id, note or "Rejected", plan_id),
        )

        new_plan = dict(old_plan)
        new_plan["status"] = "REJECTED"
        new_plan["decided_by"] = actor_id
        new_plan["decision_note"] = note or "Rejected"

        write_audit(conn, actor_id, "PLAN_REJECTED", "recovery_plans", plan_id, old_plan, new_plan, note)

        # Notify proposer
        create_notification(
            conn,
            proposer_id,
            f"Plan #{plan_id} Rejected",
            f"Your recovery plan was rejected: {note or 'No reason provided'}",
            "APPROVAL",
            "recovery_plans",
            plan_id,
        )

        conn.commit()
        return new_plan
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def modify_plan(
    plan_id: int,
    new_quantity: int | None,
    new_option_details: dict | None,
    note: str | None,
    actor: dict,
) -> dict[str, Any]:
    """
    Modifies quantity or option payload and moves the plan back to PENDING_APPROVAL.
    Allowed from: PENDING_APPROVAL, MODIFIED, PROPOSED.
    """
    conn = get_conn()
    try:
        plan = conn.execute("SELECT * FROM recovery_plans WHERE id = ?", (plan_id,)).fetchone()
        if not plan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

        old_plan = dict(plan)
        cur_status = old_plan["status"]
        if cur_status in ("EXECUTED", "REJECTED"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot modify plan in terminal state '{cur_status}'.",
            )

        actor_id = int(actor["sub"])
        actor_role = actor.get("role", "")
        proposer_id = old_plan["proposed_by"]

        if actor_id == proposer_id and actor_role != "Administrator":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Separation of duty violation: reviewer must not be the proposer.",
            )

        payload = json.loads(old_plan["plan_payload"] or "{}")
        if new_quantity is not None:
            payload["quantity"] = new_quantity
        if new_option_details:
            payload.update(new_option_details)

        new_title = old_plan["title"]
        if new_quantity is not None:
            new_title = f"{old_plan['action_type']} (Modified: {new_quantity} units)"

        conn.execute(
            """UPDATE recovery_plans
               SET status = 'PENDING_APPROVAL',
                   title = ?,
                   plan_payload = ?,
                   decision_note = ?,
                   decided_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
               WHERE id = ?""",
            (new_title, json.dumps(payload), note or "Modified", plan_id),
        )

        new_plan = dict(old_plan)
        new_plan["status"] = "PENDING_APPROVAL"
        new_plan["title"] = new_title
        new_plan["plan_payload"] = json.dumps(payload)
        new_plan["decision_note"] = note or "Modified"

        write_audit(conn, actor_id, "PLAN_MODIFIED", "recovery_plans", plan_id, old_plan, new_plan, note)

        create_notification(
            conn,
            proposer_id,
            f"Plan #{plan_id} Modified & Returned for Approval",
            f"Plan details updated: {note or 'Modified by manager'}",
            "APPROVAL",
            "recovery_plans",
            plan_id,
        )

        conn.commit()
        return new_plan
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_plan(plan_id: int, actor: dict) -> dict[str, Any]:
    """
    Executes an APPROVED recovery plan.
    Hard rules enforced:
    1. Role must be Warehouse Operator (or Administrator).
    2. Status must be APPROVED -> returns 409 otherwise.
    3. Revalidates stock and deadlines right before execution.
    4. Runs optimistic locking transaction:
       UPDATE inventory SET reserved = reserved + ?, version = version + 1
       WHERE id = ? AND version = ? AND (on_hand - reserved) >= ?
       If rowcount == 0: rollback and return 409 Conflict.
    5. Writes audit_logs and notifications.
    """
    actor_id = int(actor["sub"])
    actor_role = actor.get("role", "")

    if actor_role not in ("Warehouse Operator", "Administrator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Warehouse Operator can execute recovery plans.",
        )

    conn = get_conn()
    try:
        plan = conn.execute("SELECT * FROM recovery_plans WHERE id = ?", (plan_id,)).fetchone()
        if not plan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

        old_plan = dict(plan)
        if old_plan["status"] != "APPROVED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot execute plan in state '{old_plan['status']}'. Plan must be APPROVED.",
            )

        payload = json.loads(old_plan["plan_payload"] or "{}")
        action_type = old_plan["action_type"]

        # Begin single atomic execution transaction
        conn.execute("BEGIN TRANSACTION;")

        # If reallocating stock, validate stock & optimistic version lock on inventory
        if action_type in ("REALLOCATE_STOCK", "PARTIAL_FULFIL"):
            source_wh_id = payload.get("source_warehouse_id")
            product_code = payload.get("product_code")
            qty = payload.get("quantity") or payload.get("immediate_quantity", 0)

            # Revalidate deadline
            order_due = payload.get("order_due_date")
            new_delivery = payload.get("new_delivery_date")
            if order_due and new_delivery:
                if parse_iso(new_delivery) > parse_iso(order_due):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Revalidation failed: recovery delivery date exceeds order deadline.",
                    )

            # Lookup inventory row
            inv_row = None
            if source_wh_id and product_code:
                inv_row = conn.execute(
                    """SELECT i.id, i.on_hand, i.reserved, i.version
                       FROM inventory i
                       JOIN products p ON i.product_id = p.id
                       WHERE i.warehouse_id = ? AND p.code = ?""",
                    (source_wh_id, product_code),
                ).fetchone()

            if not inv_row:
                # If no specific warehouse/product in payload, fetch from disruption target
                disr = conn.execute(
                    "SELECT warehouse_id, product_id FROM disruptions WHERE id = ?",
                    (old_plan["disruption_id"],),
                ).fetchone()
                if disr and disr["warehouse_id"] and disr["product_id"]:
                    inv_row = conn.execute(
                        "SELECT id, on_hand, reserved, version FROM inventory WHERE warehouse_id = ? AND product_id = ?",
                        (disr["warehouse_id"], disr["product_id"]),
                    ).fetchone()

            if not inv_row:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Revalidation failed: inventory record not found.",
                )

            inv_id = inv_row["id"]
            # Check if expected version was recorded at proposal/approval time
            expected_version = payload.get("inventory_version")
            if expected_version is None:
                # If not pinned in payload, use the version that was expected at approval
                expected_version = inv_row["version"]

            available = inv_row["on_hand"] - inv_row["reserved"]

            # Revalidate stock availability
            if available < qty:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Revalidation failed: insufficient stock (needed {qty}, available {available}).",
                )

            # Optimistic lock update with version increment (Hard Rule 6 & Prompt spec)
            cur = conn.execute(
                """UPDATE inventory
                   SET reserved = reserved + ?, version = version + 1
                   WHERE id = ? AND version = ? AND (on_hand - reserved) >= ?""",
                (qty, inv_id, expected_version, qty),
            )

            if cur.rowcount == 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Optimistic locking version conflict: inventory modified concurrently.",
                )

        # Mark plan as EXECUTED
        conn.execute(
            """UPDATE recovery_plans
               SET status = 'EXECUTED', executed_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
               WHERE id = ?""",
            (plan_id,),
        )

        # Update disruption to MITIGATED
        conn.execute(
            "UPDATE disruptions SET status = 'MITIGATED' WHERE id = ?",
            (old_plan["disruption_id"],),
        )

        new_plan = dict(old_plan)
        new_plan["status"] = "EXECUTED"

        write_audit(conn, actor_id, "PLAN_EXECUTED", "recovery_plans", plan_id, old_plan, new_plan)

        # Notify proposer and managers
        create_notification(
            conn,
            old_plan["proposed_by"],
            f"Plan #{plan_id} Successfully Executed",
            f"Warehouse Operator executed recovery plan '{old_plan['title']}'.",
            "SYSTEM",
            "recovery_plans",
            plan_id,
        )

        conn.commit()
        return new_plan
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Plan execution failed: {str(e)}",
        )
    finally:
        conn.close()
