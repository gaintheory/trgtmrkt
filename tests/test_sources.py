import json
import sqlite3

import pandas as pd
import pytest

from trgtmrkt import db, synthetic
from trgtmrkt.analysis.catchment import DEMO_CENTROIDS
from trgtmrkt.analysis.market import lot_summary, trade_area
from trgtmrkt.sources import bls, census, fred, gazetteer, http, nhtsa


def acs_payload(rows):
    header = ["NAME", *census.VARIABLES, "zip code tabulation area"]
    return json.dumps([header, *rows]).encode()


def acs_row(zip5, **over):
    vals = {v: "0" for v in census.VARIABLES}
    vals.update({"B01003_001E": "20000", "B19013_001E": "52000", "B19001_001E": "1000",
                 "B19001_002E": "50", "B19001_003E": "50", "B19001_004E": "50", "B19001_005E": "50",
                 "B19001_006E": "50", "B19001_007E": "50", "B19001_008E": "50", "B19001_009E": "50",
                 "B19001_010E": "50", "B25003_001E": "900", "B25003_003E": "300",
                 "B08201_002E": "40", "B08301_001E": "800", "B08301_003E": "600",
                 "B17001_001E": "5000", "B17001_002E": "750", "B23025_003E": "900",
                 "B23025_005E": "45"})
    vals.update(over)
    return [f"ZCTA5 {zip5}", *vals.values(), zip5]


def test_acs_parse_derives_ratios_and_drops_sentinels():
    payload = acs_payload([acs_row("37167"), acs_row("37130", B19013_001E="-666666666"),
                           acs_row("99999")])
    df = census.parse_acs(payload, {"37167", "37130"}).set_index("zip5")
    assert set(df.index) == {"37167", "37130"}
    r = df.loc["37167"]
    assert r["hh_under_50k"] == 450 and r["pct_hh_under_50k"] == pytest.approx(0.45)
    assert r["renter_share"] == pytest.approx(1 / 3)
    assert r["poverty_rate"] == pytest.approx(0.15) and r["unemployment_rate"] == pytest.approx(0.05)
    assert pd.isna(df.loc["37130", "median_hh_income"])  # sentinel -> NaN


def test_acs_requires_key(monkeypatch):
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="CENSUS_API_KEY"):
        census.fetch_acs({"37167"})


