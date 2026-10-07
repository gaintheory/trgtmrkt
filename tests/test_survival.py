import pandas as pd
import pytest

from trgtmrkt.analysis.survival import km, months_on_book, observations, data_notes, at_month


def notes(rows):
    base = {"status": "active", "sale_date": "2025-01-01", "repo_date": None, "write_off_date": None,
            "last_payment_date": None, "days_past_due": 0}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_hand_computed_kaplan_meier():
    # as_of 2025-04-11 = 100 days after the Jan 1 sales
    d = notes([
        {"status": "repossessed", "repo_date": "2025-01-31"},                 # event at 30 days
        {},                                                                    # observed 100 days
        {"status": "paid_off", "last_payment_date": "2025-03-02"},            # ends at 60 days, no event
        {"status": "repossessed", "repo_date": "2025-04-01"},                 # event at 90 days
    ])
    obs = observations(d, as_of="2025-04-11")
    table = km(obs)
    # t=30d: 4 at risk, 1 event -> S=.75.  t=90d: 2 still observed (100d note and the 90d event)
    # -> S=.75*(1-1/2)=.375
    assert list(table["at_risk"]) == [4, 2] and table["survival"].iloc[-1] == pytest.approx(0.375)
    row = at_month(obs, table, 3.5)  # 3.5 months = 106 days: both events are behind us
    assert row["cum_bad"] == pytest.approx(0.625)


def test_young_notes_do_not_dilute_the_rate_the_way_a_plain_rate_does():
    old_bad = [{"status": "repossessed", "sale_date": "2024-01-01", "repo_date": "2024-04-01"}] * 5
    old_ok = [{"sale_date": "2024-01-01"}] * 5
    young = [{"sale_date": "2025-03-25"}] * 90  # a few days old: cannot have defaulted yet
    d = notes(old_bad + old_ok + young)
    plain_rate = 5 / len(d)  # 5%
    out = months_on_book(d, as_of="2025-04-01", milestones=(3,))
    assert out.loc[0, "cum_bad"] == pytest.approx(0.5)  # of the 10 old notes, half went bad by month 3
    assert out.loc[0, "cum_bad"] > plain_rate * 5


def test_cash_and_wholesale_never_enter_and_undated_or_late_notes_are_counted_separately():
    d = notes([{"status": "cash"}, {"status": "wholesale"},
               {"status": "repossessed"},                       # bad but no date
               {"days_past_due": 75},                           # late, not repossessed
               {"status": "charged_off", "write_off_date": "2025-02-15"}])
    n = data_notes(d, as_of="2025-04-11")
    assert n == {"notes": 3, "events": 1, "undated_bad": 1, "late_not_repossessed": 1,
                 "max_months_observed": 3.3}


def test_earliest_of_repo_and_write_off_is_the_event_date():
    d = notes([{"status": "repossessed", "repo_date": "2025-03-01", "write_off_date": "2025-02-01"}])
    assert observations(d, as_of="2025-04-11").loc[0, "months"] == pytest.approx(31 / 30.4375)


def test_no_milestone_beyond_the_longest_observation_and_group_cuts_work(deals):
    out = months_on_book(deals, milestones=(3, 12, 120))
    assert 120 not in set(out["month"]) and set(out["month"]) == {3, 12}
    assert out["cum_bad"].is_monotonic_increasing
    by_down = months_on_book(deals, by="down_pct_band", milestones=(12,))
    assert len(by_down) >= 2 and by_down["cum_bad"].between(0, 1).all()


def test_planted_down_payment_signal_shows_up_on_the_curve(deals):
    g = months_on_book(deals, by="down_pct_band", milestones=(12,)).set_index("group")
    assert g.loc["20%+", "cum_bad"] < g.loc["<5%", "cum_bad"]


def test_recorded_export_date_extends_observation_beyond_the_newest_sale():
    from trgtmrkt.analysis.default import resolve_as_of
    d = notes([{"sale_date": "2025-01-01"}])
    assert resolve_as_of(d) == pd.Timestamp("2025-01-01")            # fallback: newest sale
    d["export_date"] = "2025-04-11"
    assert resolve_as_of(d) == pd.Timestamp("2025-04-11")            # recorded export date wins
    assert resolve_as_of(d, "2025-06-01") == pd.Timestamp("2025-06-01")  # explicit beats both
    months = observations(d).loc[0, "months"]
    assert months == pytest.approx(100 / 30.4375)


def test_ingest_stores_export_date_and_cli_warns_without_it(conn, raw_exports, tmp_path, capsys):
    from trgtmrkt import cli, ingest
    ingest.ingest_frazer(conn, raw_exports["smyrna"], "smyrna", salt="test-salt", export_date="2026-10-06")
    assert conn.execute("SELECT DISTINCT export_date FROM deals WHERE lot='smyrna'").fetchall()[0][0] == "2026-10-06"
    p = tmp_path / "x.csv"
    raw_exports["smyrna"].to_csv(p, index=False)
    cli.main(["--db", str(tmp_path / "t.db"), "ingest", str(p), "--lot", "smyrna"])
    assert "--as-of" in capsys.readouterr().out
