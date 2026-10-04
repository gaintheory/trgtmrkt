from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import db, ingest, listings, report, synthetic


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="trgtmrkt")
    p.add_argument("--db", default=str(db.DEFAULT_DB))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("demo", help="load synthetic data (never real) into a separate demo DB")
    s.add_argument("--per-lot", type=int, default=300)

    s = sub.add_parser("ingest", help="de-identify a Frazer CSV export and load it")
    s.add_argument("csv")
    s.add_argument("--lot", required=True)
    s.add_argument("--default-status", default="active",
                   help="status for rows with no status column (an M-8 export is active-only)")

    s = sub.add_parser("report", help="write analyses to data/out")
    s.add_argument("--out", default="data/out")
    s.add_argument("--lots", default="config/lots.json")
    s.add_argument("--gazetteer", default=None)

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
        path = report.build_report(deals, "data/out/demo", lots)
        print(f"demo report: {path}")
        return 0

    conn = db.connect(args.db)
    if args.cmd == "ingest":
        raw = pd.read_csv(args.csv, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        n = ingest.ingest_frazer(conn, raw, args.lot, default_status=args.default_status)
        print(f"{n} de-identified deals loaded for {args.lot}")
    elif args.cmd == "report":
        deals = ingest.load_deals(conn)
        path = report.build_report(deals, args.out, report.load_lots(args.lots), args.gazetteer)
        print(f"report: {path}")
    elif args.cmd == "snapshot":
        res = listings.snapshot(conn, zip_code=args.zip, radius=args.radius,
                                price_max=args.price_max, live=args.live, monthly_cap=args.cap)
        print(res if args.live else f"DRY RUN (no call made): {res}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
