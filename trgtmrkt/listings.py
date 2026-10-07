"""Weekly local listing snapshot, kept in SQLite so reports never hit the API.

Why snapshots: listing feeds rarely give a trustworthy days-on-market. Pull the
same narrow search every week, and first-seen / last-seen per VIN gives you a
real one, for free, that gets better every week. It cannot be backfilled, so
start early.

Guard rails
  * dry-run by default; --live is required to spend a call
  * every call is logged in api_calls and a monthly cap is enforced
  * nothing here is a live client query; reports read the local table

UNVERIFIED against the live API: pagination (`page`) and the price filter
(`price_max`). comps.ts in Autodoss verifies only make, model, year_min,
year_max, zip, distance and limit, plus priceUnformatted / mileageUnformatted
on records. Check the Auto.dev docs and the plan's commercial-use terms before
the first --live run, then confirm with one call.
"""
from __future__ import annotations

import json
import os
import sqlite3
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Callable

import pandas as pd

ENDPOINT = "https://auto.dev/api/listings"
DEFAULT_MONTHLY_CAP = 400


class QuotaExceeded(RuntimeError):
    pass


def calls_this_month(conn: sqlite3.Connection, provider: str = "auto.dev",
                     now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    prefix = now.strftime("%Y-%m")
    row = conn.execute(
        "SELECT COUNT(*) FROM api_calls WHERE provider=? AND called_at LIKE ?",
        (provider, f"{prefix}%")).fetchone()
    return int(row[0])


def _http_fetch(url: str, key: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        return json.load(resp)


def _pick(rec: dict, *names):
    for n in names:
        v = rec.get(n)
        if v not in (None, ""):
            return v
    return None


def normalize(rec: dict) -> dict | None:
    vin = _pick(rec, "vin", "VIN")
    if not vin:
        return None
    dealer = _pick(rec, "dealerName", "dealer_name", "dealer")
    if isinstance(dealer, dict):
        dealer = dealer.get("name")
    return {
        "vin": str(vin).upper(),
        "year": _pick(rec, "year"),
        "make": _pick(rec, "make"),
        "model": _pick(rec, "model"),
        "price": _pick(rec, "priceUnformatted", "price"),
        "mileage": _pick(rec, "mileageUnformatted", "mileage"),
        "dealer": dealer,
    }


def snapshot(conn: sqlite3.Connection, *, zip_code: str, radius: int = 25,
             price_max: int = 10_000, limit: int = 100, max_pages: int = 1,
             live: bool = False, key: str | None = None,
             monthly_cap: int = DEFAULT_MONTHLY_CAP,
             fetch: Callable[[str, str], dict] | None = None,
             today: date | None = None) -> dict:
    """Pull one narrow search. Returns a summary; dry-run spends nothing."""
    today = today or date.today()
    params = {"zip": zip_code, "distance": radius, "price_max": price_max, "limit": limit}
    planned = max_pages
    used = calls_this_month(conn)
    summary = {"planned_calls": planned, "used_this_month": used, "cap": monthly_cap,
               "rows": 0, "live": live}
    if not live:
        return summary
    if used + planned > monthly_cap:
        raise QuotaExceeded(f"{used} calls used + {planned} planned exceeds cap {monthly_cap}")
    key = key or os.environ.get("AUTO_DEV_API_KEY")
    if not key and fetch is None:
        raise RuntimeError("AUTO_DEV_API_KEY is not set")
    do_fetch = fetch or _http_fetch

    for page in range(1, max_pages + 1):
        p = dict(params)
        if page > 1:
            p["page"] = page
        url = f"{ENDPOINT}?{urllib.parse.urlencode(p)}"
        data = do_fetch(url, key or "")
        conn.execute("INSERT INTO api_calls VALUES (?,?,?,?,?)",
                     (datetime.now(timezone.utc).isoformat(), "auto.dev", ENDPOINT,
                      json.dumps(p), 200))
        records = data.get("records", []) if isinstance(data, dict) else []
        for rec in records:
            n = normalize(rec)
            if n is None:
                continue
            # Filter client-side too, in case the API ignores price_max.
            if n["price"] is not None and float(n["price"]) > price_max:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO listing_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
                (today.isoformat(), n["vin"], n["year"], n["make"], n["model"],
                 n["price"], n["mileage"], n["dealer"], zip_code, json.dumps(rec)))
            summary["rows"] += 1
        if len(records) < limit:
            break
    conn.commit()
    return summary


def market_velocity(conn: sqlite3.Connection) -> pd.DataFrame:
    """Per VIN: first/last seen, days listed, price change. Uses only snapshots."""
    df = pd.read_sql_query(
        "SELECT snapshot_date, vin, year, make, model, price, dealer FROM listing_snapshots", conn)
    if df.empty:
        return df
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df = df.sort_values("snapshot_date")
    g = df.groupby("vin")
    out = g.agg(first_seen=("snapshot_date", "min"), last_seen=("snapshot_date", "max"),
                sightings=("snapshot_date", "count"), make=("make", "last"),
                model=("model", "last"), year=("year", "last"), dealer=("dealer", "last"),
                first_price=("price", "first"), last_price=("price", "last")).reset_index()
    out["days_listed"] = (out["last_seen"] - out["first_seen"]).dt.days
    out["price_change"] = out["last_price"] - out["first_price"]
    latest = df["snapshot_date"].max()
    out["still_listed"] = out["last_seen"] == latest  # False => sold/removed since
    return out
