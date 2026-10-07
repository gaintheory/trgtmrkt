"""Where each lot's customers live, and how far they drive.

Real runs need Census ZCTA centroids: download the "ZIP Code Tabulation Areas"
gazetteer from census.gov (tab-separated; GEOID, INTPTLAT, INTPTLONG) into
data/reference/ and pass its path. The built-in table is rough and covers a
few Middle TN ZIPs; it exists only so the demo runs offline.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

DEMO_CENTROIDS = {  # approximate, demo only
    "37167": (36.00, -86.52), "37086": (36.01, -86.58), "37130": (35.85, -86.40),
    "37129": (35.88, -86.45), "37128": (35.81, -86.46), "37127": (35.79, -86.35),
    "37013": (36.06, -86.67), "37122": (36.20, -86.52), "37076": (36.19, -86.62),
    "37153": (35.77, -86.51),
}


def load_centroids(gazetteer: str | Path | None = None) -> dict[str, tuple[float, float]]:
    if gazetteer is None:
        return dict(DEMO_CENTROIDS)
    df = pd.read_csv(gazetteer, sep="\t", dtype={"GEOID": str})
    df.columns = [c.strip() for c in df.columns]
    return {r.GEOID: (float(r.INTPTLAT), float(r.INTPTLONG)) for r in df.itertuples()}


def haversine_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 3958.8 * math.asin(math.sqrt(h))


def catchment(deals: pd.DataFrame, lots: dict[str, tuple[float, float]],
              centroids: dict[str, tuple[float, float]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (per lot+ZIP table, per-lot distance summary)."""
    d = deals.dropna(subset=["zip5"]).copy()
    d["miles"] = [
        haversine_miles(lots[lot], centroids[z]) if lot in lots and z in centroids else math.nan
        for lot, z in zip(d["lot"], d["zip5"])
    ]
    by_zip = (d.groupby(["lot", "zip5"]).agg(deals=("deal_id", "count"), miles=("miles", "first"))
              .reset_index())
    by_zip["share"] = by_zip["deals"] / by_zip.groupby("lot")["deals"].transform("sum")
    by_zip = by_zip.sort_values(["lot", "deals"], ascending=[True, False])

    known = d.dropna(subset=["miles"])
    summary = known.groupby("lot")["miles"].agg(
        deals="count", median_miles="median", p80_miles=lambda s: s.quantile(0.8),
        within_5=lambda s: (s <= 5).mean(), within_10=lambda s: (s <= 10).mean(),
        within_15=lambda s: (s <= 15).mean(),
    ).reset_index()

    # How much of each lot's customer base also appears at another lot's ZIPs:
    # a rough overlap signal for the owner (do the three lots compete?).
    zips = {lot: set(g["zip5"]) for lot, g in by_zip.groupby("lot")}
    summary["zip_overlap_other_lots"] = [
        len(zips[l] & set().union(*(zips[o] for o in zips if o != l))) / max(len(zips[l]), 1)
        if len(zips) > 1 else math.nan for l in summary["lot"]
    ]
    return by_zip.round(3), summary.round(3)
