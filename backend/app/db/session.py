"""Database connection, migrations and graceful degradation.

On startup FleetMind connects to ``FLEETMIND_DATABASE_URL`` (PostgreSQL) and applies Alembic
migrations. If PostgreSQL is unreachable it falls back to ``FLEETMIND_DATABASE_FALLBACK_URL``
(SQLite by default) and reports that clearly in ``/api/health``; if that is disabled too,
the simulator still runs and persistence is switched off.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

log = logging.getLogger("fleetmind.db")
BACKEND_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Database:
    url: str
    engine: Engine
    session_factory: sessionmaker[Session]
    is_fallback: bool = False

    @property
    def dialect(self) -> str:
        return self.engine.dialect.name

    def describe(self) -> dict:
        return {"connected": True, "dialect": self.dialect, "fallback": self.is_fallback,
                "url": self.engine.url.render_as_string(hide_password=True)}


def run_migrations(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(cfg, "head")


def _connect(url: str, is_fallback: bool) -> Database:
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if url.startswith("postgresql"):
        kwargs["connect_args"] = {"connect_timeout": 3}
    elif url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    run_migrations(url)
    return Database(url, engine, sessionmaker(engine, expire_on_commit=False), is_fallback)


def connect_database(primary_url: str, fallback_url: str | None) -> Database | None:
    try:
        db = _connect(primary_url, False)
        log.info("database connected: %s", db.engine.url.render_as_string(hide_password=True))
        return db
    except Exception as exc:  # noqa: BLE001 - any driver/network error means "unavailable"
        log.warning("primary database unavailable (%s): %s", primary_url.split("@")[-1], exc.__class__.__name__)
    if fallback_url:
        try:
            db = _connect(fallback_url, True)
            log.warning("using FALLBACK database %s — start PostgreSQL for the full setup", fallback_url)
            return db
        except Exception as exc:  # noqa: BLE001
            log.error("fallback database unavailable: %s", exc)
    log.error("running WITHOUT persistence")
    return None
