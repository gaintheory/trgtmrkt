# Free and public data

Status is what was actually checked from this environment on 2026-10-04, not
what the providers' marketing pages say. Re-verify before relying on any row.

## Wired in (`python -m trgtmrkt.cli refresh-public`)

| Source | Gives you | Key | Status |
|---|---|---|---|
| Census ZCTA gazetteer (`sources/gazetteer.py`) | Lat/lon centroid per ZIP, for distance and trade areas | none | **Live-tested**: 33,791 ZCTAs parsed, ZIP 37167 resolves |
| Census ACS 5-year (`sources/census.py`) | Per ZIP: households by income, renter share, no-vehicle households, poverty, unemployment, drive-alone commuters, rent | free, `CENSUS_API_KEY` ([signup](https://api.census.gov/data/key_signup.html)) | **Keyless call is refused ("Missing Key")**; parser and derived ratios unit-tested on canned payloads, **not yet run live**. Confirm the variable list on the first real call |
| BLS LAUS (`sources/bls.py`) | Monthly county unemployment rate | optional free `BLS_API_KEY` | **Live-tested** (Rutherford returned 3.1% for Aug 2026), then the keyless daily limit was hit from this shared IP. **Get a key.** Series ID format pinned by a test |
| FRED (`sources/fred.py`) | National gas price, used-car CPI, unemployment | free, `FRED_API_KEY` | Refused without a key (400). Parser unit-tested, **not run live**. Confirm the series IDs |
| NHTSA vPIC (`sources/nhtsa.py`) | VIN decode: body class, drivetrain, fuel, engine | none | **Live-tested** (batch POST must be form-encoded) |

Each source is cached on disk (`data/reference/cache/`), keys are never written
to the cache, and a failed or rate-limited response is never cached. A missing
key skips that source with a message instead of failing the run.

## Worth adding next (not built)

| Source | Why it matters for BHPH | Notes |
|---|---|---|
| Census LODES origin-destination | Where residents of your ZIPs work, i.e. employer concentration and commute | Directory reachable (`lehd.ces.census.gov/data/lodes/LODES8/tn/od/`). Block-level gzip files, needs aggregating to ZIP. Not downloaded or parsed |
| Tennessee WARN notices | Layoff early warning for collections | Published by the state Dept. of Labor and Workforce Development. Format and URL **not checked**; may be HTML or PDF needing a scraper |
| TN Motor Vehicle Commission dealer licenses | Competitor saturation map, new and closed lots | **Not checked.** A lookup is known to exist; whether a bulk download exists is unknown |
| FDIC National Survey of Unbanked and Underbanked Households | Credit-access proxy by state/metro | Bulk CSV download; not integrated |
| CFPB / NY Fed credit and auto-loan delinquency | Macro risk context | Mostly national or state level |

## Not free in the way the first plan assumed

- **Auto.dev**: Autodoss's `comps.ts` documents a paid per-call starter tier, not
  a free quota. Check your actual plan and its terms before `snapshot --live`.
- **MarketCheck**: free-tier limits and commercial-use terms are unverified.
  Nothing in this repo calls it.
