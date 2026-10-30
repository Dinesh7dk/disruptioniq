"""
backend/services/drafts.py

Service for LLM-assisted and template fallback communication drafts.
Handles customer and supplier email drafting, peer approval (separation of duty),
and simulated transmission with audit logging.
"""
import os
import json
import httpx
from typing import Any
from fastapi import HTTPException, status
from backend.db import get_conn
from backend.services.approval import write_audit

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
TIMEOUT_SECONDS = 10.0


def call_gemini_draft(prompt: str, api_key: str) -> dict | None:
    """
    Calls Google Gemini REST API with a 10s timeout to draft an email.
    Returns parsed JSON dict {"subject": "...", "body": "..."} or None if failed.
    """
    url = f"{GEMINI_API_URL}?key={api_key}"
    headers = {"Content-Type": "application/json"}
    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            resp = client.post(url, headers=headers, json=body)
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text)
                if isinstance(parsed, dict) and "subject" in parsed and "body" in parsed:
                    return parsed
    except Exception:
        pass
    return None


def get_template_draft(
    audience: str,
    order_code: str,
    customer: str,
    new_delivery_date: str,
    reason: str,
    option_chosen: str,
) -> dict[str, str]:
    """
    Deterministic template fallback when LLM is unavailable or fails.
    Uses strictly verified facts.
    """
    aud = audience.upper().strip()
    if aud == "CUSTOMER":
        subject = f"Delivery schedule update for order {order_code}"
        body = (
            f"Dear {customer},\n\n"
            f"We are writing to provide an operational status update regarding your order {order_code}.\n\n"
            f"Due to {reason}, the updated delivery date is now estimated for {new_delivery_date}.\n"
            f"Our operations team has initiated the following recovery action: {option_chosen}.\n\n"
            f"We will notify you immediately once the shipment is dispatched. Thank you for your continued partnership.\n\n"
            f"Operations Desk\nDisruptionIQ Logistics"
        )
    else:  # SUPPLIER
        subject = f"Urgent supply coordination: Order {order_code}"
        body = (
            f"Dear Supply Chain Partner,\n\n"
            f"Regarding procurement commitments for order {order_code}: due to {reason}, we are executing recovery action: {option_chosen}.\n\n"
            f"Please ensure inventory dispatch and transit handling are aligned with the target arrival date of {new_delivery_date}.\n\n"
            f"Please confirm receipt and release schedule at your earliest convenience.\n\n"
            f"Procurement & Operations Desk\nDisruptionIQ Logistics"
        )
    return {"subject": subject, "body": body}


