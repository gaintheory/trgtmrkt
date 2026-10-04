"""Bad-outcome rate by band, with confidence intervals and a survivorship check."""
from __future__ import annotations

import pandas as pd

from .bands import MIN_N, add_bands, is_bad_outcome, wilson


def survivorship_warning(deals: pd.DataFrame) -> str | None:
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


def bad_rate_by(deals: pd.DataFrame, by: str | list[str]) -> pd.DataFrame:
    d = add_bands(deals)
    d["bad"] = is_bad_outcome(d)
    g = d.groupby(by, observed=True)["bad"].agg(n="count", bad="sum").reset_index()
    cis = g.apply(lambda r: wilson(int(r["bad"]), int(r["n"])), axis=1)
    g["bad_rate"] = g["bad"] / g["n"]
    g["ci_low"] = [c[0] for c in cis]
    g["ci_high"] = [c[1] for c in cis]
    g["reliable"] = g["n"] >= MIN_N
    return g.round(3)
