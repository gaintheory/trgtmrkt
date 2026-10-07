from __future__ import annotations

import sqlite3

import pandas as pd

from .deidentify import deidentify, load_salt

DEAL_COLUMNS = [
    "deal_id", "lot", "sale_date", "year", "make", "model", "mileage_at_sale",
    "sale_price", "down_payment", "amount_financed", "apr", "term_payments",
    "payment_amount", "payment_frequency", "total_cost", "profit_on_sale",
    "days_on_lot", "status", "days_past_due", "repo_date", "zip5",
    "sale_type", "vehicle_source", "purchase_date", "original_cost", "added_costs",
    "write_off_date", "last_payment_date",
]


def ingest_frazer(conn: sqlite3.Connection, raw: pd.DataFrame, lot: str,
                  salt: str | None = None, default_status: str = "active") -> int:
    """De-identify one lot's export and upsert it. Returns rows written."""
    clean = deidentify(raw, lot, salt or load_salt(), default_status)[DEAL_COLUMNS]
    clean = clean.astype(object).where(clean.notna(), None)
    placeholders = ",".join("?" * len(DEAL_COLUMNS))
    conn.executemany(
        f"INSERT OR REPLACE INTO deals ({','.join(DEAL_COLUMNS)}) VALUES ({placeholders})",
        clean.itertuples(index=False, name=None),
    )
    conn.commit()
    return len(clean)


def load_deals(conn: sqlite3.Connection, lot: str | None = None) -> pd.DataFrame:
    q = "SELECT * FROM deals" + (" WHERE lot = ?" if lot else "")
    return pd.read_sql_query(q, conn, params=(lot,) if lot else None)


def ingest_inventory(conn: sqlite3.Connection, raw: pd.DataFrame, lot: str, snapshot_date: str,
                     salt: str | None = None) -> int:
    """Load an unsold-inventory export. VINs and titles are not read."""
    from .deidentify import _date, _find, _int, _money, _year, deal_id

    salt = salt or load_salt()
    cols = list(raw.columns)

    def col(*names):
        c = _find(cols, list(names))
        return raw[c] if c else pd.Series([None] * len(raw), index=raw.index)

    out = pd.DataFrame({
        "unit_id": [deal_id(lot, str(s).strip(), salt) for s in col("Stock #")],
        "lot": lot,
        "year": col("Vehicle Year", "Year").map(_year),
        "make": col("Vehicle Make", "Make").astype("string").str.strip().str.title(),
        "model": col("Vehicle Model", "Model").astype("string").str.strip(),
        "mileage": col("Mileage").map(_int),
        "original_cost": col("Original Cost").map(_money),
        "added_costs": col("Added Costs").map(_money),
        "retail_price": col("Retail Price", "Internet Price").map(_money),
        "purchase_date": col("Purchase Date").map(_date),
        "ready_date": col("Ready To Sell Date").map(_date),
        "vendor": col("Vendor").astype("string").str.strip().str.upper(),
        "snapshot_date": snapshot_date,
    }).drop_duplicates("unit_id")
    out = out.astype(object).where(out.notna(), None)
    conn.executemany(
        f"INSERT OR REPLACE INTO inventory ({','.join(out.columns)}) VALUES ({','.join('?' * len(out.columns))})",
        out.itertuples(index=False, name=None))
    conn.commit()
    return len(out)