def create_order_draft(
    order_id: int,
    audience: str,
    user: dict,
    custom_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a communication draft for an order.
    Audience must be 'CUSTOMER' or 'SUPPLIER'.
    Extracts verified facts from DB, queries LLM or falls back to template,
    and saves the draft with status 'DRAFT'.
    """
    audience_norm = (audience or "").upper().strip()
    if audience_norm not in ("CUSTOMER", "SUPPLIER"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audience must be 'CUSTOMER' or 'SUPPLIER'.",
        )

    actor_id = int(user["sub"])
    conn = get_conn()
    try:
        # 1. Fetch order & linked disruption facts
        query = """
        SELECT o.id, o.code, o.customer, o.priority, o.status, o.due_date,
               di.disruption_id, di.risk_score, di.risk_level, di.units_at_risk,
               d.type AS disruption_type, d.description AS disruption_description,
               s.code AS shipment_code, s.delay_days, s.current_eta,
               rp.action_type AS plan_action_type, rp.title AS plan_title, rp.plan_payload
        FROM orders o
        LEFT JOIN disruption_impacts di ON o.id = di.order_id
        LEFT JOIN disruptions d ON di.disruption_id = d.id
        LEFT JOIN shipments s ON d.shipment_id = s.id
        LEFT JOIN recovery_plans rp ON (rp.disruption_id = d.id AND rp.status IN ('APPROVED', 'EXECUTED', 'PENDING_APPROVAL', 'PROPOSED'))
        WHERE o.id = ?
        ORDER BY rp.id DESC
        LIMIT 1
        """
        row = conn.execute(query, (order_id,)).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order #{order_id} not found.",
            )

        order_code = row["code"]
        customer = row["customer"]
        disruption_id = row["disruption_id"]

        # Parse plan payload if available
        plan_payload = {}
        if row["plan_payload"]:
            try:
                plan_payload = json.loads(row["plan_payload"])
            except Exception:
                plan_payload = {}

        # Determine verified facts
        new_delivery_date = (
            (custom_facts and custom_facts.get("new_delivery_date"))
            or plan_payload.get("new_delivery_date")
            or row["current_eta"]
            or row["due_date"]
        )
        reason = (
            (custom_facts and custom_facts.get("reason"))
            or row["disruption_description"]
            or (f"Shipment {row['shipment_code']} delayed by {row['delay_days']} days" if row["shipment_code"] and row["delay_days"] else None)
            or "Operational logistics schedule adjustment"
        )
        option_chosen = (
            (custom_facts and custom_facts.get("option_chosen"))
            or row["plan_title"]
            or (row["plan_action_type"].replace("_", " ") if row["plan_action_type"] else None)
            or "Expedited stock reallocation and carrier dispatch"
        )

        # 2. Try LLM drafting with verified facts
        draft_content = None
        api_key = os.getenv("LLM_API_KEY", "").strip()

        if api_key:
            prompt = f"""You are a logistics operations coordinator drafting an email to a {audience_norm}.
Draft a concise, polite, professional operations email using ONLY the verified facts below.
NEVER invent tracking numbers, fake carrier promises, dates, or details not provided in the facts.
Return a JSON object with exactly two keys: "subject" and "body".

VERIFIED OPERATIONAL FACTS:
- Order Code: {order_code}
- Customer Name: {customer}
- Updated Delivery Date: {new_delivery_date}
- Delay Reason: {reason}
- Operational Recovery Action: {option_chosen}
"""
            draft_content = call_gemini_draft(prompt, api_key)

        # 3. Fallback to deterministic template if LLM failed or key is missing
        if not draft_content:
            draft_content = get_template_draft(
                audience=audience_norm,
                order_code=order_code,
                customer=customer,
                new_delivery_date=new_delivery_date,
                reason=reason,
                option_chosen=option_chosen,
            )

        # 4. Insert into message_drafts
        cur = conn.execute(
            """INSERT INTO message_drafts (order_id, disruption_id, audience, subject, body, status, created_by)
               VALUES (?, ?, ?, ?, ?, 'DRAFT', ?)""",
            (
                order_id,
                disruption_id,
                audience_norm,
                draft_content["subject"],
                draft_content["body"],
                actor_id,
            ),
        )
        draft_id = cur.lastrowid

        new_draft = {
            "id": draft_id,
            "order_id": order_id,
            "order_code": order_code,
            "customer": customer,
            "disruption_id": disruption_id,
            "audience": audience_norm,
            "subject": draft_content["subject"],
            "body": draft_content["body"],
            "status": "DRAFT",
            "created_by": actor_id,
            "creator_username": user.get("username", "User"),
            "approved_by": None,
            "approver_username": None,
        }

        # Audit log creation
        write_audit(conn, actor_id, "DRAFT_CREATED", "message_drafts", draft_id, None, new_draft)
        # In-app notification
        conn.execute(
            """INSERT INTO notifications (user_id, title, body, type, ref_table, ref_id)
               VALUES (?, ?, ?, 'INFO', 'message_drafts', ?)""",
            (
                actor_id,
                f"New {audience_norm} draft created",
                f"Draft #{draft_id} for order {order_code} generated. Awaiting peer approval.",
                draft_id,
            ),
        )
        conn.commit()

        return new_draft
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_disruption_draft(
    disruption_id: int,
    audience: str,
    user: dict,
    order_id: int | None = None,
    custom_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a draft from a disruption context.
    If order_id is given or an affected order exists and audience is CUSTOMER,
    links to that order.
    If audience is SUPPLIER or no order exists, drafts supplier coordination for the disruption shipment.
    """
    audience_norm = (audience or "").upper().strip()
    if audience_norm not in ("CUSTOMER", "SUPPLIER"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audience must be 'CUSTOMER' or 'SUPPLIER'.",
        )

    actor_id = int(user["sub"])
    conn = get_conn()
    try:
        d_row = conn.execute(
            """SELECT d.id, d.type, d.description, s.code AS shipment_code, s.delay_days, s.current_eta,
                      sup.name AS supplier_name,
                      rp.action_type AS plan_action_type, rp.title AS plan_title, rp.plan_payload
               FROM disruptions d
               LEFT JOIN shipments s ON d.shipment_id = s.id
               LEFT JOIN suppliers sup ON s.supplier_id = sup.id
               LEFT JOIN recovery_plans rp ON (rp.disruption_id = d.id AND rp.status IN ('APPROVED', 'EXECUTED', 'PENDING_APPROVAL', 'PROPOSED'))
               WHERE d.id = ?
               ORDER BY rp.id DESC
               LIMIT 1""",
            (disruption_id,),
        ).fetchone()

        if not d_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Disruption #{disruption_id} not found.",
            )

        target_order_id = order_id
        if not target_order_id and audience_norm == "CUSTOMER":
            impact = conn.execute(
                "SELECT order_id FROM disruption_impacts WHERE disruption_id = ? ORDER BY risk_score DESC LIMIT 1",
                (disruption_id,),
            ).fetchone()
            if impact:
                target_order_id = impact["order_id"]
    finally:
        conn.close()

    if target_order_id:
        return create_order_draft(order_id=target_order_id, audience=audience_norm, user=user, custom_facts=custom_facts)

    # Disruption supplier coordination draft
    conn = get_conn()
    try:
        plan_payload = {}
        if d_row["plan_payload"]:
            try:
                plan_payload = json.loads(d_row["plan_payload"])
            except Exception:
                plan_payload = {}

        supplier_name = d_row["supplier_name"] or "Supply Chain Partner"
        order_code = d_row["shipment_code"] or f"DISR-{disruption_id}"
        new_delivery_date = (
            (custom_facts and custom_facts.get("new_delivery_date"))
            or plan_payload.get("new_delivery_date")
            or d_row["current_eta"]
            or "TBD"
        )
        reason = (
            (custom_facts and custom_facts.get("reason"))
            or d_row["description"]
            or (f"Shipment {d_row['shipment_code']} delayed by {d_row['delay_days']} days" if d_row["shipment_code"] and d_row["delay_days"] else None)
            or "Logistics inbound schedule adjustment"
        )
        option_chosen = (
            (custom_facts and custom_facts.get("option_chosen"))
            or d_row["plan_title"]
            or (d_row["plan_action_type"].replace("_", " ") if d_row["plan_action_type"] else None)
            or "Expedited supply coordination and alternative routing"
        )

        draft_content = None
        api_key = os.getenv("LLM_API_KEY", "").strip()

        if api_key:
            prompt = f"""You are a logistics operations coordinator drafting an email to a {audience_norm}.
Draft a concise, polite, professional operations email using ONLY the verified facts below.
NEVER invent tracking numbers, fake carrier promises, dates, or details not provided in the facts.
Return a JSON object with exactly two keys: "subject" and "body".

VERIFIED OPERATIONAL FACTS:
- Reference / Shipment: {order_code}
- Supplier / Partner: {supplier_name}
- Updated Schedule Date: {new_delivery_date}
- Disruption Reason: {reason}
- Operational Recovery Action: {option_chosen}
"""
            draft_content = call_gemini_draft(prompt, api_key)

        if not draft_content:
            draft_content = get_template_draft(
                audience=audience_norm,
                order_code=order_code,
                customer=supplier_name,
                new_delivery_date=new_delivery_date,
                reason=reason,
                option_chosen=option_chosen,
            )

        cur = conn.execute(
            """INSERT INTO message_drafts (order_id, disruption_id, audience, subject, body, status, created_by)
               VALUES (NULL, ?, ?, ?, ?, 'DRAFT', ?)""",
            (disruption_id, audience_norm, draft_content["subject"], draft_content["body"], actor_id),
        )
        draft_id = cur.lastrowid
        new_draft = {
            "id": draft_id,
            "order_id": None,
            "order_code": order_code,
            "customer": supplier_name,
            "disruption_id": disruption_id,
            "audience": audience_norm,
            "subject": draft_content["subject"],
            "body": draft_content["body"],
            "status": "DRAFT",
            "created_by": actor_id,
            "creator_username": user.get("username", "User"),
            "approved_by": None,
            "approver_username": None,
        }

        write_audit(conn, actor_id, "DRAFT_CREATED", "message_drafts", draft_id, None, new_draft)
        conn.execute(
            """INSERT INTO notifications (user_id, title, body, type, ref_table, ref_id)
               VALUES (?, ?, ?, 'INFO', 'message_drafts', ?)""",
            (
                actor_id,
                f"New {audience_norm} draft created",
                f"Draft #{draft_id} for {order_code} generated. Awaiting peer approval.",
                draft_id,
            ),
        )
        conn.commit()
        return new_draft
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_order_drafts(order_id: int) -> list[dict[str, Any]]:
    """
    List all message drafts for a specific order.
    """
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT md.*, o.code AS order_code, o.customer,
                      u1.username AS creator_username,
                      u2.username AS approver_username
               FROM message_drafts md
               LEFT JOIN orders o ON md.order_id = o.id
               LEFT JOIN users u1 ON md.created_by = u1.id
               LEFT JOIN users u2 ON md.approved_by = u2.id
               WHERE md.order_id = ?
               ORDER BY md.id DESC""",
            (order_id,),
        ).fetchall()

        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_disruption_drafts(disruption_id: int) -> list[dict[str, Any]]:
    """
    List all message drafts for a specific disruption (both order-linked and disruption-level).
    """
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT md.*, o.code AS order_code, o.customer,
                      u1.username AS creator_username,
                      u2.username AS approver_username
               FROM message_drafts md
               LEFT JOIN orders o ON md.order_id = o.id
               LEFT JOIN users u1 ON md.created_by = u1.id
               LEFT JOIN users u2 ON md.approved_by = u2.id
               WHERE md.disruption_id = ?
               ORDER BY md.id DESC""",
            (disruption_id,),
        ).fetchall()

        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_drafts(
    disruption_id: int | None = None,
    order_id: int | None = None,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    List message drafts with optional filters.
    """
    conn = get_conn()
    try:
        sql = """SELECT md.*, o.code AS order_code, o.customer,
                        u1.username AS creator_username,
                        u2.username AS approver_username
                 FROM message_drafts md
                 LEFT JOIN orders o ON md.order_id = o.id
                 LEFT JOIN users u1 ON md.created_by = u1.id
                 LEFT JOIN users u2 ON md.approved_by = u2.id
                 WHERE 1=1"""
        params = []
        if disruption_id is not None:
            sql += " AND md.disruption_id = ?"
            params.append(disruption_id)
        if order_id is not None:
            sql += " AND md.order_id = ?"
            params.append(order_id)
        if status_filter:
            sql += " AND md.status = ?"
            params.append(status_filter.upper().strip())
        sql += " ORDER BY md.id DESC"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_draft_by_id(draft_id: int) -> dict[str, Any]:
    """
    Retrieve single draft by ID.
    """
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT md.*, o.code AS order_code, o.customer,
                      u1.username AS creator_username,
                      u2.username AS approver_username
               FROM message_drafts md
               LEFT JOIN orders o ON md.order_id = o.id
               LEFT JOIN users u1 ON md.created_by = u1.id
               LEFT JOIN users u2 ON md.approved_by = u2.id
               WHERE md.id = ?""",
            (draft_id,),
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Draft #{draft_id} not found.",
            )
        return dict(row)
    finally:
        conn.close()


