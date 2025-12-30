CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS orders (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  buyer_id TEXT NOT NULL,
  seller_id TEXT NOT NULL,
  amount_cents INT NOT NULL CHECK (amount_cents >= 0),
  currency TEXT NOT NULL,
  buyer_trust TEXT NOT NULL CHECK (buyer_trust IN ('trusted','new')),
  status TEXT NOT NULL CHECK (status IN ('PENDING_PAYMENT','PAID','FAILED')),
  ready_to_ship BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
  idem_key TEXT PRIMARY KEY,
  request_hash TEXT NOT NULL,
  status_code INT,
  response_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS webhook_events (
  event_id TEXT PRIMARY KEY,
  order_id UUID NOT NULL REFERENCES orders(id),
  payload JSONB NOT NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ledger_transactions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  order_id UUID NOT NULL REFERENCES orders(id),
  type TEXT NOT NULL CHECK (type IN ('CHARGE')),
  currency TEXT NOT NULL,
  amount_cents INT NOT NULL CHECK (amount_cents >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ledger_entries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  txn_id UUID NOT NULL REFERENCES ledger_transactions(id),
  account TEXT NOT NULL,
  direction TEXT NOT NULL CHECK (direction IN ('DEBIT','CREDIT')),
  currency TEXT NOT NULL,
  amount_cents INT NOT NULL CHECK (amount_cents >= 0)
);
