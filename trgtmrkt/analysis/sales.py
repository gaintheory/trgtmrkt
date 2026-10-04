"""Days-to-sell and gross by band. Needs only Frazer's cost/profit/days columns."""
from __future__ import annotations

import pandas as pd

from .bands import MIN_N, add_bands


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
