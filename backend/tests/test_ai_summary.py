"""
backend/tests/test_ai_summary.py

Tests for:
1. Deterministic template fallback when LLM_API_KEY is missing or empty.
2. Verified LLM recommendation when LLM_API_KEY is configured.
3. Fallback when LLM recommends an option NOT in the verified list.
4. Saving ai_summary and ai_source to disruptions table.
"""
import sys
import os
from pathlib import Path
from datetime import date, timedelta
import pytest

from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.seed.seed import seed as _do_seed
from backend.db import get_conn
from backend.services.detection import run_detection
from backend.services.ai import generate_ai_summary, validate_recommended_option
import backend.services.ai as ai_module


@pytest.fixture(autouse=True)
def reset_db():
    _do_seed()


def setup_disruption():
    conn = get_conn()
    sh = conn.execute("SELECT id, expected_arrival FROM shipments WHERE code = 'SH-001'").fetchone()
    base_date = date.fromisoformat(sh['expected_arrival'])
    new_eta = (base_date + timedelta(days=6)).isoformat()
    conn.execute(
        "UPDATE shipments SET current_eta = ?, delay_days = 6, status = 'DELAYED' WHERE id = ?",
        (new_eta, sh['id']),
    )
    conn.commit()
    conn.close()
    d_ids = run_detection(shipment_id=1)
    return d_ids[0] if d_ids else 1


class TestAISummaryAndFallback:
    def test_fallback_when_key_is_missing(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "")
        did = setup_disruption()

        res = generate_ai_summary(did)
        assert res["source"] == "FALLBACK"
        assert "[Fallback Summary]" in res["summary"]
        assert "REALLOCATE_STOCK" in res["summary"]

        # Check DB update
        conn = get_conn()
        try:
            d = conn.execute("SELECT ai_summary, ai_source FROM disruptions WHERE id = ?", (did,)).fetchone()
            assert d["ai_source"] == "FALLBACK"
            assert d["ai_summary"] == res["summary"]
        finally:
            conn.close()

    def test_summary_with_valid_llm_response(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "mock-gemini-key")
        did = setup_disruption()

        def mock_llm_call(prompt, key):
            return {
                "summary": "Critical delay detected on SH-001 affecting City Hospital.",
                "recommended_option_type": "REALLOCATE_STOCK",
                "recommended_option_description": "Transfer 200 units of P1 from Hyderabad to Chennai"
            }

        monkeypatch.setattr(ai_module, "call_gemini_api", mock_llm_call)

        res = generate_ai_summary(did)
        assert res["source"] == "LLM"
        assert "Critical delay detected" in res["summary"]
        assert "REALLOCATE_STOCK" in res["summary"]

        conn = get_conn()
        try:
            d = conn.execute("SELECT ai_summary, ai_source FROM disruptions WHERE id = ?", (did,)).fetchone()
            assert d["ai_source"] == "LLM"
            assert d["ai_summary"] == res["summary"]
        finally:
            conn.close()

    def test_fallback_triggered_when_llm_invents_option(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "mock-gemini-key")
        did = setup_disruption()

        def mock_invalid_option(prompt, key):
            return {
                "summary": "Hallucinated option.",
                "recommended_option_type": "DRONE_AIRLIFT_NONEXISTENT",
                "recommended_option_description": "Airlift via autonomous drone fleet"
            }

        monkeypatch.setattr(ai_module, "call_gemini_api", mock_invalid_option)

        res = generate_ai_summary(did)
        # Invalidation must force fallback to deterministic option
        assert res["source"] == "FALLBACK"
        assert "[Fallback Summary]" in res["summary"]
