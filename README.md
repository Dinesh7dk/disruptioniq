# DisruptionIQ: Logistics Disruption Detection & Recovery Platform

DisruptionIQ is a high-reliability supply chain resilience desk engineered to detect shipment delays and warehouse stock shortages, analyze multi-factor risk, generate verified recovery actions, and provide human-in-the-loop authorization workflows.

---

## 1. The Problem

Modern supply chains operate under tight tolerances with lean inventory. When disruptions strike—such as an inbound overseas shipment delayed by 6 days or unexpected warehouse stock shortages—they trigger dangerous cascade failures downstream:
- Critical customer orders (e.g., intensive care hospital supplies) miss firm due dates.
- Expedited freight or emergency transfers are proposed reactively without holistic cost-benefit evaluation.
- Traditional ERP systems rely on manual spreadsheets or unconstrained, opaque "black-box" automation that risks hallucinating numbers, generating phantom inventory allocations, or executing unauthorized actions.

**DisruptionIQ solves this by pairing deterministic, mathematically verified logistics logic with constrained, safety-bounded AI assistance.**

---

## 2. System Architecture

```text
+----------------------------------------------------------------------------------------------------+
|                                           INCOMING INPUTS                                          |
|   +--------------------------+  +--------------------------+  +--------------------------------+   |
|   | Carrier Tracking Webhook |  | Bulk CSV / JSON Ingestion|  | UI Dashboard & NL Query Box    |   |
|   +------------+-------------+  +------------+-------------+  +---------------+----------------+   |
+----------------|-----------------------------|--------------------------------|--------------------+
                 |                             |                                |
                 v                             v                                v
+----------------------------------------------------------------------------------------------------+
|                                    GATEWAY & GOVERNANCE LAYER                                      |
|  * JWT Auth & Role-Based Access Control (5 whitelisted roles)                                      |
|  * Hard Rule 5: Webhook Idempotency (Deduplication via unique event_id)                            |
|  * Whitelist Pydantic Parser: Natural Query -> JSON Filter (extra="forbid", LLM never writes SQL)  |
+----------------------------------------------------------------------------------------------------+
                                               |
                                               v
+----------------------------------------------------------------------------------------------------+
|                              DETERMINISTIC LOGISTICS ENGINE (Python)                               |
|  * Detection Engine: Compares ETA > Due Date & checks (on_hand - reserved) < demand                |
|  * Multi-Factor Risk Scorer: Urgency, delay, customer tier, shortfall, alternative stock (0-100)   |
|  * Feasibility Filter: Reallocation, expediting, order splitting verified against actual stock     |
|  * Pre-Execution Revalidation: Re-verifies inventory & deadlines right before execution           |
+----------------------------------------------------------------------------------------------------+
                       |                                               |
                       v                                               v
+---------------------------------------------+ +----------------------------------------------------+
|         CONSTRAINED AI SERVICE (LLM)        | |           STATE MACHINE & RECOVERY CONTROL         |
|  * Executive Summaries & Recommendations    | |  * Plan Lifecycle:                                 |
|    strictly from verified feasible options  | |    PROPOSED -> PENDING_APPROVAL -> APPROVED         |
|  * Drafted Messages (Human-in-the-loop)     | |             -> EXECUTED                            |
|  * Strict 10-second timeout with fallback   | |  * Hard Rule 4: Separation of Duty (No self-appr)  |
|  * Zero database mutation permissions       | |  * Hard Rule 6: Optimistic Concurrency (version)   |
+---------------------------------------------+ +----------------------------------------------------+
                       |                                               |
                       +-----------------------+-----------------------+
                                               |
                                               v
+----------------------------------------------------------------------------------------------------+
|                                      DATA PERSISTENCE & AUDIT                                      |
|  * SQLite with Raw Parameterized SQL (? placeholders only; zero string formatting / f-strings)     |
|  * What-If Simulator: Transaction-isolated sandbox (Hard Rule 14: ALWAYS rolled back in finally)   |
|  * Append-Only Audit Trail: Every state transition and mutation recorded in audit_logs             |
+----------------------------------------------------------------------------------------------------+
```

---

## 3. How to Run

### Prerequisites
- **Python 3.12+**
- **Node.js 18+** & npm
- Operating System: Windows, macOS, or Linux

### Environment Setup
Create a `.env` file in the project root:
```env
JWT_SECRET=your-super-secret-jwt-key-min-32-chars
LLM_API_KEY=your-gemini-api-key-optional
DEMO_MODE=true
DATABASE_URL=sqlite:///./disruptioniq.db
```
*(Note: If `LLM_API_KEY` is not provided or fails, the platform automatically activates deterministic template fallbacks with zero interruption).*

