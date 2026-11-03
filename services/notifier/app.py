"""Notifier (worker): Consumes booking events and sends notifications

Implements board edges:
  -> email via smtp '' (sends email via external provider - simulated)
  <- booking_api via event 'booking.created' (subscribes to booking events)

Responsibility: Consumes booking events and sends notifications
"""
from fastapi import FastAPI

from common.bus import bus
from common.db import init_db
import common.models  # noqa: F401 ensure tables exist

app = FastAPI(title="Notifier")
init_db()

# In-memory store for sent emails (for testing / verification)
sent_emails: list[dict] = []
# Also track received events
received_events: list[dict] = []

def send_email(to: str, subject: str, body: str) -> dict:
    """Simulate sending email via external Email provider (smtp edge)."""
    email_record = {"to": to, "subject": subject, "body": body}
    sent_emails.append(email_record)
    return email_record

def handle_booking_created(payload: dict) -> None:
    """Handler for booking.created event from booking_api."""
    received_events.append(payload)
    # Send confirmation email to guest
    guest_email = payload.get("guest_email", "")
    guest_name = payload.get("guest_name", "")
    booking_id = payload.get("booking_id")
    room_id = payload.get("room_id")
    start_time = payload.get("start_time", "")
    end_time = payload.get("end_time", "")

    subject = f"Booking Confirmation #{booking_id}"
    body = (
        f"Hello {guest_name},\n"
        f"Your booking for room {room_id} has been confirmed.\n"
        f"From: {start_time}\n"
        f"To: {end_time}\n"
        f"Booking ID: {booking_id}\n"
    )
    send_email(to=guest_email, subject=subject, body=body)

# Subscribe at import time as required
bus.subscribe("booking.created", handle_booking_created)

@app.get("/health")
def health() -> dict:
    return {"service": "notifier", "status": "ok"}

@app.get("/sent-emails")
def list_sent_emails() -> list[dict]:
    return sent_emails

@app.get("/received-events")
def list_received_events() -> list[dict]:
    return received_events

@app.post("/send-test-email")
def send_test_email(to: str, subject: str = "Test", body: str = "Hello") -> dict:
    """Manual endpoint to trigger email sending (for testing smtp edge)."""
    return send_email(to=to, subject=subject, body=body)
