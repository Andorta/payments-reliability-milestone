from pydantic import BaseModel, Field
from typing import Literal, Optional

BuyerTrust = Literal["trusted", "new"]

class CheckoutRequest(BaseModel):
    buyer_id: str
    seller_id: str
    amount_cents: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    buyer_trust: BuyerTrust

class CheckoutResponse(BaseModel):
    order_id: str
    status: Literal["PENDING_PAYMENT", "PAID", "FAILED"]
    ready_to_ship: bool

class ProviderChargeResponse(BaseModel):
    provider_status: Literal["SUCCEEDED", "DECLINED"]
    provider_payment_id: Optional[str] = None

class WebhookEvent(BaseModel):
    event_id: str
    order_id: str
    outcome: Literal["PAID", "FAILED"]
