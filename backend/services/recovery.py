"""
backend/services/recovery.py

Pure functions for evaluating feasible recovery options:
1. reallocate: another warehouse has on_hand - reserved >= needed.
2. expedite: faster ETA meets the due date, with cost.
3. alternative_supplier: backup supplier's lead time meets the deadline, with cost.
4. split_order: part of the order ships on time from available stock.

Each function returns None if infeasible, otherwise a dict:
{
    "type": str,
    "details": dict,
    "cost": float,
    "new_delivery_date": str,
    "meets_deadline": bool
}

generate_options(disruption_id, order_id=None) reads the database (no writes, no LLM)
and returns only feasible options.
"""
from datetime import date, timedelta
from typing import Any
from backend.db import get_conn


def parse_iso(d_str: str) -> date:
    return date.fromisoformat(d_str.split("T")[0])


def option_reallocate(
    source_warehouse: dict,
    target_warehouse: dict,
    product: dict,
    quantity_needed: int,
    order_due_date: str,
    current_date: date | None = None,
) -> dict[str, Any] | None:
    """
    Feasible when another warehouse has (on_hand - reserved) >= quantity_needed.
    Inter-warehouse transfer takes 2 days transit + 1 day handling.
    Transfer cost = flat handling (500) + 5.0 per unit.
    """
    if current_date is None:
        current_date = date.today()

    available = source_warehouse.get("available_stock", 0)
    if available < quantity_needed:
        return None

    # Delivery date: current_date + 2 days transfer + 1 day handling
    delivery_date = current_date + timedelta(days=3)
    due = parse_iso(order_due_date)
    meets_deadline = delivery_date <= due

    cost = round(500.0 + (5.0 * quantity_needed), 2)

    return {
        "type": "REALLOCATE_STOCK",
        "details": {
            "source_warehouse_id": source_warehouse["id"],
            "source_warehouse_code": source_warehouse.get("code"),
            "source_warehouse_city": source_warehouse.get("city"),
            "target_warehouse_id": target_warehouse["id"],
            "target_warehouse_city": target_warehouse.get("city"),
            "quantity": quantity_needed,
            "product_code": product.get("code"),
            "description": f"Transfer {quantity_needed} units of {product.get('code')} from {source_warehouse.get('city')} to {target_warehouse.get('city')}",
        },
        "cost": cost,
        "new_delivery_date": delivery_date.isoformat(),
        "meets_deadline": meets_deadline,
    }


def option_expedite(
    shipment: dict | None,
    order_due_date: str,
    current_date: date | None = None,
) -> dict[str, Any] | None:
    """
    Feasible when faster ETA meets the due date.
    Expediting reduces the remaining delay by up to 4 days (or brings arrival to current_date + 1).
    Air/express freight surcharge: flat fee 2500 + 10.0 per unit.
    """
    if not shipment or not shipment.get("current_eta"):
        return None

    if current_date is None:
        current_date = date.today()

    cur_eta = parse_iso(shipment["current_eta"])
    # Expedited arrival: min 1 day from now, saving up to 4 days of delay
    expedited_arrival = max(current_date + timedelta(days=1), cur_eta - timedelta(days=4))
    delivery_date = expedited_arrival + timedelta(days=1)  # 1 day handling

    due = parse_iso(order_due_date)
    meets_deadline = delivery_date <= due

    if not meets_deadline:
        return None

    qty = shipment.get("quantity", 0)
    cost = round(2500.0 + (10.0 * qty), 2)

    return {
        "type": "EXPEDITE_ORDER",
        "details": {
            "shipment_code": shipment.get("code"),
            "original_eta": shipment.get("current_eta"),
            "expedited_arrival": expedited_arrival.isoformat(),
            "description": f"Expedite shipment {shipment.get('code')} via air freight to arrive {expedited_arrival.isoformat()}",
        },
        "cost": cost,
        "new_delivery_date": delivery_date.isoformat(),
        "meets_deadline": meets_deadline,
    }


