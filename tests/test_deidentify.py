import pandas as pd
import pytest

from trgtmrkt.deidentify import FORBIDDEN_OUTPUT, deal_id, deidentify


def test_output_has_no_pii_columns_or_values(raw_exports):
    out = deidentify(raw_exports["smyrna"], "smyrna", "salt")
    assert not (set(out.columns) & FORBIDDEN_OUTPUT)
    blob = out.to_csv()
    for needle in ("Testperson", "example.invalid", "555-0100", "Fake St", "SYNTH",
                   "Example Co", "Alex", "38,000"):
        assert needle not in blob, needle


def test_zip_is_five_digits_only(raw_exports):
    out = deidentify(raw_exports["smyrna"], "smyrna", "salt")
    assert out["zip5"].str.fullmatch(r"\d{5}").all()


def test_deal_id_is_salted_and_lot_scoped():
    assert deal_id("a", "1", "s1") != deal_id("a", "1", "s2")
    assert deal_id("a", "1", "s") != deal_id("b", "1", "s")


def test_money_dates_and_vehicle_string_parsing():
    raw = pd.DataFrame([{
        "Stock#": "X1", "Vehicle": "14 CHEVROLET Malibu LT", "Sale Date": "3/5/25",
        "Sales Price": "$8,450.00", "Down Payment": "($500.00)", "Zip Code": "37167-1234",
        "Days past Due": "", "Profit On Sale": "$2,100.50",
    }])
    out = deidentify(raw, "smyrna", "s").iloc[0]
    assert (out["year"], out["make"], out["model"]) == (2014, "Chevrolet", "Malibu LT")
    assert out["sale_price"] == 8450.0 and out["down_payment"] == -500.0
    assert out["sale_date"] == "2025-03-05" and out["zip5"] == "37167"
    assert out["days_past_due"] == 0  # blank means nothing overdue, not unknown


def test_duplicate_stock_numbers_collapse_and_missing_stock_column_errors():
    raw = pd.DataFrame({"Stock #": ["A", "A", "B"], "Sales Price": ["1", "2", "3"]})
    assert len(deidentify(raw, "l", "s")) == 2
    with pytest.raises(ValueError):
        deidentify(pd.DataFrame({"Nope": [1]}), "l", "s")


def test_status_inference_without_status_column():
    raw = pd.DataFrame({"Stock #": ["A", "B", "C"],
                        "Repo Date Out": ["1/1/2026", "1/1/2026", ""],
                        "Repo Date Redeemed": ["", "2/1/2026", ""]})
    assert list(deidentify(raw, "l", "s")["status"]) == ["repossessed", "active", "active"]


def test_ingest_is_idempotent(conn, raw_exports):
    from trgtmrkt import ingest
    before = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
    ingest.ingest_frazer(conn, raw_exports["smyrna"], "smyrna", salt="test-salt")
    assert conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0] == before
