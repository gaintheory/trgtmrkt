from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .analysis.bands import BAND_COLUMNS
from .analysis.catchment import catchment, load_centroids
from .analysis.default import bad_rate_by, survivorship_warning
from .analysis.sales import sales_by


def _md(df: pd.DataFrame) -> str:
    return df.to_markdown(index=False) if hasattr(df, "to_markdown") and _has_tabulate() else df.to_string(index=False)


def _has_tabulate() -> bool:
    try:
        import tabulate  # noqa: F401
        return True
    except ImportError:
        return False


def build_report(deals: pd.DataFrame, out_dir: str | Path, lots_cfg: dict | None = None,
                 gazetteer: str | None = None) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# TRGT MRKT internal report", ""]
    warn = survivorship_warning(deals)
    if warn:
        lines += [f"> **Data warning:** {warn}", ""]
    lines.append(f"Deals: {len(deals)} across lots: {', '.join(sorted(deals['lot'].unique()))}")
    lines.append("Rows flagged `reliable=False` have fewer than 20 deals; treat as anecdotes.\n")

    for band in BAND_COLUMNS:
        s = sales_by(deals, band)
        s.to_csv(out / f"sales_by_{band}.csv", index=False)
        lines += [f"## Days to sell and gross by {band}", "```", s.to_string(index=False), "```", ""]
    for band in BAND_COLUMNS:
        b = bad_rate_by(deals, band)
        b.to_csv(out / f"bad_rate_by_{band}.csv", index=False)
        lines += [f"## Bad-outcome rate by {band}", "```", b.to_string(index=False), "```", ""]
    by_lot = bad_rate_by(deals, "lot")
    by_lot.to_csv(out / "bad_rate_by_lot.csv", index=False)
    lines += ["## Bad-outcome rate by lot", "```", by_lot.to_string(index=False), "```", ""]

    if lots_cfg:
        lots = {l["id"]: (l["lat"], l["lon"]) for l in lots_cfg["lots"]}
        by_zip, summary = catchment(deals, lots, load_centroids(gazetteer))
        by_zip.to_csv(out / "catchment_by_zip.csv", index=False)
        summary.to_csv(out / "catchment_summary.csv", index=False)
        lines += ["## Customer catchment", "```", summary.to_string(index=False), "```", ""]

    path = out / "report.md"
    path.write_text("\n".join(lines))
    return path


def load_lots(path: str | Path) -> dict | None:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None
