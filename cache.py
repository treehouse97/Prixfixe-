import os
import sqlite3
import threading

_lock = threading.Lock()

# Absolute path to ensure persistent storage
DB_PATH = os.path.join(os.path.dirname(__file__), "prix_cache.db")

with _lock, sqlite3.connect(DB_PATH) as conn:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS cache (
            place_id TEXT PRIMARY KEY,
            text     TEXT NOT NULL
        )
    ''')

def get_cached_text(place_id: str) -> str | None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT text FROM cache WHERE place_id = ?",
            (place_id,)
        ).fetchone()
        return row[0] if row else None

def set_cached_text(place_id: str, text: str) -> None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cache (place_id, text) VALUES (?, ?)",
            (place_id, text)
        )