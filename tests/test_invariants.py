"""Invariant tests for board notes.

Invariant 1: The system must reject any booking that overlaps in time with an existing
confirmed booking for the same room. (no double booking!)

Invariant 2: The system must reject a new booking if the user already has 3 active bookings
(max 3 active bookings per user!)
"""
import pytest
from fastapi.testclient import TestClient

from common.db import reset_db
from common.bus import bus
from services.booking_api.app import app as booking_app
from services.notifier.app import sent_emails, received_events
from services.payments_api.app import charges as payment_charges

@pytest.fixture(autouse=True)
def isolate():
    reset_db()
    bus.log.clear()
    sent_emails.clear()
    received_events.clear()
    payment_charges.clear()
    from services.payments_api import app as papp
    papp._charge_counter = 0
    yield

def _create_room(client, name="Test Room", capacity=2):
    r = client.post("/rooms", json={"name": name, "capacity": capacity})
    assert r.status_code == 201, r.text
    return r.json()["id"]

def _book(client, room_id, start, end, guest_name="Guest", guest_email="guest@example.com", amount=None):
    payload = {
        "room_id": room_id,
        "guest_name": guest_name,
        "guest_email": guest_email,
        "start_time": start,
        "end_time": end,
    }
    if amount is not None:
        payload["amount"] = amount
    return client.post("/bookings", json=payload)

# ---- Invariant: no double booking ----

def test_no_double_booking_exact_overlap_rejected():
    """Exact same time range for same room must be rejected."""
    client = TestClient(booking_app)
    room_id = _create_room(client)

    r1 = _book(client, room_id, "2026-06-01T14:00:00", "2026-06-02T11:00:00", guest_name="Alice")
    assert r1.status_code == 201

    r2 = _book(client, room_id, "2026-06-01T14:00:00", "2026-06-02T11:00:00", guest_name="Bob")
    assert r2.status_code == 409
    assert "already booked" in r2.json()["detail"].lower() or "double booking" in r2.json()["detail"].lower()

def test_no_double_booking_partial_overlap_rejected():
    """Partial overlap must be rejected (new booking starts during existing)."""
    client = TestClient(booking_app)
    room_id = _create_room(client)

    r1 = _book(client, room_id, "2026-06-01T14:00:00", "2026-06-05T11:00:00")
    assert r1.status_code == 201

    # Overlaps: starts before existing ends
    r2 = _book(client, room_id, "2026-06-03T14:00:00", "2026-06-07T11:00:00")
    assert r2.status_code == 409

def test_no_double_booking_contained_overlap_rejected():
    """New booking fully contained within existing must be rejected."""
    client = TestClient(booking_app)
    room_id = _create_room(client)

    r1 = _book(client, room_id, "2026-06-01T14:00:00", "2026-06-10T11:00:00")
    assert r1.status_code == 201

    r2 = _book(client, room_id, "2026-06-03T14:00:00", "2026-06-04T11:00:00")
    assert r2.status_code == 409

def test_no_double_booking_enveloping_overlap_rejected():
    """New booking that envelops existing must be rejected."""
    client = TestClient(booking_app)
    room_id = _create_room(client)

    r1 = _book(client, room_id, "2026-06-03T14:00:00", "2026-06-04T11:00:00")
    assert r1.status_code == 201

    r2 = _book(client, room_id, "2026-06-01T14:00:00", "2026-06-10T11:00:00")
    assert r2.status_code == 409

def test_no_double_booking_different_rooms_allowed():
    """Same time range for different rooms must be allowed."""
    client = TestClient(booking_app)
    room_a = _create_room(client, name="Room A")
    room_b = _create_room(client, name="Room B")

    r1 = _book(client, room_a, "2026-06-01T14:00:00", "2026-06-02T11:00:00")
    assert r1.status_code == 201

    r2 = _book(client, room_b, "2026-06-01T14:00:00", "2026-06-02T11:00:00")
    assert r2.status_code == 201

