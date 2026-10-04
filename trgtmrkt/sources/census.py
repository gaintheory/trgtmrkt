"""ACS 5-year estimates by ZIP code tabulation area (ZCTA).

Needs a free key: https://api.census.gov/data/key_signup.html -> CENSUS_API_KEY.
One call returns every ZCTA in the US; we filter to the ZIPs asked for.
Census marks "not available" with large negative sentinels; those become NaN.
"""
from __future__ import annotations

import json
import os
import urllib.parse

import pandas as pd

from .http import Fetch, cached_get

VARIABLES = {
    "B01003_001E": "population",
    "B19013_001E": "median_hh_income",
    "B19001_001E": "households",
    "B19001_002E": "inc_lt10", "B19001_003E": "inc_10_15", "B19001_004E": "inc_15_20",
    "B19001_005E": "inc_20_25", "B19001_006E": "inc_25_30", "B19001_007E": "inc_30_35",
    "B19001_008E": "inc_35_40", "B19001_009E": "inc_40_45", "B19001_010E": "inc_45_50",
    "B25003_001E": "occupied_units", "B25003_003E": "renter_units",
    "B25064_001E": "median_gross_rent",
    "B08201_002E": "hh_no_vehicle",
    "B08301_001E": "workers", "B08301_003E": "workers_drive_alone",
    "B08301_010E": "workers_transit",
    "B17001_001E": "poverty_universe", "B17001_002E": "below_poverty",
    "B23025_003E": "civilian_labor_force", "B23025_005E": "unemployed",
}
INCOME_UNDER_50K = ["inc_lt10", "inc_10_15", "inc_15_20", "inc_20_25", "inc_25_30",
                    "inc_30_35", "inc_35_40", "inc_40_45", "inc_45_50"]


def acs_url(year: int, key: str) -> str:
    q = {"get": ",".join(["NAME", *VARIABLES]), "for": "zip code tabulation area:*", "key": key}
    return f"https://api.census.gov/data/{year}/acs/acs5?{urllib.parse.urlencode(q)}"


def parse_acs(payload: bytes, zips: set[str] | None = None) -> pd.DataFrame:
    rows = json.loads(payload)
    df = pd.DataFrame(rows[1:], columns=rows[0])
    df = df.rename(columns={**VARIABLES, "zip code tabulation area": "zip5"})
    if zips is not None:
        df = df[df["zip5"].isin(zips)]
    for col in VARIABLES.values():
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[df[col] < 0, col] = float("nan")  # -666666666 and friends
    df = df.drop(columns=["NAME"]).reset_index(drop=True)
    return _derive(df)


def _ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    return num / den.where(den > 0)


def _derive(df: pd.DataFrame) -> pd.DataFrame:
    df["hh_under_50k"] = df[INCOME_UNDER_50K].sum(axis=1, min_count=len(INCOME_UNDER_50K))
    df["pct_hh_under_50k"] = _ratio(df["hh_under_50k"], df["households"])
    df["renter_share"] = _ratio(df["renter_units"], df["occupied_units"])
    df["no_vehicle_share"] = _ratio(df["hh_no_vehicle"], df["households"])
    df["poverty_rate"] = _ratio(df["below_poverty"], df["poverty_universe"])
    df["unemployment_rate"] = _ratio(df["unemployed"], df["civilian_labor_force"])
    df["drive_alone_share"] = _ratio(df["workers_drive_alone"], df["workers"])
    return df


def fetch_acs(zips: set[str] | None = None, year: int = 2023, key: str | None = None,
              fetch: Fetch | None = None, **cache_kw) -> pd.DataFrame:
    key = key or os.environ.get("CENSUS_API_KEY")
    if not key:
        raise RuntimeError("CENSUS_API_KEY is not set (free: api.census.gov/data/key_signup.html)")
    kw = {"fetch": fetch} if fetch else {}
    payload = cached_get(acs_url(year, key), max_age_days=180,
                         validate=lambda b: json.loads(b), **kw, **cache_kw)
    df = parse_acs(payload, zips)
    df.insert(1, "acs_year", year)
    return df
