"""A few national macro series from FRED. Free key: fred.stlouisfed.org/docs/api
-> FRED_API_KEY. Series ids below are worth confirming on first run."""
from __future__ import annotations

import json
import os
import sqlite3
import urllib.parse

from .http import Fetch, cached_get

SERIES = {
    "GASREGW": "US regular gasoline, weekly",
    "CUSR0000SETA02": "CPI: used cars and trucks",
    "UNRATE": "US unemployment rate",
}


def parse(payload: bytes, series: str) -> list[tuple[str, str, float]]:
    out = []
    for o in json.loads(payload).get("observations", []):
        try:
            out.append((series, o["date"], float(o["value"])))
        except ValueError:  # FRED uses "." for missing
            continue
    return out


def refresh(conn: sqlite3.Connection, series: dict[str, str] | None = None,
            key: str | None = None, fetch: Fetch | None = None, start: str = "2022-01-01",
            **cache_kw) -> int:
    key = key or os.environ.get("FRED_API_KEY")
    if not key:
        raise RuntimeError("FRED_API_KEY is not set (free: fred.stlouisfed.org/docs/api)")
    kw = {"fetch": fetch} if fetch else {}
    total = 0
    for sid in series or SERIES:
        q = urllib.parse.urlencode({"series_id": sid, "api_key": key, "file_type": "json",
                                    "observation_start": start})
        rows = parse(cached_get(f"https://api.stlouisfed.org/fred/series/observations?{q}",
                                max_age_days=3, validate=lambda b: parse(b, sid),
                                **kw, **cache_kw), sid)
        conn.executemany(
            "INSERT OR REPLACE INTO macro_series (series, date, value) VALUES (?,?,?)", rows)
        total += len(rows)
    conn.commit()
    return total
