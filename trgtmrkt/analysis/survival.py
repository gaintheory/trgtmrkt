"""Months on book: cumulative bad-outcome rate that counts each note only for the
time it has actually been observed (Kaplan-Meier).

Why: a note sold last month cannot have defaulted yet, so counting it as "good"
(as a plain rate does) understates risk. Here it only contributes the months it
has really been at risk.

Event  = repossession or write-off, with a known date (earliest of the two).
Ends   = the event date; otherwise a paid-off note ends at its last payment date;
         everything else is still being observed and ends at `as_of`.
Not an event: a note that is 60+ days late today but not yet repossessed. Its
         date of going bad is unknown, so it cannot be placed on the curve. It is
         counted separately (`late_not_repossessed`) as a leading indicator.

Only financed notes are included; cash and wholesale sales cannot default.
`as_of` defaults to the newest sale date, roughly the export date. Pass the real
export date when you know it.
"""
from __future__ import annotations

import math

import pandas as pd

from .bands import MIN_N, add_bands
from .default import financed_only

DAYS_PER_MONTH = 30.4375
MILESTONES = (3, 6, 9, 12, 18, 24, 36)
BAD_STATUSES = ("repossessed", "charged_off")


def observations(deals: pd.DataFrame, as_of: str | None = None) -> pd.DataFrame:
    """One row per financed note: months observed and whether it ended in an event."""
    d = financed_only(deals).copy()
    sale = pd.to_datetime(d["sale_date"], errors="coerce")
    ref = pd.to_datetime(as_of) if as_of else pd.to_datetime(deals["sale_date"], errors="coerce").max()
    repo = pd.to_datetime(d["repo_date"], errors="coerce")
    wo = pd.to_datetime(d["write_off_date"], errors="coerce") if "write_off_date" in d else pd.NaT
    last = pd.to_datetime(d["last_payment_date"], errors="coerce") if "last_payment_date" in d else pd.NaT
    event_date = pd.concat([repo, wo], axis=1).min(axis=1)

    is_bad = d["status"].isin(BAD_STATUSES)
    event = is_bad & event_date.notna()
    paid = (d["status"] == "paid_off") & last.notna() & (last >= sale)
    end = event_date.where(event, last.where(paid, ref))
    d["months"] = ((end - sale).dt.days / DAYS_PER_MONTH).clip(lower=0)
    d["event"] = event
    d["undated_bad"] = is_bad & ~event  # bad status but no date: cannot be placed
    d["late_not_repossessed"] = (~is_bad) & (d["days_past_due"].fillna(0) >= 60)
    return d[d["months"].notna()]


def km(obs: pd.DataFrame) -> pd.DataFrame:
    """Kaplan-Meier table: one row per distinct event time."""
    t = obs[["months", "event"]].sort_values("months")
    rows, s, green = [], 1.0, 0.0
    for time, grp in t[t["event"]].groupby("months"):
        n_risk = int((t["months"] >= time).sum())
        d_i = len(grp)
        s *= 1 - d_i / n_risk
        if n_risk > d_i:
            green += d_i / (n_risk * (n_risk - d_i))
        rows.append({"months": time, "at_risk": n_risk, "events": d_i, "survival": s,
                     "greenwood": green})
    return pd.DataFrame(rows, columns=["months", "at_risk", "events", "survival", "greenwood"])


def at_month(obs: pd.DataFrame, table: pd.DataFrame, month: float) -> dict:
    """Cumulative bad rate by `month`, with a 95% interval and how many notes are
    still under observation at that age (the number to trust it by)."""
    seen = table[table["months"] <= month]
    surv = float(seen["survival"].iloc[-1]) if len(seen) else 1.0
    green = float(seen["greenwood"].iloc[-1]) if len(seen) else 0.0
    se = surv * math.sqrt(green)
    at_risk = int((obs["months"] >= month).sum())
    return {"month": month, "at_risk": at_risk, "events_by_then": int(seen["events"].sum()),
            "cum_bad": round(1 - surv, 3),
            "ci_low": round(max(0.0, 1 - surv - 1.96 * se), 3),
            "ci_high": round(min(1.0, 1 - surv + 1.96 * se), 3),
            "reliable": at_risk >= MIN_N}


def months_on_book(deals: pd.DataFrame, by: str | None = None, as_of: str | None = None,
                   milestones: tuple[int, ...] = MILESTONES) -> pd.DataFrame:
    """Cumulative bad rate at each milestone, overall or per group."""
    obs = observations(deals, as_of)
    if by:
        obs = add_bands(obs)
    groups = obs.groupby(by, observed=True) if by else [("all", obs)]
    out = []
    for name, g in groups:
        if g.empty:
            continue
        table = km(g)
        for m in milestones:
            if m > g["months"].max():  # nobody has been observed this long
                break
            row = at_month(g, table, m)
            row = {"group": name, **row, "notes": len(g)}
            out.append(row)
    return pd.DataFrame(out, columns=["group", "month", "notes", "at_risk", "events_by_then",
                                      "cum_bad", "ci_low", "ci_high", "reliable"])


def data_notes(deals: pd.DataFrame, as_of: str | None = None) -> dict:
    obs = observations(deals, as_of)
    return {"notes": len(obs), "events": int(obs["event"].sum()),
            "undated_bad": int(obs["undated_bad"].sum()),
            "late_not_repossessed": int(obs["late_not_repossessed"].sum()),
            "max_months_observed": round(float(obs["months"].max()), 1) if len(obs) else 0.0}
