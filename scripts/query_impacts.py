import sqlite3
import json

conn = sqlite3.connect('disruptioniq.db')
conn.row_factory = sqlite3.Row

print(f"{'order_id':<10} {'order_code':<12} {'customer':<22} {'risk_score':<12} {'risk_breakdown'}")
print("-" * 110)

rows = conn.execute('''
    SELECT di.order_id, di.risk_score, di.risk_breakdown, o.code as order_code, o.customer
    FROM disruption_impacts di
    JOIN orders o ON di.order_id = o.id
    ORDER BY di.risk_score DESC
''').fetchall()

for r in rows:
    breakdown_compact = json.dumps(json.loads(r['risk_breakdown']))
    print(f"{r['order_id']:<10} {r['order_code']:<12} {r['customer']:<22} {r['risk_score']:<12} {breakdown_compact}")

conn.close()
