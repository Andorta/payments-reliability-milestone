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

Open API Docs
```
Swagger UI: http://localhost:8000/docs

## Demos & usage
1) Idempotent checkout

Create an order using an Idempotency-Key:
```
curl -s -X POST "http://localhost:8000/checkout" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-1" \
  -d '{"buyer_id":"b1","seller_id":"s1","amount_cents":5000,"currency":"EUR","buyer_trust":"trusted"}'
```

## What to expect:

Success: you receive PAID (or sometimes FAILED depending on simulator).

Idempotency proof: run the same request again (same key + same body) → exact same order_id.

Conflict prevention: reuse the same key with a different request body → 409 Conflict.

2) Provider outage to webhook finalization

The provider is simulated and occasionally times out.

Step A: Create a pending order

Use a new idempotency key each attempt until you trigger PENDING_PAYMENT:
```
curl -s -X POST "http://localhost:8000/checkout" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: pending-1" \
  -d '{"buyer_id":"b2","seller_id":"s2","amount_cents":5000,"currency":"EUR","buyer_trust":"trusted"}'
```

Example response:

{"order_id":"...","status":"PENDING_PAYMENT","ready_to_ship":false}

Step B: Finalize via webhook

Use the <ORDER_ID> from the previous step:
```
curl -s -X POST "http://localhost:8000/webhooks/provider" \
  -H "Content-Type: application/json" \
  -d '{"event_id":"evt-200","order_id":"<ORDER_ID>","outcome":"PAID"}'
```

Step C: Replay protection

Send the same webhook again (same event_id) — it should be detected as a duplicate:
```
curl -s -X POST "http://localhost:8000/webhooks/provider" \
  -H "Content-Type: application/json" \
  -d '{"event_id":"evt-200","order_id":"<ORDER_ID>","outcome":"PAID"}'
```

Expected:

{"ok":true,"duplicate":true}

Ledger & accounting

When an order is finalized, the system records two entries:

DEBIT cash

CREDIT seller_payable

Inspecting the database

List tables:
```
docker compose exec db psql -U app -d payments -P pager=off -c "\dt"
```

Inspect ledger entries for an order:
```
docker compose exec db psql -U app -d payments -P pager=off -c \
"SELECT e.account, e.direction, e.amount_cents, e.currency
 FROM ledger_entries e
 JOIN ledger_transactions t ON t.id = e.txn_id
 WHERE t.order_id = '<ORDER_ID>'
 ORDER BY e.account, e.direction;"
```

Design policies
Outage mode policy

To limit risk during outages, PENDING_PAYMENT is only allowed if:

buyer_trust is "trusted"

the order amount is below the OUTAGE_PENDING_CAP_CENTS threshold

## Project structure

app/            # FastAPI application code
sql/init.sql    # Postgres schema created on container startup
tests/          # (optional) tests
docker-compose.yml
Dockerfile
requirements.txt







