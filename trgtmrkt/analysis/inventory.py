"""Unsold stock: how long it has been owned and what margin is left in it.

Margin potential = asking price - (original cost + added/recon costs). Units
with no asking price yet (0 or blank) are reported separately, not as zero margin.
"""
from __future__ import annotations

import pandas as pd

from .bands import MIN_N


def prepare(inv: pd.DataFrame, as_of: str) -> pd.DataFrame:
    d = inv.copy()
    d["total_cost"] = d["original_cost"].fillna(0) + d["added_costs"].fillna(0)
    d["days_owned"] = (pd.to_datetime(as_of) - pd.to_datetime(d["purchase_date"], errors="coerce")).dt.days
    priced = d["retail_price"].where(d["retail_price"] > 0)
    d["margin_potential"] = priced - d["total_cost"]
    d["recon_share"] = d["added_costs"].fillna(0) / d["total_cost"].where(d["total_cost"] > 0)
    d["vendor"] = d["vendor"].fillna("(none)").replace("", "(none)")
    return d


def by_vendor(inv: pd.DataFrame, as_of: str) -> pd.DataFrame:
    d = prepare(inv, as_of)
    out = d.groupby("vendor").agg(
        units=("unit_id", "count"), avg_cost=("original_cost", "mean"),
        avg_recon=("added_costs", "mean"), median_days_owned=("days_owned", "median"),
        avg_margin_potential=("margin_potential", "mean"),
        unpriced=("margin_potential", lambda s: s.isna().sum()),
    ).reset_index().sort_values("units", ascending=False)
    out["reliable"] = out["units"] >= MIN_N
    return out.round(1)


def aged(inv: pd.DataFrame, as_of: str, days: int = 45) -> pd.DataFrame:
    d = prepare(inv, as_of)
    return d[d["days_owned"] >= days].sort_values("days_owned", ascending=False)[
        ["year", "make", "model", "mileage", "total_cost", "retail_price", "days_owned",
         "margin_potential", "vendor"]]
