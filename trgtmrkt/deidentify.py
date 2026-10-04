"""Turn a raw Frazer export into de-identified deal rows.

The raw file holds names, phones, street addresses, birthdays, license numbers,
employers, incomes and credit data. None of that is read into the output: every
output column is picked by name from ALIASES, and anything not listed is
dropped. The only location kept is the 5-digit ZIP.

Header spellings differ between Frazer presets, so each field lists the
spellings seen in the Autodoss importer. Matching ignores case and punctuation.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
from pathlib import Path

import pandas as pd

ALIASES: dict[str, list[str]] = {
    "stock_no": ["Stock #", "Stock No", "Stock"],
    "sale_date": ["Sale Date", "Date of Sale"],
    "year": ["Year", "Vehicle Year"],
    "make": ["Make", "Vehicle Make"],
    "model": ["Model", "Vehicle Model"],
    "vehicle": ["Vehicle", "Year Make Model", "Vehicle Description"],
    "mileage_at_sale": ["Mileage At Sale"],
    "sale_price": ["Sales Price", "Sale Price"],
    "down_payment": ["Down Payment"],
    "amount_financed": ["Amt Financed", "Amount Financed"],
    "apr": ["APR"],
    "term_payments": ["Number of Payments"],
    "payment_amount": ["Payment Amt", "Payment Amount", "Scheduled Payment Amount"],
    "payment_frequency": ["Pay Schedule", "Payment Frequency"],
    "total_cost": ["Total Cost"],
    "profit_on_sale": ["Profit On Sale"],
    "days_on_lot": ["Days On Lot"],
    "days_past_due": ["Days past Due", "Days Past Due"],
    "total_balance": ["Balance", "Total Balance Owed"],
    "principal_balance": ["Principal Balance"],
    "account_status": ["Account Status", "Status"],
    "repo_date_out": ["Repo Date Out"],
    "repo_date_redeemed": ["Repo Date Redeemed"],
    "zip": ["Zip", "Zip Code"],
}

# Never read, listed so a test can prove the output never carries them.
FORBIDDEN_OUTPUT = {
    "first_name", "last_name", "customer_name", "phone", "email", "street",
    "address", "birthday", "license_number", "employer", "credit_score",
    "customer_income", "vin",
}


def _norm(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(header).lower())


def _find(columns: list[str], names: list[str]) -> str | None:
    index: dict[str, str] = {}
    for col in columns:
        index.setdefault(_norm(col), col)  # leftmost duplicate wins
    for name in names:
        hit = index.get(_norm(name))
        if hit is not None:
            return hit
    return None


def _money(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[^0-9.\-]", "", s)
    if s in ("", "-", "."):
        return None
    out = float(s)
    return -abs(out) if neg else out


def _int(value) -> int | None:
    m = _money(value)
    return None if m is None else int(round(m))


def _date(value) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    parsed = pd.to_datetime(str(value).strip(), errors="coerce", format="mixed")
    return None if pd.isna(parsed) else parsed.strftime("%Y-%m-%d")


def _zip5(value) -> str | None:
    m = re.match(r"\s*(\d{5})", str(value or ""))
    return m.group(1) if m else None


def _split_vehicle(text) -> tuple[int | None, str | None, str | None]:
    m = re.match(r"\s*((?:19|20)\d{2}|\d{2})\s+(\S+)\s+(.+?)\s*$", str(text or ""))
    if not m:
        return None, None, None
    y = int(m.group(1))
    if y < 100:
        y += 2000 if y < 70 else 1900
    return y, m.group(2).title(), m.group(3).strip()


def load_salt(path: str | Path = "data/private/.salt") -> str:
    """Per-installation salt so deal_id cannot be reversed from stock numbers."""
    env = os.environ.get("TRGTMRKT_SALT")
    if env:
        return env
    p = Path(path)
    if p.exists():
        return p.read_text().strip()
    p.parent.mkdir(parents=True, exist_ok=True)
    salt = secrets.token_hex(16)
    p.write_text(salt)
    return salt


def deal_id(lot: str, stock_no: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}|{lot}|{stock_no}".encode()).hexdigest()[:16]


def derive_status(row: pd.Series, has_status_col: bool, default: str) -> str:
    if has_status_col:
        raw = _norm(row.get("_status")) if pd.notna(row.get("_status")) else ""
        if "repo" in raw:
            return "repossessed"
        if "charge" in raw or "writeoff" in raw:
            return "charged_off"
        if "paid" in raw or "closed" in raw:
            return "paid_off"
        if "active" in raw or "open" in raw:
            return "active"
    # pandas turns a missing date into NaN, which is truthy: test with notna.
    if pd.notna(row.get("_repo_out")) and pd.isna(row.get("_repo_redeemed")):
        return "repossessed"
    return default


def deidentify(raw: pd.DataFrame, lot: str, salt: str,
               default_status: str = "active") -> pd.DataFrame:
    cols = list(raw.columns)
    pick = {key: _find(cols, names) for key, names in ALIASES.items()}
    if pick["stock_no"] is None:
        raise ValueError("No 'Stock #' column: this does not look like a Frazer export.")

    def col(key):
        c = pick[key]
        return raw[c] if c is not None else pd.Series([None] * len(raw), index=raw.index)

    out = pd.DataFrame(index=raw.index)
    out["deal_id"] = [deal_id(lot, str(s).strip(), salt) for s in col("stock_no")]
    out["lot"] = lot
    out["sale_date"] = col("sale_date").map(_date)

    if pick["year"] and pick["make"] and pick["model"]:
        out["year"] = col("year").map(_int)
        out["make"] = col("make").astype("string").str.strip().str.title()
        out["model"] = col("model").astype("string").str.strip()
    else:
        parts = col("vehicle").map(_split_vehicle)
        out["year"] = parts.map(lambda t: t[0])
        out["make"] = parts.map(lambda t: t[1])
        out["model"] = parts.map(lambda t: t[2])

    out["mileage_at_sale"] = col("mileage_at_sale").map(_int)
    for key in ("sale_price", "down_payment", "amount_financed", "payment_amount",
                "total_cost", "profit_on_sale"):
        out[key] = col(key).map(_money)
    out["apr"] = col("apr").map(_money)
    out["term_payments"] = col("term_payments").map(_int)
    out["payment_frequency"] = col("payment_frequency").astype("string").str.strip()
    out["days_on_lot"] = col("days_on_lot").map(_int)
    # Frazer leaves "Days past Due" blank for "nothing overdue"; keep that as 0.
    out["days_past_due"] = col("days_past_due").map(_int).fillna(0).astype(int)

    tmp = pd.DataFrame({
        "_status": col("account_status"),
        "_repo_out": col("repo_date_out").map(_date),
        "_repo_redeemed": col("repo_date_redeemed").map(_date),
    })
    has_status = pick["account_status"] is not None
    out["status"] = tmp.apply(derive_status, axis=1, has_status_col=has_status,
                              default=default_status)
    out["repo_date"] = tmp["_repo_out"]
    out["zip5"] = col("zip").map(_zip5)

    out = out.drop_duplicates("deal_id", keep="first").reset_index(drop=True)
    assert not (set(out.columns) & FORBIDDEN_OUTPUT)
    return out
