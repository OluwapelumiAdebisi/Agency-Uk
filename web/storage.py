"""Lead storage — job-seeker applications sent to agencies.

Uses DATABASE_URL (a hosted Postgres, e.g. Supabase or Neon) in production, and a
local SQLite file in development. On Render's free tier the local disk is wiped on
every deploy, so production MUST set DATABASE_URL or leads will be lost.
"""
import os
from datetime import datetime, timezone

from sqlalchemy import (Column, DateTime, Integer, MetaData, String, Table,
                        create_engine, insert, select)

_metadata = MetaData()
applications = Table(
    "applications", _metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(200), nullable=False),
    Column("phone", String(50), nullable=False),
    Column("email", String(200), nullable=False),
    Column("company_number", String(20)),
    Column("agency_name", String(300)),
    Column("sector", String(80)),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

_engine = None


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "sqlite:///applications.db")
    if url.startswith("postgres://"):          # Render/Heroku style -> SQLAlchemy style
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(_database_url(), pool_pre_ping=True)
        _metadata.create_all(_engine)
    return _engine


def using_persistent_db() -> bool:
    """False means we're on the ephemeral local SQLite fallback (dev / misconfigured)."""
    return bool(os.environ.get("DATABASE_URL"))


def add_application(data: dict) -> None:
    row = {
        "name": data["name"].strip(),
        "phone": data["phone"].strip(),
        "email": data["email"].strip(),
        "company_number": (data.get("company_number") or "").strip() or None,
        "agency_name": (data.get("agency_name") or "").strip() or None,
        "sector": (data.get("sector") or "").strip() or None,
        "created_at": datetime.now(timezone.utc),
    }
    with engine().begin() as c:
        c.execute(insert(applications), row)


def list_applications(limit: int = 500):
    with engine().begin() as c:
        rows = c.execute(
            select(applications).order_by(applications.c.created_at.desc()).limit(limit)
        ).mappings().all()
    return [dict(r) for r in rows]
