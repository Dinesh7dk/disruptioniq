# DisruptionIQ: Logistics Disruption Detection & Recovery Platform

DisruptionIQ is a high-reliability supply chain resilience desk engineered to detect shipment delays and warehouse stock shortages, analyze multi-factor risk, generate verified recovery actions, and provide human-in-the-loop authorization workflows.

---

## Architecture & Hard Rules

- **Deterministic Core**: Inventory allocation, delivery deadlines, role authorization, and state transitions are strictly deterministic Python. The LLM never writes business data directly or generates SQL.
- **Strict Whitelist & Parameterized SQL**: Natural language queries convert to validated JSON filters with strictly whitelisted keys (`extra="forbid"`) and parameterized SQL (`?` placeholders).
- **Separation of Duty (Hard Rule 4)**: The approver of a recovery plan or customer/supplier message draft must differ from the proposer/creator.
- **Webhook Idempotency (Hard Rule 5)**: Carrier webhook events are deduplicated via unique `event_id`. Duplicate events return `{"status": "duplicate, ignored"}` without state changes.
- **Optimistic Concurrency Control (Hard Rule 6)**: Inventory allocations check and increment the `version` column inside a transaction. Concurrent conflicts return `HTTP 409 Conflict`.
- **Append-Only Audit Trail (Hard Rule 7)**: Every state change, webhook, import, and plan transition writes an immutable audit log record.
- **Demo Mode Isolation (Hard Rule 13)**: Reset and scenario-triggering endpoints (`/demo/reset`, `/demo/scenario/{1|2}`) are restricted to the `Administrator` role and function only when `DEMO_MODE=true` in `.env`.

---

## Seeded Users & Role Matrix

| Username | Password | Role | Responsibilities |
| :--- | :--- | :--- | :--- |
| `admin` | `admin123` | **Administrator** | System reset, scenario triggers, CSV/JSON imports, audit review |
| `anita` / `alice` | `pass123` | **Operations Analyst** | Monitors order risk, proposes recovery plans, creates drafts |
| `meera` / `carol` | `pass123` | **Supply Chain Manager** | Approves stock reallocations, expediting, and order splitting |
| `ravi` / `dave` | `pass123` | **Warehouse Operator** | Executes approved recovery plans, updates reservations |
| `priya` / `eve` | `pass123` | **Procurement Approver** | Authorizes alternative supplier purchase orders |

---

## Quick Start

