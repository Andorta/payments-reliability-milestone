# Payments Milestone — Idempotent Checkout, Outage Mode, Webhooks, Ledger

This repo is a small “payments platform” milestone built to demonstrate the core reliability patterns you need in real payment systems:

- **Idempotent checkout** (safe retries without double-charging / double-creating orders)
- **Provider outage simulation** (degraded mode that can create `PENDING_PAYMENT` orders under controlled risk)
- **Replay-safe webhooks** (provider retries are deduped)
- **Double-entry ledger writes** (balanced accounting entries on successful payment)

It’s intentionally minimal, but production-minded: the focus is on correctness and safety around money movement.

---

## What it does (high level)

A client calls `POST /checkout` to create an order and attempt a payment.

- If the payment provider succeeds: the order becomes **PAID**, and we write a **double-entry ledger** transaction.
- If the provider is unavailable (simulated by timeouts): eligible orders become **PENDING_PAYMENT** (trusted buyers, under a cap).  
  Later, a provider **webhook** can mark the order as **PAID** (and then ledger entries are written).
- Webhooks are **replay-safe**: the same `event_id` received twice will only be processed once.

---

## Tech stack

- **FastAPI** (Python) for the API
- **Postgres** for persistence (orders, idempotency keys, webhook events, ledger tables)
- **Docker Compose** for local dev

---

## Quick start

### 1) Run it 

```bash
docker compose up --build

**### 2) Open API Docs**

Swagger UI is available at: http://localhost:8000/docs

**Demos & usage**

**1. Idempotent Checkout**
Create an order using an Idempotency-Key.

**run the following in your terminal or CMD:**

curl -s -X POST "http://localhost:8000/checkout" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-1" \
  -d '{"buyer_id":"b1","seller_id":"s1","amount_cents":5000,"currency":"EUR","buyer_trust":"trusted"}'
Success: You receive a PAID status.

Idempotency Proof: Run the same request again. You will receive the exact same order_id.

Conflict Prevention: Change the request body but keep the same key; the API returns a 409 Conflict.

2. Provider Outage to Webhook Finalization

The provider is simulated and occasionally times out.

Step A: Create a Pending Order Use a new key until you trigger the outage logic:

**run the following in your terminal or CMD:**

curl -s -X POST "http://localhost:8000/checkout" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: pending-1" \
  -d '{"buyer_id":"b2","seller_id":"s2","amount_cents":5000,"currency":"EUR","buyer_trust":"trusted"}'
Response: {"status":"PENDING_PAYMENT", "ready_to_ship": false}

Step B: Finalize via Webhook Use the <ORDER_ID> from the previous step to simulate a provider callback:

**run the following in your terminal or CMD:**

curl -s -X POST "http://localhost:8000/webhooks/provider" \
  -H "Content-Type: application/json" \
  -d '{"event_id":"evt-200","order_id":"<ORDER_ID>","outcome":"PAID"}'
Step C: Replay Protection Send the same webhook again. The response will show duplicate: true, and the ledger will not be updated twice.

**Ledger & Accounting**
When an order is finalized, the system will record two entries:

DEBIT cash

CREDIT seller_payable

**Inspecting the Database**
To view the underlying tables:

**run the following in your terminal or CMD:**

docker compose exec db psql -U app -d payments -P pager=off -c "\dt"
To inspect ledger entries for a specific order:

**Then run the following in your terminal or CMD:**

docker compose exec db psql -U app -d payments -P pager=off -c \
"SELECT e.account, e.direction, e.amount_cents, e.currency
 FROM ledger_entries e
 JOIN ledger_transactions t ON t.id = e.txn_id
 WHERE t.order_id = '<ORDER_ID>'
 ORDER BY e.account, e.direction;"
Design Policies
Outage Mode Policy

To limit risk during outages, PENDING_PAYMENT is only allowed if:

buyer_trust is "trusted".

The order amount is below the OUTAGE_PENDING_CAP_CENTS threshold.

**Project structure**

app/            # FastAPI application code
sql/init.sql    # Postgres schema created on container startup
tests/          # (optional) tests
docker-compose.yml
Dockerfile
requirements.txt



