"""
backend/services/risk.py

Deterministic Risk Scoring Engine.
NO LLM CALLS.

Weights (total = 100):
- Urgency: 35%
- Delay length: 25%
- Customer priority: 20%
- Shortfall size: 10%
- Lack of alternative stock: 10%

Levels:
- HIGH: score >= 70
- MEDIUM: 40 <= score < 70
- LOW: score < 40

Returns:
- score: float (0 to 100, rounded to 1 decimal)
- level: "HIGH" | "MEDIUM" | "LOW"
- reasons: list[str]
- breakdown: dict[str, float] where values sum exactly to score
"""
from typing import TypedDict


class RiskResult(TypedDict):
    score: float
    level: str
    reasons: list[str]
    breakdown: dict[str, float]


def calculate_risk(
    buffer_days: int,
    delay_days: int,
    priority: str,
    shortfall: int,
    order_quantity: int,
    alt_stock_available: int,
) -> RiskResult:
    """
    Compute explainable, deterministic risk score out of 100.
    """
    breakdown: dict[str, float] = {}
    reasons: list[str] = []

    # 1. Urgency (Weight 35)
    # buffer_days < 0 means deadline will be breached.
    # More negative buffer = more severe urgency.
    if buffer_days <= -5:
        urgency_pts = 35.0
        reasons.append(f"Critical deadline breach: buffer is {buffer_days} days")
    elif buffer_days < 0:
        # e.g., buffer -1 to -4
        urgency_pts = round(20.0 + (-buffer_days / 5.0) * 15.0, 1)
        reasons.append(f"Delivery deadline will be missed by {-buffer_days} days")
    elif buffer_days == 0:
        urgency_pts = 15.0
        reasons.append("Zero buffer days remaining before shipment handling cutoff")
    elif buffer_days <= 3:
        urgency_pts = 8.0
        reasons.append(f"Tight delivery buffer: {buffer_days} days")
    else:
        urgency_pts = 0.0

    breakdown["urgency"] = urgency_pts

    # 2. Delay length (Weight 25)
    if delay_days >= 7:
        delay_pts = 25.0
        reasons.append(f"Major shipment delay of {delay_days} days")
    elif delay_days >= 4:
        delay_pts = round(15.0 + ((delay_days - 4) / 3.0) * 10.0, 1)
        reasons.append(f"Significant shipment delay of {delay_days} days")
    elif delay_days > 0:
        delay_pts = round((delay_days / 4.0) * 15.0, 1)
        reasons.append(f"Shipment delayed by {delay_days} days")
    else:
        delay_pts = 0.0

    breakdown["delay_length"] = delay_pts

    # 3. Customer priority (Weight 20)
    p_upper = priority.upper()
    if p_upper == "HIGH":
        priority_pts = 20.0
        reasons.append("High-priority customer order")
    elif p_upper == "MEDIUM":
        priority_pts = 10.0
        reasons.append("Medium-priority customer order")
    else:  # LOW
        priority_pts = 2.0
        reasons.append("Low-priority customer order")

    breakdown["customer_priority"] = priority_pts

    # 4. Shortfall size (Weight 10)
    if order_quantity > 0:
        shortfall_ratio = min(1.0, max(0.0, shortfall / order_quantity))
        shortfall_pts = round(shortfall_ratio * 10.0, 1)
    else:
        shortfall_pts = 0.0

    if shortfall > 0:
        reasons.append(f"Quantity shortfall of {shortfall} units")
    breakdown["shortfall_size"] = shortfall_pts

    # 5. Lack of alternative stock across other warehouses (Weight 10)
    if shortfall <= 0:
        alt_pts = 0.0
    elif alt_stock_available <= 0:
        alt_pts = 10.0
        reasons.append("No alternative stock available across other warehouses")
    elif alt_stock_available < shortfall:
        shortfall_covered = alt_stock_available / shortfall
        alt_pts = round((1.0 - shortfall_covered) * 10.0, 1)
        reasons.append(f"Partial alternative stock available ({alt_stock_available} units available, {shortfall} needed)")
    else:
        # Full alternative stock exists elsewhere
        alt_pts = 0.0
        reasons.append(f"Alternative stock available in network ({alt_stock_available} units)")

    breakdown["lack_of_alternative_stock"] = alt_pts

    # Total score calculation: exactly equals sum of breakdown
    total_score = round(sum(breakdown.values()), 1)

    if total_score >= 70.0:
        level = "HIGH"
    elif total_score >= 40.0:
        level = "MEDIUM"
    else:
        level = "LOW"

    return {
        "score": total_score,
        "level": level,
        "reasons": reasons,
        "breakdown": breakdown,
    }
