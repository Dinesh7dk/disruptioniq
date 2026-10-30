"""
backend/services/nlquery.py

Natural Language Query Service for DisruptionIQ.
Translates unstructured user questions into a strictly validated JSON filter.
Enforces Hard Rules:
- Rule 1: Deterministic Python execution.
- Rule 8: SQL always uses ? placeholders, never string formatting.
- Rule 11: Creative features never write business data.
- Rule 12: The LLM never writes SQL. May only return a JSON filter, validated against
          a strict whitelist of fields and values and run as a parameterized query.
"""
import os
import re
import json
from datetime import date, timedelta
from typing import Any, Literal
import httpx
from pydantic import BaseModel, Field, ConfigDict, field_validator, ValidationError
from fastapi import HTTPException, status
from backend.db import get_conn

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
TIMEOUT_SECONDS = 10.0

# Disallowed prompt injection or destructive phrases
INJECTION_PATTERNS = [
    r"\bignore\s+(all\s+)?(rules|instructions|constraints|prompts|previous)\b",
    r"\bdelete\b",
    r"\bdrop\s+table\b",
    r"\btruncate\s+table\b",
    r"\balter\s+table\b",
    r"\binsert\s+into\b",
    r"\bupdate\s+\w+\s+set\b",
    r"\bselect\s+.*\bfrom\b",
    r"--",
    r";",
]


class OrderFilter(BaseModel):
    """
    Strict whitelist model for natural language order queries.
    Allows: priority, risk_level, status, due_within_days, warehouse, product, customer.
    Forbids any extra keys.
    """
    model_config = ConfigDict(extra="forbid")

    priority: Literal["HIGH", "MEDIUM", "LOW"] | None = None
    risk_level: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "AT_RISK"] | None = None
    status: Literal["OPEN", "FULFILLED", "PARTIAL", "CANCELLED"] | None = None
    due_within_days: int | None = Field(default=None, ge=1, le=60)
    warehouse: str | None = Field(default=None, max_length=100)
    product: str | None = Field(default=None, max_length=100)
    customer: str | None = Field(default=None, max_length=100)

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, v):
        if isinstance(v, str):
            v_up = v.upper().strip()
            if v_up in ("HIGH", "MEDIUM", "LOW"):
                return v_up
        return v

    @field_validator("risk_level", mode="before")
    @classmethod
    def normalize_risk_level(cls, v):
        if isinstance(v, str):
            v_up = v.upper().strip()
            if v_up in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "AT_RISK"):
                return v_up
            if v_up in ("RISK", "AT-RISK", "AT RISK"):
                return "AT_RISK"
        return v

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v):
        if isinstance(v, str):
            v_up = v.upper().strip()
            if v_up in ("OPEN", "FULFILLED", "PARTIAL", "CANCELLED"):
                return v_up
        return v

    @field_validator("warehouse", "product", "customer")
    @classmethod
    def sanitize_search_string(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            return None
        if not re.match(r"^[\w\s\-]+$", cleaned):
            raise ValueError("Disallowed characters in search filter string.")
        return cleaned


def is_prompt_injection(query: str) -> bool:
    """Detects obvious prompt injection or SQL injection attacks in input query."""
    q_lower = query.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, q_lower):
            return True
    return False


