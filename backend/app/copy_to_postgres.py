"""One-off copy of the SQLite database into the empty PostgreSQL database named by DATABASE_URL.

Run:  python -m app.copy_to_postgres [path/to/sqlite.db]       (from the backend folder)
The SQLite file is only read. The copy runs in one transaction and refuses a target that already holds data.
"""
import sys
from pathlib import Path

from sqlalchemy import create_engine, func, insert, select, text

from . import models  # noqa: F401  (registers the tables)
from .config import BACKEND_DIR, DATABASE_URL
from .db import Base, engine


def main() -> None:
    if not DATABASE_URL.startswith("postgresql"):
        sys.exit("Set DATABASE_URL to the PostgreSQL database first.")
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND_DIR / "householdai.db"
    if not path.is_file():
        sys.exit(f"SQLite file not found: {path}")
    source = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    tables = Base.metadata.sorted_tables
    with source.connect() as src, engine.begin() as dst:
        for t in tables:
            if dst.scalar(select(func.count()).select_from(t)):
                sys.exit(f"Nothing copied: table {t.name} in the target already has rows.")
        for t in tables:
            rows = [dict(r._mapping) for r in src.execute(select(t))]
            if rows:
                dst.execute(insert(t), rows)
                if "id" in t.c:   # keep new rows from reusing copied ids
                    dst.execute(text("SELECT setval(pg_get_serial_sequence(:t, 'id'), :n)"),
                                {"t": t.name, "n": max(r["id"] for r in rows)})
            copied = dst.scalar(select(func.count()).select_from(t))
            if copied != len(rows):
                raise RuntimeError(f"{t.name}: read {len(rows)} rows but the target has {copied}.")
            print(f"{t.name}: {copied}")


if __name__ == "__main__":
    main()
