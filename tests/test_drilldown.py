import pytest

from nexuspulse_analytics.drilldown import drill_down
from nexuspulse_generator import MAIN_FASHION, Scenario, generate_store


@pytest.fixture(scope="module")
def store():
    sc = (
        Scenario("conversion_drop", "2025-06-10", 10, {"multiplier": 0.5, "segment": {"device": "mobile"}, "event": True}),
        Scenario("stockout", "2025-08-10", 9, {"category": "Dresses", "event": False}),
        Scenario("traffic_loss", "2025-10-01", 12, {"multiplier": 0.4, "segment": {"channel": "paid_social"}, "event": True}),
    )
    return generate_store(MAIN_FASHION, seed=51, days=320, scenarios=sc)


@pytest.mark.parametrize(
    "start,end,dim,segment",
    [("2025-06-10", "2025-06-19", "device", "mobile"), ("2025-08-10", "2025-08-18", "category", "Dresses"),
     ("2025-10-01", "2025-10-12", "channel", "paid_social")],
)
def test_planted_segment_is_primary(store, start, end, dim, segment):
    d = drill_down(store.tables(), store.profile.timezone, start, end)
    assert d["primary"]["dimension"] == dim and d["primary"]["segment"] == segment


def test_segment_contributions_sum_and_split_exactly(store):
    d = drill_down(store.tables(), store.profile.timezone, "2025-06-10", "2025-06-19", depth=1)
    for dim in ("device", "channel", "region"):
        v = d["dimensions"][dim]
        assert sum(r["change"] for r in v["rows"]) == pytest.approx(v["total_change"])
        for r in v["rows"]:
            assert r["traffic_part"] + r["rate_part"] == pytest.approx(r["current_per_day"] - r["baseline_per_day"])
    totals = {dim: d["dimensions"][dim]["total_change"] for dim in ("device", "channel", "region")}
    assert totals["device"] == pytest.approx(totals["channel"]) == pytest.approx(totals["region"])


def test_traffic_loss_is_a_traffic_effect(store):
    d = drill_down(store.tables(), store.profile.timezone, "2025-10-01", "2025-10-12", depth=1)
    ps = next(r for r in d["dimensions"]["channel"]["rows"] if r["segment"] == "paid_social")
    assert abs(ps["traffic_part"]) > abs(ps["rate_part"])


def test_flagged_segment_is_preferred_when_it_holds_most_of_the_change():
    from nexuspulse_analytics.drilldown import flagged_choice

    def dim(rows):
        return {"rows": [{"segment": s, "change": c, "noise_score": n, "volume_ok": True} for s, c, n in rows],
                "total_change": sum(c for _, c, _ in rows)}

    dims = {"channel": dim([("paid_social", -80.0, -1.5), ("email", -30.0, -0.5), ("organic", 10.0, 0.2)]),
            "device": dim([("mobile", -60.0, -3.0), ("desktop", -40.0, -1.0)])}
    # Flagged and the largest decline in its dimension: chosen even though its noise score is below the usual bar.
    dim_name, c = flagged_choice(dims, [{"dimension": "channel", "value": "paid_social"}], "down")
    assert (dim_name, c["segment"], c["flagged"]) == ("channel", "paid_social", True)
    # A flagged segment that is not the largest mover, or moved against the issue, is not chosen.
    assert flagged_choice(dims, [{"dimension": "channel", "value": "email"}], "down") is None
    assert flagged_choice(dims, [{"dimension": "channel", "value": "organic"}], "down") is None
    assert flagged_choice(dims, [], "down") is None
    # Offsetting noise elsewhere (share above 100%) does not disqualify the largest mover.
    noisy = {"channel": dim([("paid_social", -230.0, -1.9), ("organic", 240.0, 1.0), ("email", -110.0, -0.4)])}
    assert flagged_choice(noisy, [{"dimension": "channel", "value": "paid_social"}], "down")[1]["share"] > 1
