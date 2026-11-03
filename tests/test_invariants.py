"""Invariant tests for board notes.

Invariant: The system must reject any booking that overlaps in time with an existing
confirmed booking for the same room. (no double booking!)
"""
import pytest
from fastapi.testclient import TestClient

from common.db import reset_db
from common.bus import bus
from services.booking_api.app import app as booking_app
from services.notifier.app import sent_emails, received_events

@pytest.fixture(autouse=True)
def isolate():
    reset_db()
    bus.log.clear()
    sent_emails.clear()
    received_events.clear()
    yield

def _create_room(client, name="Test Room", capacity=2):
    r = client.post("/rooms", json={"name": name, "capacity": capacity})
    assert r.status_code == 201, r.text
    return r.json()["id"]

def _book(client, room_id, start, end, guest_name="Guest", guest_email="guest@example.com"):
    return client.post("/bookings", json={
        "room_id": room_id,
        "guest_name": guest_name,
        "guest_email": guest_email,
        "start_time": start,
        "end_time": end,
    })

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
