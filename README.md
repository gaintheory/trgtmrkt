# TRGT MRKT

Market research for buy-here-pay-here lots in Middle Tennessee. Starts as an
internal tool for a three-lot operator and grows from there.

Dealer data comes from Frazer exports (the same exports the Autodoss DMS
imports). This repo only ever stores a **de-identified** copy.

## Quick start

```bash
pip install -r requirements.txt
python -m trgtmrkt.cli demo        # synthetic data end to end -> data/out/demo/report.md
python -m pytest
```

The demo data is fake and its patterns are planted by `synthetic.py`; it proves
the pipeline works, not anything about your lots.

## With real data

1. In Frazer, export each lot **with column headers and with closed accounts**
   (paid off, repossessed, charged off). An active-only export hides every bad
   outcome and the report will say so. Save under `data/private/` (gitignored).
2. `python -m trgtmrkt.cli ingest data/private/smyrna.csv --lot smyrna --as-of 2026-10-06`
   (`--as-of` is the date you ran the export; months-on-book needs it. For the
   inventory export use `ingest-inventory ... --as-of`.)
   (repeat per lot). Names, phones, street addresses, birthdays, license numbers,
   employers, incomes, credit data and VINs are never read. ZIP5 is kept for
   catchment. Deal IDs are salted hashes; the salt lives in `data/private/.salt`.
3. Copy `config/lots.example.json` to `config/lots.json` with real coordinates.
   For accurate distances, download the Census ZCTA gazetteer into
   `data/reference/` and pass `--gazetteer`.
4. `python -m trgtmrkt.cli report` writes CSVs and `report.md` to `data/out/`.

If a header is not recognised, add its spelling to `ALIASES` in
`trgtmrkt/deidentify.py`.

## What it produces

| Analysis | Module | Note |
|---|---|---|
| Days to sell and gross by price / down % / age / mileage band | `analysis/sales.py` | Uses Frazer cost, profit and days-on-lot columns |
| Bad-outcome rate by band, with 95% intervals | `analysis/default.py` | Bad = repossessed, charged off, or 60+ days past due. Warns on active-only data |
| Cumulative bad rate by months on book (Kaplan-Meier) | `analysis/survival.py` | Repo or write-off with a known date; each note counts only for the time actually observed, so young notes do not flatter the rate. Read a row only when `at_risk` is large |
| Customer catchment per lot | `analysis/catchment.py` | ZIP counts, distance to lot, overlap between lots |
| Trade-area sizing and whitespace ZIPs (ACS + your deals) | `analysis/market.py` | Households under $50k are a proxy for the buyer pool, not a credit measure |
| Weekly local listing snapshot and market velocity | `listings.py` | Dry-run by default, monthly call cap, days-on-market from first/last seen |

Small book, so bands are coarse and every row carries `reliable` (n >= 20).
Per-model cuts exist but are mostly anecdotes until you pool lots.

## Free public data

```bash
export CENSUS_API_KEY=...   # free; ACS demographics
export BLS_API_KEY=...      # free; the keyless daily limit runs out quickly
export FRED_API_KEY=...     # free; macro series
python -m trgtmrkt.cli refresh-public
python -m trgtmrkt.cli report
```

`refresh-public` fetches the Census ZIP centroids, ACS demographics for every
ZIP within 30 miles of your lots (including ZIPs where you sell nothing, which is
where whitespace is), BLS county unemployment and FRED series. Sources without a
key are skipped. The report then adds a trade-area table and a whitespace list.
See `docs/free-data-sources.md` for what was verified live and what was not.

## Weekly listing snapshot

```bash
python -m trgtmrkt.cli snapshot --zip 37167 --radius 25            # dry run
AUTO_DEV_API_KEY=... python -m trgtmrkt.cli snapshot --zip 37167 --live
```

Before the first `--live` run, read the `listings.py` docstring: pagination and
the price filter are unverified against the live API, and your plan's terms must
allow this use.

## Rules of the road

- FRED data carries a required notice and a copyright check; see
  `docs/free-data-sources.md`. Do not name a domain or host after FRED or the Fed.
- Never commit anything from `data/private/`, `data/out/` or any `.db`.
- Outputs shared outside the owner's lots should be aggregates, with small cells
  suppressed.