def call_gemini_filter(query: str, api_key: str) -> dict[str, Any] | None:
    """
    Calls Google Gemini REST API to convert the question into a JSON filter.
    Returns parsed dict or None on failure/timeout.
    """
    prompt = f"""You are a logistics database query translator.
Convert the following natural language user question into a JSON object filter with ONLY these allowed keys:
- "priority": "HIGH" | "MEDIUM" | "LOW" (or null)
- "risk_level": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" (or null)
- "status": "OPEN" | "FULFILLED" | "PARTIAL" | "CANCELLED" (or null)
- "due_within_days": integer between 1 and 60 (or null)
- "warehouse": string warehouse city/name e.g. "Chennai", "Bangalore", "Hyderabad" (or null)
- "product": string product code e.g. "P1", "P2" (or null)

CRITICAL SAFETY RULES:
- NEVER write SQL queries, SQL clauses, or code.
- Return ONLY valid JSON with exactly the allowed keys.
- If a criterion is not mentioned, omit it or set it to null.
- Do NOT add any additional keys.

User question: "{query}"
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
            "temperature": 0.0,
            "responseMimeType": "application/json",
        },
    }
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            resp = client.post(url, headers=headers, json=body)
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    # Clean out nulls or empty values
                    return {k: v for k, v in parsed.items() if v is not None and v != ""}
    except Exception:
        pass
    return None


def keyword_parser_fallback(query: str) -> dict[str, Any]:
    """
    Deterministic rule-based keyword extractor when LLM is unavailable or fails.
    Extracts priority, risk_level, status, due_within_days, warehouse, and product.
    """
    q = query.lower()
    extracted: dict[str, Any] = {}

    # 1. Priority
    if "high priority" in q:
        extracted["priority"] = "HIGH"
    elif "medium priority" in q:
        extracted["priority"] = "MEDIUM"
    elif "low priority" in q:
        extracted["priority"] = "LOW"
    elif re.search(r"\bhigh\b", q) and not re.search(r"\bhigh\s+risk\b", q):
        extracted["priority"] = "HIGH"
    elif re.search(r"\bmedium\b", q) and not re.search(r"\bmedium\s+risk\b", q):
        extracted["priority"] = "MEDIUM"
    elif re.search(r"\blow\b", q) and not re.search(r"\blow\s+risk\b", q):
        extracted["priority"] = "LOW"

    # 2. Risk level
    if "critical risk" in q or "critical" in q:
        extracted["risk_level"] = "CRITICAL"
    elif "high risk" in q:
        extracted["risk_level"] = "HIGH"
    elif "medium risk" in q:
        extracted["risk_level"] = "MEDIUM"
    elif "low risk" in q:
        extracted["risk_level"] = "LOW"
    elif "at risk" in q or "risk" in q:
        extracted["risk_level"] = "AT_RISK"

    # 3. Status
    if "fulfilled" in q:
        extracted["status"] = "FULFILLED"
    elif "partial" in q:
        extracted["status"] = "PARTIAL"
    elif "cancelled" in q or "canceled" in q:
        extracted["status"] = "CANCELLED"
    elif "open" in q:
        extracted["status"] = "OPEN"

    # 4. Due within days
    if "this week" in q or "current week" in q:
        extracted["due_within_days"] = 7
    elif "today" in q:
        extracted["due_within_days"] = 1
    elif "tomorrow" in q:
        extracted["due_within_days"] = 2
    elif "next week" in q:
        extracted["due_within_days"] = 14
    elif "this month" in q:
        extracted["due_within_days"] = 30
    else:
        m = re.search(r"(?:due\s+in|due\s+within|within|next|in)\s+(\d{1,2})\s*days?", q)
        if not m:
            m = re.search(r"(\d{1,2})\s*days?", q)
        if m:
            days = int(m.group(1))
            if 1 <= days <= 60:
                extracted["due_within_days"] = days

    # 5. Warehouse city
    cities = ["chennai", "bangalore", "mumbai", "delhi", "hyderabad", "kolkata"]
    for city in cities:
        if city in q:
            extracted["warehouse"] = city.capitalize()
            break

    # 6. Product
    p_match = re.search(r"\b(p[1-9]\d?)\b", q)
    if p_match:
        extracted["product"] = p_match.group(1).upper()

    # 7. Customer keywords
    customer_terms = [
        "hospital", "hospitals", "clinic", "clinics", "pharmacy", "pharmacies",
        "retail", "health", "healthcare", "diagnostics", "store", "stores", "dist"
    ]
    for term in customer_terms:
        if re.search(rf"\b{term}\b", q):
            extracted["customer"] = "Hospital" if "hospital" in term else term.capitalize()
            break

    return extracted


def query_orders_by_filter(filter_obj: OrderFilter) -> list[dict[str, Any]]:
    """
    Executes a strictly parameterized SQL query based on the validated OrderFilter.
    Hard Rule 8: Always parameterized with ? placeholders.
    Hard Rule 12: Hand-coded SQL, LLM never sees or writes SQL.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()

        base_sql = """
        SELECT DISTINCT
            o.id,
            o.code,
            o.customer,
            o.priority,
            o.due_date,
            o.status,
            COALESCE(MAX(di.risk_score), 0.0) AS risk_score,
            (
                SELECT di2.risk_level FROM disruption_impacts di2
                JOIN disruptions d2 ON d2.id = di2.disruption_id AND d2.status = 'OPEN'
                WHERE di2.order_id = o.id
                ORDER BY di2.risk_score DESC LIMIT 1
            ) AS risk_level,
            (
                SELECT di2.risk_reasons FROM disruption_impacts di2
                JOIN disruptions d2 ON d2.id = di2.disruption_id AND d2.status = 'OPEN'
                WHERE di2.order_id = o.id
                ORDER BY di2.risk_score DESC LIMIT 1
            ) AS risk_reasons,
            (
                SELECT di2.risk_breakdown FROM disruption_impacts di2
                JOIN disruptions d2 ON d2.id = di2.disruption_id AND d2.status = 'OPEN'
                WHERE di2.order_id = o.id
                ORDER BY di2.risk_score DESC LIMIT 1
            ) AS risk_breakdown,
            (
                SELECT di2.units_at_risk FROM disruption_impacts di2
                JOIN disruptions d2 ON d2.id = di2.disruption_id AND d2.status = 'OPEN'
                WHERE di2.order_id = o.id
                ORDER BY di2.risk_score DESC LIMIT 1
            ) AS units_at_risk,
            (
                SELECT di2.disruption_id FROM disruption_impacts di2
                JOIN disruptions d2 ON d2.id = di2.disruption_id AND d2.status = 'OPEN'
                WHERE di2.order_id = o.id
                ORDER BY di2.risk_score DESC LIMIT 1
            ) AS disruption_id
        FROM orders o
        LEFT JOIN disruption_impacts di ON di.order_id = o.id
        LEFT JOIN disruptions d ON d.id = di.disruption_id AND d.status = 'OPEN'
        LEFT JOIN order_lines ol ON ol.order_id = o.id
        LEFT JOIN products p ON p.id = ol.product_id
        LEFT JOIN warehouses w ON w.id = ol.warehouse_id
        WHERE 1=1
        """
        params: list[Any] = []

        if filter_obj.priority:
            base_sql += " AND o.priority = ?"
            params.append(filter_obj.priority)

        if filter_obj.status:
            base_sql += " AND o.status = ?"
            params.append(filter_obj.status)

        if filter_obj.due_within_days is not None:
            target_date = (date.today() + timedelta(days=filter_obj.due_within_days)).isoformat()
            base_sql += " AND o.due_date <= ?"
            params.append(target_date)

        if filter_obj.warehouse:
            base_sql += " AND (LOWER(w.city) = LOWER(?) OR LOWER(w.name) LIKE LOWER(?) OR LOWER(w.code) = LOWER(?))"
            params.extend([filter_obj.warehouse, f"%{filter_obj.warehouse}%", filter_obj.warehouse])

        if filter_obj.product:
            base_sql += " AND (LOWER(p.code) = LOWER(?) OR LOWER(p.name) LIKE LOWER(?))"
            params.extend([filter_obj.product, f"%{filter_obj.product}%"])

        if filter_obj.customer:
            base_sql += " AND LOWER(o.customer) LIKE LOWER(?)"
            params.append(f"%{filter_obj.customer}%")

        base_sql += " GROUP BY o.id"

        if filter_obj.risk_level == "AT_RISK":
            base_sql += " HAVING (risk_score > 0 OR risk_level IN ('CRITICAL', 'HIGH', 'MEDIUM') OR o.priority = 'HIGH')"
        elif filter_obj.risk_level:
            base_sql += " HAVING risk_level = ?"
            params.append(filter_obj.risk_level)

        base_sql += " ORDER BY risk_score DESC, o.due_date ASC"

        rows = cur.execute(base_sql, params).fetchall()
        if not rows:
            return []

        # Fetch lines for each order
        order_ids = [r["id"] for r in rows]
        placeholders = ",".join("?" for _ in order_ids)
        lines_rows = cur.execute(
            f"""SELECT ol.order_id, p.code AS product_code, p.name AS product_name,
                      ol.quantity, ol.fulfilled, w.city AS warehouse_city
               FROM order_lines ol
               JOIN products p ON p.id = ol.product_id
               JOIN warehouses w ON w.id = ol.warehouse_id
               WHERE ol.order_id IN ({placeholders})
               ORDER BY ol.id ASC""",
            order_ids,
        ).fetchall()

        lines_by_order: dict[int, list] = {}
        for l in lines_rows:
            lines_by_order.setdefault(l["order_id"], []).append({
                "product_code": l["product_code"],
                "product_name": l["product_name"],
                "quantity": l["quantity"],
                "fulfilled": l["fulfilled"],
                "warehouse_city": l["warehouse_city"],
            })

        orders = []
        for r in rows:
            orders.append({
                "id": r["id"],
                "code": r["code"],
                "customer": r["customer"],
                "priority": r["priority"],
                "due_date": r["due_date"],
                "status": r["status"],
                "risk_score": round(float(r["risk_score"]), 1),
                "risk_level": r["risk_level"] or "LOW",
                "risk_reasons": json.loads(r["risk_reasons"]) if r["risk_reasons"] else [],
                "risk_breakdown": json.loads(r["risk_breakdown"]) if r["risk_breakdown"] else {},
                "units_at_risk": r["units_at_risk"] or 0,
                "disruption_id": r["disruption_id"],
                "lines": lines_by_order.get(r["id"], []),
            })
        return orders
    finally:
        conn.close()


