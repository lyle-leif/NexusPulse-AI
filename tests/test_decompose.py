from math import prod

import pandas as pd
import pytest

from nexuspulse_analytics.decompose import CORE_FACTORS, baseline_days, decompose, funnel_daily, shapley
from nexuspulse_generator import MAIN_FASHION, Scenario, generate_store


def test_shapley_sums_exactly_and_matches_two_factor_closed_form():
    base, cur = {"a": 2.0, "b": 5.0}, {"a": 3.0, "b": 4.0}
    c = shapley(base, cur, lambda s: s["a"] * s["b"])
    assert c["a"] + c["b"] == pytest.approx(12 - 10)
    # closed form for two factors: average of the two orderings
    assert c["a"] == pytest.approx(((3 - 2) * 5 + (3 - 2) * 4) / 2)


def test_shapley_zero_change_factor_gets_zero():
    base = {"a": 2.0, "b": 5.0, "c": 7.0}
    cur = {"a": 3.0, "b": 5.0, "c": 6.0}
    c = shapley(base, cur, lambda s: prod(s.values()))
    assert c["b"] == pytest.approx(0)
    assert sum(c.values()) == pytest.approx(prod(cur.values()) - prod(base.values()))


@pytest.fixture(scope="module")
def store():
    sc = (Scenario("conversion_drop", "2025-06-10", 10, {"multiplier": 0.5, "segment": {"device": "mobile"}, "event": True}),)
    return generate_store(MAIN_FASHION, seed=51, days=200, scenarios=sc)


def test_funnel_telescopes_to_attributed_gross(store):
    f = funnel_daily(store.tables(), store.profile.timezone)
    assert (f["checkouts"] <= f["carts"]).all() and (f["converting_sessions"] <= f["checkouts"]).all()


def test_decomposition_sums_and_finds_the_planted_stage(store):
    d = decompose(store.tables(), store.profile.timezone, "2025-06-10", "2025-06-19")
    bridge = d["bridge"]
    assert sum(x["change"] for x in bridge[:-1]) == pytest.approx(bridge[-1]["change"], abs=1e-6)
    total = sum(x["contribution"] for x in d["core"])
    assert total == pytest.approx(d["core_total"]["change"], rel=1e-9)
    biggest = max(d["core"], key=lambda x: abs(x["contribution"]))
    assert biggest["factor"] == "purchase_rate" and biggest["contribution"] < 0
    assert [x["factor"] for x in d["core"]] == CORE_FACTORS


def test_baseline_uses_same_weekdays_before_window():
    idx = pd.date_range("2025-01-01", "2025-03-31")
    b = baseline_days(pd.Timestamp("2025-03-10"), pd.Timestamp("2025-03-12"), idx)
    assert len(b) == 12 and (b < pd.Timestamp("2025-03-10")).all()
    assert set(b.day_of_week) == {0, 1, 2}
