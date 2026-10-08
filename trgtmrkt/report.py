from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .analysis.bands import BAND_COLUMNS
from .analysis.catchment import catchment, load_centroids
from .analysis.default import bad_rate_by, survivorship_warning
from .analysis.inventory import aged, by_vendor
from .analysis.market import lot_summary, trade_area
from .analysis.sales import retail_scope, sales_by
from .analysis.survival import data_notes, months_on_book
from .sources.fred import FRED_NOTICE, TERMS_URL, citation


def _md(df: pd.DataFrame) -> str:
    return df.to_markdown(index=False) if hasattr(df, "to_markdown") and _has_tabulate() else df.to_string(index=False)


def _has_tabulate() -> bool:
    try:
        import tabulate  # noqa: F401
        return True
    except ImportError:
        return False


def build_report(deals: pd.DataFrame, out_dir: str | Path, lots_cfg: dict | None = None,
                 gazetteer: str | None = None, acs: pd.DataFrame | None = None,
                 radius_miles: float = 15.0, macro: pd.DataFrame | None = None,
                 inventory: pd.DataFrame | None = None, seasoning_days: int = 180) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# TRGT MRKT internal report", ""]
    warn = survivorship_warning(deals)
    if warn:
        lines += [f"> **Data warning:** {warn}", ""]
    lines.append(f"Deals: {len(deals)} across lots: {', '.join(sorted(deals['lot'].unique()))}")
    lines.append("Rows flagged `reliable=False` have fewer than 20 deals; treat as anecdotes.\n")

    retail = retail_scope(deals)
    lines += [f"Days-to-sell and gross bands cover {len(retail)} of {len(deals)} deals: wholesale deals and "
              "repossession-sourced cars are excluded (see the sale_type and vehicle_source tables).", ""]
    for band in BAND_COLUMNS:
        s = sales_by(retail, band)
        s.to_csv(out / f"sales_by_{band}.csv", index=False)
        lines += [f"## Days to sell and gross by {band}", "```", s.to_string(index=False), "```", ""]
    for cut in ("sale_type", "vehicle_source"):
        if deals[cut].notna().any():
            s = sales_by(deals, cut)
            s.to_csv(out / f"sales_by_{cut}.csv", index=False)
            lines += [f"## Days to sell and gross by {cut}", "```", s.to_string(index=False), "```", ""]
    lines += [f"Bad-outcome tables below cover financed (BHPH) deals only and, to avoid "
              f"diluting rates with accounts too young to have gone bad, only deals at least "
              f"{seasoning_days} days old at the newest sale in the data.", ""]
    for band in BAND_COLUMNS + ["vehicle_source"]:
        if band not in BAND_COLUMNS and not deals[band].notna().any():
            continue
        b = bad_rate_by(deals, band, min_age_days=seasoning_days)
        b.to_csv(out / f"bad_rate_by_{band}.csv", index=False)
        lines += [f"## Bad-outcome rate by {band}", "```", b.to_string(index=False), "```", ""]
    from .analysis.default import resolve_as_of
    as_of = resolve_as_of(deals)
    mob_notes = data_notes(deals)
    lines += ["## Cumulative bad-outcome rate by months on book (repossession or write-off)",
              f"Each note counts only for the time actually observed, so recent sales do not "
              f"flatter the result. {mob_notes['notes']} financed notes, {mob_notes['events']} with a "
              f"dated repossession or write-off, observed through {as_of.date()}, longest observed {mob_notes['max_months_observed']} months. "
              f"{mob_notes['late_not_repossessed']} more are 60+ days late but not repossessed; their "
              f"date of going bad is unknown, so they are not on the curve (they are a leading "
              f"indicator, not an outcome). Trust a row only when `at_risk` is large.", ""]
    if mob_notes["undated_bad"]:
        lines += [f"Warning: {mob_notes['undated_bad']} repossessed/charged-off notes have no date "
                  "and were left off the curve.", ""]
    mob = months_on_book(deals)
    mob.to_csv(out / "months_on_book.csv", index=False)
    lines += ["```", mob.to_string(index=False), "```", ""]
    for cut in ("lot", "down_pct_band", "price_band"):
        if cut == "lot" and deals["lot"].nunique() < 2:
            continue
        g = months_on_book(deals, by=cut, milestones=(6, 12))
        if not g.empty:
            g.to_csv(out / f"months_on_book_by_{cut}.csv", index=False)
            lines += [f"### By {cut} (6 and 12 months)", "```", g.to_string(index=False), "```", ""]
    by_lot = bad_rate_by(deals, "lot", min_age_days=seasoning_days)
    by_lot.to_csv(out / "bad_rate_by_lot.csv", index=False)
    lines += ["## Bad-outcome rate by lot", "```", by_lot.to_string(index=False), "```", ""]

    if lots_cfg:
        centroids = load_centroids(gazetteer)
        lots = {}
        for l in lots_cfg["lots"]:
            if "lat" in l and "lon" in l:
                lots[l["id"]] = (l["lat"], l["lon"])
            elif l.get("zip") in centroids:  # no coordinates given: use the ZIP's centre
                lots[l["id"]] = centroids[l["zip"]]
            else:
                raise ValueError(f"lot {l['id']!r} needs lat/lon, or a ZIP found in the gazetteer")
        by_zip, summary = catchment(deals, lots, centroids)
        by_zip.to_csv(out / "catchment_by_zip.csv", index=False)
        summary.to_csv(out / "catchment_summary.csv", index=False)
        lines += ["## Customer catchment", "```", summary.to_string(index=False), "```", ""]
        if acs is not None and not acs.empty:
            area = trade_area(lots, centroids, acs, deals, radius_miles)
            area.to_csv(out / "trade_area.csv", index=False)
            lines += [f"## Trade area within {radius_miles:g} miles (ACS households under $50k)",
                      "```", lot_summary(area).to_string(index=False), "```", "",
                      "### Whitespace ZIPs (large target pool, below-median penetration)", "```",
                      area[area["whitespace"]][["lot", "zip5", "miles", "hh_under_50k",
                                                 "median_hh_income", "deals_all_lots",
                                                 "penetration_per_1000"]].to_string(index=False),
                      "```", ""]

    if inventory is not None and not inventory.empty:
        as_of = str(inventory["snapshot_date"].max())
        v = by_vendor(inventory, as_of)
        v.to_csv(out / "inventory_by_vendor.csv", index=False)
        lines += [f"## Unsold inventory by vendor (as of {as_of})", "```", v.to_string(index=False), "```", "",
                  "### Units owned 45+ days", "```", aged(inventory, as_of).to_string(index=False), "```", ""]

    if macro is not None and not macro.empty:
        lines += ["## Macro context (national)", "```",
                  macro[["series", "title", "date", "value"]].to_string(index=False), "```", ""]
        lines += ["Sources:", *[f"- {citation(r.series, r.title, r.source)}"
                                for r in macro.itertuples()], ""]
        # Required by the FRED API Terms of Use wherever FRED data is shown.
        lines += ["---", FRED_NOTICE, f"FRED API Terms of Use: {TERMS_URL}", ""]

    path = out / "report.md"
    path.write_text("\n".join(lines))
    return path


def load_lots(path: str | Path) -> dict | None:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None
