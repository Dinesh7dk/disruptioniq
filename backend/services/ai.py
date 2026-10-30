"""
backend/services/ai.py

AI Assistance & Recommendation Service with Deterministic Fallback.

Rules:
1. Receives the disruption, affected orders (with scores and reasons), and verified feasible options.
2. Instructs the LLM (Gemini via standard REST API) to write a concise summary and recommend
   EXACTLY ONE option from the verified list, never inventing numbers or options.
3. 10-second timeout.
4. Validates that the recommended option exists in the verified list.
5. If validation fails, or if the LLM call times out/fails, or if LLM_API_KEY is empty/absent:
   falls back to a template summary picking the cheapest option meeting the deadline.
6. Saves the result in disruptions.ai_summary and records whether it came from 'LLM' or 'FALLBACK' (in disruptions.ai_source).
"""
import os
import json
import httpx
from typing import Any
from backend.db import get_conn
from backend.services.recovery import generate_options

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
TIMEOUT_SECONDS = 10.0


def generate_fallback_summary(disruption: dict, affected_orders: list[dict], options: list[dict]) -> tuple[str, str]:
    """
    Deterministic template fallback picking the cheapest option meeting the deadline.
    Returns (summary_text, 'FALLBACK').
    """
    if not options:
        summary = (
            f"Disruption #{disruption['id']} ({disruption['type']}): {disruption.get('description', '')}. "
            f"Affects {len(affected_orders)} customer orders. No feasible single-action recovery options found; "
            f"manual expedited intervention required."
        )
        return summary, "FALLBACK"

    # Filter options meeting deadline, then sort by cost
    meeting_deadline = [opt for opt in options if opt.get("meets_deadline")]
    candidate_list = meeting_deadline if meeting_deadline else options
    cheapest = min(candidate_list, key=lambda x: x.get("cost", float("inf")))

    order_desc = ""
    if "order" in cheapest:
        ord_info = cheapest["order"]
        order_desc = f" for order {ord_info.get('code')} ({ord_info.get('customer')})"

    summary = (
        f"[Fallback Summary] Disruption #{disruption['id']}: {disruption.get('description', '')}. "
        f"{len(affected_orders)} orders impacted. Evaluated {len(options)} verified feasible recovery options. "
        f"Recommended Action: {cheapest['type']} - {cheapest['details'].get('description', '')}{order_desc} "
        f"at an estimated cost of Rs. {cheapest.get('cost', 0):,.2f}, arriving by {cheapest.get('new_delivery_date', 'TBD')} "
        f"({'meets delivery deadline' if cheapest.get('meets_deadline') else 'minimizes delay'})."
    )
    return summary, "FALLBACK"


def validate_recommended_option(llm_recommendation_type: str, llm_description: str, options: list[dict]) -> bool:
    """
    Validates that the option recommended by the LLM exists in the verified options list.
    """
    if not options:
        return False

    norm_type = (llm_recommendation_type or "").strip().upper()
    norm_desc = (llm_description or "").strip().lower()

    for opt in options:
        opt_type = opt.get("type", "").strip().upper()
        opt_desc = opt.get("details", {}).get("description", "").strip().lower()

        if norm_type and norm_type == opt_type:
            # If description keyword matches or type matches
            if not norm_desc or any(word in opt_desc for word in norm_desc.split() if len(word) > 3):
                return True

    return False


