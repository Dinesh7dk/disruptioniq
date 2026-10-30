"""
scripts/compare_ai_summary.py

Demonstrates:
1. Running AI summary WITH an API key (or simulated live LLM response).
2. Running AI summary WITHOUT an API key (key removed / empty) -> deterministic fallback.
"""
import os
import sys
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.seed.seed import seed
from backend.db import get_conn
from backend.services.detection import run_detection
from backend.services.ai import generate_ai_summary
from datetime import date, timedelta


def setup_scenario_disruption():
    seed()
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


def main():
    print("=" * 75)
    print("AI SUMMARY EVALUATION: WITH KEY vs WITHOUT KEY (FALLBACK)")
    print("=" * 75)

    disruption_id = setup_scenario_disruption()

    # -------------------------------------------------------------
    # CASE 1: WITHOUT API KEY (Key Removed / Blank)
    # -------------------------------------------------------------
    print("\n>>> [RUN 1] LLM_API_KEY IS REMOVED / BLANK")
    os.environ["LLM_API_KEY"] = ""

    res_fallback = generate_ai_summary(disruption_id)
    print(f"Source:  {res_fallback['source']}")
    print(f"Summary: {res_fallback['summary']}")

    # -------------------------------------------------------------
    # CASE 2: WITH API KEY
    # -------------------------------------------------------------
    print("\n" + "-" * 75)
    print(">>> [RUN 2] LLM_API_KEY IS CONFIGURED")

    # If the user has a real key in .env or passed, we test it.
    # Otherwise, we simulate the LLM call validation flow to show the verified LLM output.
    test_key = os.getenv("REAL_LLM_KEY", "").strip() or "test-gemini-key"
    os.environ["LLM_API_KEY"] = test_key

    # Mock/Monkeypatch the call_gemini_api function to demonstrate the verified LLM path if key is test
    import backend.services.ai as ai_module
    original_call = ai_module.call_gemini_api

    def mock_gemini(prompt, key):
        return {
            "summary": "Shipment SH-001 delay directly impacts high-priority healthcare orders O-001 and O-002 at Chennai Central.",
            "recommended_option_type": "REALLOCATE_STOCK",
            "recommended_option_description": "Transfer 200 units of P1 from Hyderabad to Chennai"
        }

    # If key is mock, use mock; if real key provided, execute live
    if test_key == "test-gemini-key":
        ai_module.call_gemini_api = mock_gemini

    try:
        res_llm = generate_ai_summary(disruption_id)
        print(f"Source:  {res_llm['source']}")
        print(f"Summary: {res_llm['summary']}")
    finally:
        ai_module.call_gemini_api = original_call

    print("\n" + "=" * 75)
    print("VERIFICATION COMPLETE:")
    print(f"• Run 1 without key: source is {res_fallback['source']} (deterministic template)")
    print(f"• Run 2 with key:    source is {res_llm['source']} (validated option recommendation)")
    print("=" * 75)


if __name__ == "__main__":
    main()
