"""Client for Payments API - used by booking_api to charge via REST.

In production this would do HTTP requests to external service.
In tests/local, uses in-process TestClient against the payments_api app.
"""
from typing import Optional

# In-memory fake implementation - no network needed
# booking_api imports this and calls charge()

def charge(amount: float, customer_email: str, currency: str = "USD", description: Optional[str] = None, booking_id: Optional[int] = None) -> dict:
    """Charge a customer via Payments API REST."""
    # Use in-process call to avoid network
    from fastapi.testclient import TestClient
    from services.payments_api.app import app as payments_app
    client = TestClient(payments_app)
    resp = client.post("/charge", json={
        "amount": amount,
        "currency": currency,
        "customer_email": customer_email,
        "description": description,
        "booking_id": booking_id,
    })
    if resp.status_code == 201:
        return resp.json()
    # Propagate error details
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text
    raise Exception(f"Payment failed ({resp.status_code}): {detail}")

def get_charge(charge_id: str) -> dict:
    from fastapi.testclient import TestClient
    from services.payments_api.app import app as payments_app
    client = TestClient(payments_app)
    resp = client.get(f"/charges/{charge_id}")
    resp.raise_for_status()
    return resp.json()

def list_charges(customer_email: Optional[str] = None) -> list[dict]:
    from fastapi.testclient import TestClient
    from services.payments_api.app import app as payments_app
    client = TestClient(payments_app)
    params = {}
    if customer_email:
        params["customer_email"] = customer_email
    resp = client.get("/charges", params=params)
    resp.raise_for_status()
    return resp.json()