def process_natural_query(user_query: str) -> dict[str, Any]:
    """
    Main entry point for natural language query execution.
    1. Checks for prompt injection and rejects destructive commands.
    2. Queries LLM or falls back to keyword parser.
    3. Validates against Pydantic whitelist (rejects extra keys).
    4. Executes parameterized SQL query.
    5. Returns filter used and matching orders.
    """
    raw_query = (user_query or "").strip()
    if not raw_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query string cannot be empty.",
        )

    # Hard rejection for prompt injection / destructive instructions
    if is_prompt_injection(raw_query):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prompt injection or disallowed command detected and rejected.",
        )

    # 1. Try LLM translation
    api_key = os.getenv("LLM_API_KEY", "").strip()
    parsed_dict = None
    parsed_by = "KEYWORD_FALLBACK"

    if api_key:
        llm_result = call_gemini_filter(raw_query, api_key)
        if llm_result is not None:
            try:
                # Validate LLM output against Pydantic whitelist
                validated_model = OrderFilter(**llm_result)
                parsed_dict = validated_model.model_dump(exclude_unset=True)
                parsed_by = "LLM"
            except (ValidationError, Exception):
                parsed_dict = None

    # 2. Fallback to keyword parser if LLM failed or not configured
    if parsed_dict is None:
        raw_fallback = keyword_parser_fallback(raw_query)
        try:
            validated_model = OrderFilter(**raw_fallback)
            parsed_dict = validated_model.model_dump(exclude_unset=True)
            parsed_by = "KEYWORD_FALLBACK"
        except ValidationError as ve:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Filter validation failed: {ve}",
            )

    # Create OrderFilter instance for SQL execution
    order_filter = OrderFilter(**parsed_dict)

    # 3. Query DB using parameterized query
    orders = query_orders_by_filter(order_filter)

    return {
        "query": raw_query,
        "filter": parsed_dict,
        "parsed_by": parsed_by,
        "count": len(orders),
        "orders": orders,
    }