def test_cache_hits_disk_strips_key_and_never_caches_errors(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        return b'{"ok": 1}'
    a = http.cached_get("https://x.test/d?a=1&key=SECRET1", fetch=fetch, cache_dir=tmp_path)
    b = http.cached_get("https://x.test/d?a=1&key=SECRET2", fetch=fetch, cache_dir=tmp_path)
    assert a == b and len(calls) == 1  # same cache entry regardless of key
    assert all("SECRET" not in p.name and "SECRET" not in p.read_text() for p in tmp_path.iterdir())

    def boom(_):
        raise RuntimeError("rate limited")
    with pytest.raises(RuntimeError):
        http.cached_get("https://x.test/bad", fetch=lambda u: b"limit", cache_dir=tmp_path,
                        validate=boom)
    assert len(list(tmp_path.iterdir())) == 1  # the bad response was not stored


def test_bls_parse_and_refresh(tmp_path):
    ok = json.dumps({"status": "REQUEST_SUCCEEDED", "Results": {"series": [{"data": [
        {"year": "2026", "period": "M08", "value": "3.1"},
        {"year": "2026", "period": "M13", "value": "3.3"},  # annual average: skipped
        {"year": "2026", "period": "M07", "value": "-"}]}]}}).encode()
    conn = db.connect(":memory:")
    assert bls.refresh(conn, {"47149": "Rutherford"}, fetch=lambda u: ok, cache_dir=tmp_path) == 1
    assert [tuple(r) for r in conn.execute("SELECT * FROM county_unemployment")] == [("47149", "2026-08", 3.1)]
    assert bls.series_id("47149") == "LAUCN471490000000003"
    bad = json.dumps({"status": "REQUEST_NOT_PROCESSED", "message": ["limit"]}).encode()
    with pytest.raises(RuntimeError):
        bls.refresh(conn, {"47037": "Davidson"}, fetch=lambda u: bad, cache_dir=tmp_path / "b")


def test_fred_parse_skips_missing_and_needs_key(monkeypatch):
    out = fred.parse(json.dumps({"observations": [{"date": "2026-01-05", "value": "3.10"},
                                                  {"date": "2026-01-12", "value": "."}]}).encode(), "GASREGW")
    assert out == [("GASREGW", "2026-01-05", 3.10)]
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        fred.refresh(db.connect(":memory:"))


def test_nhtsa_batches_of_50_and_skips_known(tmp_path):
    conn = db.connect(":memory:")
    posted = []

    def post(url, payload):
        vins = payload["data"].split(";")
        posted.append(len(vins))
        return json.dumps({"Results": [{"VIN": v, "BodyClass": "Sedan", "ErrorCode": "0"} for v in vins]}).encode()
    vins = [f"VIN{i:014d}" for i in range(120)]
    assert nhtsa.decode(conn, vins + vins[:5], post=post) == 120
    assert posted == [50, 50, 20]
    assert nhtsa.decode(conn, vins, post=post) == 0  # already stored


def test_gazetteer_extracts_txt(tmp_path):
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("2023_Gaz_zcta_national.txt", "GEOID\tINTPTLAT\tINTPTLONG  \n37167\t35.96\t-86.52\n")
    dest = gazetteer.download(dest=tmp_path / "g.txt", fetch=lambda u: buf.getvalue())
    from trgtmrkt.analysis.catchment import load_centroids
    assert load_centroids(dest)["37167"] == (35.96, -86.52)


def test_trade_area_flags_whitespace(deals):
    acs = synthetic.acs()
    lots = {"smyrna": (36.00, -86.52)}
    area = trade_area(lots, DEMO_CENTROIDS, acs, deals, radius_miles=40)
    assert not area.empty and (area["miles"] <= 40).all()
    assert set(area.columns) >= {"hh_under_50k", "deals_all_lots", "penetration_per_1000", "whitespace"}
    # Add a big ZIP the operator has never sold into: it must be flagged.
    extra = pd.concat([acs, pd.DataFrame([{**acs.iloc[0].to_dict(), "zip5": "37122",
                                           "hh_under_50k": 20_000, "households": 30_000}])]
                      ).drop_duplicates("zip5", keep="last")
    area2 = trade_area(lots, DEMO_CENTROIDS, extra, deals[deals["zip5"] != "37122"], radius_miles=40)
    row = area2[area2["zip5"] == "37122"].iloc[0]
    assert row["deals_all_lots"] == 0 and bool(row["whitespace"])
    assert lot_summary(area2).loc[0, "target_households"] > 0


# ---- FRED terms compliance -------------------------------------------------

def _fred_fetch(notes_by_series):
    """Fake FRED: /series returns notes, /series/observations returns two points."""
    calls = []

    def fetch(url):
        calls.append(url)
        sid = url.split("series_id=")[1].split("&")[0]
        if "/series/observations" in url:
            return json.dumps({"observations": [{"date": "2026-09-01", "value": "1.5"},
                                                {"date": "2026-10-01", "value": "2.5"}]}).encode()
        return json.dumps({"seriess": [{"id": sid, "title": f"Title {sid}",
                                        "notes": notes_by_series[sid]}]}).encode()
    fetch.calls = calls
    return fetch


def test_fred_stores_clean_series_and_records_meta(tmp_path):
    conn = db.connect(":memory:")
    f = _fred_fetch({"GASREGW": "Weighted average based on sampling."})
    r = fred.refresh(conn, {"GASREGW": ""}, key="k", fetch=f, cache_dir=tmp_path)
    assert r.rows == 2 and r.copyrighted == []
    meta = conn.execute("SELECT title, copyrighted FROM macro_series_meta").fetchone()
    assert tuple(meta) == ("Title GASREGW", 0)


def test_fred_refuses_to_store_copyrighted_series(tmp_path):
    conn = db.connect(":memory:")
    conn.execute("INSERT INTO macro_series VALUES ('OWNED', '2026-01-01', 9.9)")  # stale earlier pull
    f = _fred_fetch({"OWNED": "Copyright, 2026, Some Vendor. Used with permission.",
                     "OK": "Public data."})
    r = fred.refresh(conn, {"OWNED": "", "OK": ""}, key="k", fetch=f, cache_dir=tmp_path)
    assert r.copyrighted == ["OWNED"] and r.rows == 2  # only OK's two points
    assert conn.execute("SELECT COUNT(*) FROM macro_series WHERE series='OWNED'").fetchone()[0] == 0
    assert not any("series/observations" in u and "OWNED" in u for u in f.calls)  # never fetched
    assert conn.execute("SELECT copyrighted FROM macro_series_meta WHERE series='OWNED'").fetchone()[0] == 1


def test_fred_fails_closed_when_the_copyright_check_cannot_run(tmp_path):
    conn = db.connect(":memory:")

    def fetch(url):
        if "/series/observations" in url:
            return json.dumps({"observations": [{"date": "2026-10-01", "value": "1"}]}).encode()
        return json.dumps({"error_code": 400, "error_message": "bad key"}).encode()
    with pytest.raises(Exception):
        fred.refresh(conn, {"GASREGW": ""}, key="k", fetch=fetch, cache_dir=tmp_path)
    assert conn.execute("SELECT COUNT(*) FROM macro_series").fetchone()[0] == 0


def test_report_carries_fred_notice_only_when_fred_data_is_shown(deals, tmp_path):
    from trgtmrkt import report
    plain = report.build_report(deals, tmp_path / "a").read_text()
    assert fred.FRED_NOTICE not in plain

    conn = db.connect(":memory:")
    fred.refresh(conn, {"GASREGW": ""}, key="k", fetch=_fred_fetch({"GASREGW": "ok"}),
                 cache_dir=tmp_path / "c")
    shown = report.build_report(deals, tmp_path / "b", macro=fred.latest(conn)).read_text()
    assert fred.FRED_NOTICE in shown and fred.TERMS_URL in shown
    assert "retrieved from FRED, Federal Reserve Bank of St. Louis" in shown
    assert "https://fred.stlouisfed.org/series/GASREGW" in shown
    assert "2026-10-01" in shown and "2.5" in shown  # latest point, not the older one
