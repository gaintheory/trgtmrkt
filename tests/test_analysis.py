import math

import pandas as pd

from trgtmrkt.analysis.bands import add_bands, is_bad_outcome, wilson
from trgtmrkt.analysis.catchment import catchment, haversine_miles, load_centroids
from trgtmrkt.analysis.default import bad_rate_by, survivorship_warning
from trgtmrkt.analysis.sales import sales_by


def test_wilson_interval_basics():
    lo, hi = wilson(50, 100)
    assert 0.40 < lo < 0.5 < hi < 0.60
    assert all(math.isnan(x) for x in wilson(0, 0))
    assert wilson(0, 10)[0] == 0.0


def test_bad_outcome_definition():
    d = pd.DataFrame({"status": ["active", "repossessed", "paid_off", "active"],
                      "days_past_due": [0, 0, 0, 75]})
    assert list(is_bad_outcome(d)) == [False, True, False, True]


def test_planted_down_payment_signal_is_recovered(deals):
    r = bad_rate_by(deals, "down_pct_band").set_index("down_pct_band")
    assert r.loc["20%+", "bad_rate"] < r.loc["<5%", "bad_rate"]


def test_planted_age_signal_is_recovered(deals):
    r = bad_rate_by(deals, "age_band").set_index("age_band")
    assert r.loc["12+ yrs", "bad_rate"] > r.loc["6-8 yrs", "bad_rate"]


def test_pricier_cars_sell_slower_and_gross_more(deals):
    s = sales_by(deals, "price_band").set_index("price_band")
    assert s.loc["$7.5-10k", "median_days_on_lot"] > s.loc["<$5k", "median_days_on_lot"]
    assert s.loc["$7.5-10k", "median_gross"] > s.loc["<$5k", "median_gross"]


def test_small_groups_are_flagged_unreliable(deals):
    r = bad_rate_by(deals, "model_key")
    assert (r.loc[r["n"] < 20, "reliable"] == False).all()  # noqa: E712
    assert r["reliable"].any()


def test_survivorship_warning_fires_on_active_only_export(deals):
    assert survivorship_warning(deals) is None
    active_only = deals[deals["status"] == "active"]
    assert "understated" in survivorship_warning(active_only)


def test_haversine_known_distance():
    # Smyrna to Murfreesboro is roughly 15 miles as the crow flies.
    d = haversine_miles((36.00, -86.52), (35.85, -86.40))
    assert 12 < d < 20


def test_catchment_shapes(deals):
    lots = {"smyrna": (36.00, -86.52), "la_vergne": (36.01, -86.58), "murfreesboro": (35.85, -86.40)}
    by_zip, summary = catchment(deals, lots, load_centroids())
    assert abs(by_zip.groupby("lot")["share"].sum() - 1).max() < 0.01
    assert set(summary["lot"]) == set(lots)
    # Murfreesboro's lot sits in its own ZIPs, so it should draw closer than Smyrna's.
    s = summary.set_index("lot")
    assert s.loc["murfreesboro", "median_miles"] < s.loc["smyrna", "median_miles"]
