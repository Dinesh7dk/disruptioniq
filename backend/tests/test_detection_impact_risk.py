"""
backend/tests/test_detection_impact_risk.py

Tests for:
1. Detection engine (late shipment, stock shortage, no duplicate active disruptions).
2. Impact analysis & Deterministic Risk scoring.
3. Scenario 1 test:
   Delaying SH-001 by 6 days:
   - Ranks O-001 above O-002 above O-003.
   - Verifies that risk breakdown points sum EXACTLY to the risk_score for each order.
   - Verifies risk levels and explainability reasons.
"""
import sys
import json
from datetime import date, timedelta
from pathlib import Path
import pytest

from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.seed.seed import seed as _do_seed
from backend.db import get_conn
from backend.services.detection import run_detection, detect_late_shipments, detect_stock_shortages
from backend.services.impact import analyze_impact


@pytest.fixture(autouse=True)
def reset_db():
    _do_seed()


class TestScenario1AndRisk:
    def test_sh001_delay_ranking_and_breakdown_sum(self):
        """
        Delay SH-001 by 6 days:
        - Ranks O-001 above O-002 above O-003.
        - Each order's risk breakdown values sum exactly to its risk_score.
        """
        conn = get_conn()
        try:
            # SH-001 expected_arrival was day 2, update current_eta to day 8 (delay of 6 days)
            sh = conn.execute("SELECT id, expected_arrival FROM shipments WHERE code = 'SH-001'").fetchone()
            base_date = date.fromisoformat(sh["expected_arrival"])
            new_eta = (base_date + timedelta(days=6)).isoformat()

            conn.execute(
                "UPDATE shipments SET current_eta = ?, delay_days = 6, status = 'DELAYED' WHERE id = ?",
                (new_eta, sh["id"]),
            )
            conn.commit()
        finally:
            conn.close()

        # Run detection
        disruptions = run_detection(shipment_id=sh["id"])
        assert len(disruptions) > 0

        # Find the disruption for SH-001
        conn = get_conn()
        try:
            disr = conn.execute(
                "SELECT id FROM disruptions WHERE shipment_id = ? AND status = 'OPEN'",
                (sh["id"],),
            ).fetchone()
            assert disr is not None
            disruption_id = disr["id"]

            # Query impacts ordered by risk_score DESC
            impact_rows = conn.execute(
                """SELECT di.*, o.code as order_code, o.customer, o.priority
                   FROM disruption_impacts di
                   JOIN orders o ON di.order_id = o.id
                   WHERE di.disruption_id = ?
                   ORDER BY di.risk_score DESC""",
                (disruption_id,),
            ).fetchall()

            order_codes = [r["order_code"] for r in impact_rows]
            print(f"Impacts order codes: {order_codes}")

            # Verify O-001 > O-002 > O-003
            assert "O-001" in order_codes
            assert "O-002" in order_codes
            assert "O-003" in order_codes
            idx_001 = order_codes.index("O-001")
            idx_002 = order_codes.index("O-002")
            idx_003 = order_codes.index("O-003")

            assert idx_001 < idx_002 < idx_003, f"Expected O-001 < O-002 < O-003, got indices: {idx_001}, {idx_002}, {idx_003}"

            # Verify each breakdown sums to its score
            for r in impact_rows:
                breakdown = json.loads(r["risk_breakdown"])
                reasons = json.loads(r["risk_reasons"])
                score = r["risk_score"]

                assert isinstance(breakdown, dict)
                assert isinstance(reasons, list)
                assert len(reasons) > 0

                breakdown_sum = round(sum(breakdown.values()), 1)
                assert breakdown_sum == score, f"For {r['order_code']}: breakdown sum {breakdown_sum} != risk_score {score}"

                # Verify expected weights exist
                assert "urgency" in breakdown
                assert "delay_length" in breakdown
                assert "customer_priority" in breakdown
                assert "shortfall_size" in breakdown
                assert "lack_of_alternative_stock" in breakdown

            # Check individual levels
            row_001 = next(r for r in impact_rows if r["order_code"] == "O-001")
            row_002 = next(r for r in impact_rows if r["order_code"] == "O-002")
            row_003 = next(r for r in impact_rows if r["order_code"] == "O-003")

            assert row_001["risk_level"] == "HIGH"
            assert row_001["risk_score"] >= 70.0
            assert row_002["risk_score"] > row_003["risk_score"]
        finally:
            conn.close()

    def test_no_duplicate_active_disruptions(self):
        """
        Running detection multiple times must never create a second active (OPEN) disruption
        for the same shipment or target.
        """
        conn = get_conn()
        try:
            sh = conn.execute("SELECT id, expected_arrival FROM shipments WHERE code = 'SH-001'").fetchone()
            base_date = date.fromisoformat(sh["expected_arrival"])
            new_eta = (base_date + timedelta(days=5)).isoformat()
            conn.execute(
                "UPDATE shipments SET current_eta = ?, delay_days = 5, status = 'DELAYED' WHERE id = ?",
                (new_eta, sh["id"]),
            )
            conn.commit()
        finally:
            conn.close()

        # Run detection 3 times
        run_detection(sh["id"])
        run_detection(sh["id"])
        run_detection(sh["id"])

        conn = get_conn()
        try:
            count = conn.execute(
                "SELECT COUNT(*) as cnt FROM disruptions WHERE shipment_id = ? AND status = 'OPEN'",
                (sh["id"],),
            ).fetchone()["cnt"]
            assert count == 1, f"Expected exactly 1 OPEN disruption, got {count}"
        finally:
            conn.close()

    def test_detect_stock_shortage(self):
        """
        Stock shortage scenario: Bangalore P2 has demand 60, available 5.
        Should detect a STOCK_SHORTAGE disruption.
        """
        disruptions = detect_stock_shortages()
        assert len(disruptions) > 0

        conn = get_conn()
        try:
            d = conn.execute(
                """SELECT d.*, p.code as pcode, w.city as wcity
                   FROM disruptions d
                   JOIN products p ON d.product_id = p.id
                   JOIN warehouses w ON d.warehouse_id = w.id
                   WHERE d.type = 'STOCK_SHORTAGE' AND p.code = 'P2' AND w.city = 'Bangalore' AND d.status = 'OPEN'"""
            ).fetchone()
            assert d is not None
            assert "shortfall 55" in d["description"]
        finally:
            conn.close()
