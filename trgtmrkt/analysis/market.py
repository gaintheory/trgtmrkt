"""Trade-area sizing and whitespace: public demographics against your own deals.

For each lot, every ZIP whose centroid is within `radius_miles` is sized by the
number of households earning under $50k (the core BHPH buyer pool, a proxy and
not a credit measure), then compared with how many deals the operator's lots
actually closed from that ZIP.

Read `penetration_per_1000` as relative, not absolute: deals span the whole
export window while households are a point-in-time count. The useful signal is
which large ZIPs have unusually low penetration, i.e. whitespace.
"""
from __future__ import annotations

import pandas as pd

from .catchment import haversine_miles

KEEP = ["households", "hh_under_50k", "pct_hh_under_50k", "median_hh_income",
        "renter_share", "no_vehicle_share", "poverty_rate", "unemployment_rate"]


def trade_area(lots: dict[str, tuple[float, float]], centroids: dict[str, tuple[float, float]],
               acs: pd.DataFrame, deals: pd.DataFrame, radius_miles: float = 15.0) -> pd.DataFrame:
    acs = acs.set_index("zip5")
    all_lot_deals = deals.dropna(subset=["zip5"]).groupby("zip5").size()
    own_deals = deals.dropna(subset=["zip5"]).groupby(["lot", "zip5"]).size()
    rows = []
    for lot, pos in lots.items():
        for zip5, c in centroids.items():
            if zip5 not in acs.index:
                continue
            miles = haversine_miles(pos, c)
            if miles > radius_miles:
                continue
            rec = {"lot": lot, "zip5": zip5, "miles": round(miles, 1),
                   **{k: acs.at[zip5, k] for k in KEEP},
                   "deals_this_lot": int(own_deals.get((lot, zip5), 0)),
                   "deals_all_lots": int(all_lot_deals.get(zip5, 0))}
            rows.append(rec)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    target = out["hh_under_50k"].where(out["hh_under_50k"] > 0)
    out["penetration_per_1000"] = (out["deals_all_lots"] / target * 1000).round(1)
    out["whitespace_rank"] = out.groupby("lot")["hh_under_50k"].transform(
        lambda s: s.rank(ascending=False, method="first"))
    # Whitespace = large target pool, below-median penetration within the lot's area.
    med = out.groupby("lot")["penetration_per_1000"].transform("median")
    out["whitespace"] = (out["penetration_per_1000"] < med) & (out["whitespace_rank"] <= 10)
    return out.sort_values(["lot", "whitespace_rank"]).reset_index(drop=True).round(3)


def lot_summary(area: pd.DataFrame) -> pd.DataFrame:
    if area.empty:
        return area
    g = area.groupby("lot")
    return g.agg(zips=("zip5", "count"), households=("households", "sum"),
                 target_households=("hh_under_50k", "sum"),
                 deals_this_lot=("deals_this_lot", "sum"),
                 deals_all_lots=("deals_all_lots", "sum"),
                 median_income=("median_hh_income", "median")).reset_index()
