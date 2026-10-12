"""Versioned, non-destructive schema migrations (Alembic is not configured).

`schema_version` (base.SchemaVersion) records every applied version.
`apply_pending(engine)` creates only what is missing (SQLAlchemy create_all
never drops/alters), runs pending migrations in order inside one transaction
each, and is safe to run repeatedly.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from .base import Base, SchemaVersion

# Ordered migrations. Append-only: never edit an applied migration.
MIGRATIONS: list[tuple[str, str]] = [
    ("0001_initial",
     "create projects, risk_results, early_warnings, import_snapshots, "
     "schema_version tables with unique constraints and indexes"),
]


def _migration_0001(engine: Engine) -> None:
    # Imports the models so they register on Base.metadata, then creates
    # every missing table (idempotent; never drops anything).
    from . import models  # noqa: F401  (registration side-effect)
    Base.metadata.create_all(engine)


MIGRATION_FUNCTIONS = {"0001_initial": _migration_0001}


def apply_pending(engine: Engine) -> list[str]:
    """Apply pending migrations; returns the versions applied now."""
    from . import models  # noqa: F401
    SchemaVersion.__table__.create(bind=engine, checkfirst=True)
    applied: list[str] = []
    with Session(engine) as session:
        done = {row.version for row in
                session.execute(select(SchemaVersion)).scalars()}
    for version, _description in MIGRATIONS:
        if version in done:
            continue
        MIGRATION_FUNCTIONS[version](engine)
        with Session(engine) as session:
            session.add(SchemaVersion(
                version=version,
                applied_at=datetime.now(timezone.utc).replace(tzinfo=None)))
            session.commit()
        applied.append(version)
    return applied