def test_no_double_booking_adjacent_allowed():
    """Adjacent bookings (end == start) must be allowed - no overlap."""
    client = TestClient(booking_app)
    room_id = _create_room(client)

    r1 = _book(client, room_id, "2026-06-01T14:00:00", "2026-06-02T11:00:00")
    assert r1.status_code == 201

    # Starts exactly when previous ends - should be allowed
    r2 = _book(client, room_id, "2026-06-02T11:00:00", "2026-06-03T11:00:00")
    assert r2.status_code == 201

def test_no_double_booking_non_overlapping_allowed():
    """Non-overlapping bookings for same room must be allowed."""
    client = TestClient(booking_app)
    room_id = _create_room(client)

    r1 = _book(client, room_id, "2026-06-01T14:00:00", "2026-06-02T11:00:00")
    assert r1.status_code == 201

    r2 = _book(client, room_id, "2026-06-05T14:00:00", "2026-06-06T11:00:00")
    assert r2.status_code == 201

def test_no_double_booking_cancelled_does_not_block():
    """Cancelled bookings should not block new bookings for same time."""
    client = TestClient(booking_app)
    room_id = _create_room(client)

    r1 = _book(client, room_id, "2026-06-01T14:00:00", "2026-06-02T11:00:00")
    assert r1.status_code == 201
    booking_id = r1.json()["id"]

    # Cancel first booking
    r = client.delete(f"/bookings/{booking_id}")
    assert r.status_code == 200

    # Now same time should be bookable
    r2 = _book(client, room_id, "2026-06-01T14:00:00", "2026-06-02T11:00:00", guest_name="Bob", guest_email="bob@example.com")
    assert r2.status_code == 201

def test_no_double_booking_rejected_does_not_publish_event():
    """Rejected double booking must not publish booking.created event."""
    client = TestClient(booking_app)
    room_id = _create_room(client)

    r1 = _book(client, room_id, "2026-06-01T14:00:00", "2026-06-02T11:00:00")
    assert r1.status_code == 201
    assert len(bus.log) == 1
    assert len(sent_emails) == 1

    r2 = _book(client, room_id, "2026-06-01T14:00:00", "2026-06-02T11:00:00")
    assert r2.status_code == 409
    # No additional event or email
    assert len(bus.log) == 1
    assert len(sent_emails) == 1
    assert len(received_events) == 1

# ---- Invariant: max 3 active bookings per user ----

def test_max_3_active_bookings_per_user_rejects_fourth():
    """User with 3 active bookings must be rejected on 4th attempt."""
    client = TestClient(booking_app)
    room_ids = [_create_room(client, name=f"Room {i}") for i in range(4)]

    # Create 3 bookings for same user - all should succeed
    for i in range(3):
        r = _book(client, room_ids[i],
                  f"2026-06-0{1+i*2}T14:00:00", f"2026-06-0{2+i*2}T11:00:00",
                  guest_name="Alice", guest_email="alice@example.com")
        assert r.status_code == 201, f"Booking {i+1} should succeed: {r.text}"

    # 4th booking must be rejected
    r = _book(client, room_ids[3], "2026-06-10T14:00:00", "2026-06-11T11:00:00",
              guest_name="Alice", guest_email="alice@example.com")
    assert r.status_code == 409
    assert "3 active" in r.json()["detail"].lower() or "max" in r.json()["detail"].lower()

def test_max_3_active_bookings_per_user_allows_up_to_3():
    """User with fewer than 3 active bookings can still book."""
    client = TestClient(booking_app)
    room_ids = [_create_room(client, name=f"Room {i}") for i in range(3)]

    for i in range(3):
        r = _book(client, room_ids[i],
                  f"2026-07-0{1+i*2}T14:00:00", f"2026-07-0{2+i*2}T11:00:00",
                  guest_name="Bob", guest_email="bob@example.com")
        assert r.status_code == 201, r.text

    # Verify 3 bookings exist
    r = client.get("/bookings")
    assert len([b for b in r.json() if b["guest_email"] == "bob@example.com"]) == 3

