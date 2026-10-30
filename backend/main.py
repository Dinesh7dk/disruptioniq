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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # tighten for production
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