def approve_draft(draft_id: int, user: dict) -> dict[str, Any]:
    """
    Approve a message draft.
    Hard rule 4 & separation of duty: approver must be a different user than the creator.
    """
    actor_id = int(user["sub"])
    conn = get_conn()
    try:
        draft = conn.execute("SELECT * FROM message_drafts WHERE id = ?", (draft_id,)).fetchone()
        if not draft:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Draft #{draft_id} not found.",
            )

        old_draft = dict(draft)

        # Separation of duty: approver must not be the creator
        if actor_id == old_draft["created_by"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Separation of duty violation: approver must be a different user than the creator.",
            )

        if old_draft["status"] != "DRAFT":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot approve draft in state '{old_draft['status']}'. Draft must be in 'DRAFT' status.",
            )

        conn.execute(
            """UPDATE message_drafts
               SET status = 'APPROVED', approved_by = ?
               WHERE id = ?""",
            (actor_id, draft_id),
        )

        new_draft = dict(old_draft)
        new_draft["status"] = "APPROVED"
        new_draft["approved_by"] = actor_id
        new_draft["approver_username"] = user.get("username", "Approver")

        write_audit(conn, actor_id, "DRAFT_APPROVED", "message_drafts", draft_id, old_draft, new_draft)

        # Notify the creator that their draft was approved
        conn.execute(
            """INSERT INTO notifications (user_id, title, body, type, ref_table, ref_id)
               VALUES (?, ?, ?, 'APPROVAL', 'message_drafts', ?)""",
            (
                old_draft["created_by"],
                f"Draft #{draft_id} approved",
                f"Your {old_draft['audience']} communication draft has been approved by {user.get('username', 'a peer')}.",
                draft_id,
            ),
        )
        conn.commit()

        return new_draft
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def send_simulated_draft(draft_id: int, user: dict) -> dict[str, Any]:
    """
    Simulate sending an approved draft.
    Does NOT send anything externally.
    Marks status as 'SENT_SIMULATED' and writes audit_logs.
    Only works on APPROVED drafts (returns 409 Conflict otherwise).
    """
    actor_id = int(user["sub"])
    conn = get_conn()
    try:
        draft = conn.execute("SELECT * FROM message_drafts WHERE id = ?", (draft_id,)).fetchone()
        if not draft:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Draft #{draft_id} not found.",
            )

        old_draft = dict(draft)

        if old_draft["status"] != "APPROVED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot send draft in state '{old_draft['status']}'. Only APPROVED drafts can be sent.",
            )

        conn.execute(
            """UPDATE message_drafts
               SET status = 'SENT_SIMULATED'
               WHERE id = ?""",
            (draft_id,),
        )

        new_draft = dict(old_draft)
        new_draft["status"] = "SENT_SIMULATED"

        write_audit(
            conn,
            actor_id,
            "DRAFT_SENT_SIMULATED",
            "message_drafts",
            draft_id,
            old_draft,
            new_draft,
            note=f"Simulated dispatch of {old_draft['audience']} message",
        )

        conn.execute(
            """INSERT INTO notifications (user_id, title, body, type, ref_table, ref_id)
               VALUES (?, ?, ?, 'INFO', 'message_drafts', ?)""",
            (
                actor_id,
                f"Simulated dispatch completed",
                f"Communication draft #{draft_id} ({old_draft['audience']}) has been simulated as sent and recorded in the audit trail.",
                draft_id,
            ),
        )
        conn.commit()

        return new_draft
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def edit_draft(draft_id: int, subject: str, body: str, user: dict) -> dict[str, Any]:
    """
    Edit an existing message draft's subject and body.
    Cannot edit already sent messages (returns 409 Conflict).
    Resets status to DRAFT and requires re-approval.
    """
    actor_id = int(user["sub"])
    conn = get_conn()
    try:
        draft = conn.execute("SELECT * FROM message_drafts WHERE id = ?", (draft_id,)).fetchone()
        if not draft:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Draft #{draft_id} not found.",
            )

        old_draft = dict(draft)

        if old_draft["status"] == "SENT_SIMULATED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot edit a draft that has already been sent.",
            )

        # Update subject, body, reset to DRAFT if it was approved
        new_status = "DRAFT"
        conn.execute(
            """UPDATE message_drafts
               SET subject = ?, body = ?, status = ?, approved_by = NULL
               WHERE id = ?""",
            (subject, body, new_status, draft_id),
        )

        new_draft = dict(old_draft)
        new_draft["subject"] = subject
        new_draft["body"] = body
        new_draft["status"] = new_status
        new_draft["approved_by"] = None

        write_audit(conn, actor_id, "DRAFT_EDITED", "message_drafts", draft_id, old_draft, new_draft)
        conn.commit()

        return new_draft
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
