"""Banding and the shared statistics.

Small book, so everything is sliced into coarse bands and every rate carries a
Wilson interval and a `reliable` flag. Per-model cuts are available but should
be read with the flag: a lot with ~300 deals has a handful per model.
"""
from __future__ import annotations

import math

import pandas as pd

MIN_N = 20  # below this a row is shown but flagged unreliable

PRICE_BINS = [0, 5_000, 7_500, 10_000, 12_500, float("inf")]
PRICE_LABELS = ["<$5k", "$5-7.5k", "$7.5-10k", "$10-12.5k", "$12.5k+"]
DOWN_BINS = [-0.001, 0.05, 0.10, 0.15, 0.20, float("inf")]
DOWN_LABELS = ["<5%", "5-10%", "10-15%", "15-20%", "20%+"]
AGE_BINS = [-1, 5, 8, 11, 100]
AGE_LABELS = ["0-5 yrs", "6-8 yrs", "9-11 yrs", "12+ yrs"]
MILE_BINS = [0, 80_000, 110_000, 140_000, float("inf")]
MILE_LABELS = ["<80k", "80-110k", "110-140k", "140k+"]

BAND_COLUMNS = ["price_band", "down_pct_band", "age_band", "mileage_band"]


def add_bands(deals: pd.DataFrame) -> pd.DataFrame:
    d = deals.copy()
    d["down_pct"] = d["down_payment"] / d["sale_price"].where(d["sale_price"] > 0)
    sale_year = pd.to_datetime(d["sale_date"], errors="coerce").dt.year
    d["vehicle_age"] = sale_year - d["year"]
    d["price_band"] = pd.cut(d["sale_price"], PRICE_BINS, labels=PRICE_LABELS)
    d["down_pct_band"] = pd.cut(d["down_pct"], DOWN_BINS, labels=DOWN_LABELS)
    d["age_band"] = pd.cut(d["vehicle_age"], AGE_BINS, labels=AGE_LABELS)
    d["mileage_band"] = pd.cut(d["mileage_at_sale"], MILE_BINS, labels=MILE_LABELS)
    d["model_key"] = (d["make"].fillna("?") + " " + d["model"].fillna("?")).str.strip()
    return d


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def is_bad_outcome(d: pd.DataFrame) -> pd.Series:
    """Repossessed, charged off, or seriously delinquent (60+ days)."""
    return d["status"].isin(["repossessed", "charged_off"]) | (d["days_past_due"].fillna(0) >= 60)
