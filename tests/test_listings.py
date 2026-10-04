from datetime import date

import pytest

from trgtmrkt import listings


def fake(records):
    calls = []

    def _fetch(url, key):
        calls.append(url)
        return {"records": records}
    _fetch.calls = calls
    return _fetch


REC = [
    {"vin": "AAA", "year": 2013, "make": "Chevrolet", "model": "Malibu",
     "priceUnformatted": 7900, "mileageUnformatted": 111000, "dealerName": "Lot A"},
    {"vin": "BBB", "year": 2015, "make": "Nissan", "model": "Rogue",
     "priceUnformatted": 12500, "mileageUnformatted": 90000},  # over price cap
    {"year": 2012, "make": "Ford", "model": "Focus", "priceUnformatted": 5000},  # no VIN
]


def test_dry_run_makes_no_call_and_logs_nothing(conn):
    f = fake(REC)
    res = listings.snapshot(conn, zip_code="37167", fetch=f)
    assert res["live"] is False and f.calls == []
    assert listings.calls_this_month(conn) == 0


def test_live_snapshot_stores_filtered_rows_and_logs_call(conn):
    f = fake(REC)
    res = listings.snapshot(conn, zip_code="37167", live=True, key="k", fetch=f,
                            today=date(2026, 10, 4))
    assert res["rows"] == 1 and len(f.calls) == 1
    assert "price_max=10000" in f.calls[0] and "zip=37167" in f.calls[0]
    assert listings.calls_this_month(conn) == 1


def test_monthly_cap_is_enforced(conn):
    f = fake(REC)
    with pytest.raises(listings.QuotaExceeded):
        listings.snapshot(conn, zip_code="37167", live=True, key="k", fetch=f,
                          monthly_cap=0)
    assert f.calls == []


def test_market_velocity_from_repeated_snapshots(conn):
    base = {"vin": "AAA", "year": 2013, "make": "Chevrolet", "model": "Malibu", "mileageUnformatted": 1}
    for d, price, extra in [(date(2026, 9, 6), 8500, []), (date(2026, 9, 20), 7900, []),
                            (date(2026, 10, 4), 7900, [])]:
        recs = [dict(base, priceUnformatted=price)]
        if d == date(2026, 9, 6):  # a second car that disappears before the last pull
            recs.append(dict(base, vin="CCC", priceUnformatted=6000))
        listings.snapshot(conn, zip_code="37167", live=True, key="k", fetch=fake(recs), today=d)
    v = listings.market_velocity(conn).set_index("vin")
    assert v.loc["AAA", "days_listed"] == 28 and v.loc["AAA", "price_change"] == -600
    assert bool(v.loc["AAA", "still_listed"]) and not bool(v.loc["CCC", "still_listed"])
