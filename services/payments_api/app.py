"""Payments API (external): External payment processing via REST

Implements board edges:
  <- booking_api via http 'charge / REST' (exposes REST API for charging)

Responsibility: External payment processing via REST
"""
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Payments API")

# In-memory store for charges (for testing / verification)
charges: list[dict] = []
_charge_counter: int = 0

class ChargeRequest(BaseModel):
    amount: float
    currency: str = "USD"
    customer_email: str
    description: Optional[str] = None
    booking_id: Optional[int] = None

class ChargeOut(BaseModel):
    id: str
    amount: float
    currency: str
    customer_email: str
    description: Optional[str] = None
    status: str
    booking_id: Optional[int] = None

class RefundRequest(BaseModel):
    charge_id: str
    amount: Optional[float] = None

@app.get("/health")
def health() -> dict:
    return {"service": "payments_api", "status": "ok"}

@app.post("/charge", response_model=ChargeOut, status_code=201)
def create_charge(payload: ChargeRequest):
    global _charge_counter
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount, must be > 0")
    # Simulate decline for specific test email pattern
    if "decline" in payload.customer_email:
        raise HTTPException(status_code=402, detail="Payment declined")
    _charge_counter += 1
    charge = {
        "id": f"ch_{_charge_counter:06d}",
        "amount": payload.amount,
        "currency": payload.currency,
        "customer_email": payload.customer_email,
        "description": payload.description,
        "status": "succeeded",
        "booking_id": payload.booking_id,
    }
    charges.append(charge)
    return charge

@app.get("/charges", response_model=List[ChargeOut])
def list_charges(customer_email: Optional[str] = None):
    if customer_email:
        return [c for c in charges if c["customer_email"] == customer_email]
    return charges

@app.get("/charges/{charge_id}", response_model=ChargeOut)
def get_charge(charge_id: str):
    for c in charges:
        if c["id"] == charge_id:
            return c
    raise HTTPException(status_code=404, detail="Charge not found")

@app.post("/refund", response_model=ChargeOut)
def refund_charge(payload: RefundRequest):
    for c in charges:
        if c["id"] == payload.charge_id:
            refunded = dict(c)
            refunded["status"] = "refunded"
            refunded["id"] = f"re_{c['id']}"
            charges.append(refunded)
            return refunded
    raise HTTPException(status_code=404, detail="Charge not found")

def reset_charges():
    global _charge_counter
    charges.clear()
    _charge_counter = 0
