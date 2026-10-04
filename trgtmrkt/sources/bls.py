"""BLS Local Area Unemployment Statistics by county (works without a key at low
volume; set BLS_API_KEY for more). Series: LAUCN + state + county + 00000000 +
measure, measure 03 = unemployment rate."""
from __future__ import annotations

import json
import os
import sqlite3
import urllib.parse

from .http import Fetch, cached_get

# Middle TN counties of interest (FIPS, verify against your trade area).
COUNTIES = {
    "47149": "Rutherford", "47037": "Davidson", "47187": "Williamson", "47189": "Wilson",
    "47165": "Sumner", "47015": "Cannon", "47003": "Bedford", "47119": "Maury",
}


def series_id(fips: str, measure: str = "03") -> str:
    return f"LAUCN{fips}00000000{measure}"


def parse(payload: bytes, fips: str) -> list[tuple[str, str, float]]:
    data = json.loads(payload)
    if data.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS error for {fips}: {data.get('message')}")
    rows = []
    for s in data["Results"]["series"]:
        for d in s["data"]:
            if not d["period"].startswith("M") or d["period"] == "M13":
                continue
            try:
                rows.append((fips, f'{d["year"]}-{d["period"][1:]}', float(d["value"])))
            except ValueError:
                continue
    return rows


def refresh(conn: sqlite3.Connection, counties: dict[str, str] | None = None,
            fetch: Fetch | None = None, key: str | None = None, **cache_kw) -> int:
    key = key or os.environ.get("BLS_API_KEY")
    kw = {"fetch": fetch} if fetch else {}
    total = 0
    for fips in (counties or COUNTIES):
        url = f"https://api.bls.gov/publicAPI/v2/timeseries/data/{series_id(fips)}"
        if key:
            url += "?" + urllib.parse.urlencode({"registrationkey": key})
        payload = cached_get(url, max_age_days=7, validate=lambda b: parse(b, fips),
                             **kw, **cache_kw)
        rows = parse(payload, fips)
        conn.executemany(
            "INSERT OR REPLACE INTO county_unemployment (fips, month, rate) VALUES (?,?,?)", rows)
        total += len(rows)
    conn.commit()
    return total