def test_max_3_active_bookings_per_user_different_users_independent():
    """Different users each have their own limit of 3."""
    client = TestClient(booking_app)
    room_ids = [_create_room(client, name=f"Room {i}") for i in range(6)]

    # Alice books 3
    for i in range(3):
        r = _book(client, room_ids[i],
                  f"2026-06-0{1+i*2}T14:00:00", f"2026-06-0{2+i*2}T11:00:00",
                  guest_name="Alice", guest_email="alice@example.com")
        assert r.status_code == 201

    # Bob should still be able to book 3
    for i in range(3, 6):
        r = _book(client, room_ids[i],
                  f"2026-06-0{1+(i-3)*2}T14:00:00", f"2026-06-0{2+(i-3)*2}T11:00:00",
                  guest_name="Bob", guest_email="bob@example.com")
        assert r.status_code == 201, r.text

def test_max_3_active_bookings_cancelled_frees_slot():
    """Cancelling a booking frees up a slot for the user."""
    client = TestClient(booking_app)
    room_ids = [_create_room(client, name=f"Room {i}") for i in range(4)]

    booking_ids = []
    for i in range(3):
        r = _book(client, room_ids[i],
                  f"2026-08-0{1+i*2}T14:00:00", f"2026-08-0{2+i*2}T11:00:00",
                  guest_name="Carol", guest_email="carol@example.com")
        assert r.status_code == 201
        booking_ids.append(r.json()["id"])

    # 4th should fail
    r = _book(client, room_ids[3], "2026-08-10T14:00:00", "2026-08-11T11:00:00",
              guest_name="Carol", guest_email="carol@example.com")
    assert r.status_code == 409

    # Cancel one
    r = client.delete(f"/bookings/{booking_ids[0]}")
    assert r.status_code == 200

    # Now 4th should succeed
    r = _book(client, room_ids[3], "2026-08-10T14:00:00", "2026-08-11T11:00:00",
              guest_name="Carol", guest_email="carol@example.com")
    assert r.status_code == 201, r.text

def test_max_3_active_bookings_rejected_does_not_publish_event_or_charge():
    """Rejected booking due to max limit must not publish event or charge payment."""
    client = TestClient(booking_app)
    room_ids = [_create_room(client, name=f"Room {i}") for i in range(4)]

    for i in range(3):
        r = _book(client, room_ids[i],
                  f"2026-09-0{1+i*2}T14:00:00", f"2026-09-0{2+i*2}T11:00:00",
                  guest_name="Dave", guest_email="dave@example.com")
        assert r.status_code == 201

    assert len(bus.log) == 3
    assert len(payment_charges) == 3

    r = _book(client, room_ids[3], "2026-09-10T14:00:00", "2026-09-11T11:00:00",
              guest_name="Dave", guest_email="dave@example.com")
    assert r.status_code == 409

    # No additional event or payment charge
    assert len(bus.log) == 3
    assert len(payment_charges) == 3
    assert len(sent_emails) == 3

def test_max_3_active_bookings_rejected_does_not_create_db_record():
    """Rejected booking must not create a DB record."""
    client = TestClient(booking_app)
    room_ids = [_create_room(client, name=f"Room {i}") for i in range(4)]

    for i in range(3):
        r = _book(client, room_ids[i],
                  f"2026-10-0{1+i*2}T14:00:00", f"2026-10-0{2+i*2}T11:00:00",
                  guest_name="Eve", guest_email="eve@example.com")
        assert r.status_code == 201

    r = _book(client, room_ids[3], "2026-10-10T14:00:00", "2026-10-11T11:00:00",
              guest_name="Eve", guest_email="eve@example.com")
    assert r.status_code == 409

    # Only 3 bookings in DB for Eve
    from common.db import SessionLocal
    from common.models import Booking as BookingModel
    db = SessionLocal()
    try:
        count = db.query(BookingModel).filter(BookingModel.guest_email == "eve@example.com").count()
        assert count == 3
        active = db.query(BookingModel).filter(
            BookingModel.guest_email == "eve@example.com",
            BookingModel.status == "confirmed"
        ).count()
        assert active == 3
    finally:
        db.close()