### 1. Backend Setup & Startup
```powershell
# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1   # On Linux/macOS: source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Seed the database
python backend/seed/seed.py

# Start the FastAPI server
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend Setup & Startup
```powershell
cd frontend
npm install
npm run dev
```
Open **[http://localhost:5173](http://localhost:5173)** in your browser.

### 3. Running All Tests
```powershell
pytest backend/tests/ -v
```

---

## 4. Demo Scenarios & Walkthrough Steps

### Demo User Accounts
| Username | Password | Role | Responsibilities |
| :--- | :--- | :--- | :--- |
| `admin` | `admin123` | **Administrator** | Reset database, run scenarios, CSV imports, view audit logs |
| `anita` / `alice` | `pass123` | **Operations Analyst** | Monitor disruptions, propose recovery plans, create drafts |
| `meera` / `carol` | `pass123` | **Supply Chain Manager** | Approve recovery plans and customer communications |
| `ravi` / `dave` | `pass123` | **Warehouse Operator** | Execute approved plans, physical stock reservation |
| `priya` / `eve` | `pass123` | **Procurement Approver** | Authorize supplier expediting and alternative orders |

---

### Scenario 1: Supplier Inbound Delay
- **The Event**: Inbound shipment `SH-001` (500 units of Paracetamol `P1` from Supplier A to Chennai warehouse) is delayed by 6 days.
- **The Impact**: 3 downstream orders are placed at risk:
  1. `O-001` (**City Hospital**, HIGH priority, due Day 3, 200 units) -> Risk score **85.7 (HIGH)**.
  2. `O-002` (**MediChain Retail**, MEDIUM priority, due Day 5, 150 units) -> Risk score **73.7 (HIGH)**.
  3. `O-003` (**Corner Pharmacy**, LOW priority, due Day 9, 50 units) -> Risk score **48.7 (MEDIUM)**.

#### Demo Steps (UI):
1. Log in as `admin` (`admin123`).
2. Click **Reset** on the top Demo Bar to ensure a clean baseline.
3. Click **Run Scenario 1**. The Live Event Feed logs the carrier delay webhook.
4. Navigate to **Disruptions** and select Disruption `#1` (`SUPPLIER_DELAY`).
5. Review the **AI Executive Summary**, the **Cascade Map** (`Supplier A -> SH-001 -> Chennai -> Orders`), and the **Risk Breakdown**.
6. Click **Simulate Options**: compare `REALLOCATE_STOCK` from Hyderabad vs. `EXPEDITE_AIR`. Note that Hyderabad has 300 units of `P1` spare capacity.
7. Switch role to `anita` (`Operations Analyst`) via the Demo Bar role switcher. Propose the Hyderabad stock reallocation plan for `O-001`.
8. Attempt to approve the plan as `anita` -> **Blocked** by separation-of-duty guard.
9. Switch role to `meera` (`Supply Chain Manager`) and click **Approve Plan**.
10. Switch role to `ravi` (`Warehouse Operator`) and click **Execute Plan**. The inventory reservations update atomically with OCC version checks.

#### Demo Steps (CLI Script):
```powershell
python scripts/run_scenario1.py
```

---

### Scenario 2: Regional Stock Shortage
- **The Event**: Bangalore warehouse inventory for `P2` (N95 Face Masks) has `on_hand = 40, reserved = 35` (only **5 units available**).
- **The Demand**: Open hospital orders `O-004` (Apollo Clinic, 40 units) and `O-005` (HealthMart, 20 units) require 60 units total, resulting in an immediate **55-unit shortfall**.

#### Demo Steps (UI):
1. Log in as `admin` and click **Run Scenario 2** on the Demo Bar.
2. Select Disruption `#4` (`STOCK_SHORTAGE` at Bangalore for `P2`).
3. Observe affected orders `O-004` and `O-005`.
4. Run the recovery engine: it detects Hyderabad has 300 spare units of `P2` and recommends transferring 40 units to cover `O-004` and 20 units for `O-005`.
5. Switch to `anita`, draft a customer notification for Apollo Clinic, verify facts, switch to `meera` to approve the draft, and click **Send (Simulated)**.

#### Demo Steps (CLI Script):
```powershell
python scripts/run_scenario2.py
```

---

## 5. Architectural Boundary: AI vs. Deterministic Logic

