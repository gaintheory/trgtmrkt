"""A few national macro series from FRED. Free key: fred.stlouisfed.org/docs/api
-> FRED_API_KEY. Series ids below are worth confirming on first run.

FRED API Terms of Use obligations handled here:
  * Third-party copyright: a series whose notes contain the word "Copyright" is
    owned by someone else and needs their permission. refresh() reads each
    series' notes first and refuses to store a flagged series.
  * Required notice: FRED_NOTICE must appear wherever FRED data is shown. The
    report adds it automatically when macro data is present.
"""
from __future__ import annotations

import json
import os
import sqlite3
import urllib.parse
from dataclasses import dataclass, field

import pandas as pd

from .http import Fetch, cached_get

FRED_NOTICE = ("This product uses the FRED® API but is not endorsed or certified by the "
               "Federal Reserve Bank of St. Louis.")
TERMS_URL = "https://fred.stlouisfed.org/docs/api/terms_of_use.html"

SERIES = {
    "GASREGW": "US regular gasoline, weekly",
    "CUSR0000SETA02": "CPI: used cars and trucks",
    "UNRATE": "US unemployment rate",
}
# Original data owners, for the citation line. Confirm against each series page.
SOURCES = {
    "GASREGW": "U.S. Energy Information Administration",
    "CUSR0000SETA02": "U.S. Bureau of Labor Statistics",
    "UNRATE": "U.S. Bureau of Labor Statistics",
}


@dataclass
class RefreshResult:
    rows: int = 0
    copyrighted: list[str] = field(default_factory=list)  # flagged, not stored


def parse(payload: bytes, series: str) -> list[tuple[str, str, float]]:
    out = []
    for o in json.loads(payload).get("observations", []):
        try:
            out.append((series, o["date"], float(o["value"])))
        except ValueError:  # FRED uses "." for missing
            continue
    return out


def parse_meta(payload: bytes) -> dict:
    """Title and whether the notes claim copyright. Raises if the response is
    not a series record, so an error body is never cached as a pass."""
    rec = json.loads(payload)["seriess"][0]
    notes = rec.get("notes") or ""
    return {"title": rec.get("title"), "copyrighted": "copyright" in notes.lower()}


def refresh(conn: sqlite3.Connection, series: dict[str, str] | None = None,
            key: str | None = None, fetch: Fetch | None = None, start: str = "2022-01-01",
            **cache_kw) -> RefreshResult:
    key = key or os.environ.get("FRED_API_KEY")
    if not key:
        raise RuntimeError("FRED_API_KEY is not set (free: fred.stlouisfed.org/docs/api)")
    kw = {"fetch": fetch} if fetch else {}
    result = RefreshResult()
    for sid in series or SERIES:
        # Copyright check first. If it cannot be made, this raises and nothing
        # is stored: fail closed.
        meta_q = urllib.parse.urlencode({"series_id": sid, "api_key": key, "file_type": "json"})
        meta = parse_meta(cached_get(f"https://api.stlouisfed.org/fred/series?{meta_q}",
                                     max_age_days=7, validate=parse_meta, **kw, **cache_kw))
        conn.execute("INSERT OR REPLACE INTO macro_series_meta (series, title, copyrighted, "
                     "checked_at) VALUES (?,?,?,datetime('now'))",
                     (sid, meta["title"], int(meta["copyrighted"])))
        if meta["copyrighted"]:
            conn.execute("DELETE FROM macro_series WHERE series = ?", (sid,))
            result.copyrighted.append(sid)
            continue
        q = urllib.parse.urlencode({"series_id": sid, "api_key": key, "file_type": "json",
                                    "observation_start": start})
        rows = parse(cached_get(f"https://api.stlouisfed.org/fred/series/observations?{q}",
                                max_age_days=3, validate=lambda b: parse(b, sid),
                                **kw, **cache_kw), sid)
        conn.executemany(
            "INSERT OR REPLACE INTO macro_series (series, date, value) VALUES (?,?,?)", rows)
        result.rows += len(rows)
    conn.commit()
    return result


def latest(conn: sqlite3.Connection) -> pd.DataFrame:
    """Most recent observation per stored series, with citation fields."""
    df = pd.read_sql_query(
        "SELECT m.series, COALESCE(x.title, m.series) AS title, m.date, m.value "
        "FROM macro_series m LEFT JOIN macro_series_meta x ON x.series = m.series "
        "WHERE m.date = (SELECT MAX(date) FROM macro_series WHERE series = m.series) "
        "ORDER BY m.series", conn)
    df["source"] = df["series"].map(SOURCES).fillna("source per series page")
    return df


def citation(series: str, title: str, source: str) -> str:
    return (f"{source}, {title} [{series}], retrieved from FRED, Federal Reserve Bank of "
            f"St. Louis; https://fred.stlouisfed.org/series/{series}")
