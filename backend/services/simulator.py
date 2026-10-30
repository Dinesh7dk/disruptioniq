"""
backend/services/simulator.py

What-If Simulator Service.
Runs recovery option simulations inside a database transaction that is ALWAYS rolled back.
Never writes business data to the database (Hard Rules 11 and 14).

Calculates before/after comparisons:
- Affected orders (due date, delivery date before & after, buffer days, shortfall, risk level & score)
- Estimated logistics cost
- Collateral impact on other orders sharing the same stock at the source/local warehouse
"""
import json
from datetime import date, timedelta
from typing import Any
from fastapi import HTTPException, status
from backend.db import get_conn
from backend.services.risk import calculate_risk
from backend.services.recovery import (
    option_reallocate,
    option_expedite,
    option_alternative_supplier,
    option_split_order,
    parse_iso,
)


def simulate_option(
    disruption_id: int,
    action_type: str,
    parameters: dict[str, Any] | None = None,
    plan_id: int | None = None,
) -> dict[str, Any]:
    """
    Simulate a recovery action for a disruption inside an explicit transaction
    that is ALWAYS rolled back in the finally block.
    """
    if parameters is None:
        parameters = {}

    action_type = (action_type or "").upper().strip()
    if not action_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="action_type or option_type is required.",
        )

    conn = get_conn()
    try:
        # Start transaction - guaranteed rollback in finally
        conn.execute("BEGIN IMMEDIATE;")

        # 1. Fetch disruption details
        d = conn.execute(
            """SELECT d.*, s.id AS s_id, s.code AS s_code, s.current_eta, s.expected_arrival,
                      s.delay_days, s.quantity AS shipment_qty, s.supplier_id AS s_supplier_id,
                      s.product_id AS s_product_id, s.dest_warehouse_id AS s_warehouse_id,
                      p.code AS product_code, p.name AS product_name, p.unit_cost,
                      w.code AS warehouse_code, w.city AS warehouse_city
               FROM disruptions d
               LEFT JOIN shipments s ON d.shipment_id = s.id
               LEFT JOIN products p ON (d.product_id = p.id OR s.product_id = p.id)
               LEFT JOIN warehouses w ON (d.warehouse_id = w.id OR s.dest_warehouse_id = w.id)
               WHERE d.id = ?""",
            (disruption_id,),
        ).fetchone()

        if not d:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Disruption #{disruption_id} not found.",
            )

        product_id = d["product_id"] or d["s_product_id"]
        warehouse_id = d["warehouse_id"] or d["s_warehouse_id"]

        if not product_id or not warehouse_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Disruption is missing product or warehouse reference.",
            )

        product = {
            "id": product_id,
            "code": d["product_code"] or "P1",
            "name": d["product_name"] or "Product",
            "unit_cost": d["unit_cost"] or 50.0,
        }
        warehouse = {
            "id": warehouse_id,
            "code": d["warehouse_code"] or "WH",
            "city": d["warehouse_city"] or "Local Warehouse",
        }

        # 2. Local available stock & other warehouse stock
        local_inv = conn.execute(
            "SELECT id, on_hand, reserved FROM inventory WHERE warehouse_id = ? AND product_id = ?",
            (warehouse_id, product_id),
        ).fetchone()
        local_avail_before = (local_inv["on_hand"] - local_inv["reserved"]) if local_inv else 0

        alt_row = conn.execute(
            """SELECT SUM(MAX(0, on_hand - reserved)) AS alt_avail
               FROM inventory
               WHERE product_id = ? AND warehouse_id <> ?""",
            (product_id, warehouse_id),
        ).fetchone()
        alt_avail = alt_row["alt_avail"] if (alt_row and alt_row["alt_avail"] is not None) else 0

        # Current arrival date without intervention
        if d["current_eta"]:
            cur_arrival = parse_iso(d["current_eta"])
        elif d["expected_arrival"]:
            cur_arrival = parse_iso(d["expected_arrival"])
        else:
            cur_arrival = date.today() + timedelta(days=5)

        current_delivery_date = cur_arrival + timedelta(days=1)  # 1 day handling
        current_delay_days = d["delay_days"] or 0
        if d["current_eta"] and d["expected_arrival"]:
            d1 = parse_iso(d["expected_arrival"])
            d2 = parse_iso(d["current_eta"])
            if d2 > d1:
                current_delay_days = (d2 - d1).days

        # 3. Find affected orders
        order_query = """
            SELECT o.id, o.code, o.customer, o.priority, o.due_date, ol.quantity
            FROM orders o
            JOIN order_lines ol ON o.id = ol.order_id
            WHERE ol.product_id = ? AND ol.warehouse_id = ? AND o.status = 'OPEN'
        """
        params: list[Any] = [product_id, warehouse_id]
        target_order_id = parameters.get("order_id")
        if target_order_id:
            order_query += " AND o.id = ?"
            params.append(target_order_id)
        order_query += " ORDER BY o.due_date ASC"

        order_rows = conn.execute(order_query, params).fetchall()
        if not order_rows:
            # Fall back to any open orders in disruption_impacts
            impact_orders = conn.execute(
                """SELECT o.id, o.code, o.customer, o.priority, o.due_date, di.units_at_risk as quantity
                   FROM disruption_impacts di
                   JOIN orders o ON di.order_id = o.id
                   WHERE di.disruption_id = ?
                   ORDER BY di.risk_score DESC""",
                (disruption_id,),
            ).fetchall()
            order_rows = impact_orders

        # Compute BEFORE state for each affected order
        affected_orders_before: list[dict[str, Any]] = []
        rem_local = max(0, local_avail_before)
        for ord_row in order_rows:
            due = parse_iso(ord_row["due_date"])
            qty = ord_row["quantity"]
            buf_days = (due - current_delivery_date).days

            if rem_local >= qty:
                shortfall = 0
                rem_local -= qty
            else:
                shortfall = qty - rem_local
                rem_local = 0

            risk_b = calculate_risk(
                buffer_days=buf_days,
                delay_days=current_delay_days,
                priority=ord_row["priority"],
                shortfall=shortfall,
                order_quantity=qty,
                alt_stock_available=alt_avail,
            )

            affected_orders_before.append({
                "order_id": ord_row["id"],
                "order_code": ord_row["code"],
                "customer": ord_row["customer"],
                "priority": ord_row["priority"],
                "due_date": ord_row["due_date"],
                "quantity": qty,
                "delivery_date": current_delivery_date.isoformat(),
                "meets_deadline": current_delivery_date <= due,
                "buffer_days": buf_days,
                "shortfall": shortfall,
                "risk_score": risk_b["score"],
                "risk_level": risk_b["level"],
                "risk_reasons": risk_b["reasons"],
            })

        # 4. Simulate the specific option
        total_quantity_needed = sum(o["quantity"] for o in affected_orders_before) if affected_orders_before else 100
        sim_quantity = int(parameters.get("quantity") or total_quantity_needed)

        sim_cost = 0.0
        new_delivery_date_str = current_delivery_date.isoformat()
        meets_deadline_flag = False
        action_summary = ""
        collateral_orders: list[dict[str, Any]] = []

        if action_type in ("REALLOCATE_STOCK", "REALLOCATE"):
            # Source warehouse
            source_wh_id = parameters.get("source_warehouse_id")
            if not source_wh_id:
                # Pick the warehouse with the highest available stock
                top_wh = conn.execute(
                    """SELECT w.id, w.code, w.city, (i.on_hand - i.reserved) AS available_stock
                       FROM inventory i
                       JOIN warehouses w ON i.warehouse_id = w.id
                       WHERE i.product_id = ? AND i.warehouse_id <> ? AND (i.on_hand - i.reserved) > 0
                       ORDER BY (i.on_hand - i.reserved) DESC LIMIT 1""",
                    (product_id, warehouse_id),
                ).fetchone()
                if top_wh:
                    source_wh_id = top_wh["id"]

            if not source_wh_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No alternative warehouse with available stock found for reallocation.",
                )

            src_wh = conn.execute(
                """SELECT w.id, w.code, w.city, i.id AS inv_id, i.on_hand, i.reserved
                   FROM inventory i
                   JOIN warehouses w ON i.warehouse_id = w.id
                   WHERE i.warehouse_id = ? AND i.product_id = ?""",
                (source_wh_id, product_id),
            ).fetchone()

            if not src_wh:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Warehouse #{source_wh_id} does not stock product #{product_id}.",
                )

            src_available_before = max(0, src_wh["on_hand"] - src_wh["reserved"])

            # Call existing pure feasibility function
            first_due = affected_orders_before[0]["due_date"] if affected_orders_before else date.today().isoformat()
            opt_eval = option_reallocate(
                source_warehouse={
                    "id": src_wh["id"],
                    "code": src_wh["code"],
                    "city": src_wh["city"],
                    "available_stock": src_available_before,
                },
                target_warehouse=warehouse,
                product=product,
                quantity_needed=sim_quantity,
                order_due_date=first_due,
            )

            if opt_eval:
                sim_cost = opt_eval["cost"]
                new_delivery_date_str = opt_eval["new_delivery_date"]
                meets_deadline_flag = opt_eval["meets_deadline"]
            else:
                # If not feasible via helper (e.g. partial shortfall or misses deadline), calculate projected values
                deliv = date.today() + timedelta(days=3)
                new_delivery_date_str = deliv.isoformat()
                meets_deadline_flag = deliv <= parse_iso(first_due)
                sim_cost = round(500.0 + (5.0 * sim_quantity), 2)

            action_summary = f"Reallocate {sim_quantity} units of {product['code']} from {src_wh['city']} to {warehouse['city']} (transit: 2d + handling: 1d)."

            # SIMULATE IN DATABASE (inside transaction)
            # Reserve stock at source warehouse
            conn.execute(
                "UPDATE inventory SET reserved = reserved + ? WHERE id = ?",
                (sim_quantity, src_wh["inv_id"]),
            )

            # Check which OTHER orders sharing the same stock at source warehouse would be affected
            src_available_after = src_available_before - sim_quantity
            affected_ids = [o["order_id"] for o in affected_orders_before]
            placeholders = ",".join("?" for _ in affected_ids) if affected_ids else "0"

            other_orders = conn.execute(
                f"""SELECT o.id, o.code, o.customer, o.priority, o.due_date, ol.quantity
                    FROM orders o
                    JOIN order_lines ol ON o.id = ol.order_id
                    WHERE ol.warehouse_id = ? AND ol.product_id = ? AND o.status = 'OPEN'
                      AND o.id NOT IN ({placeholders})
                    ORDER BY o.due_date ASC""",
                [source_wh_id, product_id] + affected_ids,
            ).fetchall()

            for oth in other_orders:
                req_qty = oth["quantity"]
                deficit = max(0, req_qty - max(0, src_available_after))
                if deficit > 0:
                    status_col = "SHORTFALL_CREATED"
                    note = f"Order faces a shortage of {deficit} units because available stock at {src_wh['city']} dropped from {src_available_before} to {src_available_after}."
                else:
                    status_col = "STOCK_BUFFER_REDUCED"
                    note = f"Order remains covered, but safety buffer at {src_wh['city']} is reduced from {src_available_before} to {src_available_after} units."

                collateral_orders.append({
                    "order_id": oth["id"],
                    "order_code": oth["code"],
                    "customer": oth["customer"],
                    "priority": oth["priority"],
                    "due_date": oth["due_date"],
                    "warehouse_id": source_wh_id,
                    "warehouse_city": src_wh["city"],
                    "product_id": product_id,
                    "product_code": product["code"],
                    "order_quantity": req_qty,
                    "stock_before": src_available_before,
                    "stock_after": max(0, src_available_after),
                    "deficit": deficit,
                    "status": status_col,
                    "impact_note": note,
                })

        elif action_type in ("EXPEDITE_ORDER", "EXPEDITE"):
            shipment_data = None
            if d["s_id"]:
                shipment_data = {
                    "id": d["s_id"],
                    "code": d["s_code"],
                    "current_eta": d["current_eta"],
                    "expected_arrival": d["expected_arrival"],
                    "quantity": d["shipment_qty"] or sim_quantity,
                }

            if not shipment_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot expedite: disruption is not linked to an in-transit shipment.",
                )

            first_due = affected_orders_before[0]["due_date"] if affected_orders_before else date.today().isoformat()
            opt_eval = option_expedite(shipment_data, first_due)

            if opt_eval:
                sim_cost = opt_eval["cost"]
                new_delivery_date_str = opt_eval["new_delivery_date"]
                meets_deadline_flag = opt_eval["meets_deadline"]
            else:
                cur_eta_d = parse_iso(shipment_data["current_eta"]) if shipment_data["current_eta"] else date.today() + timedelta(days=6)
                exp_arr = max(date.today() + timedelta(days=1), cur_eta_d - timedelta(days=4))
                deliv = exp_arr + timedelta(days=1)
                new_delivery_date_str = deliv.isoformat()
                meets_deadline_flag = deliv <= parse_iso(first_due)
                sim_cost = round(2500.0 + (10.0 * shipment_data["quantity"]), 2)

            action_summary = f"Expedite shipment {shipment_data['code']} via priority air freight. Surcharge: Rs. {sim_cost}."

            # SIMULATE IN DATABASE (inside transaction)
            expedited_eta = (parse_iso(new_delivery_date_str) - timedelta(days=1)).isoformat()
            conn.execute(
                "UPDATE shipments SET current_eta = ?, delay_days = 1 WHERE id = ?",
                (expedited_eta, shipment_data["id"]),
            )

        elif action_type in ("ALTERNATIVE_SUPPLIER", "BACKUP_SUPPLIER"):
            supplier_id = parameters.get("supplier_id")
            if supplier_id:
                sup_row = conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
            else:
                exclude_sup = d["s_supplier_id"] or -1
                sup_row = conn.execute(
                    "SELECT * FROM suppliers WHERE id <> ? AND reliability_score >= 0.70 ORDER BY reliability_score DESC LIMIT 1",
                    (exclude_sup,),
                ).fetchone()

            if not sup_row:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No qualified backup supplier with reliability >= 0.70 available.",
                )

            first_due = affected_orders_before[0]["due_date"] if affected_orders_before else date.today().isoformat()
            opt_eval = option_alternative_supplier(
                backup_supplier=dict(sup_row),
                product=product,
                quantity_needed=sim_quantity,
                order_due_date=first_due,
                target_warehouse=warehouse,
            )

            if opt_eval:
                sim_cost = opt_eval["cost"]
                new_delivery_date_str = opt_eval["new_delivery_date"]
                meets_deadline_flag = opt_eval["meets_deadline"]
            else:
                lead_days = sup_row["lead_time_days"] or 4
                deliv = date.today() + timedelta(days=lead_days + 1)
                new_delivery_date_str = deliv.isoformat()
                meets_deadline_flag = deliv <= parse_iso(first_due)
                unit_p = product.get("unit_cost", 50.0)
                sim_cost = round(1000.0 + (unit_p * 1.15 * sim_quantity), 2)

            action_summary = f"Emergency procurement of {sim_quantity} units from backup supplier {sup_row['name']} (lead time: {sup_row['lead_time_days']} days)."

        elif action_type in ("PARTIAL_FULFIL", "SPLIT_ORDER"):
            first_due = affected_orders_before[0]["due_date"] if affected_orders_before else date.today().isoformat()
            opt_eval = option_split_order(
                local_available=local_avail_before,
                order_quantity=sim_quantity,
                order_due_date=first_due,
                delayed_delivery_date=current_delivery_date.isoformat(),
            )

            if opt_eval:
                sim_cost = opt_eval["cost"]
                new_delivery_date_str = opt_eval["new_delivery_date"]
                meets_deadline_flag = opt_eval["meets_deadline"]
            else:
                sim_cost = 350.0
                new_delivery_date_str = (date.today() + timedelta(days=1)).isoformat()
                meets_deadline_flag = True

            action_summary = f"Split fulfillment: ship {local_avail_before} units immediately from local stock, remaining {max(0, sim_quantity - local_avail_before)} units upon delayed shipment arrival."

            # SIMULATE IN DATABASE (inside transaction)
            if local_inv and local_avail_before > 0:
                conn.execute(
                    "UPDATE inventory SET reserved = reserved + ? WHERE id = ?",
                    (min(sim_quantity, local_avail_before), local_inv["id"]),
                )

            # Check other orders at same local warehouse
            affected_ids = [o["order_id"] for o in affected_orders_before]
            placeholders = ",".join("?" for _ in affected_ids) if affected_ids else "0"
            rem_after = max(0, local_avail_before - sim_quantity)
            other_local_orders = conn.execute(
                f"""SELECT o.id, o.code, o.customer, o.priority, o.due_date, ol.quantity
                    FROM orders o
                    JOIN order_lines ol ON o.id = ol.order_id
                    WHERE ol.warehouse_id = ? AND ol.product_id = ? AND o.status = 'OPEN'
                      AND o.id NOT IN ({placeholders})
                    ORDER BY o.due_date ASC""",
                [warehouse_id, product_id] + affected_ids,
            ).fetchall()

            for oth in other_local_orders:
                req_qty = oth["quantity"]
                deficit = max(0, req_qty - rem_after)
                collateral_orders.append({
                    "order_id": oth["id"],
                    "order_code": oth["code"],
                    "customer": oth["customer"],
                    "priority": oth["priority"],
                    "due_date": oth["due_date"],
                    "warehouse_id": warehouse_id,
                    "warehouse_city": warehouse["city"],
                    "product_id": product_id,
                    "product_code": product["code"],
                    "order_quantity": req_qty,
                    "stock_before": local_avail_before,
                    "stock_after": rem_after,
                    "deficit": deficit,
                    "status": "SHORTFALL_CREATED" if deficit > 0 else "STOCK_BUFFER_REDUCED",
                    "impact_note": f"Local inventory reduced from {local_avail_before} to {rem_after}.",
                })

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported action_type '{action_type}'. Supported: REALLOCATE_STOCK, EXPEDITE_ORDER, ALTERNATIVE_SUPPLIER, PARTIAL_FULFIL.",
            )

        # 5. Compute AFTER state for affected orders
        sim_new_deliv = parse_iso(new_delivery_date_str)
        affected_orders_comparison: list[dict[str, Any]] = []

        for b_ord in affected_orders_before:
            due = parse_iso(b_ord["due_date"])
            new_buf = (due - sim_new_deliv).days
            new_shortfall = 0 if action_type != "PARTIAL_FULFIL" else max(0, b_ord["quantity"] - local_avail_before)
            new_delay = max(0, (sim_new_deliv - cur_arrival).days) if sim_new_deliv > cur_arrival else 0

            risk_a = calculate_risk(
                buffer_days=new_buf,
                delay_days=new_delay,
                priority=b_ord["priority"],
                shortfall=new_shortfall,
                order_quantity=b_ord["quantity"],
                alt_stock_available=alt_avail,
            )

            score_delta = round(risk_a["score"] - b_ord["risk_score"], 1)

            affected_orders_comparison.append({
                "order_id": b_ord["order_id"],
                "order_code": b_ord["order_code"],
                "customer": b_ord["customer"],
                "priority": b_ord["priority"],
                "due_date": b_ord["due_date"],
                "quantity": b_ord["quantity"],
                "before": {
                    "delivery_date": b_ord["delivery_date"],
                    "meets_deadline": b_ord["meets_deadline"],
                    "buffer_days": b_ord["buffer_days"],
                    "shortfall": b_ord["shortfall"],
                    "risk_score": b_ord["risk_score"],
                    "risk_level": b_ord["risk_level"],
                    "risk_reasons": b_ord["risk_reasons"],
                },
                "after": {
                    "delivery_date": new_delivery_date_str,
                    "meets_deadline": sim_new_deliv <= due,
                    "buffer_days": new_buf,
                    "shortfall": new_shortfall,
                    "risk_score": risk_a["score"],
                    "risk_level": risk_a["level"],
                    "risk_reasons": risk_a["reasons"],
                },
                "risk_score_delta": score_delta,
                "risk_level_changed": risk_a["level"] != b_ord["risk_level"],
                "status": "IMPROVED" if score_delta < 0 else ("UNCHANGED" if score_delta == 0 else "WORSENED"),
            })

        avg_score_before = round(
            sum(o["before"]["risk_score"] for o in affected_orders_comparison) / max(1, len(affected_orders_comparison)), 1
        )
        avg_score_after = round(
            sum(o["after"]["risk_score"] for o in affected_orders_comparison) / max(1, len(affected_orders_comparison)), 1
        )

        result = {
            "simulation_id": f"sim-d{disruption_id}-{action_type.lower()}",
            "disruption_id": disruption_id,
            "plan_id": plan_id,
            "action_type": action_type,
            "parameters": parameters,
            "action_summary": action_summary,
            "cost": sim_cost,
            "new_delivery_date": new_delivery_date_str,
            "meets_deadline": meets_deadline_flag,
            "affected_orders": affected_orders_comparison,
            "collateral_orders_affected": collateral_orders,
            "overall_before": {
                "avg_risk_score": avg_score_before,
                "total_shortfall": sum(o["before"]["shortfall"] for o in affected_orders_comparison),
            },
            "overall_after": {
                "avg_risk_score": avg_score_after,
                "total_shortfall": sum(o["after"]["shortfall"] for o in affected_orders_comparison),
                "total_cost": sim_cost,
                "risk_reduction": round(avg_score_before - avg_score_after, 1),
            },
        }
        return result

    finally:
        # HARD RULE 11 & 14: ALWAYS ROLLBACK TRANSACTION
        conn.rollback()
        conn.close()


def simulate_plan(plan_id: int, parameters_override: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Simulate the recovery option defined in a recovery_plans row.
    Loads action_type and parameters from the plan, applies any overrides,
    and runs simulate_option inside a transaction that is always rolled back.
    """
    conn = get_conn()
    try:
        plan = conn.execute("SELECT * FROM recovery_plans WHERE id = ?", (plan_id,)).fetchone()
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan #{plan_id} not found.",
            )

        payload = json.loads(plan["plan_payload"] or "{}")
        if parameters_override:
            payload.update(parameters_override)

        action_type = plan["action_type"]
        disruption_id = plan["disruption_id"]

        return simulate_option(
            disruption_id=disruption_id,
            action_type=action_type,
            parameters=payload,
            plan_id=plan_id,
        )
    finally:
        conn.close()
