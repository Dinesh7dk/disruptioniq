"""
backend/tests/test_monitoring.py
Tests for monitoring endpoints and role restrictions:
- GET /dashboard/summary
- GET /disruptions
- GET /disruptions/{id}
- GET /orders?sort=risk
- GET /notifications
- GET /audit (Administrator and Supply Chain Manager only; 403 for others)
- GET /events/recent
"""
import os
import sys
import pytest
from pathlib import Path
from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import app
from backend.seed.seed import seed
from backend.services.detection import run_detection
from datetime import date, timedelta
from backend.db import get_conn


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(scope="module", autouse=True)
def setup_data():
    seed()
    conn = get_conn()
    sh = conn.execute("SELECT id, expected_arrival FROM shipments WHERE code = 'SH-001'").fetchone()
    base_date = date.fromisoformat(sh["expected_arrival"])
    new_eta = (base_date + timedelta(days=6)).isoformat()
    conn.execute(
        "UPDATE shipments SET current_eta = ?, delay_days = 6, status = 'DELAYED' WHERE id = ?",
        (new_eta, sh["id"]),
    )
    conn.commit()
    conn.close()
    run_detection(shipment_id=1)


@pytest.fixture(scope="module")
def tokens(client):
    users = {
        "analyst": ("anita", "pass123"),
        "manager": ("meera", "pass123"),
        "operator": ("ravi", "pass123"),
        "procurement": ("priya", "pass123"),
        "admin": ("admin", "admin123"),
    }
    t = {}
    for role_name, (u, p) in users.items():
        resp = client.post("/auth/login", json={"username": u, "password": p})
        assert resp.status_code == 200, f"Login failed for {u}: {resp.text}"
        t[role_name] = resp.json()["access_token"]
    return t


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


class TestDashboardSummary:
    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/dashboard/summary")
        assert resp.status_code == 401

    def test_all_roles_can_access_summary(self, client, tokens):
        for role_name, token in tokens.items():
            resp = client.get("/dashboard/summary", headers=auth_header(token))
            assert resp.status_code == 200, f"Failed for {role_name}: {resp.text}"
            data = resp.json()
            assert "active_disruptions" in data
            assert "affected_orders" in data
            assert "pending_approvals" in data
            assert "executed_plans" in data
            assert data["active_disruptions"] >= 1
            assert data["affected_orders"] >= 1


class TestDisruptionsEndpoints:
    def test_disruptions_list_authenticated(self, client, tokens):
        resp = client.get("/disruptions", headers=auth_header(tokens["analyst"]))
        assert resp.status_code == 200
        disruptions = resp.json()
        assert isinstance(disruptions, list)
        assert len(disruptions) > 0
        d1 = next(d for d in disruptions if d["id"] == 1)
        assert d1["type"] == "SUPPLIER_DELAY"
        assert d1["status"] == "OPEN"
        assert d1["shipment"]["code"] == "SH-001"
        assert d1["affected_orders_count"] == 3

    def test_disruption_detail_contains_impacts_options_summary(self, client, tokens):
        resp = client.get("/disruptions/1", headers=auth_header(tokens["manager"]))
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
        assert "ai_summary" in data
        assert "ai_source" in data
        assert data["ai_source"] in ["GEMINI_LLM", "FALLBACK"]
        
        # Check impacts
        impacts = data["impacts"]
        assert len(impacts) == 3
        o001 = impacts[0]
        assert o001["order_code"] == "O-001"
        assert isinstance(o001["reasons"], list)
        assert len(o001["reasons"]) > 0
        assert isinstance(o001["breakdown"], dict)
        assert "shortfall_size" in o001["breakdown"]

        # Check options
        options = data["options"]
        assert isinstance(options, list)
        assert any(opt["type"] == "REALLOCATE_STOCK" and "Hyderabad" in opt["details"]["description"] for opt in options)

    def test_disruption_not_found_returns_404(self, client, tokens):
        resp = client.get("/disruptions/99999", headers=auth_header(tokens["analyst"]))
        assert resp.status_code == 404

    def test_disruption_graph_cascade(self, client, tokens):
        """
        Verify GET /disruptions/{id}/graph returns {nodes, edges} for
        Supplier -> Shipment -> Warehouse -> Orders -> Customers,
        with risk level and breakdown on each order node.
        """
        resp = client.get("/disruptions/1/graph", headers=auth_header(tokens["analyst"]))
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        nodes = data["nodes"]
        edges = data["edges"]

        # Check node entity types present
        entity_types = {n["data"]["entity_type"] for n in nodes}
        assert "supplier" in entity_types
        assert "shipment" in entity_types
        assert "warehouse" in entity_types
        assert "order" in entity_types
        assert "customer" in entity_types

        # Verify risk level on each order node
        order_nodes = [n for n in nodes if n["data"]["entity_type"] == "order"]
        assert len(order_nodes) >= 1
        for onode in order_nodes:
            d = onode["data"]
            assert d["risk_level"] in ("HIGH", "MEDIUM", "LOW")
            assert "risk_score" in d
            assert "risk_breakdown" in d
            assert isinstance(d["risk_breakdown"], dict)
            assert "order_code" in d

        # Check edge cascade links
        edge_pairs = {(e["source"], e["target"]) for e in edges}
        sup_node = next(n for n in nodes if n["data"]["entity_type"] == "supplier")
        ship_node = next(n for n in nodes if n["data"]["entity_type"] == "shipment")
        wh_node = next(n for n in nodes if n["data"]["entity_type"] == "warehouse")

        assert (sup_node["id"], ship_node["id"]) in edge_pairs
        assert (ship_node["id"], wh_node["id"]) in edge_pairs

        # Each order connected from warehouse and to its customer
        for onode in order_nodes:
            assert (wh_node["id"], onode["id"]) in edge_pairs
            cust_edges = [e for e in edges if e["source"] == onode["id"]]
            assert len(cust_edges) >= 1

        # Unauthenticated returns 401
        assert client.get("/disruptions/1/graph").status_code == 401

        # Not found returns 404
        assert client.get("/disruptions/99999/graph", headers=auth_header(tokens["analyst"])).status_code == 404


