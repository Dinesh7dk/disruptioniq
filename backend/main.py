"""
backend/main.py
FastAPI application entry point.
"""
import os
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json as _json

# Load .env before any module reads os.getenv
load_dotenv()

from backend.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    require_role,
)
from backend.services.import_service import (
    import_shipments_csv,
    import_shipments_json,
    import_orders_json,
)
from backend.db import get_conn
from backend.services.detection import run_detection
from backend.services.recovery import generate_options
from backend.services.approval import (
    propose_plan,
    approve_plan,
    reject_plan,
    modify_plan,
    execute_plan,
)
from backend.services.monitoring import (
    get_dashboard_summary,
    get_all_disruptions,
    get_disruption_by_id,
    get_orders,
    get_notifications,
    get_audit_logs,
    get_recent_events,
    get_disruption_graph,
)
from backend.services.simulator import simulate_option, simulate_plan
from backend.services.drafts import (
    create_order_draft,
    create_disruption_draft,
    get_order_drafts,
    get_disruption_drafts,
    get_all_drafts,
    get_draft_by_id,
    approve_draft,
    send_simulated_draft,
    edit_draft,
)
from pydantic import Field

# ── App setup ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast at startup if JWT_SECRET is missing
    from backend.auth import _secret
    _secret()
    yield

app = FastAPI(
    title="DisruptionIQ API",
    description="Logistics disruption detection and recovery platform.",
    version="0.1.0",
    lifespan=lifespan,
)

allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class MeResponse(BaseModel):
    id: int
    username: str
    role: str


class CarrierWebhookRequest(BaseModel):
    event_id: str = Field(..., min_length=1)
    shipment_ref: str = Field(..., min_length=1)
    status: str = Field(..., min_length=1)
    new_eta: str = Field(..., min_length=1)


class ProposePlanRequest(BaseModel):
    title: str = Field(..., min_length=1)
    action_type: str = Field(..., min_length=1)
    description: str = ""
    plan_payload: dict[str, Any] = Field(default_factory=dict)


class DecisionRequest(BaseModel):
    note: str | None = None


class ModifyPlanRequest(BaseModel):
    new_quantity: int | None = None
    new_option_details: dict[str, Any] | None = None
    note: str | None = None


class SimulationRequest(BaseModel):
    action_type: str | None = None
    option_type: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class CreateDraftRequest(BaseModel):
    audience: str = Field(..., description="CUSTOMER or SUPPLIER")
    order_id: int | None = None
    custom_facts: dict[str, Any] | None = None


class EditDraftRequest(BaseModel):
    subject: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)



# ── Routes ─────────────────────────────────────────────────────────────────────

@app.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def login(body: LoginRequest):
    """
    Authenticate with username + password.
    Returns a signed JWT valid for 12 hours.
    """
    user  = authenticate_user(body.username, body.password)
    token = create_access_token(user["id"], user["username"], user["role"])
    return TokenResponse(
        access_token=token,
        username=user["username"],
        role=user["role"],
    )


@app.get("/me", response_model=MeResponse, tags=["auth"])
def me(user: dict = Depends(get_current_user)):
    """Return the currently authenticated user's identity."""
    return MeResponse(id=int(user["sub"]), username=user["username"], role=user["role"])


# ── Role-restricted example endpoints (used in tests) ─────────────────────────

@app.get("/admin/ping", tags=["admin"])
def admin_ping(user: dict = Depends(require_role("Administrator"))):
    """Reachable only by Administrator role."""
    return {"message": f"Hello, {user['username']}! Admin area."}


@app.get("/analyst/ping", tags=["analyst"])
def analyst_ping(
    user: dict = Depends(require_role("Operations Analyst", "Supply Chain Manager"))
):
    """Reachable by Operations Analyst or Supply Chain Manager."""
    return {"message": f"Hello, {user['username']}!"}


# ── Import endpoints ──────────────────────────────────────────────────────────

@app.post("/import/shipments/csv", tags=["import"])
@app.post("/import/csv", tags=["import"])
async def import_csv_endpoint(
    file: UploadFile = File(...),
    user: dict = Depends(require_role("Administrator", "Operations Analyst")),
):
    content = await file.read()
    return import_shipments_csv(content, actor_id=int(user["sub"]))


@app.post("/import/shipments/json", tags=["import"])
def import_shipments_json_endpoint(
    records: list[dict[str, Any]],
    user: dict = Depends(require_role("Administrator", "Operations Analyst")),
):
    return import_shipments_json(records, actor_id=int(user["sub"]))


