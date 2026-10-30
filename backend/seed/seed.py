"""
backend/seed/seed.py
Safe to run multiple times: deletes child→parent, resets sequences, re-inserts.
Faker locale en_IN, seed 42.
"""
import sys
import os
import sqlite3
import json
import csv
import bcrypt
from datetime import date, timedelta
from pathlib import Path
from faker import Faker

# ── paths ──────────────────────────────────────────────────────────────────────
HERE    = Path(__file__).parent
ROOT    = HERE.parent.parent
DB_PATH = ROOT / "disruptioniq.db"
SEED_DIR = HERE  # csv / json written next to this file

fake = Faker("en_IN")
fake.seed_instance(42)

TODAY = date.today()
def day(n): return (TODAY + timedelta(days=n)).isoformat()

# ── bcrypt helper ──────────────────────────────────────────────────────────────
def hashed(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()

# ══════════════════════════════════════════════════════════════════════════════
def seed(db_path: Path = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF;")   # allow truncation ordering
    conn.row_factory = sqlite3.Row

    # ── 1. Wipe in child→parent order, reset sequences ─────────────────────
    WIPE_ORDER = [
        "message_drafts", "audit_logs", "notifications",
        "webhook_events", "recovery_plans", "disruption_impacts",
        "disruptions", "order_lines", "orders",
        "inventory", "shipments",
        "products", "warehouses", "suppliers", "users",
    ]
    for tbl in WIPE_ORDER:
        conn.execute(f"DELETE FROM {tbl};")
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name = ?;", (tbl,)
        )
    conn.commit()
    print("[seed] Tables cleared.")

    # ── 2. USERS ───────────────────────────────────────────────────────────
    users = [
        # username, email, password, role
        ("alice",   "alice@diq.local",   "pass123",  "Operations Analyst"),
        ("bob",     "bob@diq.local",     "pass123",  "Operations Analyst"),
        ("carol",   "carol@diq.local",   "pass123",  "Supply Chain Manager"),
        ("dave",    "dave@diq.local",    "pass123",  "Warehouse Operator"),
        ("eve",     "eve@diq.local",     "pass123",  "Procurement Approver"),
        ("admin",   "admin@diq.local",   "admin123", "Administrator"),
    ]
    for u in users:
        conn.execute(
            "INSERT INTO users(username,email,password_hash,role) VALUES(?,?,?,?);",
            (u[0], u[1], hashed(u[2]), u[3])
        )
    conn.commit()
    print(f"[seed] {len(users)} users inserted.")

    # ── 3. SUPPLIERS ───────────────────────────────────────────────────────
    suppliers = [
        # code, name, contact, email, reliability
        ("SUP-A", "Supplier A",       "Ramesh Kumar",   "supplierA@example.com",  0.62),
        ("SUP-B", "Supplier B",       "Priya Sharma",   "supplierB@example.com",  0.88),
        ("SUP-C", "Supplier C",       "Anil Mehta",     "supplierC@example.com",  0.75),
        ("SUP-D", "Supplier D",       "Sunita Patel",   "supplierD@example.com",  0.91),
        ("SUP-E", "Supplier E",       "Vijay Nair",     "supplierE@example.com",  0.80),
    ]
    for s in suppliers:
        conn.execute(
            "INSERT INTO suppliers(code,name,contact,email,reliability_score) VALUES(?,?,?,?,?);",
            s
        )
    conn.commit()
    print(f"[seed] {len(suppliers)} suppliers inserted.")

    # ── 4. PRODUCTS P1-P8 ─────────────────────────────────────────────────
    products = [
        ("P1", "Paracetamol 500mg",     "box",  120.0),
        ("P2", "Amoxicillin 250mg",     "strip",  85.0),
        ("P3", "Surgical Gloves L",     "pair",   22.0),
        ("P4", "IV Saline 500ml",       "bag",    55.0),
        ("P5", "Syringes 5ml",          "box",    30.0),
        ("P6", "Face Mask N95",         "box",   200.0),
        ("P7", "Blood Glucose Strips",  "box",   350.0),
        ("P8", "Bandage Roll 10cm",     "roll",   18.0),
    ]
    for p in products:
        conn.execute(
            "INSERT INTO products(code,name,unit,unit_cost) VALUES(?,?,?,?);", p
        )
    conn.commit()
    print(f"[seed] {len(products)} products inserted.")

    # ── 5. WAREHOUSES ──────────────────────────────────────────────────────
    warehouses = [
        # code, name, city, capacity
        ("WH-CHN", "Chennai Central",   "Chennai",   5000),
        ("WH-BLR", "Bangalore Hub",     "Bangalore", 6000),
        ("WH-HYD", "Hyderabad Store",   "Hyderabad", 8000),
    ]
    for w in warehouses:
        conn.execute(
            "INSERT INTO warehouses(code,name,city,capacity) VALUES(?,?,?,?);", w
        )
    conn.commit()
    print(f"[seed] {len(warehouses)} warehouses inserted.")

    # resolve IDs
    def wid(code): return conn.execute("SELECT id FROM warehouses WHERE code=?", (code,)).fetchone()[0]
    def pid(code): return conn.execute("SELECT id FROM products  WHERE code=?", (code,)).fetchone()[0]
    def sid(code): return conn.execute("SELECT id FROM suppliers WHERE code=?", (code,)).fetchone()[0]

    CHN, BLR, HYD = wid("WH-CHN"), wid("WH-BLR"), wid("WH-HYD")
    P = {f"P{i}": pid(f"P{i}") for i in range(1, 9)}

    # ── 6. INVENTORY ───────────────────────────────────────────────────────
    # Scenario-exact values first, filler for P3-P8
    scenario_inv = {
        # (wh_id, prod_id): (on_hand, reserved)
        (CHN, P["P1"]): (20,  0),     # scenario 1: barely any P1 at Chennai
        (BLR, P["P1"]): (0,   0),     # Bangalore has none
        (HYD, P["P1"]): (300, 20),    # Hyderabad has spare P1
        (BLR, P["P2"]): (40,  35),    # scenario 2: near-exhausted P2
        (HYD, P["P2"]): (400, 100),   # Hyderabad spare P2
    }
    # CHN P2 - reasonable filler
    scenario_inv.setdefault((CHN, P["P2"]), (150, 30))

    inv_rows = []
    fake2 = Faker("en_IN"); fake2.seed_instance(42)
    for wh in [CHN, BLR, HYD]:
        for pc in ["P1","P2","P3","P4","P5","P6","P7","P8"]:
            key = (wh, P[pc])
            if key in scenario_inv:
                on_hand, reserved = scenario_inv[key]
            else:
                on_hand  = fake2.random_int(50, 500)
                reserved = fake2.random_int(0, min(on_hand, 50))
            inv_rows.append((wh, P[pc], on_hand, reserved))

    for row in inv_rows:
        conn.execute(
            "INSERT INTO inventory(warehouse_id,product_id,on_hand,reserved,version) VALUES(?,?,?,?,0);",
            row
        )
    conn.commit()
    print(f"[seed] {len(inv_rows)} inventory rows inserted.")

    # ── 7. SHIPMENTS ───────────────────────────────────────────────────────
    # SH-001 is the scenario shipment
    shipments = [
        # code, supplier_code, product_code, dest_wh_id, qty, status, expected_arrival, delay_days
        ("SH-001", "SUP-A", "P1", CHN, 500, "IN_TRANSIT", day(2), 0),
    ]
    # 14 filler shipments using P2-P8
    filler_codes = [f"SH-{i:03d}" for i in range(2, 16)]
    sup_codes  = ["SUP-A","SUP-B","SUP-C","SUP-D","SUP-E"]
    prod_codes = ["P2","P3","P4","P5","P6","P7","P8"]
    wh_ids     = [CHN, BLR, HYD]
    statuses   = ["IN_TRANSIT","IN_TRANSIT","IN_TRANSIT","DELAYED","ARRIVED"]
    fake3 = Faker("en_IN"); fake3.seed_instance(99)
    for i, code in enumerate(filler_codes):
        sc = sup_codes[i % len(sup_codes)]
        pc = prod_codes[i % len(prod_codes)]
        wh = wh_ids[i % 3]
        st = statuses[i % len(statuses)]
        dd = fake3.random_int(1, 14)
        shipments.append((code, sc, pc, wh, fake3.random_int(50, 400), st, day(dd), 0))

    for sh in shipments:
        code, sc, pc, wh, qty, st, eta, dly = sh
        conn.execute(
            """INSERT INTO shipments(code,supplier_id,product_id,dest_warehouse_id,
               quantity,status,expected_arrival,current_eta,delay_days) VALUES(?,?,?,?,?,?,?,?,?);""",
            (code, sid(sc), pid(pc), wh, qty, st, eta, eta, dly)
        )
    conn.commit()
    print(f"[seed] {len(shipments)} shipments inserted.")

    # ── 8. ORDERS + ORDER LINES ────────────────────────────────────────────
    # Scenario orders O-001..O-005
    scenario_orders = [
        # code, customer, priority, status, due_date
        ("O-001", "City Hospital",      "HIGH",   "OPEN", day(3)),
        ("O-002", "MediChain Retail",   "MEDIUM", "OPEN", day(5)),
        ("O-003", "Corner Pharmacy",    "LOW",    "OPEN", day(9)),
        ("O-004", "Apollo Clinic",      "HIGH",   "OPEN", day(4)),
        ("O-005", "HealthMart",         "MEDIUM", "OPEN", day(6)),
    ]
    # scenario order lines: (order_code, product_code, wh_id, qty)
    scenario_lines = {
        "O-001": [("P1", CHN, 200)],
        "O-002": [("P1", CHN, 150)],
        "O-003": [("P1", CHN, 50)],
        "O-004": [("P2", BLR, 40)],
        "O-005": [("P2", BLR, 20)],
    }

    # 25 filler orders using P3-P8 only
    priorities = ["HIGH","MEDIUM","LOW"]
    customers  = [
        "Sun Pharma Dist","Apollo Pharmacy","MedPlus Store","Fortis Hospital",
        "Manipal Clinic","Narayana Health","Star Health Mart","Care Hospitals",
        "Aster DM","Columbia Asia","Cloudnine","Rainbow Hosp","Yashoda Hosp",
        "Omega Healthcare","Vijaya Diagnostics","Kovai Medical","PSG Hospitals",
        "Meenakshi Mission","Kauvery Hospital","Sree Balaji",
        "Royal Care","SRM Hospitals","Vasan Health","GEM Hospital","MIOT Intl",
    ]
    filler_prod_codes = ["P3","P4","P5","P6","P7","P8"]
    fake4 = Faker("en_IN"); fake4.seed_instance(77)
    filler_orders = []
    for i in range(25):
        code = f"O-{i+6:03d}"
        cust = customers[i % len(customers)]
        pri  = priorities[i % 3]
        due  = day(fake4.random_int(2, 20))
        filler_orders.append((code, cust, pri, "OPEN", due))

    all_orders = scenario_orders + filler_orders

    for o in all_orders:
        conn.execute(
            "INSERT INTO orders(code,customer,priority,status,due_date) VALUES(?,?,?,?,?);",
            o
        )
    conn.commit()

    # order lines for scenario orders
    for ocode, lines in scenario_lines.items():
        oid = conn.execute("SELECT id FROM orders WHERE code=?", (ocode,)).fetchone()[0]
        for (pc, wh, qty) in lines:
            conn.execute(
                "INSERT INTO order_lines(order_id,product_id,warehouse_id,quantity) VALUES(?,?,?,?);",
                (oid, P[pc], wh, qty)
            )

    # lines for filler orders (P3-P8, random warehouse)
    fake5 = Faker("en_IN"); fake5.seed_instance(55)
    for o in filler_orders:
        oid = conn.execute("SELECT id FROM orders WHERE code=?", (o[0],)).fetchone()[0]
        n_lines = fake5.random_int(1, 3)
        used_prods = set()
        for _ in range(n_lines):
            pc = filler_prod_codes[fake5.random_int(0, 5)]
            if pc in used_prods:
                continue
            used_prods.add(pc)
            wh = wh_ids[fake5.random_int(0, 2)]
            qty = fake5.random_int(10, 200)
            conn.execute(
                "INSERT INTO order_lines(order_id,product_id,warehouse_id,quantity) VALUES(?,?,?,?);",
                (oid, P[pc], wh, qty)
            )

    conn.commit()
    print(f"[seed] {len(all_orders)} orders + lines inserted.")

    conn.execute("PRAGMA foreign_keys = ON;")
    conn.commit()
    conn.close()
    print("[seed] Done. All data committed.")


# ══════════════════════════════════════════════════════════════════════════════
# CSV / JSON FIXTURE FILES
# ══════════════════════════════════════════════════════════════════════════════
def write_fixtures():
    # ── shipments_clean.csv ────────────────────────────────────────────────
    clean_rows = [
        ["ref","supplier_code","product_code","dest_city","quantity","expected_arrival"],
        ["SH-C01","SUP-B","P3","Chennai",  "120", day(5)],
        ["SH-C02","SUP-C","P4","Bangalore","200", day(7)],
        ["SH-C03","SUP-D","P5","Hyderabad","80",  day(3)],
        ["SH-C04","SUP-E","P6","Chennai",  "60",  day(10)],
    ]
    clean_path = SEED_DIR / "shipments_clean.csv"
    with open(clean_path, "w", newline="") as f:
        csv.writer(f).writerows(clean_rows)

    # ── shipments_dirty.csv ────────────────────────────────────────────────
    dirty_rows = [
        ["ref","supplier_code","product_code","dest_city","quantity","expected_arrival"],
        ["SH-D01","SUP-B",   "P3", "Chennai",   "-50",   day(5)],     # negative qty
        ["SH-D02","SUP-ZZZZ","P4", "Bangalore", "100",   day(7)],     # unknown supplier
        ["SH-D03","SUP-C",   "P5", "Hyderabad", "80",    "not-a-date"],# bad date
        ["SH-D04","SUP-D",   "P6", "Chennai",   "60",    day(10)],    # duplicate ref
        ["SH-D04","SUP-D",   "P6", "Chennai",   "60",    day(10)],    # ← duplicate
    ]
    dirty_path = SEED_DIR / "shipments_dirty.csv"
    with open(dirty_path, "w", newline="") as f:
        csv.writer(f).writerows(dirty_rows)

    # ── orders_import.json ─────────────────────────────────────────────────
    orders_import = [
        {
            "code": "O-IMP-001",
            "customer": "Apex Diagnostics",
            "priority": "HIGH",
            "due_date": day(4),
            "lines": [
                {"product_code": "P5", "warehouse_code": "WH-CHN", "quantity": 50},
                {"product_code": "P6", "warehouse_code": "WH-BLR", "quantity": 30},
            ]
        },
        {
            "code": "O-IMP-002",
            "customer": "Prime Health",
            "priority": "MEDIUM",
            "due_date": day(8),
            "lines": [
                {"product_code": "P7", "warehouse_code": "WH-HYD", "quantity": 20},
            ]
        },
        {
            "code": "O-IMP-003",
            "customer": "BlueCross Pharmacy",
            "priority": "LOW",
            "due_date": day(14),
            "lines": [
                {"product_code": "P3", "warehouse_code": "WH-CHN", "quantity": 100},
                {"product_code": "P8", "warehouse_code": "WH-HYD", "quantity": 200},
            ]
        },
    ]
    orders_path = SEED_DIR / "orders_import.json"
    orders_path.write_text(json.dumps(orders_import, indent=2), encoding="utf-8")

    # ── webhook_delay.json ─────────────────────────────────────────────────
    webhook = {
        "event_id":   "EVT-20240101-SH001",
        "source":     "SupplierA-Portal",
        "event_type": "SHIPMENT_DELAYED",
        "payload": {
            "shipment_ref":  "SH-001",
            "supplier_code": "SUP-A",
            "product_code":  "P1",
            "delay_days":    5,
            "new_eta":       day(7),
            "reason":        "Regulatory hold at origin port",
            "notified_at":   day(0) + "T06:30:00Z"
        }
    }
    webhook_path = SEED_DIR / "webhook_delay.json"
    webhook_path.write_text(json.dumps(webhook, indent=2), encoding="utf-8")

    print("[seed] Fixture files written:")
    for p in [clean_path, dirty_path, orders_path, webhook_path]:
        print(f"       • {p.name}")


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    seed()
    write_fixtures()