| System Feature / Component | Classification | Implementation Details & Boundaries |
| :--- | :---: | :--- |
| **Inventory & Buffer Calculation** | **Deterministic** | Pure Python math: `on_hand - reserved - demand`. Zero AI inference. |
| **Deadline & Lead Time Checking** | **Deterministic** | Date arithmetic: `target_date + lead_days <= due_date`. |
| **Disruption Detection Engine** | **Deterministic** | SQL & Python logic detecting late shipments and inventory deficits. |
| **Multi-Factor Risk Scoring** | **Deterministic** | Weighted 5-factor formula (urgency, delay, priority, shortfall, alternative stock). |
| **Recovery Feasibility Generation** | **Deterministic** | Validates inventory availability, warehouse routes, and capacity before presenting. |
| **Plan Execution & Concurrency** | **Deterministic** | SQLite transaction with `version = version + 1` optimistic concurrency control. |
| **Disruption Executive Summary** | **Constrained AI** | Gemini REST API generates a 2-3 sentence overview. Falls back to deterministic template if offline or timed out (>10s). |
| **Recommendation Selection** | **Constrained AI** | LLM selects strictly ONE option from code-verified list. Recommendation is verified by code before display. |
| **Customer/Supplier Draft Messages** | **Constrained AI** | LLM crafts professional email drafts from pre-verified facts. Requires human peer approval before simulated sending. |
| **Natural Language Search Box** | **Constrained AI** | LLM converts user query into whitelisted JSON filter. Code runs parameterized SQL. The LLM never sees or writes SQL. |
| **What-If Impact Simulator** | **Deterministic** | Runs trial mutations inside an isolated transaction that is ALWAYS rolled back in `finally:`. |

---

## 6. Safety & Resilience Mechanisms

1. **Role-Based Access Control (RBAC - Hard Rule 3)**:
   - Enforced globally on every backend endpoint.
   - Restricts privileged operations (e.g., executing plans to `Warehouse Operator` or `Administrator`, approving to `Supply Chain Manager` or `Procurement Approver`, CSV imports to `Operations Analyst` or `Administrator`).
2. **Separation of Duty / No Self-Approval (Hard Rule 4)**:
   - Proposers of recovery plans or message drafts cannot approve their own submissions (`approver_id != proposer_id`).
   - Verified by automated test suite and standalone test script `scripts/self_approval_blocked.py`.
3. **Webhook Idempotency (Hard Rule 5)**:
   - Carrier webhook updates require unique `event_id`.
   - Repeated deliveries return `{"status": "duplicate, ignored"}` without mutating database state.
4. **Optimistic Concurrency Control (OCC - Hard Rule 6)**:
   - Inventory updates check `WHERE id = ? AND version = ? AND (on_hand - reserved) >= ?` and increment `version = version + 1`.
   - If another user modified stock concurrently, row count is 0 and system raises `HTTP 409 Conflict`.
5. **Pre-Execution Revalidation (Hard Rule 10)**:
   - Immediately before executing an approved plan, stock availability and customer delivery deadlines are re-verified from live state to prevent executing obsolete mitigations.
6. **Append-Only Immutable Audit Trail (Hard Rule 7)**:
   - Every state change, webhook event, CSV ingestion, plan transition, and simulated dispatch appends a structured record to `audit_logs` (`actor_id`, `action`, `entity_type`, `entity_id`, `new_value`, `timestamp`).
7. **Simulation Isolation (Hard Rule 14)**:
   - What-if simulator executes trial inventory reservations inside a database transaction that is unconditionally rolled back in `finally:`, guaranteeing zero persistent mutation.
8. **Parameterized SQL (Hard Rule 8)**:
   - Raw SQL exclusively uses `?` parameter bindings. Zero string formatting, concatenation, or f-strings.

---

## 7. Verification Scripts

The `scripts/` directory provides one-click standalone scripts to verify all core platform invariants:

```powershell
python scripts/run_scenario1.py            # Scenario 1 end-to-end execution
python scripts/run_scenario2.py            # Scenario 2 end-to-end execution
python scripts/duplicate_webhook.py        # Proves webhook idempotency (Hard Rule 5)
python scripts/dirty_csv_import.py         # Proves dirty CSV validation & isolation
python scripts/self_approval_blocked.py    # Proves separation-of-duty enforcement (Hard Rule 4)
python scripts/stock_version_conflict.py   # Proves OCC race condition protection (Hard Rule 6)
python scripts/record_demo_video.py        # Records full browser backup demo video (saves to demo_videos/)
```

A pre-recorded backup demo video is available at `demo_videos/disruptioniq_demo_backup.webm`.

---

## 8. Known Limitations & Production Roadmap

- **Single-Node SQLite Storage**: DisruptionIQ uses SQLite with raw parameterized SQL to provide atomic ACID transactions with zero ORM overhead. For multi-region enterprise scale, the raw SQL architecture seamlessly transitions to PostgreSQL or Google Cloud Spanner with row-level locks.
- **Synchronous LLM Calls with Fallback**: AI summaries run synchronously with a strict 10-second timeout. In high-throughput industrial environments, drafting and summary jobs can be queued via background workers (e.g., Celery/Redis) with WebSocket streaming.
- **Static Carrier Webhook Schemas**: The platform currently consumes standardized JSON webhook payloads. Real-world rollouts require adapter microservices to ingest legacy EDI 214/315 transportation formats.
- **Static Transportation Cost Tables**: Reallocation and air-expedite shipping costs currently leverage realistic regional distance-matrix tables rather than live dynamic carrier spot-rate APIs.
