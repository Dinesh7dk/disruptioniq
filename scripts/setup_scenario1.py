import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.seed.seed import seed
from backend.services.detection import run_detection
from backend.db import get_conn
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

d_ids = run_detection(shipment_id=1)
print("Disruptions created/updated:", d_ids)

conn = get_conn()
disr = conn.execute("SELECT id, type, description FROM disruptions WHERE shipment_id = 1 AND status = 'OPEN'").fetchone()
print("Scenario 1 Disruption:", dict(disr))
conn.close()
