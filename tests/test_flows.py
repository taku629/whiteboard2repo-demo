"""End-to-end tests for each board edge."""
import pytest
from fastapi.testclient import TestClient

from common.db import reset_db
from common.bus import bus

# Import apps - this also triggers bus subscriptions
from services.booking_api.app import app as booking_app
from services.notifier.app import app as notifier_app
from services.notifier.app import sent_emails, received_events

@pytest.fixture(autouse=True)
def isolate():
    reset_db()
    bus.log.clear()
    sent_emails.clear()
    received_events.clear()
    yield
    # cleanup after
    bus.log.clear()

def test_edge_web_app_to_booking_api_http():
    """Edge: web_app -> booking_api via http - frontend can create rooms and bookings via HTTP."""
    client = TestClient(booking_app)
    # Create a room (simulating web_app initiating booking flow)
    r = client.post("/rooms", json={"name": "Deluxe Suite", "capacity": 2, "description": "Nice view"})
    assert r.status_code == 201, r.text
    room_id = r.json()["id"]

    # List rooms
    r = client.get("/rooms")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["name"] == "Deluxe Suite"

    # Get single room
    r = client.get(f"/rooms/{room_id}")
    assert r.status_code == 200
    assert r.json()["id"] == room_id

    # Create booking via HTTP
    r = client.post("/bookings", json={
        "room_id": room_id,
        "guest_name": "Alice",
        "guest_email": "alice@example.com",
        "start_time": "2026-06-01T14:00:00",
        "end_time": "2026-06-02T11:00:00"
    })
    assert r.status_code == 201, r.text
    assert r.json()["guest_name"] == "Alice"
    assert r.json()["status"] == "confirmed"

    # Retrieve booking
    booking_id = r.json()["id"]
    r = client.get(f"/bookings/{booking_id}")
    assert r.status_code == 200
    assert r.json()["id"] == booking_id

def test_edge_booking_api_to_rooms_db_sql():
    """Edge: booking_api -> rooms_db via sql 'SQL' - bookings persist in DB."""
    client = TestClient(booking_app)
    # Create room
    r = client.post("/rooms", json={"name": "Room 101", "capacity": 1})
    assert r.status_code == 201
    room_id = r.json()["id"]

    # Create booking
    r = client.post("/bookings", json={
        "room_id": room_id,
        "guest_name": "Bob",
        "guest_email": "bob@example.com",
        "start_time": "2026-07-10T15:00:00",
        "end_time": "2026-07-11T11:00:00"
    })
    assert r.status_code == 201
    booking_id = r.json()["id"]

    # Verify persistence via listing bookings (reads from DB)
    r = client.get("/bookings")
    assert r.status_code == 200
    bookings = r.json()
    assert len(bookings) == 1
    assert bookings[0]["id"] == booking_id
    assert bookings[0]["room_id"] == room_id

    # Verify filtering by room_id
    r = client.get(f"/bookings?room_id={room_id}")
    assert r.status_code == 200
    assert len(r.json()) == 1

    # Verify direct DB access
    from common.db import SessionLocal
    from common.models import Booking as BookingModel
    db = SessionLocal()
    try:
        count = db.query(BookingModel).count()
        assert count == 1
        b = db.query(BookingModel).filter(BookingModel.id == booking_id).first()
        assert b is not None
        assert b.guest_name == "Bob"
    finally:
        db.close()

def test_edge_booking_api_to_notifier_event():
    """Edge: booking_api -> notifier via event 'booking.created' - creating booking publishes event and notifier receives it."""
    client = TestClient(booking_app)
    # Create room
    r = client.post("/rooms", json={"name": "Event Room", "capacity": 3})
    assert r.status_code == 201
    room_id = r.json()["id"]

    # Ensure no events yet
    assert len(bus.log) == 0
    assert len(received_events) == 0

    # Create booking - should publish booking.created
    r = client.post("/bookings", json={
        "room_id": room_id,
        "guest_name": "Carol",
        "guest_email": "carol@example.com",
        "start_time": "2026-08-01T14:00:00",
        "end_time": "2026-08-02T11:00:00"
    })
    assert r.status_code == 201
    booking_id = r.json()["id"]

    # Check bus log has booking.created event
    assert len(bus.log) == 1
    topic, payload = bus.log[0]
    assert topic == "booking.created"
    assert payload["booking_id"] == booking_id
    assert payload["room_id"] == room_id
    assert payload["guest_email"] == "carol@example.com"
    assert payload["guest_name"] == "Carol"

    # Check notifier handler received it
    assert len(received_events) == 1
    assert received_events[0]["booking_id"] == booking_id

    # Also verify notifier's HTTP endpoint reflects received events
    nclient = TestClient(notifier_app)
    r = nclient.get("/received-events")
    assert r.status_code == 200
    assert len(r.json()) == 1

def test_edge_notifier_to_email_smtp():
    """Edge: notifier -> email via smtp '' - notifier sends email on booking.created."""
    client = TestClient(booking_app)
    # Create room
    r = client.post("/rooms", json={"name": "Email Room", "capacity": 2})
    assert r.status_code == 201
    room_id = r.json()["id"]

    # Create booking - should trigger email
    r = client.post("/bookings", json={
        "room_id": room_id,
        "guest_name": "Dave",
        "guest_email": "dave@example.com",
        "start_time": "2026-09-01T14:00:00",
        "end_time": "2026-09-02T11:00:00"
    })
    assert r.status_code == 201

    # Check that email was "sent" via notifier's smtp edge
    assert len(sent_emails) == 1
    email = sent_emails[0]
    assert email["to"] == "dave@example.com"
    assert "Booking Confirmation" in email["subject"]
    assert "Dave" in email["body"]

    # Also test direct smtp endpoint
    nclient = TestClient(notifier_app)
    r = nclient.post("/send-test-email?to=test@example.com&subject=Hello&body=World")
    assert r.status_code == 200
    assert len(sent_emails) == 2
    assert sent_emails[1]["to"] == "test@example.com"

    # Verify sent-emails endpoint
    r = nclient.get("/sent-emails")
    assert r.status_code == 200
    assert len(r.json()) == 2