@app.post("/import/orders/json", tags=["import"])
def import_orders_json_endpoint(
    records: list[dict[str, Any]],
    user: dict = Depends(require_role("Administrator", "Operations Analyst")),
):
    return import_orders_json(records, actor_id=int(user["sub"]))


@app.post("/import/json", tags=["import"])
def import_json_endpoint(
    records: list[dict[str, Any]],
    user: dict = Depends(require_role("Administrator", "Operations Analyst")),
):
    if records and "lines" in records[0]:
        return import_orders_json(records, actor_id=int(user["sub"]))
    return import_shipments_json(records, actor_id=int(user["sub"]))


# ── Webhook endpoints ─────────────────────────────────────────────────────────

@app.post("/webhooks/carrier", tags=["webhooks"])
def carrier_webhook(event: CarrierWebhookRequest):
    """
    Simulated carrier webhook.
    - Idempotent: duplicate event_id returns {"status": "duplicate, ignored"} without changes.
    - Updates shipment current_eta and status in one transaction.
    - 404 on unknown shipment.
    - 422 on invalid payload (handled by Pydantic).
    - Calls run_detection(shipment_id) after transaction commits.
    """
    conn = get_conn()
    shipment_id = None
    try:
        # Check if event already exists
        existing_event = conn.execute(
            "SELECT event_id FROM webhook_events WHERE event_id = ?",
            (event.event_id,),
        ).fetchone()

        if existing_event:
            return {"status": "duplicate, ignored"}

        # Check shipment exists
        shipment = conn.execute(
            "SELECT id, code, expected_arrival, status FROM shipments WHERE code = ?",
            (event.shipment_ref,),
        ).fetchone()

        if not shipment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Shipment '{event.shipment_ref}' not found",
            )

        shipment_id = shipment["id"]

        # In ONE transaction: record event + update shipment + write audit log
        conn.execute("BEGIN TRANSACTION;")
        
        conn.execute(
            """INSERT INTO webhook_events (event_id, source, event_type, payload, status, processed_at)
               VALUES (?, 'carrier', 'CARRIER_UPDATE', ?, 'PROCESSED', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))""",
            (event.event_id, _json.dumps(event.model_dump())),
        )

        conn.execute(
            """UPDATE shipments
               SET current_eta = ?, status = ?
               WHERE id = ?""",
            (event.new_eta, event.status, shipment_id),
        )

        conn.execute(
            """INSERT INTO audit_logs (actor_id, action, entity_type, entity_id, new_value)
               VALUES (NULL, 'CARRIER_WEBHOOK_PROCESSED', 'shipments', ?, ?)""",
            (shipment_id, _json.dumps(event.model_dump())),
        )

        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process webhook: {str(e)}",
        )
    finally:
        conn.close()

    # Trigger detection outside the transaction
    if shipment_id is not None:
        run_detection(shipment_id)

    return {"status": "processed", "shipment_id": shipment_id}


# ── Disruption endpoints ──────────────────────────────────────────────────────

@app.get("/disruptions", tags=["disruptions"])
def list_disruptions(user: dict = Depends(get_current_user)):
    """List all disruptions with status, shipment/warehouse/product details, and impact stats."""
    return get_all_disruptions()


@app.get("/disruptions/{id}", tags=["disruptions"])
def get_disruption(id: int, user: dict = Depends(get_current_user)):
    """Disruption details: impacts, reasons, breakdowns, options, AI summary and its source."""
    disruption = get_disruption_by_id(id)
    if disruption is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Disruption {id} not found.",
        )
    return disruption


@app.get("/disruptions/{id}/graph", tags=["disruptions"])
def disruption_graph(id: int, user: dict = Depends(get_current_user)):
    """
    Supply chain cascade graph for Supplier -> Shipment -> Warehouse -> Orders -> Customers,
    with risk level and breakdown on each order node.
    """
    return get_disruption_graph(disruption_id=id)


@app.get("/disruptions/{id}/options", tags=["disruptions"])
def get_disruption_options(
    id: int,
    order_id: int | None = None,
    user: dict = Depends(get_current_user),
):
    """
    Returns only verified feasible recovery options for the given disruption.
    No database writes and no LLM.
    """
    options = generate_options(disruption_id=id, order_id=order_id)
    return {"disruption_id": id, "options_count": len(options), "options": options}


# ── Recovery Plan Approval & Execution Endpoints ──────────────────────────────

