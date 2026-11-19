import numpy as np
import pandas as pd
import pytest

from nexuspulse_analytics import local_date, run_reconciliation
from nexuspulse_generator import (
    MAIN_FASHION,
    PERMANENT_KINDS,
    Scenario,
    generate_store,
    load_spec,
    sample_scenarios,
)

DAYS = 200


def _store(*scenarios, seed=5):
    return generate_store(MAIN_FASHION, seed=seed, days=DAYS, scenarios=scenarios)


@pytest.mark.parametrize("split,seed", [("dev", 101), ("heldout", 201), ("dev", 102), ("heldout", 202)])
def test_sampling_is_deterministic_non_overlapping_and_permanent_last(split, seed):
    spec = load_spec(f"scenarios/{split}.yaml")
    a = sample_scenarios(spec, seed, MAIN_FASHION.start, MAIN_FASHION.days)
    b = sample_scenarios(spec, seed, MAIN_FASHION.start, MAIN_FASHION.days)
    assert a == b and len(a) >= 5
    starts = [pd.Timestamp(s.start) for s in a]
    assert starts == sorted(starts)
    assert (starts[0] - pd.Timestamp(MAIN_FASHION.start)).days >= spec["warmup_days"]
    for prev, nxt in zip(a, a[1:]):
        assert pd.Timestamp(prev.start) + pd.Timedelta(days=prev.days) < pd.Timestamp(nxt.start)
    perm = [i for i, s in enumerate(a) if s.kind in PERMANENT_KINDS]
    assert perm in ([], [len(a) - 1])


def test_dev_and_heldout_differ():
    dev = load_spec("scenarios/dev.yaml")
    held = load_spec("scenarios/heldout.yaml")
    assert {s["kind"] for s in held["scenarios"]} - {s["kind"] for s in dev["scenarios"]}  # an unseen kind


def test_conversion_drop_hits_only_its_segment():
    store = _store(Scenario("conversion_drop", "2025-05-01", 14, {"multiplier": 0.4, "segment": {"device": "mobile"}}))
    tz = store.profile.timezone
    s = store.sessions.assign(day=local_date(store.sessions["started_at"], tz))
    conv = store.orders.dropna(subset=["session_id"]).merge(s[["session_id", "day", "device"]], on="session_id")
    in_w = (conv["day"] >= "2025-05-01") & (conv["day"] <= "2025-05-14")
    pre = (conv["day"] >= "2025-04-01") & (conv["day"] <= "2025-04-28")
    sess_in = s[(s["day"] >= "2025-05-01") & (s["day"] <= "2025-05-14")].groupby("device").size()
    sess_pre = s[(s["day"] >= "2025-04-01") & (s["day"] <= "2025-04-28")].groupby("device").size()
    rate_in = conv[in_w].groupby("device")["session_id"].nunique() / sess_in
    rate_pre = conv[pre].groupby("device")["session_id"].nunique() / sess_pre
    assert rate_in["mobile"] / rate_pre["mobile"] < 0.6
    assert 0.85 < rate_in["desktop"] / rate_pre["desktop"] < 1.15


def test_stockout_removes_category_and_price_increase_raises_prices():
    store = _store(
        Scenario("stockout", "2025-04-01", 10, {"category": "Dresses"}),
        Scenario("price_increase", "2025-06-01", 14, {"pct": 0.10}),
    )
    tz = store.profile.timezone
    items = store.order_items.merge(store.orders[["order_id", "placed_at"]], on="order_id")
    items["day"] = local_date(items["placed_at"], tz)
    items = items.merge(store.products[["product_id", "category", "price"]], on="product_id")
    # placed_at day can differ from session day near midnight; check the inner window
    window = items[(items["day"] >= "2025-04-02") & (items["day"] <= "2025-04-09")]
    assert (window["category"] == "Dresses").sum() == 0
    before = items[items["day"] < "2025-05-31"]
    after = items[items["day"] > "2025-06-02"]
    assert (before["unit_price"] == before["price"]).all()
    assert np.allclose(after["unit_price"] / after["price"], 1.10, atol=0.001)


def test_labels_stay_out_of_observable_data_and_events_share_templates():
    store = _store(
        Scenario("conversion_drop", "2025-05-01", 7, {"multiplier": 0.5, "segment": {"device": "mobile"}, "event": True}),
        Scenario("red_herring", "2025-06-15", 7, {"event_type": "deploy"}),
    )
    ev = store.change_events
    deploys = ev[ev["event_type"] == "deploy"]
    assert len(deploys) == 2
    text = " ".join(map(str, ev.astype(str).to_numpy().ravel())).lower()
    for leak in ("red_herring", "herring", "conversion_drop", "scenario", "sc_0", "sc_1", "ground"):
        assert leak not in text
    for df in store.tables().values():
        assert not any(c in ("label", "scenario_id", "expected") for c in df.columns)
    kinds = {lab["kind"]: lab for lab in store.labels}
    assert kinds["red_herring"]["expected"]["business_anomaly"] is False
    assert kinds["conversion_drop"]["expected"]["cause_event"] is not None


def test_reconciliation_still_passes_with_all_scenario_kinds():
    spec = load_spec("scenarios/heldout.yaml")
    sc = sample_scenarios(spec, 7, MAIN_FASHION.start, MAIN_FASHION.days)
    store = generate_store(MAIN_FASHION, seed=7, scenarios=sc)
    assert [c.name for c in run_reconciliation(store.tables(), store.profile.timezone) if not c.passed] == []