def option_alternative_supplier(
    backup_supplier: dict,
    product: dict,
    quantity_needed: int,
    order_due_date: str,
    target_warehouse: dict,
    current_date: date | None = None,
) -> dict[str, Any] | None:
    """
    Feasible when a backup supplier's lead time fits the deadline.
    Default lead time is 3 days + 1 day handling.
    Unit premium: unit_cost * 1.25 + expedited procurement fee 1500.
    """
    if current_date is None:
        current_date = date.today()

    lead_days = backup_supplier.get("lead_time_days", 3)
    delivery_date = current_date + timedelta(days=lead_days + 1)
    due = parse_iso(order_due_date)
    meets_deadline = delivery_date <= due

    if not meets_deadline:
        return None

    unit_cost = product.get("unit_cost", 50.0)
    cost = round(1500.0 + (unit_cost * 1.25 * quantity_needed), 2)

    return {
        "type": "ALTERNATIVE_SUPPLIER",
        "details": {
            "supplier_id": backup_supplier.get("id"),
            "supplier_code": backup_supplier.get("code"),
            "supplier_name": backup_supplier.get("name"),
            "quantity": quantity_needed,
            "product_code": product.get("code"),
            "description": f"Emergency procurement of {quantity_needed} units of {product.get('code')} from {backup_supplier.get('name')}",
        },
        "cost": cost,
        "new_delivery_date": delivery_date.isoformat(),
        "meets_deadline": meets_deadline,
    }


def option_split_order(
    local_available: int,
    order_quantity: int,
    order_due_date: str,
    delayed_delivery_date: str,
    current_date: date | None = None,
) -> dict[str, Any] | None:
    """
    Feasible when part of the quantity (> 0 and < order_quantity) can ship on time from local available stock.
    Remaining balance delivers when the delayed shipment arrives.
    Cost: extra packaging & separate shipping dispatch fee = 800.
    """
    if current_date is None:
        current_date = date.today()

    if local_available <= 0 or local_available >= order_quantity:
        return None

    immediate_qty = local_available
    backlog_qty = order_quantity - immediate_qty

    immediate_delivery = current_date + timedelta(days=1)
    due = parse_iso(order_due_date)
    meets_deadline = immediate_delivery <= due

    cost = 800.0

    return {
        "type": "PARTIAL_FULFIL",
        "details": {
            "immediate_quantity": immediate_qty,
            "backlog_quantity": backlog_qty,
            "immediate_delivery_date": immediate_delivery.isoformat(),
            "remaining_delivery_date": delayed_delivery_date,
            "description": f"Split order: ship {immediate_qty} units immediately from local stock, remaining {backlog_qty} units on {delayed_delivery_date}",
        },
        "cost": cost,
        "new_delivery_date": immediate_delivery.isoformat(),
        "meets_deadline": meets_deadline,
    }


