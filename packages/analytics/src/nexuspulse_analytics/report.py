"""Template-first reports.

Every number, table and claim in a report comes from validated findings through
deterministic templates. A language model may only fill two bounded slots (a short
summary and the wording of hypotheses and next steps) and its output must pass the
validator (narrate.py); otherwise the template text below is used. With no model at all
the template report is complete on its own ("template" narration mode).

Each summary sentence lists the finding ids it relies on and the strongest epistemic
status it claims, so the UI can link every sentence to its evidence.
"""
from __future__ import annotations

from .investigate import FACTOR_LABEL

STATUS_RANK = {"observed": 0, "attributed": 1, "associated": 2, "hypothesis": 3}

# Curated next-step catalogue. The model may choose and rephrase, never add.
NEXT_STEPS = {
    "check_segment_funnel": "Review the {stage} step for {segment} {dimension} users (recent releases, errors, payment failures).",
    "check_channel": "Review {segment} campaign settings, budget and delivery for the incident dates.",
    "check_stock": "Check stock levels and product availability in {segment}.",
    "review_event": "Review the recorded change '{event}' and whether it can be rolled back or tested.",
    "check_pricing": "Compare prices and discounts before and during the incident.",
    "look_unrecorded": "Look for changes not in the change log (outages, competitor activity, external demand).",
    "watch": "Keep monitoring; the change is within normal variation and may not need action.",
}

STAGE = {"cart_rate": "add-to-cart", "checkout_rate": "cart-to-checkout", "purchase_rate": "checkout-to-purchase"}


def _f(findings, ftype):
    return [f for f in findings if f["type"] == ftype]


def _money(v: float, currency: str = "USD") -> str:
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.0f}" if currency == "USD" else f"{sign}{abs(v):,.0f} {currency}"


def next_step_ids(inv: dict) -> list[dict]:
    """Applicable catalogue entries with their filled parameters."""
    seg = inv.get("segment")
    drv = inv["driver"]
    ev = inv.get("cause_event")
    out = []
    if inv["explanation_evidence"]["level"] == "None" and not seg:
        out.append({"id": "watch", "params": {}})
    if seg and seg["dimension"] == "category":
        out.append({"id": "check_stock", "params": {"segment": seg["segment"]}})
    elif seg and drv in STAGE:
        out.append({"id": "check_segment_funnel", "params": {"stage": STAGE[drv], "segment": seg["segment"], "dimension": seg["dimension"]}})
    elif seg and seg["dimension"] == "channel":
        out.append({"id": "check_channel", "params": {"segment": seg["segment"]}})
    if drv == "attributed_aov":
        out.append({"id": "check_pricing", "params": {}})
    if ev:
        out.append({"id": "review_event", "params": {"event": ev["description"]}})
    out.append({"id": "look_unrecorded", "params": {}})
    return [s | {"text": NEXT_STEPS[s["id"]].format(**s["params"])} for s in out]


def template_summary(inv: dict, currency: str = "USD") -> list[dict]:
    """Deterministic summary sentences, each tied to finding ids and a status."""
    fs = inv["findings"]
    inc = _f(fs, "incident")[0]
    net = _f(fs, "bridge_change")[0]
    drv = _f(fs, "driver")[0]
    seg = _f(fs, "segment")[0]
    hyp = _f(fs, "hypothesis")
    v = inc["values"]
    s1 = (f"Net revenue averaged {_money(net['values']['current'], currency)} per day from {v['start']} to {v['end']}, "
          f"{_money(abs(net['values']['change']), currency)} {'below' if net['values']['change'] < 0 else 'above'} the baseline.")
    out = [{"text": s1, "finding_ids": [inc["finding_id"], net["finding_id"]], "status": "observed"}]
    d = drv["values"]
    s2 = f"The largest measured part of the change came from the {FACTOR_LABEL[d['factor']]} ({_money(d['contribution'], currency)} per day)"
    if seg["values"].get("segment"):
        sv = seg["values"]
        s2 += f", and {sv['share']:.0%} of it was in {sv['segment']} ({sv['dimension']})."
    else:
        s2 += "; it was spread across segments."
    out.append({"text": s2, "finding_ids": [drv["finding_id"], seg["finding_id"]], "status": "attributed"})
    if hyp:
        h = hyp[0]
        ev = _f(fs, "event")
        out.append({"text": f"A recorded change, '{inv['cause_event']['description']}', fits the timing and may explain it, but the data cannot show that it did.",
                    "finding_ids": [h["finding_id"]] + [e["finding_id"] for e in ev if e["values"]["event_id"] == h["values"]["event_id"]],
                    "status": "hypothesis"})
    else:
        alt = _f(fs, "alternative")[0]
        out.append({"text": "No recorded change explains it; the reason is unknown from the available data.",
                    "finding_ids": [alt["finding_id"]], "status": "hypothesis"})
    return out


def build_report(inv: dict, currency: str = "USD", narration: dict | None = None) -> dict:
    """Assemble the report. `narration` is a validated model result or None (template)."""
    steps = next_step_ids(inv)
    summary = template_summary(inv, currency)
    for s in summary:
        s["source"] = "template"
    report = {
        "incident_id": inv["incident_id"],
        "headline": f"{inv['window']['start']} to {inv['window']['end']}: explanation evidence {inv['explanation_evidence']['level']}",
        "summary": summary,
        "next_steps": [{"id": s["id"], "text": s["text"], "source": "template"} for s in steps],
        "narration": {"mode": "template", "model": None, "fallback": False, "attempts": 0, "validation": []},
    }
    if narration:
        report["narration"] = {k: narration[k] for k in ("mode", "model", "fallback", "attempts", "validation", "prompt_version") if k in narration}
        if not narration.get("fallback") and narration.get("summary"):
            report["summary"] = [s | {"source": "model"} for s in narration["summary"]]
            report["next_steps"] = [s | {"source": "model"} for s in narration.get("next_steps", report["next_steps"])]
    return report