@app.post("/disruptions/{id}/plans", tags=["plans"])
def propose_disruption_plan(
    id: int,
    body: ProposePlanRequest,
    user: dict = Depends(require_role("Operations Analyst", "Administrator")),
):
    """Propose a recovery plan for a disruption (Operations Analyst role)."""
    return propose_plan(
        disruption_id=id,
        title=body.title,
        action_type=body.action_type,
        description=body.description,
        plan_payload=body.plan_payload,
        actor=user,
    )


@app.post("/plans/{id}/approve", tags=["plans"])
def approve_recovery_plan(
    id: int,
    body: DecisionRequest = DecisionRequest(),
    user: dict = Depends(
        require_role("Supply Chain Manager", "Procurement Approver", "Administrator")
    ),
):
    """Approve a recovery plan (approver must not be the proposer)."""
    return approve_plan(plan_id=id, note=body.note, actor=user)


@app.post("/plans/{id}/reject", tags=["plans"])
def reject_recovery_plan(
    id: int,
    body: DecisionRequest = DecisionRequest(),
    user: dict = Depends(
        require_role("Supply Chain Manager", "Procurement Approver", "Administrator")
    ),
):
    """Reject a recovery plan."""
    return reject_plan(plan_id=id, note=body.note, actor=user)


@app.post("/plans/{id}/modify", tags=["plans"])
def modify_recovery_plan(
    id: int,
    body: ModifyPlanRequest,
    user: dict = Depends(
        require_role("Supply Chain Manager", "Procurement Approver", "Administrator")
    ),
):
    """Modify plan parameters and return it to PENDING_APPROVAL."""
    return modify_plan(
        plan_id=id,
        new_quantity=body.new_quantity,
        new_option_details=body.new_option_details,
        note=body.note,
        actor=user,
    )


@app.post("/plans/{id}/execute", tags=["plans"])
def execute_recovery_plan(
    id: int,
    user: dict = Depends(require_role("Warehouse Operator", "Administrator")),
):
    """Execute an APPROVED plan with stock revalidation and optimistic locking."""
    return execute_plan(plan_id=id, actor=user)


# ── Orders endpoints ───────────────────────────────────────────────────────────

@app.get("/orders", tags=["orders"])
def list_orders(sort: str | None = "risk", user: dict = Depends(get_current_user)):
    """List orders, optionally sorted by risk score descending (sort=risk)."""
    return get_orders(sort_by=sort or "risk")


# ── Dashboard & Monitoring Endpoints ──────────────────────────────────────────

@app.get("/dashboard/summary", tags=["dashboard"])
def dashboard_summary(user: dict = Depends(get_current_user)):
    """Counts of active disruptions, affected orders, pending approvals, executed plans."""
    return get_dashboard_summary()


@app.get("/notifications", tags=["notifications"])
def list_notifications(limit: int = 50, user: dict = Depends(get_current_user)):
    """In-app notifications for the authenticated user/role."""
    return get_notifications(user_id=int(user["sub"]), role=user["role"], limit=limit)


@app.get("/audit", tags=["audit"])
def list_audit_logs(
    limit: int = 100,
    user: dict = Depends(require_role("Administrator", "Supply Chain Manager")),
):
    """Append-only audit logs. Restricted to Administrator and Supply Chain Manager."""
    return get_audit_logs(limit=limit)


@app.get("/events/recent", tags=["events"])
def list_recent_events(limit: int = 50, user: dict = Depends(get_current_user)):
    """Last 50 audit and webhook events combined for a live feed."""
    return get_recent_events(limit=limit)


# ── What-If Simulator Endpoints ───────────────────────────────────────────────

@app.post("/disruptions/{id}/simulate", tags=["simulation"])
def simulate_disruption_endpoint(
    id: int,
    body: SimulationRequest,
    user: dict = Depends(
        require_role("Operations Analyst", "Supply Chain Manager", "Procurement Approver", "Administrator")
    ),
):
    """
    Simulate a recovery action for a disruption inside a transaction that is always rolled back.
    Allowed roles: Operations Analyst, Supply Chain Manager, Procurement Approver, Administrator.
    """
    act = body.action_type or body.option_type
    if not act:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="action_type or option_type is required.",
        )
    return simulate_option(disruption_id=id, action_type=act, parameters=body.parameters)