def call_gemini_api(prompt: str, api_key: str) -> dict | None:
    """
    Calls Google Gemini REST API with 10-second timeout.
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
                return json.loads(text)
            else:
                print(f"[AI Service] Gemini API returned status {resp.status_code}: {resp.text}")
                return None
    except Exception as e:
        print(f"[AI Service] Gemini API request failed: {e}")
        return None


def generate_ai_summary(disruption_id: int) -> dict[str, str]:
    """
    Main entry point for AI analysis and recommendation.
    Fetches disruption, affected orders, and verified options.
    Calls Gemini if key exists; validates output; falls back deterministically on any failure.
    Saves ai_summary and ai_source to disruptions table.
    """
    conn = get_conn()
    disruption = None
    affected_orders = []
    try:
        d_row = conn.execute("SELECT * FROM disruptions WHERE id = ?", (disruption_id,)).fetchone()
        if not d_row:
            return {"summary": "", "source": "FALLBACK"}
        disruption = dict(d_row)

        order_rows = conn.execute(
            """SELECT di.risk_score, di.risk_level, di.risk_reasons, di.units_at_risk,
                      o.id, o.code, o.customer, o.priority, o.due_date
               FROM disruption_impacts di
               JOIN orders o ON di.order_id = o.id
               WHERE di.disruption_id = ?
               ORDER BY di.risk_score DESC""",
            (disruption_id,),
        ).fetchall()
        affected_orders = [dict(r) for r in order_rows]
    finally:
        conn.close()

    # Generate verified options (read-only)
    options = generate_options(disruption_id=disruption_id)

    api_key = os.getenv("LLM_API_KEY", "").strip()

    summary_text = None
    source = "FALLBACK"

    if api_key:
        # Construct strict prompt
        prompt = f"""
You are an expert AI logistics assistant for DisruptionIQ.
Analyze this supply chain disruption, the affected customer orders, and the verified feasible recovery options.

Disruption Details:
- ID: {disruption['id']}
- Type: {disruption['type']}
- Description: {disruption.get('description', '')}

Affected Orders:
{json.dumps([{
    'order_code': o['code'],
    'customer': o['customer'],
    'priority': o['priority'],
    'due_date': o['due_date'],
    'risk_score': o['risk_score'],
    'risk_level': o['risk_level'],
    'reasons': json.loads(o['risk_reasons']) if isinstance(o['risk_reasons'], str) else o['risk_reasons']
} for o in affected_orders], indent=2)}

Verified Feasible Recovery Options:
{json.dumps([{
    'type': opt['type'],
    'cost': opt['cost'],
    'new_delivery_date': opt['new_delivery_date'],
    'meets_deadline': opt['meets_deadline'],
    'description': opt['details'].get('description', ''),
    'target_order': opt.get('order', {}).get('code', 'N/A')
} for opt in options], indent=2)}

STRICT RULES:
1. Write a concise executive summary (2-3 sentences) explaining the situation and risk.
2. Recommend EXACTLY ONE option chosen strictly from the verified feasible list above.
3. NEVER invent numbers, costs, delivery dates, or new options not present in the list.
4. Output your response as a JSON object with this exact structure:
{{
  "summary": "Executive summary string...",
  "recommended_option_type": "EXACT_TYPE_FROM_LIST",
  "recommended_option_description": "EXACT_DESCRIPTION_FROM_LIST"
}}
"""
        result = call_gemini_api(prompt, api_key)
        if result and isinstance(result, dict) and "summary" in result:
            rec_type = result.get("recommended_option_type", "")
            rec_desc = result.get("recommended_option_description", "")
            # Strict validation
            if validate_recommended_option(rec_type, rec_desc, options):
                summary_text = (
                    f"{result['summary'].strip()} "
                    f"Recommended Action: {rec_type} ({rec_desc})."
                )
                source = "LLM"
            else:
                print(f"[AI Service] LLM recommended an unverified option '{rec_type}'. Discarding and using fallback.")

    if not summary_text:
        summary_text, source = generate_fallback_summary(disruption, affected_orders, options)

    # Save to disruptions table
    conn = get_conn()
    try:
        conn.execute(
            """UPDATE disruptions
               SET ai_summary = ?, ai_source = ?
               WHERE id = ?""",
            (summary_text, source, disruption_id),
        )
        conn.execute(
            """INSERT INTO audit_logs (actor_id, action, entity_type, entity_id, new_value, note)
               VALUES (NULL, 'AI_SUMMARY_GENERATED', 'disruptions', ?, ?, ?)""",
            (
                disruption_id,
                json.dumps({"ai_summary": summary_text, "ai_source": source}),
                f"Generated summary via {source}",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {"summary": summary_text, "source": source}
