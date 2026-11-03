"""Shared SQLAlchemy models for Rooms DB."""
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.db import Base

class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="room", cascade="all, delete-orphan")

class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    guest_name: Mapped[str] = mapped_column(String(100), nullable=False)
    guest_email: Mapped[str] = mapped_column(String(200), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="confirmed")

    room: Mapped[Room] = relationship(back_populates="bookings")
