from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

DEFAULT_DB = Path("data/trgtmrkt.db")


def connect(path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(resources.files("trgtmrkt").joinpath("schema.sql").read_text())
    _add_missing_columns(conn)
    return conn


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    """Older local databases predate some columns; CREATE IF NOT EXISTS will not add them."""
    want = {"deals": {"sale_type": "TEXT", "vehicle_source": "TEXT", "purchase_date": "TEXT",
                      "original_cost": "REAL", "added_costs": "REAL",
                      "write_off_date": "TEXT", "last_payment_date": "TEXT"}}
    for table, cols in want.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, typ in cols.items():
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
    conn.commit()
