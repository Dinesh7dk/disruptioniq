import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.seed.seed import seed
from backend.db import get_conn
from backend.services.detection import run_detection
from datetime import date, timedelta
import json

seed()
conn = get_conn()
sh = conn.execute("SELECT id, expected_arrival FROM shipments WHERE code = 'SH-001'").fetchone()
base_date = date.fromisoformat(sh['expected_arrival'])
new_eta = (base_date + timedelta(days=6)).isoformat()
conn.execute("UPDATE shipments SET current_eta = ?, delay_days = 6, status = 'DELAYED' WHERE id = ?", (new_eta, sh['id']))
conn.commit()
conn.close()

run_detection(shipment_id=1)

conn = get_conn()
impacts = conn.execute('''
    SELECT di.risk_score, di.risk_level, di.risk_breakdown, di.risk_reasons, o.code, o.customer, o.priority
    FROM disruption_impacts di
    JOIN orders o ON di.order_id = o.id
    ORDER BY di.risk_score DESC
''').fetchall()

print('=== SCENARIO 1 RANKING & BREAKDOWN SUMMARY ===')
for r in impacts:
    breakdown = json.loads(r['risk_breakdown'])
    reasons = json.loads(r['risk_reasons'])
    sum_pts = round(sum(breakdown.values()), 1)
    print(f"{r['code']} ({r['customer']}) - Priority: {r['priority']} - Score: {r['risk_score']} ({r['risk_level']})")
    print(f"  Breakdown: {breakdown} -> Sum: {sum_pts}")
    print(f"  Key reasons: {reasons[:2]}")
conn.close()
