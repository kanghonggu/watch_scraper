import sqlite3
from typing import List, Dict

DB_NAME = "watches.db"


def init_db() -> None:
    """Initialize the SQLite database."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS watches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def insert_watches(watches: List[Dict[str, str]]) -> int:
    """Insert a list of watches into the database.

    Args:
        watches: List of dictionaries with ``name`` and ``price``.

    Returns:
        Number of inserted rows.
    """
    if not watches:
        return 0
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO watches (name, price) VALUES (?, ?)",
        [(w["name"], w["price"]) for w in watches],
    )
    conn.commit()
    rowcount = cur.rowcount
    conn.close()
    return rowcount


def get_watches() -> List[Dict[str, str]]:
    """Retrieve all stored watches."""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT name, price FROM watches")
    rows = cur.fetchall()
    conn.close()
    return [{"name": name, "price": price} for name, price in rows]
