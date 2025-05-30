# cache.py

import sqlite3
import threading

# Initialize a thread lock to ensure thread-safe database access
_lock = threading.Lock()

# SQLite database file
DB_PATH = "prix_cache.db"

# Ensure table exists
with _lock, sqlite3.connect(DB_PATH) as conn:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS cache (
            place_id TEXT PRIMARY KEY,
            text     TEXT NOT NULL
        )
    ''')

def get_cached_text(place_id: str) -> str | None:
    """Return cached result if exists, else None."""
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT text FROM cache WHERE place_id = ?",
            (place_id,)
        ).fetchone()
        return row[0] if row else None

def set_cached_text(place_id: str, text: str) -> None:
    """Cache result for future lookups."""
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cache (place_id, text) VALUES (?, ?)",
            (place_id, text)
        )