"""Bad-outcome rate by band, with confidence intervals and a survivorship check."""
from __future__ import annotations

import pandas as pd

from .bands import MIN_N, add_bands, is_bad_outcome, wilson


NON_NOTE = ["cash", "wholesale", "outside_financing"]  # can never default on a lot-held note


def resolve_as_of(deals: pd.DataFrame, as_of: str | None = None) -> pd.Timestamp:
    """End of the observation window: explicit value, else the newest recorded
    export date, else (a rougher guess) the newest sale date."""
    if as_of:
        return pd.to_datetime(as_of)
    if "export_date" in deals and deals["export_date"].notna().any():
        return pd.to_datetime(deals["export_date"]).max()
    return pd.to_datetime(deals["sale_date"], errors="coerce").max()


def financed_only(deals: pd.DataFrame) -> pd.DataFrame:
    return deals[~deals["status"].isin(NON_NOTE)]


def seasoned(deals: pd.DataFrame, min_age_days: int, as_of: str | None = None) -> pd.DataFrame:
    """Keep deals old enough to have had time to go bad. Without this, last
    month's sales dilute every rate (right-censoring). `as_of` defaults to the
    recorded export date (else the newest sale)."""
    d = pd.to_datetime(deals["sale_date"], errors="coerce")
    return deals[(resolve_as_of(deals, as_of) - d).dt.days >= min_age_days]


def survivorship_warning(deals: pd.DataFrame) -> str | None:
    deals = financed_only(deals)
    """An active-only export hides repos and paid-off accounts, which makes
    default look rarer than it is. Say so loudly rather than report a clean
    number."""
    if deals.empty:
        return "No deals loaded."
    closed = deals["status"].isin(["repossessed", "charged_off", "paid_off"]).mean()
    if closed == 0:
        return ("Every account is active. Repossessed and paid-off accounts are "
                "missing, so bad-outcome rates are understated. Re-export with "
                "closed accounts included before trusting these numbers.")
    if not deals["status"].isin(["repossessed", "charged_off"]).any():
        return "No repossessed or charged-off accounts present; rates are likely understated."
    return None


def bad_rate_by(deals: pd.DataFrame, by: str | list[str], min_age_days: int = 0,
                as_of: str | None = None) -> pd.DataFrame:
    """Bad-outcome rate over financed deals only, optionally only seasoned ones."""
    deals = financed_only(deals)
    if min_age_days:
        deals = seasoned(deals, min_age_days, as_of)
    d = add_bands(deals)
    d["bad"] = is_bad_outcome(d)
    g = d.groupby(by, observed=True)["bad"].agg(n="count", bad="sum").reset_index()
    cis = [wilson(int(b), int(n)) for b, n in zip(g["bad"], g["n"])]  # empty-safe
    g["bad_rate"] = g["bad"] / g["n"]
    g["ci_low"] = [c[0] for c in cis]
    g["ci_high"] = [c[1] for c in cis]
    g["reliable"] = g["n"] >= MIN_N
    return g.round(3)