@app.post("/plans/{id}/simulate", tags=["simulation"])
def simulate_plan_endpoint(
    id: int,
    body: SimulationRequest | None = None,
    user: dict = Depends(
        require_role("Operations Analyst", "Supply Chain Manager", "Procurement Approver", "Administrator")
    ),
):
    """
    Simulate the recovery option defined in a plan inside a transaction that is always rolled back.
    Allowed roles: Operations Analyst, Supply Chain Manager, Procurement Approver, Administrator.
    """
    act = body.action_type or body.option_type if body else None
    params = body.parameters if body else {}
    if act:
        conn = get_conn()
        try:
            plan = conn.execute(
                "SELECT disruption_id, plan_payload FROM recovery_plans WHERE id = ?",
                (id,),
            ).fetchone()
            if not plan:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Plan #{id} not found.",
                )
            disruption_id = plan["disruption_id"]
            merged = _json.loads(plan["plan_payload"] or "{}")
            merged.update(params)
            return simulate_option(
                disruption_id=disruption_id,
                action_type=act,
                parameters=merged,
                plan_id=id,
            )
        finally:
            conn.close()
    return simulate_plan(plan_id=id, parameters_override=params)


# ── Drafted Messages Endpoints ────────────────────────────────────────────────

@app.post("/orders/{id}/drafts", tags=["drafts"])
def create_order_draft_endpoint(
    id: int,
    body: CreateDraftRequest,
    user: dict = Depends(
        require_role("Operations Analyst", "Supply Chain Manager", "Procurement Approver", "Administrator")
    ),
):
    """
    Create an LLM-drafted or template-fallback communication draft for an order.
    Audience must be CUSTOMER or SUPPLIER.
    """
    return create_order_draft(
        order_id=id,
        audience=body.audience,
        user=user,
        custom_facts=body.custom_facts,
    )


@app.get("/orders/{id}/drafts", tags=["drafts"])
def list_order_drafts_endpoint(
    id: int,
    user: dict = Depends(get_current_user),
):
    """List all message drafts for a specific order."""
    return get_order_drafts(order_id=id)


@app.post("/disruptions/{id}/drafts", tags=["drafts"])
def create_disruption_draft_endpoint(
    id: int,
    body: CreateDraftRequest,
    user: dict = Depends(
        require_role("Operations Analyst", "Supply Chain Manager", "Procurement Approver", "Administrator")
    ),
):
    """
    Create an LLM-drafted or template-fallback communication draft for a disruption.
    Audience must be CUSTOMER or SUPPLIER.
    """
    return create_disruption_draft(
        disruption_id=id,
        audience=body.audience,
        user=user,
        order_id=body.order_id,
        custom_facts=body.custom_facts,
    )


@app.get("/disruptions/{id}/drafts", tags=["drafts"])
def list_disruption_drafts_endpoint(
    id: int,
    user: dict = Depends(get_current_user),
):
    """List all message drafts for a specific disruption."""
    return get_disruption_drafts(disruption_id=id)


@app.get("/drafts", tags=["drafts"])
def list_all_drafts_endpoint(
    disruption_id: int | None = None,
    order_id: int | None = None,
    status: str | None = None,
    user: dict = Depends(get_current_user),
):
    """List message drafts, optionally filtered by disruption_id, order_id, or status."""
    return get_all_drafts(disruption_id=disruption_id, order_id=order_id, status_filter=status)


@app.get("/drafts/{id}", tags=["drafts"])
def get_draft_endpoint(
    id: int,
    user: dict = Depends(get_current_user),
):
    """Retrieve details of a single message draft."""
    return get_draft_by_id(draft_id=id)


@app.post("/drafts/{id}/approve", tags=["drafts"])
def approve_draft_endpoint(
    id: int,
    user: dict = Depends(
        require_role("Supply Chain Manager", "Procurement Approver", "Operations Analyst", "Administrator")
    ),
):
    """
    Approve a communication draft.
    Separation of duty (Rule 4): approver must be a different user than the creator.
    """
    return approve_draft(draft_id=id, user=user)


@app.post("/drafts/{id}/send", tags=["drafts"])
def send_draft_endpoint(
    id: int,
    user: dict = Depends(
        require_role("Operations Analyst", "Supply Chain Manager", "Procurement Approver", "Administrator")
    ),
):
    """
    Simulate sending an approved draft.
    Marks status as SENT_SIMULATED and logs to audit_logs.
    """
    return send_simulated_draft(draft_id=id, user=user)


@app.put("/drafts/{id}", tags=["drafts"])
def edit_draft_endpoint(
    id: int,
    body: EditDraftRequest,
    user: dict = Depends(
        require_role("Operations Analyst", "Supply Chain Manager", "Procurement Approver", "Administrator")
    ),
):
    """
    Edit a draft's subject and body before sending.
    Resets status to DRAFT and requires re-approval.
    """
    return edit_draft(draft_id=id, subject=body.subject, body=body.body, user=user)







