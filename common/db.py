"""Database access shared by services (SQLAlchemy 2.x).

DATABASE_URL defaults to a local SQLite file; docker-compose points it at Postgres.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite://")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
else:  # pragma: no cover
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    Base.metadata.create_all(engine)


def reset_db() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
