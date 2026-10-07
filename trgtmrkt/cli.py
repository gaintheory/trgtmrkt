from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import db, frazer_csv, ingest, listings, report, synthetic
from .sources import bls, census, fred, gazetteer, nhtsa


def _has_table(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone() is not None


def _acs_zips(args) -> set[str]:
    """ZIPs to size. Must include ZIPs with no deals (that is where whitespace
    is), so use everything near the lots rather than only ZIPs already served."""
    if args.zips:
        return set(args.zips.split(","))
    from .analysis.catchment import haversine_miles, load_centroids
    lots = report.load_lots("config/lots.json")
    if lots and gazetteer.DEFAULT_PATH.exists():
        cen = load_centroids(gazetteer.DEFAULT_PATH)
        pts = [(l["lat"], l["lon"]) for l in lots["lots"]]
        return {z for z, c in cen.items() if any(haversine_miles(p, c) <= args.acs_miles for p in pts)}
    raise RuntimeError("Need config/lots.json plus the ZCTA gazetteer (run refresh-public once "
                     "to fetch it), or pass --zips.")


def _refresh_public(conn, args) -> None:
    """Each source is independent: a missing key or a failure skips that source."""
    steps = []
    steps.append(("ZCTA centroids", lambda: str(gazetteer.download())))

    def _acs():
        df = census.fetch_acs(_acs_zips(args), year=args.acs_year)
        df.to_sql("acs_zcta", conn, if_exists="replace", index=False)
        return f"{len(df)} ZIPs"

    steps.append(("Census ACS", _acs))
    steps.append(("BLS county unemployment", lambda: f"{bls.refresh(conn)} rows"))
    def _fred():
        r = fred.refresh(conn)
        msg = f"{r.rows} rows"
        if r.copyrighted:
            msg += (f"; NOT STORED (third-party copyright, needs owner's permission): "
                    f"{', '.join(r.copyrighted)}")
        return msg

    steps.append(("FRED macro series", _fred))
    for name, fn in steps:
        try:
            print(f"ok    {name}: {fn()}")
        except Exception as exc:  # noqa: BLE001 - report and carry on
            print(f"skip  {name}: {exc}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="trgtmrkt")
    p.add_argument("--db", default=str(db.DEFAULT_DB))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("demo", help="load synthetic data (never real) into a separate demo DB")
    s.add_argument("--per-lot", type=int, default=300)

    s = sub.add_parser("ingest", help="de-identify a Frazer CSV export and load it")
    s.add_argument("csv")
    s.add_argument("--lot", required=True)
    s.add_argument("--as-of", default=None, help="date the export was run, YYYY-MM-DD (strongly recommended)")
    s.add_argument("--default-status", default="active",
                   help="status for rows with no status column (an M-8 export is active-only)")

    s = sub.add_parser("ingest-inventory", help="load a Frazer unsold-inventory export")
    s.add_argument("csv")
    s.add_argument("--lot", required=True)
    s.add_argument("--as-of", required=True, help="date the export was run, YYYY-MM-DD")

    s = sub.add_parser("report", help="write analyses to data/out")
    s.add_argument("--out", default="data/out")
    s.add_argument("--lots", default="config/lots.json")
    s.add_argument("--gazetteer", default=None)

    s = sub.add_parser("refresh-public", help="pull free public data (cached; skips sources with no key)")
    s.add_argument("--zips", default=None, help="comma list; default = ZIPs near your lots")
    s.add_argument("--acs-year", type=int, default=2023)
    s.add_argument("--acs-miles", type=float, default=30.0, help="ZIPs within this many miles of any lot")

    s = sub.add_parser("decode-vins", help="NHTSA-decode VINs from listing snapshots (free)")

    s = sub.add_parser("snapshot", help="weekly Auto.dev listing pull (dry-run unless --live)")
    s.add_argument("--zip", required=True)
    s.add_argument("--radius", type=int, default=25)
    s.add_argument("--price-max", type=int, default=10_000)
    s.add_argument("--live", action="store_true")
    s.add_argument("--cap", type=int, default=listings.DEFAULT_MONTHLY_CAP)

    args = p.parse_args(argv)

    if args.cmd == "demo":
        demo_db = "data/demo.db"
        conn = db.connect(demo_db)
        for lot, raw in synthetic.generate(args.per_lot).items():
            n = ingest.ingest_frazer(conn, raw, lot, salt="demo-salt")
            print(f"demo: loaded {n} synthetic deals for {lot}")
        deals = ingest.load_deals(conn)
        lots = report.load_lots("config/lots.example.json")
        acs = synthetic.acs()
        path = report.build_report(deals, "data/out/demo", lots, acs=acs)
        print(f"demo report: {path}")
        return 0

    conn = db.connect(args.db)
    if args.cmd == "ingest":
        raw, issues = frazer_csv.read_frazer(args.csv)
        for line in issues:
            print(f"warning: {line}")
        if not args.as_of:
            print("warning: no --as-of export date; months-on-book will assume the newest sale date")
        n = ingest.ingest_frazer(conn, raw, args.lot, default_status=args.default_status,
                                 export_date=args.as_of)
        print(f"{n} de-identified deals loaded for {args.lot} ({len(issues)} rows skipped)")
    elif args.cmd == "ingest-inventory":
        raw, issues = frazer_csv.read_frazer(args.csv)
        for line in issues:
            print(f"warning: {line}")
        n = ingest.ingest_inventory(conn, raw, args.lot, args.as_of)
        print(f"{n} inventory units loaded for {args.lot} ({len(issues)} rows skipped)")
    elif args.cmd == "report":
        deals = ingest.load_deals(conn)
        gaz = args.gazetteer or (str(gazetteer.DEFAULT_PATH) if gazetteer.DEFAULT_PATH.exists() else None)
        acs = pd.read_sql_query("SELECT * FROM acs_zcta", conn) if _has_table(conn, "acs_zcta") else None
        macro = fred.latest(conn) if _has_table(conn, "macro_series") else None
        inv = pd.read_sql_query("SELECT * FROM inventory", conn)
        path = report.build_report(deals, args.out, report.load_lots(args.lots), gaz, acs,
                                   macro=macro, inventory=inv if len(inv) else None)
        print(f"report: {path}")
    elif args.cmd == "refresh-public":
        _refresh_public(conn, args)
    elif args.cmd == "decode-vins":
        vins = [r[0] for r in conn.execute("SELECT DISTINCT vin FROM listing_snapshots")]
        print(f"{nhtsa.decode(conn, vins)} VINs decoded")
    elif args.cmd == "snapshot":
        res = listings.snapshot(conn, zip_code=args.zip, radius=args.radius,
                                price_max=args.price_max, live=args.live, monthly_cap=args.cap)
        print(res if args.live else f"DRY RUN (no call made): {res}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
