"""
backend/db/init_db.py
Run this script once (or on reset) to create all tables.
Usage:  python backend/db/init_db.py
"""
import sqlite3
import os
from pathlib import Path

# Resolve paths relative to this file so it works from any cwd
HERE = Path(__file__).parent
SCHEMA = HERE / "schema.sql"
DB_PATH = HERE.parent.parent / "disruptioniq.db"


def init_db(db_path: Path = DB_PATH, schema_path: Path = SCHEMA) -> None:
    sql = schema_path.read_text(encoding="utf-8")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(sql)
        conn.commit()
        print(f"[init_db] Database initialised at: {db_path.resolve()}")

        # List tables
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        )
        tables = [row[0] for row in cur.fetchall()]
        print(f"[init_db] Tables ({len(tables)}):")
        for t in tables:
            print(f"          • {t}")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
