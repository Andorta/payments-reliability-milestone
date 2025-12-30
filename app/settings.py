import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:5432/payments")
PROVIDER_TIMEOUT_SECONDS = float(os.environ.get("PROVIDER_TIMEOUT_SECONDS", "0.35"))
OUTAGE_PENDING_CAP_CENTS = int(os.environ.get("OUTAGE_PENDING_CAP_CENTS", "20000"))
