"""
backend/services/detection_service.py

Detection engine placeholders and disruption detection logic.
"""

def run_detection(shipment_id: int | None = None) -> dict:
    """
    Placeholder for disruption detection engine.
    Triggered after shipment updates, webhooks, or manual checks.
    """
    print(f"[run_detection] Triggered detection check for shipment_id={shipment_id}")
    return {"status": "detection_ran", "shipment_id": shipment_id}
