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
    return conn