class TestOrdersEndpoint:
    def test_orders_sorted_by_risk(self, client, tokens):
        resp = client.get("/orders?sort=risk", headers=auth_header(tokens["operator"]))
        assert resp.status_code == 200
        orders = resp.json()
        assert isinstance(orders, list)
        assert len(orders) >= 3
        # First order must have highest risk score
        assert orders[0]["code"] == "O-001"
        assert orders[0]["risk_score"] >= orders[1]["risk_score"]
        assert orders[1]["code"] == "O-002"
        assert orders[1]["risk_score"] >= orders[2]["risk_score"]
        # Reasons and breakdown present
        assert isinstance(orders[0]["reasons"], list)
        assert len(orders[0]["reasons"]) > 0
        assert isinstance(orders[0]["lines"], list)


class TestNotificationsEndpoint:
    def test_notifications_accessible_by_authenticated_user(self, client, tokens):
        resp = client.get("/notifications", headers=auth_header(tokens["analyst"]))
        assert resp.status_code == 200
        notifs = resp.json()
        assert isinstance(notifs, list)


class TestAuditRoleRestrictions:
    def test_audit_unauthenticated_returns_401(self, client):
        resp = client.get("/audit")
        assert resp.status_code == 401

    def test_admin_can_access_audit(self, client, tokens):
        resp = client.get("/audit", headers=auth_header(tokens["admin"]))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_supply_chain_manager_can_access_audit(self, client, tokens):
        resp = client.get("/audit", headers=auth_header(tokens["manager"]))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_operations_analyst_gets_403_on_audit(self, client, tokens):
        resp = client.get("/audit", headers=auth_header(tokens["analyst"]))
        assert resp.status_code == 403
        assert "not authorised" in resp.json()["detail"].lower()

    def test_warehouse_operator_gets_403_on_audit(self, client, tokens):
        resp = client.get("/audit", headers=auth_header(tokens["operator"]))
        assert resp.status_code == 403

    def test_procurement_approver_gets_403_on_audit(self, client, tokens):
        resp = client.get("/audit", headers=auth_header(tokens["procurement"]))
        assert resp.status_code == 403


class TestRecentEventsEndpoint:
    def test_events_recent_returns_combined_feed(self, client, tokens):
        resp = client.get("/events/recent", headers=auth_header(tokens["analyst"]))
        assert resp.status_code == 200
        events = resp.json()
        assert isinstance(events, list)
        assert len(events) <= 50
        for ev in events:
            assert ev["category"] in ["audit", "webhook"]
            assert "timestamp" in ev
            assert "title" in ev
