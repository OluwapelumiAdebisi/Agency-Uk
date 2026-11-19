"""Signup storage — job seekers registering with Agency UK (growth tracking).

Not for forwarding to agencies. Uses DATABASE_URL (a hosted Postgres like Neon)
in production and a local SQLite file in development. On Render's free tier the
local disk is wiped on every deploy, so production MUST set DATABASE_URL.
"""
import os
from datetime import datetime, timezone

from sqlalchemy import (Column, DateTime, Integer, MetaData, String, Table,
                        create_engine, func, insert, select)

_metadata = MetaData()
signups = Table(
    "signups", _metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(200), nullable=False),
    Column("email", String(200), nullable=False),
    Column("phone", String(50)),                   # optional
    Column("sector", String(80)),                  # what work they want
    Column("city", String(120)),                   # where
    Column("created_at", DateTime(timezone=True), nullable=False),
)

_engine = None


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "sqlite:///signups.db")
    if url.startswith("postgres://"):             # Render/Heroku style -> SQLAlchemy
        url = url.replace("postgres://", "postgresql://", 1)
    # Pin SQLAlchemy to psycopg2 so it does not try to import psycopg (v3) first,
    # which is not installed. We ship psycopg2-binary.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    # Neon's connection strings sometimes include &channel_binding=require which the
    # psycopg2 driver rejects as an unrecognised parameter - strip it so it just works.
    return url.replace("&channel_binding=require", "").replace("channel_binding=require&", "").replace("?channel_binding=require", "?")


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(_database_url(), pool_pre_ping=True)
        _metadata.create_all(_engine)
    return _engine


def using_persistent_db() -> bool:
    """False means we're on the ephemeral local SQLite fallback (dev / misconfigured)."""
    return bool(os.environ.get("DATABASE_URL"))


def add_signup(data: dict) -> None:
    row = {
        "name": data["name"].strip(),
        "email": data["email"].strip(),
        "phone": (data.get("phone") or "").strip() or None,
        "sector": (data.get("sector") or "").strip() or None,
        "city": (data.get("city") or "").strip() or None,
        "created_at": datetime.now(timezone.utc),
    }
    with engine().begin() as c:
        c.execute(insert(signups), row)


def list_signups(limit: int = 1000):
    with engine().begin() as c:
        rows = c.execute(
            select(signups).order_by(signups.c.created_at.desc()).limit(limit)
        ).mappings().all()
    return [dict(r) for r in rows]


def stats() -> dict:
    with engine().begin() as c:
        total = c.execute(select(func.count()).select_from(signups)).scalar() or 0
        by_sector = c.execute(
            select(signups.c.sector, func.count().label("n"))
            .where(signups.c.sector.is_not(None))
            .group_by(signups.c.sector).order_by(func.count().desc())
        ).all()
        by_city = c.execute(
            select(signups.c.city, func.count().label("n"))
            .where(signups.c.city.is_not(None))
            .group_by(signups.c.city).order_by(func.count().desc())
        ).all()
    return {"total": total,
            "by_sector": [(s, n) for s, n in by_sector],
            "by_city": [(c, n) for c, n in by_city]}
