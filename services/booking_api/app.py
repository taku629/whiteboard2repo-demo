"""Booking API (service): Handles booking requests and persists bookings

Implements board edges:
  -> rooms_db via sql 'SQL' (tables: rooms, bookings)
  -> notifier via event 'booking.created'
  <- web_app via http '' (exposes REST API for frontend)

Responsibility: Handles booking requests and persists bookings
"""
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from common.bus import bus
from common.db import init_db, SessionLocal
# Import models to ensure tables are registered
import common.models  # noqa: F401
from common.models import Room, Booking

app = FastAPI(title="Booking API")
init_db()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Schemas ---
class RoomCreate(BaseModel):
    name: str
    capacity: int = 1
    description: Optional[str] = None

class RoomOut(BaseModel):
    id: int
    name: str
    capacity: int
    description: Optional[str] = None
    class Config:
        from_attributes = True

class BookingCreate(BaseModel):
    room_id: int
    guest_name: str
    guest_email: str
    start_time: datetime
    end_time: datetime

    @field_validator('end_time')
    @classmethod
    def end_after_start(cls, v, info):
        start = info.data.get('start_time')
        if start and v <= start:
            raise ValueError('end_time must be after start_time')
        return v

class BookingOut(BaseModel):
    id: int
    room_id: int
    guest_name: str
    guest_email: str
    start_time: datetime
    end_time: datetime
    status: str
    class Config:
        from_attributes = True

# --- Helpers ---
def check_overlap(db: Session, room_id: int, start: datetime, end: datetime, exclude_id: Optional[int] = None) -> bool:
    q = db.query(Booking).filter(
        Booking.room_id == room_id,
        Booking.status == "confirmed",
        Booking.start_time < end,
        Booking.end_time > start,
    )
    if exclude_id:
        q = q.filter(Booking.id != exclude_id)
    return db.query(q.exists()).scalar()

# --- Endpoints ---

@app.get("/health")
def health() -> dict:
    return {"service": "booking_api", "status": "ok"}

@app.post("/rooms", response_model=RoomOut, status_code=201)
def create_room(payload: RoomCreate, db: Session = Depends(get_db)):
    existing = db.query(Room).filter(Room.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Room with this name already exists")
    room = Room(name=payload.name, capacity=payload.capacity, description=payload.description)
    db.add(room)
    db.commit()
    db.refresh(room)
    return room

@app.get("/rooms", response_model=List[RoomOut])
def list_rooms(db: Session = Depends(get_db)):
    return db.query(Room).all()

@app.get("/rooms/{room_id}", response_model=RoomOut)
def get_room(room_id: int, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room

@app.post("/bookings", response_model=BookingOut, status_code=201)
def create_booking(payload: BookingCreate, db: Session = Depends(get_db)):
    # Validate room exists
    room = db.query(Room).filter(Room.id == payload.room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    # Invariant: no double booking - reject overlapping confirmed bookings for same room
    if check_overlap(db, payload.room_id, payload.start_time, payload.end_time):
        raise HTTPException(status_code=409, detail="Room already booked for this time range (no double booking)")

    booking = Booking(
        room_id=payload.room_id,
        guest_name=payload.guest_name,
        guest_email=payload.guest_email,
        start_time=payload.start_time,
        end_time=payload.end_time,
        status="confirmed",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # Publish event for notifier
    bus.publish("booking.created", {
        "booking_id": booking.id,
        "room_id": booking.room_id,
        "guest_name": booking.guest_name,
        "guest_email": booking.guest_email,
        "start_time": booking.start_time.isoformat(),
        "end_time": booking.end_time.isoformat(),
        "status": booking.status,
    })

    return booking

@app.get("/bookings", response_model=List[BookingOut])
def list_bookings(room_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Booking)
    if room_id is not None:
        q = q.filter(Booking.room_id == room_id)
    return q.all()

@app.get("/bookings/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: int, db: Session = Depends(get_db)):
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Booking not found")
    return b

@app.delete("/bookings/{booking_id}")
def cancel_booking(booking_id: int, db: Session = Depends(get_db)):
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Booking not found")
    b.status = "cancelled"
    db.commit()
    return {"status": "cancelled", "id": booking_id}
