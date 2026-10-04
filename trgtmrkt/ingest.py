from __future__ import annotations

import sqlite3

import pandas as pd

from .deidentify import deidentify, load_salt

DEAL_COLUMNS = [
    "deal_id", "lot", "sale_date", "year", "make", "model", "mileage_at_sale",
    "sale_price", "down_payment", "amount_financed", "apr", "term_payments",
    "payment_amount", "payment_frequency", "total_cost", "profit_on_sale",
    "days_on_lot", "status", "days_past_due", "repo_date", "zip5",
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
