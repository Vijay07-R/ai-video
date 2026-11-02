"""Minimal versioned migrations (no extra dependency needed).

Add a new function to MIGRATIONS for every schema change; each runs once,
in order, and is recorded in the schema_version table.
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .db import Base


def _m001_initial(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def _m002_job_timing(engine: Engine) -> None:
    cols = {c["name"] for c in inspect(engine).get_columns("jobs")}
    with engine.begin() as conn:
        for col in ("started_at", "finished_at"):
            if col not in cols:
                conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {col} TIMESTAMP"))


MIGRATIONS = [(1, _m001_initial), (2, _m002_job_timing)]


def run_migrations(engine: Engine) -> int:
    from .models import SchemaVersion

    SchemaVersion.__table__.create(engine, checkfirst=True)
    with engine.begin() as conn:
        done = {r[0] for r in conn.execute(text("SELECT version FROM schema_version"))}
    for version, fn in MIGRATIONS:
        if version in done:
            continue
        fn(engine)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO schema_version (version, applied_at) VALUES (:v, CURRENT_TIMESTAMP)"), {"v": version})
    return max(v for v, _ in MIGRATIONS)


def current_tables(engine: Engine) -> list[str]:
    return sorted(inspect(engine).get_table_names())
