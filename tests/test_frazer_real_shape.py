"""Shapes seen in a real Frazer export that tidy synthetic data did not have."""
import io

import pandas as pd

from trgtmrkt import db, ingest
from trgtmrkt.analysis import inventory as inv_analysis
from trgtmrkt.analysis.default import bad_rate_by, financed_only, seasoned, survivorship_warning
from trgtmrkt.deidentify import deidentify
from trgtmrkt.frazer_csv import read_frazer


def csv_text(rows):
    return io.StringIO("\n".join(rows) + "\n")


def test_reader_drops_the_extra_trailing_field_instead_of_shifting_columns():
    # header has 3 columns; every data row has 4 fields (trailing empty), like Frazer
    raw, issues = read_frazer(csv_text(['"Stock #","Sale Date","Zip"',
                                        '"A1","04/07/26","37167",', '"A2","04/08/26","37130",']))
    assert issues == [] and list(raw["Stock #"]) == ["A1", "A2"]
    assert list(raw["Zip"]) == ["37167", "37130"]  # not shifted one column left


def test_reader_skips_torn_rows_and_reports_line_numbers_not_content():
    raw, issues = read_frazer(csv_text(['"Stock #","Sale Date","Zip"', '"A1","04/07/26","37167",',
                                        '"SECRET NAME fragment"', '"A3","04/09/26","37167",']))
    assert list(raw["Stock #"]) == ["A1", "A3"]
    assert len(issues) == 1 and "row 3" in issues[0] and "SECRET" not in issues[0]


def test_reader_renames_duplicate_headers_leftmost_wins():
    raw, _ = read_frazer(csv_text(['"Stock #","Mileage","Mileage"', '"A1","100","999",']))
    assert list(raw.columns) == ["Stock #", "Mileage", "Mileage.1"] and raw.loc[0, "Mileage"] == "100"


def _frame(**cols):
    n = len(next(iter(cols.values())))
    base = {"Stock #": [f"S{i}" for i in range(n)]}
    base.update(cols)
    return pd.DataFrame(base)


def test_status_for_cash_wholesale_writeoff_paidoff_repo_active():
    raw = _frame(**{
        "Type of Sale": ["Cash", "Wholesale", "Buy Here - Pay Here", "Buy Here - Pay Here",
                         "Buy Here - Pay Here", "Buy Here - Pay Here", "Outside Financing"],
        "Amt Financed": ["0", "0", "5000", "5000", "5000", "5000", "9000"],
        "Balance": ["0", "0", "0", "0", "1200", "800", "0"],
        "Write Off Date": ["", "", "", "01/01/26", "", "", ""],
        "Repo Date Out": ["", "", "", "", "", "02/01/26", ""],
        "Repo Date Redeemed": ["", "", "", "", "", "", ""],
    })
    out = deidentify(raw, "l", "s")
    assert list(out["status"]) == ["cash", "wholesale", "paid_off", "charged_off", "active",
                                   "repossessed", "outside_financing"]


def test_default_rates_use_financed_deals_and_seasoned_only(deals):
    d = deals.copy()
    extra = d.head(50).copy()
    extra["status"] = "cash"
    extra["deal_id"] = [f"cash{i}" for i in range(50)]
    both = pd.concat([d, extra])
    assert len(financed_only(both)) == len(d)  # cash rows never enter default rates
    young = d.copy()
    young["sale_date"] = "2026-09-20"
    young.loc[young.index[:30], "sale_date"] = "2025-01-01"
    assert len(seasoned(young, 180, as_of="2026-09-29")) == 30
    # an active-only book (cash rows ignored) still triggers the warning
    only_active = pd.concat([d[d["status"] == "active"], extra])
    assert "understated" in survivorship_warning(only_active)


def test_inventory_ingest_drops_vin_and_computes_margin_and_age():
    raw = _frame(**{"Vehicle Year": ["2016", "2014"], "Vehicle Make": ["FORD", "JEEP"],
                    "Vehicle Model": ["ESCAPE", "GRAND CHEROKEE"], "Vehicle VIN": ["1FMCU0GX3GUA60311", "X"],
                    "Mileage": ["150000", "140000"], "Original Cost": ["4500", "6000"],
                    "Added Costs": ["2000", ""], "Retail Price": ["8995", "0"],
                    "Purchase Date": ["04/07/26", "08/04/26"], "Ready To Sell Date": ["04/14/26", ""],
                    "Vendor": ["MUSIC CITY AUTO AUCTION", ""]})
    conn = db.connect(":memory:")
    assert ingest.ingest_inventory(conn, raw, "l", "2026-10-07", salt="s") == 2
    got = pd.read_sql_query("SELECT * FROM inventory", conn)
    assert "1FMCU0GX3GUA60311" not in got.to_csv() and "vin" not in " ".join(got.columns).lower()
    prep = inv_analysis.prepare(got, "2026-10-07").set_index("model")
    assert prep.loc["ESCAPE", "margin_potential"] == 8995 - 6500
    assert pd.isna(prep.loc["GRAND CHEROKEE", "margin_potential"])  # unpriced, not zero
    assert prep.loc["ESCAPE", "days_owned"] == 183


def test_bad_rate_with_no_qualifying_rows_returns_empty_not_crash(deals):
    empty = bad_rate_by(deals[deals["status"] == "cash"], "price_band")
    assert empty.empty
    assert list(empty.columns)[-1] == "reliable"


def test_year_prefers_four_digit_block_and_normalizes_two_digit_and_zero():
    raw = _frame(**{"Year": ["16", "0", "99"], "Vehicle Year": ["2016", "2014", ""],
                    "Vehicle Make": ["FORD"] * 3, "Vehicle Model": ["X"] * 3, "Make": ["F"] * 3, "Model": ["X"] * 3})
    got4 = deidentify(raw, "l", "s")["year"]
    assert list(got4[:2]) == [2016, 2014] and pd.isna(got4[2])
    only_short = _frame(**{"Year": ["16", "0", "99"], "Make": ["FORD"] * 3, "Model": ["X"] * 3})
    got = list(deidentify(only_short, "l", "s")["year"])
    assert got[0] == 2016 and pd.isna(got[1]) and got[2] == 1999


def test_retail_scope_drops_wholesale_and_repo_sourced_cars():
    from trgtmrkt.analysis.sales import retail_scope
    d = pd.DataFrame({"sale_type": ["Cash", "Wholesale", "Buy Here - Pay Here", "Buy Here - Pay Here"],
                      "vehicle_source": ["Auction", "Auction", "Repossessio", "Trade"]})
    assert list(retail_scope(d).index) == [0, 3]
