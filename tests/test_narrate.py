import json

import pandas as pd
import pytest

from nexuspulse_analytics.investigate import investigate
from nexuspulse_analytics.narrate import narrate, validate_narration
from nexuspulse_analytics.report import build_report, template_summary
from nexuspulse_eval.adversarial import cases, run_adversarial
from nexuspulse_generator import MAIN_FASHION, Scenario, generate_store

EMPTY = pd.DatetimeIndex([])


@pytest.fixture(scope="module")
def invs():
    sc = (
        Scenario("conversion_drop", "2025-06-10", 10, {"multiplier": 0.5, "segment": {"device": "mobile"}, "event": True, "event_offset_hours": -3.0}),
        Scenario("stockout", "2025-08-10", 9, {"category": "Dresses", "event": False}),
    )
    st = generate_store(MAIN_FASHION, seed=51, days=260, scenarios=sc)
    out = []
    for s, e in [("2025-06-10", "2025-06-19"), ("2025-08-10", "2025-08-18"), ("2025-04-01", "2025-04-05")]:
        inc = {"incident_id": f"inc_{s}", "start": s, "end": e, "anchor_metric": "net_sales", "direction": "down", "members": []}
        out.append(investigate(st.tables(), st.profile.timezone, inc, EMPTY, EMPTY))
    return out


def test_template_summary_passes_the_validator(invs):
    for inv in invs:
        t = template_summary(inv)
        assert validate_narration({"summary": t, "next_steps": []}, inv) == [], t


def test_named_adversarial_cases_are_caught(invs):
    must_catch = {"causal_motive", "proves_effective", "status_inflation", "direction_flip", "invented_number",
                  "recommendation", "unhedged_cause", "overclaim_hedged", "unknown_finding", "made_up_step", "wrong_total"}
    for inv in invs:
        for c in cases(inv):
            if c["id"] in must_catch:
                assert validate_narration(c["narration"], inv), c["id"]


def test_adversarial_report_counts(invs):
    r = run_adversarial(invs)
    assert r["n"] == 16 * len(invs)
    assert r["catch_rate"] >= 0.6


class FakeProvider:
    name = "fake:test"

    def __init__(self, answers):
        self.answers = list(answers)

    def generate_structured(self, prompt, schema):
        a = self.answers.pop(0)
        return {"raw": json.dumps(a), "parsed": a}


def test_retry_then_fallback(invs):
    inv = invs[0]
    bad = {"summary": [{"text": "The deploy caused the drop.", "finding_ids": ["f1"], "status": "observed"}], "next_steps": []}
    n = narrate(inv, FakeProvider([bad, bad]))
    assert n["fallback"] and n["attempts"] == 2
    rep = build_report(inv, narration=n)
    assert all(s["source"] == "template" for s in rep["summary"])


def test_valid_model_output_is_used_and_marked(invs):
    inv = invs[0]
    good = {"summary": template_summary(inv)[:2], "next_steps": []}
    n = narrate(inv, FakeProvider([good]))
    assert not n["fallback"] and n["attempts"] == 1
    rep = build_report(inv, narration=n)
    assert all(s["source"] == "model" for s in rep["summary"])


def test_no_provider_is_template_mode(invs):
    rep = build_report(invs[0], narration=narrate(invs[0], None))
    assert rep["narration"]["mode"] == "template" and rep["summary"][0]["source"] == "template"
