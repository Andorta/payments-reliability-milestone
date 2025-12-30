from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

import hashlib
import json
import uuid
import random
import asyncio
import httpx

from .db import get_conn
from .models import CheckoutRequest, CheckoutResponse, WebhookEvent
from .settings import PROVIDER_TIMEOUT_SECONDS, OUTAGE_PENDING_CAP_CENTS

app = FastAPI(title="Payments Milestone", version="0.1.0")

# Serve UI static assets under /ui and the main page at /
app.mount("/ui", StaticFiles(directory="ui"), name="ui")

@app.get("/")
def root():
    return FileResponse("ui/index.html")

@app.get("/health")
def health():
    return {"ok": True}

def sha256_json(obj: dict) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


async def call_provider_simulator(payload: dict) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "http://api:8000/_provider/charge",
            json=payload,
            timeout=PROVIDER_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        return r.json()



def create_ledger_for_paid_order(conn, order_id: str):
    """
    Minimal double-entry ledger for a paid order:
      DEBIT  cash
      CREDIT seller_payable
    Same amount, same currency => balanced.
    """
    order = conn.execute(
        "SELECT id, amount_cents, currency, status FROM orders WHERE id = %s",
        (order_id,),
    ).fetchone()
    if not order or order["status"] != "PAID":
        return

    txn = conn.execute(
        "INSERT INTO ledger_transactions(order_id, type, currency, amount_cents) "
        "VALUES (%s, 'CHARGE', %s, %s) RETURNING id",
        (order_id, order["currency"], order["amount_cents"]),
    ).fetchone()
    txn_id = txn["id"]

    amt = order["amount_cents"]
    cur = order["currency"]

    conn.execute(
        "INSERT INTO ledger_entries(txn_id, account, direction, currency, amount_cents) "
        "VALUES (%s, 'cash', 'DEBIT', %s, %s)",
        (txn_id, cur, amt),
    )
    conn.execute(
        "INSERT INTO ledger_entries(txn_id, account, direction, currency, amount_cents) "
        "VALUES (%s, 'seller_payable', 'CREDIT', %s, %s)",
        (txn_id, cur, amt),
    )


@app.post("/checkout", response_model=CheckoutResponse)
async def checkout(req: CheckoutRequest, idempotency_key: str = Header(None, alias="Idempotency-Key")):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Missing Idempotency-Key header")

    request_hash = sha256_json(req.model_dump())

    with get_conn() as conn:
        # 1) Idempotency lookup
        existing = conn.execute(
            "SELECT idem_key, request_hash, status_code, response_json "
            "FROM idempotency_keys WHERE idem_key = %s",
            (idempotency_key,),
        ).fetchone()

        if existing:
            if existing["request_hash"] != request_hash:
                raise HTTPException(status_code=409, detail="Idempotency-Key reuse with different request body")
            if existing["status_code"] and existing["response_json"] is not None:
                return JSONResponse(status_code=existing["status_code"], content=existing["response_json"])

        # 2) Reserve idempotency key (insert if new)
        if not existing:
            conn.execute(
                "INSERT INTO idempotency_keys(idem_key, request_hash) VALUES (%s, %s)",
                (idempotency_key, request_hash),
            )

        # 3) Try provider charge
        provider_payload = req.model_dump()
        provider_down = False
        provider_declined = False

        try:
            provider_resp = await call_provider_simulator(provider_payload)
            if provider_resp.get("provider_status") == "DECLINED":
                provider_declined = True
        except (httpx.TimeoutException, httpx.TransportError):
            provider_down = True

        # 4) Decide outcome (simple policy)
        if provider_declined:
            status = "FAILED"
            ready_to_ship = False
        elif provider_down:
            # Outage mode: only trusted buyers under a cap can be pending
            if req.buyer_trust == "trusted" and req.amount_cents <= OUTAGE_PENDING_CAP_CENTS:
                status = "PENDING_PAYMENT"
                ready_to_ship = False
            else:
                # Reject instead of taking risk
                raise HTTPException(status_code=503, detail="Payment provider unavailable; try again")
        else:
            status = "PAID"
            ready_to_ship = True

        # 5) Create order
        order = conn.execute(
            "INSERT INTO orders(buyer_id, seller_id, amount_cents, currency, buyer_trust, status, ready_to_ship) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id, status, ready_to_ship",
            (req.buyer_id, req.seller_id, req.amount_cents, req.currency.upper(), req.buyer_trust, status, ready_to_ship),
        ).fetchone()

        # If paid immediately, write ledger
        if status == "PAID":
            create_ledger_for_paid_order(conn, str(order["id"]))

        resp = {
            "order_id": str(order["id"]),
            "status": order["status"],
            "ready_to_ship": order["ready_to_ship"],
        }

        # 6) Store idempotent response
        conn.execute(
            "UPDATE idempotency_keys SET status_code = %s, response_json = %s, updated_at = NOW() "
            "WHERE idem_key = %s",
            (200, json.dumps(resp), idempotency_key),
        )

        return resp
    
@app.get("/orders/{order_id}")
def get_order(order_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, buyer_id, seller_id, amount_cents, currency, buyer_trust, status, ready_to_ship, created_at, updated_at "
            "FROM orders WHERE id = %s",
            (order_id,),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Order not found")

        row["id"] = str(row["id"])
        return row


@app.post("/webhooks/provider")
def provider_webhook(evt: WebhookEvent):
    """
    Replay-safe: event_id is unique; duplicates are ignored.
    """
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT event_id FROM webhook_events WHERE event_id = %s",
            (evt.event_id,),
        ).fetchone()
        if existing:
            return {"ok": True, "duplicate": True}

        # Store event first (dedupe key)
        conn.execute(
            "INSERT INTO webhook_events(event_id, order_id, payload) VALUES (%s, %s, %s)",
            (evt.event_id, evt.order_id, json.dumps(evt.model_dump())),
        )

        # Apply state change
        if evt.outcome == "PAID":
            conn.execute(
                "UPDATE orders SET status = 'PAID', ready_to_ship = TRUE, updated_at = NOW() WHERE id = %s",
                (evt.order_id,),
            )
            create_ledger_for_paid_order(conn, evt.order_id)
        else:
            conn.execute(
                "UPDATE orders SET status = 'FAILED', ready_to_ship = FALSE, updated_at = NOW() WHERE id = %s",
                (evt.order_id,),
            )

        conn.execute(
            "UPDATE webhook_events SET processed_at = NOW() WHERE event_id = %s",
            (evt.event_id,),
        )

        return {"ok": True, "duplicate": False}


@app.post("/_provider/charge")
async def provider_charge_simulator(payload: dict):
    """
    Random behavior:
      - ~35%: slow response => client timeout simulates outage
      - ~10%: declined
      - rest: success
    """
    roll = random.random()

    if roll < 0.35:
        await asyncio.sleep(PROVIDER_TIMEOUT_SECONDS * 10)  # intentionally slow
        # Even though we eventually return, client will timeout
        return {"provider_status": "SUCCEEDED", "provider_payment_id": str(uuid.uuid4())}

    if roll < 0.45:
        return {"provider_status": "DECLINED", "provider_payment_id": None}

    return {"provider_status": "SUCCEEDED", "provider_payment_id": str(uuid.uuid4())}