### 1. Backend Setup
```bash
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Start FastAPI server
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## Demo Bar & Live Event Feed

When logged in as **Administrator** (`admin` / `admin123`) with `DEMO_MODE=true` in `.env`, a dedicated top **Demo Bar** appears with:

1. **Run Scenario 1**: Triggers Supplier Delay on `SH-001` (500 units of P1 to Chennai delayed by 6 days).
2. **Run Scenario 2**: Triggers Stock Shortage at Bangalore for `P2` (60 units open demand vs 5 available).
3. **Reset**: Atomically clears and reseeds the entire database to the initial clean demo baseline.
4. **Role Switcher**: Instant dropdown logging in as seeded users (`admin`, `anita`, `meera`, `ravi`, `priya`) to test multi-role governance without manual login/logout.
5. **Live Event Feed**: Integrated drawer streaming live operational events (`/events/recent`) merging carrier webhooks and user authorizations in real time with auto-refresh.

---

## Verification & Standalone Scripts

Each script is completely self-contained, resets state where appropriate, prints formatted step-by-step progress to stdout, and verifies backend invariant enforcement.

### 1. Scenario 1: Supplier Delay (`scripts/run_scenario1.py`)
- **Purpose**: Simulates a 6-day delay for inbound shipment `SH-001` (Supplier A carrying 500 units of Paracetamol `P1` to Chennai).
- **Execution Flow**:
  1. Reseeds the database to clean baseline.
  2. Updates `SH-001` with `current_eta = expected_arrival + 6 days`, status `DELAYED`, and logs a carrier webhook event.
  3. Executes `run_detection(shipment_id=1)`.
  4. Displays affected orders ranked by multi-factor risk score (`O-001: City Hospital` [HIGH], `O-002: MediChain` [MEDIUM], `O-003: Corner Pharmacy` [LOW]) along with numeric weight breakdowns and root cause reasons.
  5. Evaluates recovery feasibility: confirms Hyderabad warehouse has spare `P1` inventory (>200 units) and generates a feasible `REALLOCATE_STOCK` plan meeting `O-001`'s deadline.
- **Run Command**:
  ```bash
  python scripts/run_scenario1.py
  ```

---

### 2. Scenario 2: Stock Shortage (`scripts/run_scenario2.py`)
- **Purpose**: Detects a severe stock shortage at the Bangalore warehouse for `P2` (Face Mask N95) and verifies reallocation recommendations.
- **Execution Flow**:
  1. Reseeds the database.
  2. Inspects Bangalore inventory for `P2`: `on_hand=40, reserved=35` -> only 5 available units against 60 units of open customer demand (`O-004`: 40 units, `O-005`: 20 units), revealing a net shortfall of 55 units.
  3. Executes `detect_stock_shortages()` and creates a `STOCK_SHORTAGE` disruption profile.
  4. Analyzes order impact and scores risks for `O-004` and `O-005`.
  5. Queries recovery options: discovers Hyderabad has 300 available `P2` units and outputs feasible reallocation transfers for both affected hospital/retail orders.
- **Run Command**:
  ```bash
  python scripts/run_scenario2.py
  ```

---

### 3. Duplicate Webhook Idempotency (`scripts/duplicate_webhook.py`)
- **Purpose**: Demonstrates **Hard Rule 5**—carrier webhook idempotency via unique `event_id`.
- **Execution Flow**:
  1. Reseeds the database.
  2. Posts carrier tracking event `EVT-CARRIER-TEST-999` for shipment `SH-001` setting status to `DELAYED`.
  3. Verifies initial event response is `HTTP 200` with `{"status": "processed", "shipment_id": 1}` and database shipment status changes to `DELAYED`.
  4. Transmits a **duplicate** webhook payload with the exact same `event_id`, but attempting an unauthorized status override to `ARRIVED`.
  5. Verifies backend responds with `{"status": "duplicate, ignored"}` and confirms shipment status in the database remained `DELAYED` without duplicate rows in `webhook_events`.
- **Run Command**:
  ```bash
  python scripts/duplicate_webhook.py
  ```

---

### 4. Dirty CSV Import Validation (`scripts/dirty_csv_import.py`)
- **Purpose**: Demonstrates bulk shipment CSV ingestion safety, validating fields and isolating corrupted records without failing the entire batch.
- **Execution Flow**:
  1. Reseeds the database and authenticates as Administrator (`admin`).
  2. Parses `backend/seed/shipments_dirty.csv` containing negative quantity, unknown supplier codes, invalid date strings, and within-batch duplicate references.
  3. POSTs the file to `/import/shipments/csv`.
  4. Verifies response: exactly 1 clean row is imported (`SH-D04`) and 4 corrupted rows are rejected with explicit row-level error diagnostics.
- **Run Command**:
  ```bash
  python scripts/dirty_csv_import.py
  ```

---

### 5. Self-Approval Blocked (`scripts/self_approval_blocked.py`)
- **Purpose**: Enforces **Hard Rule 4**—proposer/creator cannot approve their own recovery plan or message draft (Separation of Duty).
- **Execution Flow**:
  1. Reseeds the database and initializes Scenario 1.
  2. **Part 1 (Recovery Plan)**: Alice (`Operations Analyst`) proposes a stock reallocation plan. Alice attempts to approve her own proposal -> blocked with `HTTP 403 Forbidden`. Carol (`Supply Chain Manager`) then approves the plan successfully (`HTTP 200 APPROVED`).
  3. **Part 2 (Drafted Message)**: Alice creates an automated customer disruption draft for Order 1. Alice attempts self-approval -> rejected with `HTTP 403 Forbidden: Separation of duty violation: approver must be a different user than the creator`. Bob (`Operations Analyst`) reviews and approves the draft successfully.
- **Run Command**:
  ```bash
  python scripts/self_approval_blocked.py
  ```

---

### 6. Stock Version Conflict (`scripts/stock_version_conflict.py`)
- **Purpose**: Demonstrates **Hard Rule 6**—Optimistic Concurrency Control (OCC) on warehouse inventory reservations.
- **Execution Flow**:
  1. Reseeds the database and creates an approved recovery plan transferring `P1` from Hyderabad.
  2. Inspects Hyderabad `P1` inventory (`on_hand=300, reserved=20, version=0`).
  3. Simulates a concurrent race condition by manually incrementing `version = 99` in another transaction.
  4. Dave (`Warehouse Operator`) attempts to execute the approved recovery plan via `POST /plans/{id}/execute`.
  5. The execution engine detects the version mismatch, aborts the operation, rolls back the transaction, and returns `HTTP 409 Conflict: Optimistic locking version conflict: inventory modified concurrently`.
  6. Verifies database integrity: Hyderabad reserved quantity remains unchanged (`20`), ensuring zero inventory phantom allocations.
- **Run Command**:
  ```bash
  python scripts/stock_version_conflict.py
  ```

---

## Running the Pytest Suite

```bash
# Run all test suites
pytest

# Run individual test modules
pytest backend/tests/test_demo.py
pytest backend/tests/test_nlquery.py
pytest backend/tests/test_approval.py
pytest backend/tests/test_detection_impact_risk.py
pytest backend/tests/test_webhook.py
pytest backend/tests/test_import.py
```
