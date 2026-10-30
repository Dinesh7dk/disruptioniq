# DisruptionIQ: project context
Hackathon project: logistics disruption detection and recovery platform.

## Stack
Python 3.12, FastAPI, SQLite with raw parameterized SQL (no ORM), JWT auth
(bcrypt passwords), React + Vite frontend, pytest.

## Hard rules
1. Stock, deadline, permission and state-transition logic is deterministic Python.
   The LLM only writes summaries and recommends from options code already verified.
2. If the LLM fails or has no key, fall back to a template summary.
3. Roles are enforced in the backend on every endpoint: Operations Analyst,
   Supply Chain Manager, Warehouse Operator, Procurement Approver, Administrator.
4. No self-approval: approver must differ from proposer.
5. Duplicate webhook events are ignored via unique event_id.
6. Inventory updates use the version column inside a transaction.
7. Every state change writes to audit_logs (append-only).
8. SQL always uses ? placeholders, never string formatting.
9. Plan states: PROPOSED -> PENDING_APPROVAL -> APPROVED | REJECTED | MODIFIED;
   MODIFIED -> PENDING_APPROVAL; APPROVED -> EXECUTED. Anything else returns 409.
10. Revalidate stock and deadlines right before executing a plan.

## Folders
backend/ (main.py, db.py, auth.py, db/, seed/, services/, tests/), frontend/, scripts/

## Demo scenarios
1. Supplier delay: shipment SH-001 (Supplier A to Chennai, 500 x P1) is delayed;
   orders O-001 (HIGH, due day 3, 200), O-002 (MEDIUM, day 5, 150),
   O-003 (LOW, day 9, 50) are affected. Hyderabad has spare P1.
2. Stock shortage: Bangalore P2 on_hand 40, reserved 35; orders O-004 and O-005
   need 60 units total; Hyderabad has spare P2; reallocation is recommended.

## Additional hard rules
11. Creative features (what-if simulator, cascade map, risk breakdown, drafted
    messages, natural-language query) never write business data by themselves.
12. The LLM never writes SQL. For natural-language queries it may only return a
    JSON filter, which code validates against a whitelist of fields and values
    and runs as a parameterized query.
13. Demo-only endpoints (reset, run scenario) work only when DEMO_MODE=true in
    .env and only for the Administrator role.
14. The what-if simulator runs inside a transaction that is always rolled back.

## Creative features
- What-if simulator: compare recovery options before approval, no database changes
- Cascade map: Supplier -> Shipment -> Warehouse -> Orders -> Customers graph
- Risk breakdown: per-factor numeric contribution to each risk score
- Drafted messages: customer and supplier emails written by the LLM from verified
  facts, reviewed by a human, sending is simulated and logged
- Natural-language query box: question -> validated JSON filter -> parameterized query
- Demo controls: scenario run buttons, role switcher, live event feed
