"""Initialize/migrate the database schema (explicit command, never startup).

Usage (from the project root):
    python -m backend.app.db.init_db
"""

from __future__ import annotations

from pathlib import Path

from .migrations import apply_pending
from .session import engine, get_settings


def main() -> None:
    url = get_settings().database_url
    if url.startswith("sqlite:///"):
        db_path = Path(url.replace("sqlite:///", "", 1))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"database file : {db_path}")
        if db_path.exists():
            print("existing database file detected - migrations will only ADD "
                  "missing objects (nothing is dropped)")
        else:
            print("no database file yet - one will be created on first use")
    else:
        print(f"database url  : {url}")

    applied = apply_pending(engine)
    if applied:
        print(f"applied migrations: {applied}")
    else:
        print("schema already up to date (no pending migrations)")
    print("done.")


if __name__ == "__main__":
    main()
