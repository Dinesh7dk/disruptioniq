"""
backend/services/import_service.py

Row-by-row validation and insertion for:
  - POST /import/shipments/csv   — multipart CSV upload
  - POST /import/shipments/json  — JSON body (list of shipment dicts)
  - POST /import/orders/json     — JSON body (list of order dicts with lines)

Rules enforced:
  - Required fields present and non-empty
  - quantity > 0 (rule 8: ? placeholders, no string SQL)
  - ISO-8601 dates (YYYY-MM-DD)
  - supplier_code, product_code, warehouse_code must exist in DB
  - ref / code must be globally unique (not already in DB)
  - Duplicate ref within the same upload batch → rejected
  - Every successful import writes to audit_logs (rule 7)

Response schema: {"imported": n, "rejected": [{"row": i, "reason": "..."}]}
Allowed roles: Administrator, Operations Analyst (enforced in router).
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import date
from typing import Any

from backend.db import get_conn

# ── ISO date validator ──────────────────────────────────────────────────────────
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_iso_date(value: str) -> bool:
    if not _ISO_DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


# ── Lookup helpers (cached per import call via passed-in conn) ──────────────────

_LOOKUP_QUERIES = {
    "suppliers": "SELECT id, code FROM suppliers",
    "products": "SELECT id, code FROM products",
    "warehouses": "SELECT id, code FROM warehouses",
}

def _lookup_table(conn, table: str, code_col: str = "code") -> dict[str, int]:
    """Return {code: id} for the given table without dynamic string formatting."""
    query = _LOOKUP_QUERIES.get(table)
    if not query:
        raise ValueError(f"Unknown lookup table: {table}")
    rows = conn.execute(query).fetchall()
    return {r[code_col]: r["id"] for r in rows}


_CODE_QUERIES = {
    "shipments": "SELECT code FROM shipments",
    "orders": "SELECT code FROM orders",
}

def _existing_codes(conn, table: str, code_col: str = "code") -> set[str]:
    """Return set of existing codes without dynamic string formatting."""
    query = _CODE_QUERIES.get(table)
    if not query:
        raise ValueError(f"Unknown code table: {table}")
    rows = conn.execute(query).fetchall()
    return {r[code_col] for r in rows}


# ── Audit log writer ────────────────────────────────────────────────────────────

def _write_audit(conn, actor_id: int, action: str, entity_type: str,
                 entity_id: int, new_value: dict) -> None:
    conn.execute(
        "INSERT INTO audit_logs(actor_id, action, entity_type, entity_id, new_value)"
        " VALUES(?, ?, ?, ?, ?)",
        (actor_id, action, entity_type, entity_id, json.dumps(new_value)),
    )


# ══════════════════════════════════════════════════════════════════════════════
# SHIPMENT CSV IMPORT
# ══════════════════════════════════════════════════════════════════════════════

SHIPMENT_REQUIRED = {"ref", "supplier_code", "product_code", "dest_city", "quantity", "expected_arrival"}


def import_shipments_csv(content: bytes, actor_id: int) -> dict:
    """
    Parse CSV bytes, validate each row, insert valid shipments.
    Returns {"imported": n, "rejected": [{"row": i, "reason": "..."}]}.
    """
    conn = get_conn()
    try:
        suppliers  = _lookup_table(conn, "suppliers", "code")
        products   = _lookup_table(conn, "products",  "code")
        warehouses = _lookup_table(conn, "warehouses", "code")

        # Map city name → warehouse_id (CSV uses dest_city not warehouse_code)
        city_to_wh: dict[str, int] = {}
        rows_wh = conn.execute("SELECT id, city FROM warehouses").fetchall()
        for r in rows_wh:
            city_to_wh[r["city"]] = r["id"]

        existing_refs = _existing_codes(conn, "shipments", "code")

        text   = content.decode("utf-8-sig")   # handle BOM
        reader = csv.DictReader(io.StringIO(text))

        imported  = 0
        rejected  = []
        seen_refs: set[str] = set()          # dedup within this upload

        for i, raw in enumerate(reader, start=1):
            row = {k.strip(): (v.strip() if v else "") for k, v in raw.items()}

            # ── Required fields ─────────────────────────────────────────────
            missing = SHIPMENT_REQUIRED - set(row.keys())
            if missing:
                rejected.append({"row": i, "reason": f"Missing columns: {sorted(missing)}"})
                continue
            empty = [f for f in SHIPMENT_REQUIRED if not row[f]]
            if empty:
                rejected.append({"row": i, "reason": f"Empty required fields: {sorted(empty)}"})
                continue

            ref = row["ref"]

            # ── Duplicate ref (within batch) ────────────────────────────────
            if ref in seen_refs:
                rejected.append({"row": i, "reason": f"Duplicate ref '{ref}' within upload"})
                continue
            seen_refs.add(ref)

            # ── Duplicate ref (already in DB) ───────────────────────────────
            if ref in existing_refs:
                rejected.append({"row": i, "reason": f"Ref '{ref}' already exists in database"})
                continue

            # ── Quantity ────────────────────────────────────────────────────
            try:
                qty = int(row["quantity"])
            except ValueError:
                rejected.append({"row": i, "reason": f"quantity '{row['quantity']}' is not an integer"})
                continue
            if qty <= 0:
                rejected.append({"row": i, "reason": f"quantity must be > 0, got {qty}"})
                continue

            # ── ISO date ────────────────────────────────────────────────────
            if not _is_iso_date(row["expected_arrival"]):
                rejected.append({"row": i, "reason": f"expected_arrival '{row['expected_arrival']}' is not a valid YYYY-MM-DD date"})
                continue

            # ── Supplier ────────────────────────────────────────────────────
            supplier_id = suppliers.get(row["supplier_code"])
            if supplier_id is None:
                rejected.append({"row": i, "reason": f"Unknown supplier_code '{row['supplier_code']}'"})
                continue

            # ── Product ─────────────────────────────────────────────────────
            product_id = products.get(row["product_code"])
            if product_id is None:
                rejected.append({"row": i, "reason": f"Unknown product_code '{row['product_code']}'"})
                continue

            # ── Warehouse (by city) ─────────────────────────────────────────
            warehouse_id = city_to_wh.get(row["dest_city"])
            if warehouse_id is None:
                rejected.append({"row": i, "reason": f"Unknown dest_city '{row['dest_city']}'"})
                continue

            # ── Insert ──────────────────────────────────────────────────────
            cur = conn.execute(
                "INSERT INTO shipments(code, supplier_id, product_id, dest_warehouse_id,"
                " quantity, status, expected_arrival, delay_days)"
                " VALUES(?, ?, ?, ?, ?, 'IN_TRANSIT', ?, 0)",
                (ref, supplier_id, product_id, warehouse_id, qty, row["expected_arrival"]),
            )
            shipment_id = cur.lastrowid
            existing_refs.add(ref)

            _write_audit(conn, actor_id, "SHIPMENT_IMPORTED", "shipments", shipment_id,
                         {"code": ref, "quantity": qty, "supplier_code": row["supplier_code"]})
            imported += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"imported": imported, "rejected": rejected}


# ══════════════════════════════════════════════════════════════════════════════
# SHIPMENT JSON IMPORT
# ══════════════════════════════════════════════════════════════════════════════

def import_shipments_json(records: list[dict], actor_id: int) -> dict:
    """
    Accept a list of shipment dicts (same fields as CSV but as JSON).
    Converts to CSV-compatible format and reuses the same validation logic.
    """
    fieldnames = ["ref", "supplier_code", "product_code", "dest_city",
                  "quantity", "expected_arrival"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in records:
        writer.writerow({f: r.get(f, "") for f in fieldnames})
    return import_shipments_csv(buf.getvalue().encode(), actor_id)


# ══════════════════════════════════════════════════════════════════════════════
# ORDERS JSON IMPORT
# ══════════════════════════════════════════════════════════════════════════════

ORDER_REQUIRED  = {"code", "customer", "priority", "due_date", "lines"}
LINE_REQUIRED   = {"product_code", "warehouse_code", "quantity"}
VALID_PRIORITIES = {"HIGH", "MEDIUM", "LOW"}


def import_orders_json(records: list[dict[str, Any]], actor_id: int) -> dict:
    """
    Validate and insert orders with their order_lines.
    Each record: {code, customer, priority, due_date,
                  lines: [{product_code, warehouse_code, quantity}]}
    """
    conn = get_conn()
    try:
        products   = _lookup_table(conn, "products",   "code")
        warehouses = _lookup_table(conn, "warehouses", "code")

        existing_codes = _existing_codes(conn, "orders", "code")

        imported = 0
        rejected = []
        seen_codes: set[str] = set()

        for i, record in enumerate(records, start=1):
            # ── Required top-level fields ────────────────────────────────────
            missing = ORDER_REQUIRED - set(record.keys())
            if missing:
                rejected.append({"row": i, "reason": f"Missing fields: {sorted(missing)}"})
                continue

            code     = str(record.get("code", "")).strip()
            customer = str(record.get("customer", "")).strip()
            priority = str(record.get("priority", "")).strip()
            due_date = str(record.get("due_date", "")).strip()
            lines    = record.get("lines", [])

            # ── Empty checks ─────────────────────────────────────────────────
            if not code:
                rejected.append({"row": i, "reason": "code is empty"})
                continue
            if not customer:
                rejected.append({"row": i, "reason": "customer is empty"})
                continue

            # ── Priority ─────────────────────────────────────────────────────
            if priority not in VALID_PRIORITIES:
                rejected.append({"row": i, "reason": f"priority '{priority}' must be HIGH, MEDIUM or LOW"})
                continue

            # ── Due date ─────────────────────────────────────────────────────
            if not _is_iso_date(due_date):
                rejected.append({"row": i, "reason": f"due_date '{due_date}' is not a valid YYYY-MM-DD date"})
                continue

            # ── Duplicate code (batch) ────────────────────────────────────────
            if code in seen_codes:
                rejected.append({"row": i, "reason": f"Duplicate code '{code}' within upload"})
                continue
            seen_codes.add(code)

            # ── Duplicate code (DB) ───────────────────────────────────────────
            if code in existing_codes:
                rejected.append({"row": i, "reason": f"Order code '{code}' already exists in database"})
                continue

            # ── Lines ─────────────────────────────────────────────────────────
            if not isinstance(lines, list) or len(lines) == 0:
                rejected.append({"row": i, "reason": "lines must be a non-empty list"})
                continue

            line_errors: list[str] = []
            validated_lines: list[tuple] = []

            for j, line in enumerate(lines, start=1):
                lmissing = LINE_REQUIRED - set(line.keys())
                if lmissing:
                    line_errors.append(f"line {j}: missing {sorted(lmissing)}")
                    continue

                prod_code = str(line.get("product_code", "")).strip()
                wh_code   = str(line.get("warehouse_code", "")).strip()
                try:
                    lqty = int(line["quantity"])
                except (ValueError, TypeError):
                    line_errors.append(f"line {j}: quantity '{line.get('quantity')}' is not an integer")
                    continue

                if lqty <= 0:
                    line_errors.append(f"line {j}: quantity must be > 0, got {lqty}")
                    continue

                prod_id = products.get(prod_code)
                if prod_id is None:
                    line_errors.append(f"line {j}: unknown product_code '{prod_code}'")
                    continue

                wh_id = warehouses.get(wh_code)
                if wh_id is None:
                    line_errors.append(f"line {j}: unknown warehouse_code '{wh_code}'")
                    continue

                validated_lines.append((prod_id, wh_id, lqty))

            if line_errors:
                rejected.append({"row": i, "reason": "; ".join(line_errors)})
                continue

            # ── Insert order + lines atomically ───────────────────────────────
            cur = conn.execute(
                "INSERT INTO orders(code, customer, priority, status, due_date)"
                " VALUES(?, ?, ?, 'OPEN', ?)",
                (code, customer, priority, due_date),
            )
            order_id = cur.lastrowid
            existing_codes.add(code)

            for (prod_id, wh_id, lqty) in validated_lines:
                conn.execute(
                    "INSERT INTO order_lines(order_id, product_id, warehouse_id, quantity)"
                    " VALUES(?, ?, ?, ?)",
                    (order_id, prod_id, wh_id, lqty),
                )

            _write_audit(conn, actor_id, "ORDER_IMPORTED", "orders", order_id,
                         {"code": code, "customer": customer, "priority": priority,
                          "lines": len(validated_lines)})
            imported += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"imported": imported, "rejected": rejected}