def generate_options(disruption_id: int, order_id: int | None = None) -> list[dict[str, Any]]:
    """
    Generates verified, feasible recovery options for a given disruption (and optional order).
    NO DATABASE WRITES. NO LLM CALLS.
    """
    conn = get_conn()
    try:
        # Load disruption details
        d = conn.execute(
            """SELECT d.*, s.code as shipment_code, s.current_eta, s.expected_arrival,
                      s.quantity as shipment_qty, s.supplier_id as s_supplier_id,
                      s.product_id as s_product_id, s.dest_warehouse_id as s_warehouse_id
               FROM disruptions d
               LEFT JOIN shipments s ON d.shipment_id = s.id
               WHERE d.id = ?""",
            (disruption_id,),
        ).fetchone()

        if not d:
            return []

        product_id = d["product_id"] or d["s_product_id"]
        warehouse_id = d["warehouse_id"] or d["s_warehouse_id"]

        product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        warehouse = conn.execute("SELECT * FROM warehouses WHERE id = ?", (warehouse_id,)).fetchone()

        shipment_data = None
        if d["shipment_id"]:
            shipment_data = {
                "id": d["shipment_id"],
                "code": d["shipment_code"],
                "current_eta": d["current_eta"],
                "expected_arrival": d["expected_arrival"],
                "quantity": d["shipment_qty"],
            }

        # Query affected orders
        order_query = """
            SELECT o.id, o.code, o.customer, o.priority, o.due_date, ol.quantity
            FROM orders o
            JOIN order_lines ol ON o.id = ol.order_id
            WHERE ol.product_id = ? AND ol.warehouse_id = ? AND o.status = 'OPEN'
        """
        params = [product_id, warehouse_id]
        if order_id:
            order_query += " AND o.id = ?"
            params.append(order_id)
        order_query += " ORDER BY o.due_date ASC"

        orders = conn.execute(order_query, params).fetchall()

        # Check other warehouses with available stock for this product
        alt_warehouses = conn.execute(
            """SELECT w.id, w.code, w.city, (i.on_hand - i.reserved) as available_stock
               FROM inventory i
               JOIN warehouses w ON i.warehouse_id = w.id
               WHERE i.product_id = ? AND i.warehouse_id <> ? AND (i.on_hand - i.reserved) > 0""",
            (product_id, warehouse_id),
        ).fetchall()

        # Check backup suppliers
        exclude_sup = d["s_supplier_id"] or -1
        backup_suppliers = conn.execute(
            "SELECT * FROM suppliers WHERE id <> ? AND reliability_score >= 0.70 ORDER BY reliability_score DESC",
            (exclude_sup,),
        ).fetchall()

        # Local available stock
        local_inv = conn.execute(
            "SELECT on_hand, reserved FROM inventory WHERE warehouse_id = ? AND product_id = ?",
            (warehouse_id, product_id),
        ).fetchone()
        local_avail = (local_inv["on_hand"] - local_inv["reserved"]) if local_inv else 0

        delayed_eta = d["current_eta"] or d["expected_arrival"] or date.today().isoformat()
        delayed_delivery = (parse_iso(delayed_eta) + timedelta(days=1)).isoformat()

        all_options: list[dict[str, Any]] = []

        for ord_row in orders:
            needed = ord_row["quantity"]
            due_date = ord_row["due_date"]
            ord_dict = dict(ord_row)

            # 1. Option: Reallocate from other warehouses
            for alt_wh in alt_warehouses:
                opt_realloc = option_reallocate(
                    source_warehouse=dict(alt_wh),
                    target_warehouse=dict(warehouse),
                    product=dict(product),
                    quantity_needed=needed,
                    order_due_date=due_date,
                )
                if opt_realloc:
                    opt_realloc["order"] = ord_dict
                    all_options.append(opt_realloc)

            # 2. Option: Expedite shipment (if shipment exists)
            if shipment_data:
                opt_exp = option_expedite(
                    shipment=shipment_data,
                    order_due_date=due_date,
                )
                if opt_exp:
                    opt_exp["order"] = ord_dict
                    all_options.append(opt_exp)

            # 3. Option: Alternative supplier
            for sup in backup_suppliers:
                opt_sup = option_alternative_supplier(
                    backup_supplier=dict(sup),
                    product=dict(product),
                    quantity_needed=needed,
                    order_due_date=due_date,
                    target_warehouse=dict(warehouse),
                )
                if opt_sup:
                    opt_sup["order"] = ord_dict
                    all_options.append(opt_sup)
                    break  # Keep the top feasible backup supplier

            # 4. Option: Split order
            opt_split = option_split_order(
                local_available=local_avail,
                order_quantity=needed,
                order_due_date=due_date,
                delayed_delivery_date=delayed_delivery,
            )
            if opt_split:
                opt_split["order"] = ord_dict
                all_options.append(opt_split)

        return all_options
    finally:
        conn.close()
