"""Days-to-sell and gross by band. Needs only Frazer's cost/profit/days columns."""
from __future__ import annotations

import pandas as pd

from .bands import MIN_N, add_bands


def retail_scope(deals: pd.DataFrame) -> pd.DataFrame:
    """Deals where days-on-lot and gross mean something comparable.

    Excluded: wholesale deals, and any car that came from a repossession. In a
    real export 36 of 50 wholesale deals were repossessed cars sold at once, with
    0 days on lot and 0 profit booked, which makes every band look faster and
    thinner than retail really is."""
    keep = (deals["sale_type"].fillna("").str.lower() != "wholesale") & (
        deals["vehicle_source"].fillna("").str.lower().str[:6] != "reposs")
    return deals[keep]


def sales_by(deals: pd.DataFrame, by: str | list[str]) -> pd.DataFrame:
    d = add_bands(deals)
    g = d.groupby(by, observed=True)
    out = g.agg(
        n=("deal_id", "count"),
        median_days_on_lot=("days_on_lot", "median"),
        pct_sold_within_30=("days_on_lot", lambda s: (s.dropna() <= 30).mean()),
        median_gross=("profit_on_sale", "median"),
        mean_gross=("profit_on_sale", "mean"),
        median_price=("sale_price", "median"),
    ).reset_index()
    out["gross_per_day_on_lot"] = out["median_gross"] / out["median_days_on_lot"].where(
        out["median_days_on_lot"] > 0)
    out["reliable"] = out["n"] >= MIN_N
    return out.round(2)
