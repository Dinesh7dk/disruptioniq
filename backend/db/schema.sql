PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────────
-- USERS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT    NOT NULL UNIQUE,
    email       TEXT    NOT NULL UNIQUE,
    password_hash TEXT  NOT NULL,
    role        TEXT    NOT NULL CHECK(role IN (
                    'Operations Analyst',
                    'Supply Chain Manager',
                    'Warehouse Operator',
                    'Procurement Approver',
                    'Administrator'
                )),
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ─────────────────────────────────────────────
-- SUPPLIERS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS suppliers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL,
    contact     TEXT,
    email       TEXT,
    reliability_score REAL CHECK(reliability_score BETWEEN 0 AND 1),
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ─────────────────────────────────────────────
-- PRODUCTS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL,
    unit        TEXT    NOT NULL DEFAULT 'unit',
    unit_cost   REAL    NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ─────────────────────────────────────────────
-- WAREHOUSES
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS warehouses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL,
    city        TEXT    NOT NULL,
    capacity    INTEGER NOT NULL DEFAULT 0 CHECK(capacity >= 0),
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ─────────────────────────────────────────────
-- INVENTORY  (version column for optimistic locking per rule 6)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS inventory (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
    product_id   INTEGER NOT NULL REFERENCES products(id)   ON DELETE CASCADE,
    on_hand      INTEGER NOT NULL DEFAULT 0 CHECK(on_hand >= 0),
    reserved     INTEGER NOT NULL DEFAULT 0 CHECK(reserved >= 0),
    version      INTEGER NOT NULL DEFAULT 0,
    updated_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(warehouse_id, product_id),
    CHECK(reserved <= on_hand)
);

-- ─────────────────────────────────────────────
-- SHIPMENTS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS shipments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE,
    supplier_id     INTEGER NOT NULL REFERENCES suppliers(id)  ON DELETE RESTRICT,
    product_id      INTEGER NOT NULL REFERENCES products(id)   ON DELETE RESTRICT,
    dest_warehouse_id INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE RESTRICT,
    quantity        INTEGER NOT NULL CHECK(quantity > 0),
    status          TEXT    NOT NULL DEFAULT 'IN_TRANSIT'
                            CHECK(status IN ('IN_TRANSIT','DELAYED','ARRIVED','CANCELLED')),
    expected_arrival TEXT,
    current_eta      TEXT,
    actual_arrival   TEXT,
    delay_days      INTEGER NOT NULL DEFAULT 0 CHECK(delay_days >= 0),
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ─────────────────────────────────────────────
-- ORDERS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT    NOT NULL UNIQUE,
    customer     TEXT    NOT NULL,
    priority     TEXT    NOT NULL CHECK(priority IN ('HIGH','MEDIUM','LOW')),
    status       TEXT    NOT NULL DEFAULT 'OPEN'
                         CHECK(status IN ('OPEN','FULFILLED','PARTIAL','CANCELLED')),
    due_date     TEXT    NOT NULL,
    created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ─────────────────────────────────────────────
-- ORDER LINES
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS order_lines (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER NOT NULL REFERENCES orders(id)   ON DELETE CASCADE,
    product_id   INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE RESTRICT,
    quantity     INTEGER NOT NULL CHECK(quantity > 0),
    fulfilled    INTEGER NOT NULL DEFAULT 0 CHECK(fulfilled >= 0),
    UNIQUE(order_id, product_id, warehouse_id)
);

-- ─────────────────────────────────────────────
-- DISRUPTIONS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS disruptions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    type         TEXT    NOT NULL CHECK(type IN ('SUPPLIER_DELAY','STOCK_SHORTAGE','TRANSPORT','CUSTOMS','OTHER')),
    status       TEXT    NOT NULL DEFAULT 'OPEN'
                         CHECK(status IN ('OPEN','MITIGATED','RESOLVED','IGNORED')),
    shipment_id  INTEGER REFERENCES shipments(id) ON DELETE SET NULL,
    warehouse_id INTEGER REFERENCES warehouses(id) ON DELETE SET NULL,
    product_id   INTEGER REFERENCES products(id)   ON DELETE SET NULL,
    description  TEXT,
    ai_summary   TEXT,
    ai_source    TEXT,
    detected_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    resolved_at  TEXT,
    created_by   INTEGER REFERENCES users(id) ON DELETE SET NULL
);

