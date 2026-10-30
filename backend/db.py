"""
backend/db.py
Provides:
  - get_conn()      : SQLite connection with FK enforcement and Row factory
  - transaction()   : context manager that commits on success, rolls back on error
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

# DB file lives at the project root (one level above backend/)
_DB_PATH = Path(__file__).parent.parent / "disruptioniq.db"


def get_conn(db_path: Path = _DB_PATH) -> sqlite3.Connection:
    """
    Return a new SQLite connection with:
      - foreign_keys ON  (rule 8 / schema integrity)
      - Row factory      (access columns by name: row["column"])
    Caller is responsible for closing the connection.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def transaction(db_path: Path = _DB_PATH):
    """
    Context manager for a single database transaction.

    Usage:
        with transaction() as conn:
            conn.execute("INSERT INTO ...", (...,))
            # commits automatically on exit
            # rolls back automatically on any exception

    For the what-if simulator (rule 14), wrap in transaction() and raise an
    exception (or call conn.rollback() explicitly) before exiting to discard
    all changes without committing.
    """
    conn = get_conn(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
