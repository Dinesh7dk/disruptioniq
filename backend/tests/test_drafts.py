"""
backend/tests/test_drafts.py

Tests for LLM-assisted drafted messages, peer approval (separation of duty),
simulated dispatch, and audit logging.
"""
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.seed.seed import seed as _do_seed
from backend.main import app
from backend.db import get_conn


@pytest.fixture(autouse=True)
def reset_db():
    _do_seed()


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _token(client, username, password="pass123"):
    if username == "admin":
        password = "admin123"
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_create_draft_customer_and_supplier(client):
    """Verify customer and supplier drafts can be created and use verified facts."""
    t_alice = _token(client, "alice")  # Operations Analyst

    # 1. Customer draft
    res1 = client.post(
        "/orders/1/drafts",
        headers={"Authorization": f"Bearer {t_alice}"},
        json={"audience": "CUSTOMER"},
    )
    assert res1.status_code == 200, res1.text
    d1 = res1.json()
    assert d1["status"] == "DRAFT"
    assert d1["audience"] == "CUSTOMER"
    assert d1["order_id"] == 1
    assert "subject" in d1 and len(d1["subject"]) > 5
    assert "body" in d1 and len(d1["body"]) > 20
    assert d1["created_by"] == 1  # Alice

    # 2. Supplier draft
    res2 = client.post(
        "/orders/1/drafts",
        headers={"Authorization": f"Bearer {t_alice}"},
        json={"audience": "SUPPLIER"},
    )
    assert res2.status_code == 200, res2.text
    d2 = res2.json()
    assert d2["status"] == "DRAFT"
    assert d2["audience"] == "SUPPLIER"
    assert d2["order_id"] == 1

    # 3. Invalid audience fails
    res_bad = client.post(
        "/orders/1/drafts",
        headers={"Authorization": f"Bearer {t_alice}"},
        json={"audience": "INTERNAL"},
    )
    assert res_bad.status_code == 400


def test_separation_of_duty_approval(client):
    """Creator cannot approve their own draft (403); second user can approve."""
    t_alice = _token(client, "alice")  # Operations Analyst
    t_carol = _token(client, "carol")  # Supply Chain Manager

    # Alice creates draft
    create_res = client.post(
        "/orders/1/drafts",
        headers={"Authorization": f"Bearer {t_alice}"},
        json={"audience": "CUSTOMER"},
    )
    assert create_res.status_code == 200
    draft_id = create_res.json()["id"]

    # Alice tries to self-approve -> 403 Forbidden
    self_app = client.post(
        f"/drafts/{draft_id}/approve",
        headers={"Authorization": f"Bearer {t_alice}"},
    )
    assert self_app.status_code == 403
    assert "Separation of duty violation" in self_app.json()["detail"]

    # Carol (second user) approves -> 200 OK
    peer_app = client.post(
        f"/drafts/{draft_id}/approve",
        headers={"Authorization": f"Bearer {t_carol}"},
    )
    assert peer_app.status_code == 200
    approved = peer_app.json()
    assert approved["status"] == "APPROVED"
    assert approved["approved_by"] == 3  # Carol


def test_cannot_send_unapproved_draft(client):
    """Unapproved draft cannot be sent (409 Conflict)."""
    t_alice = _token(client, "alice")
    t_carol = _token(client, "carol")

    create_res = client.post(
        "/orders/1/drafts",
        headers={"Authorization": f"Bearer {t_alice}"},
        json={"audience": "CUSTOMER"},
    )
    draft_id = create_res.json()["id"]

    # Alice tries to send unapproved draft -> 409 Conflict
    send_res = client.post(
        f"/drafts/{draft_id}/send",
        headers={"Authorization": f"Bearer {t_alice}"},
    )
    assert send_res.status_code == 409
    assert "Only APPROVED drafts can be sent" in send_res.json()["detail"]


def test_send_simulated_and_audit_logged(client):
    """End-to-end happy path: create -> approve by peer -> send simulated -> audit logged."""
    t_alice = _token(client, "alice")
    t_bob = _token(client, "bob")

    # 1. Alice creates draft
    create_res = client.post(
        "/orders/2/drafts",
        headers={"Authorization": f"Bearer {t_alice}"},
        json={"audience": "CUSTOMER"},
    )
    assert create_res.status_code == 200
    draft_id = create_res.json()["id"]

    # 2. Bob approves draft
    app_res = client.post(
        f"/drafts/{draft_id}/approve",
        headers={"Authorization": f"Bearer {t_bob}"},
    )
    assert app_res.status_code == 200
    assert app_res.json()["status"] == "APPROVED"

    # 3. Send simulated
    send_res = client.post(
        f"/drafts/{draft_id}/send",
        headers={"Authorization": f"Bearer {t_alice}"},
    )
    assert send_res.status_code == 200
    sent_draft = send_res.json()
    assert sent_draft["status"] == "SENT_SIMULATED"

    # 4. Cannot send again once already sent
    send_res2 = client.post(
        f"/drafts/{draft_id}/send",
        headers={"Authorization": f"Bearer {t_alice}"},
    )
    assert send_res2.status_code == 409

    # 5. Check audit logs
    conn = get_conn()
    try:
        logs = conn.execute(
            "SELECT action, entity_type, entity_id FROM audit_logs WHERE entity_type = 'message_drafts' AND entity_id = ? ORDER BY id ASC",
            (draft_id,),
        ).fetchall()
        actions = [r["action"] for r in logs]
        assert "DRAFT_CREATED" in actions
        assert "DRAFT_APPROVED" in actions
        assert "DRAFT_SENT_SIMULATED" in actions
    finally:
        conn.close()


def test_edit_draft_resets_approval(client):
    """Editing an approved draft resets status to DRAFT and requires re-approval."""
    t_alice = _token(client, "alice")
    t_carol = _token(client, "carol")

    # Create & approve
    d_res = client.post(
        "/orders/1/drafts",
        headers={"Authorization": f"Bearer {t_alice}"},
        json={"audience": "CUSTOMER"},
    )
    draft_id = d_res.json()["id"]

    client.post(
        f"/drafts/{draft_id}/approve",
        headers={"Authorization": f"Bearer {t_carol}"},
    )

    # Alice edits the draft
    edit_res = client.put(
        f"/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {t_alice}"},
        json={
            "subject": "Updated Custom Subject",
            "body": "Updated body explaining additional mitigation steps.",
        },
    )
    assert edit_res.status_code == 200
    edited = edit_res.json()
    assert edited["status"] == "DRAFT"
    assert edited["approved_by"] is None
    assert edited["subject"] == "Updated Custom Subject"

    # Cannot send directly now
    send_res = client.post(
        f"/drafts/{draft_id}/send",
        headers={"Authorization": f"Bearer {t_alice}"},
    )
    assert send_res.status_code == 409

    # Carol re-approves
    app2 = client.post(
        f"/drafts/{draft_id}/approve",
        headers={"Authorization": f"Bearer {t_carol}"},
    )
    assert app2.status_code == 200
    assert app2.json()["status"] == "APPROVED"

    # Alice sends
    send2 = client.post(
        f"/drafts/{draft_id}/send",
        headers={"Authorization": f"Bearer {t_alice}"},
    )
    assert send2.status_code == 200
    assert send2.json()["status"] == "SENT_SIMULATED"

    # Cannot edit after simulated sending
    edit_after_send = client.put(
        f"/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {t_alice}"},
        json={"subject": "Should fail", "body": "Should fail"},
    )
    assert edit_after_send.status_code == 409