-- ─────────────────────────────────────────────
-- DISRUPTION IMPACTS  (per-order impact with risk breakdown JSON)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS disruption_impacts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    disruption_id  INTEGER NOT NULL REFERENCES disruptions(id) ON DELETE CASCADE,
    order_id       INTEGER NOT NULL REFERENCES orders(id)      ON DELETE CASCADE,
    risk_score     REAL    NOT NULL DEFAULT 0 CHECK(risk_score >= 0),
    risk_level     TEXT    NOT NULL DEFAULT 'LOW'
                           CHECK(risk_level IN ('CRITICAL','HIGH','MEDIUM','LOW')),
    risk_breakdown TEXT    NOT NULL DEFAULT '{}',   -- JSON: {factor: points, ...}
    risk_reasons   TEXT    NOT NULL DEFAULT '[]',   -- JSON: ["reason", ...]
    units_at_risk  INTEGER NOT NULL DEFAULT 0 CHECK(units_at_risk >= 0),
    computed_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(disruption_id, order_id)
);

-- ─────────────────────────────────────────────
-- RECOVERY PLANS  (no self-approval: CHECK(decided_by <> proposed_by))
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS recovery_plans (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    disruption_id   INTEGER NOT NULL REFERENCES disruptions(id) ON DELETE CASCADE,
    title           TEXT    NOT NULL,
    description     TEXT,
    action_type     TEXT    NOT NULL CHECK(action_type IN (
                        'REROUTE_SHIPMENT',
                        'REALLOCATE_STOCK',
                        'EXPEDITE_ORDER',
                        'PARTIAL_FULFIL',
                        'CANCEL_ORDER',
                        'OTHER'
                    )),
    status          TEXT    NOT NULL DEFAULT 'PROPOSED'
                            CHECK(status IN (
                                'PROPOSED',
                                'PENDING_APPROVAL',
                                'APPROVED',
                                'REJECTED',
                                'MODIFIED',
                                'EXECUTED'
                            )),
    proposed_by     INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    decided_by      INTEGER          REFERENCES users(id) ON DELETE RESTRICT,
    decision_note   TEXT,
    proposed_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    decided_at      TEXT,
    executed_at     TEXT,
    -- Rule 4 & hard rule: approver must differ from proposer
    CHECK(decided_by IS NULL OR decided_by <> proposed_by)
);

-- ─────────────────────────────────────────────
-- WEBHOOK EVENTS  (event_id is PK — deduplication per rule 5)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS webhook_events (
    event_id    TEXT    PRIMARY KEY,               -- external idempotency key
    source      TEXT    NOT NULL,
    event_type  TEXT    NOT NULL,
    payload     TEXT    NOT NULL DEFAULT '{}',      -- raw JSON
    status      TEXT    NOT NULL DEFAULT 'RECEIVED'
                        CHECK(status IN ('RECEIVED','PROCESSED','FAILED','IGNORED')),
    received_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    processed_at TEXT
);

-- ─────────────────────────────────────────────
-- NOTIFICATIONS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notifications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title        TEXT    NOT NULL,
    body         TEXT    NOT NULL,
    type         TEXT    NOT NULL CHECK(type IN ('DISRUPTION','APPROVAL','SYSTEM','INFO')),
    is_read      INTEGER NOT NULL DEFAULT 0 CHECK(is_read IN (0,1)),
    ref_table    TEXT,                             -- e.g. 'disruptions'
    ref_id       INTEGER,                          -- FK-like soft reference
    created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ─────────────────────────────────────────────
-- AUDIT LOGS  (append-only per rule 7)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action       TEXT    NOT NULL,                 -- e.g. 'PLAN_APPROVED'
    entity_type  TEXT    NOT NULL,                 -- e.g. 'recovery_plans'
    entity_id    INTEGER NOT NULL,
    old_value    TEXT,                             -- JSON snapshot before
    new_value    TEXT,                             -- JSON snapshot after
    note         TEXT,
    created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ─────────────────────────────────────────────
-- MESSAGE DRAFTS  (LLM-drafted comms, human approved, sending simulated)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS message_drafts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id      INTEGER REFERENCES orders(id)      ON DELETE SET NULL,
    disruption_id INTEGER REFERENCES disruptions(id) ON DELETE SET NULL,
    audience      TEXT    NOT NULL CHECK(audience IN ('CUSTOMER','SUPPLIER')),
    subject       TEXT    NOT NULL,
    body          TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'DRAFT'
                          CHECK(status IN ('DRAFT','APPROVED','SENT_SIMULATED')),
    created_by    INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    approved_by   INTEGER          REFERENCES users(id) ON DELETE SET NULL,
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ═════════════════════════════════════════════
-- INDEXES  (impact analysis, dashboard lookups)
-- ═════════════════════════════════════════════

-- Inventory lookups by warehouse + product (the most frequent join)
CREATE INDEX IF NOT EXISTS idx_inventory_warehouse_product
    ON inventory(warehouse_id, product_id);

-- Shipment status filtering (delayed shipments dashboard)
CREATE INDEX IF NOT EXISTS idx_shipments_status
    ON shipments(status);

-- Shipments by destination warehouse
CREATE INDEX IF NOT EXISTS idx_shipments_dest_warehouse
    ON shipments(dest_warehouse_id);

-- Orders by priority + status (impact analysis triage)
CREATE INDEX IF NOT EXISTS idx_orders_priority_status
    ON orders(priority, status);

-- Orders by due date (deadline revalidation, rule 10)
CREATE INDEX IF NOT EXISTS idx_orders_due_date
    ON orders(due_date);

-- Order lines by order
CREATE INDEX IF NOT EXISTS idx_order_lines_order
    ON order_lines(order_id);

-- Order lines by warehouse (stock reallocation queries)
CREATE INDEX IF NOT EXISTS idx_order_lines_warehouse
    ON order_lines(warehouse_id);

-- Disruption impacts by disruption (cascade map)
CREATE INDEX IF NOT EXISTS idx_impacts_disruption
    ON disruption_impacts(disruption_id);

-- Disruption impacts by order (reverse lookup)
CREATE INDEX IF NOT EXISTS idx_impacts_order
    ON disruption_impacts(order_id);

-- Recovery plans by disruption + status (approval queue)
CREATE INDEX IF NOT EXISTS idx_plans_disruption_status
    ON recovery_plans(disruption_id, status);

-- Recovery plans pending approval (approver dashboard)
CREATE INDEX IF NOT EXISTS idx_plans_pending
    ON recovery_plans(status) WHERE status = 'PENDING_APPROVAL';

-- Disruptions by status (open disruptions dashboard)
CREATE INDEX IF NOT EXISTS idx_disruptions_status
    ON disruptions(status);

-- Notifications by user + unread (live event feed)
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
    ON notifications(user_id, is_read);

-- Audit logs by entity (history panel)
CREATE INDEX IF NOT EXISTS idx_audit_entity
    ON audit_logs(entity_type, entity_id);

-- Webhook events by status (reprocessing queue)
CREATE INDEX IF NOT EXISTS idx_webhook_status
    ON webhook_events(status);

-- Message drafts by disruption + audience
CREATE INDEX IF NOT EXISTS idx_drafts_disruption_audience
    ON message_drafts(disruption_id, audience);
