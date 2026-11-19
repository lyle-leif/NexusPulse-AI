"""Investigation: typed findings with epistemic status, evidence rules, validation.

Statuses (never mixed):
- observed:   measured directly (the incident, bridge lines).
- attributed: an exact arithmetic breakdown (Shapley factor, segment share). Not a cause.
- associated: a recorded change event that matches the change in time and scope.
- hypothesis: a possible explanation that the data cannot confirm.

Explanation evidence (published rules):
- Strong:   >= 80% of the change in one segment, a scope-matching event in the 24 h
            before the change began, and data quality and calendar ruled out.
- Moderate: >= 50% in one segment and a scope-matching event; or >= 80% with no event.
- Weak:     >= 50% in one segment, or an unscoped event in the time window.
- None:     diffuse change and no matching event. Reported as "no explanation found".
"""
from __future__ import annotations

import pandas as pd

from .decompose import decompose
from .drilldown import drill_down

FACTOR_LABEL = {
    "sessions": "sessions",
    "cart_rate": "add-to-cart rate",
    "checkout_rate": "cart-to-checkout rate",
    "purchase_rate": "checkout-to-purchase rate",
    "orders_per_converting_session": "orders per converting session",
    "attributed_aov": "attributed average order value",
}
CONVERSION_FACTORS = {"cart_rate", "checkout_rate", "purchase_rate"}
EVENT_WINDOW_BEFORE = pd.Timedelta(hours=24)
EVENT_WINDOW_AFTER = pd.Timedelta(hours=24)
STATUS_ORDER = ["observed", "attributed", "associated", "hypothesis"]


def match_events(events: pd.DataFrame, tz: str, start: str, primary: dict | None) -> list[dict]:
    """Change events in [change start - 24 h, change start + 24 h), excluding calendar events."""
    t0 = pd.Timestamp(start)
    out = []
    for _, r in events[events["event_type"] != "holiday"].iterrows():
        at = r["occurred_at"].tz_convert(tz).tz_localize(None)
        if not (t0 - EVENT_WINDOW_BEFORE <= at < t0 + EVENT_WINDOW_AFTER):
            continue
        scope = dict(r["scope"] or {})
        if not scope:
            match = "unscoped"
        elif primary and scope.get(primary["dimension"]) == primary["segment"]:
            match = "scope_match"
        else:
            match = "scope_mismatch"
        out.append({"event_id": r["event_id"], "occurred_at_local": at.isoformat(), "type": r["event_type"],
                    "description": r["description"], "scope": scope, "match": match,
                    "hours_before_change": round((t0 - at).total_seconds() / 3600, 1)})
    return sorted(out, key=lambda e: ({"scope_match": 0, "unscoped": 1, "scope_mismatch": 2}[e["match"]], abs(e["hours_before_change"])))


def evidence_level(share: float | None, events: list[dict], ruled_out_ok: bool) -> tuple[str, list[str]]:
    share = share or 0.0
    scoped = any(e["match"] == "scope_match" for e in events)
    unscoped = any(e["match"] == "unscoped" for e in events)
    reasons = [f"{share:.0%} of the change is in one segment"]
    if scoped:
        reasons.append("a recorded change with the same scope happened within 24 hours of the start")
    elif unscoped:
        reasons.append("a store-wide change was recorded within 24 hours of the start, but its scope does not single out the segment")
    else:
        reasons.append("no matching recorded change")
    if share >= 0.8 and scoped and ruled_out_ok:
        return "Strong", reasons
    if (share >= 0.5 and scoped) or share >= 0.8:
        return "Moderate", reasons
    if share >= 0.5 or unscoped:
        return "Weak", reasons
    return "None", reasons


def investigate(tables: dict[str, pd.DataFrame], tz: str, incident: dict, dq_days: pd.DatetimeIndex,
                known_days: pd.DatetimeIndex, daily: pd.DataFrame | None = None) -> dict:
    start = incident["start"]
    end = incident["end"] or max(m["end"] or m["start"] for m in incident["members"])
    window = pd.date_range(start, end)
    exclude = dq_days.union(known_days)
    dec = decompose(tables, tz, start, end, exclude=exclude, daily=daily)
    dd = drill_down(tables, tz, start, end, exclude=exclude)
    primary = dd["primary"]
    events = match_events(tables["change_events"], tz, start, primary)

    findings: list[dict] = []

    def add(ftype, status, text, **values):
        fid = f"f{len(findings) + 1}"
        findings.append({"finding_id": fid, "type": ftype, "status": status, "text": text, "values": values})
        return fid

    net = dec["bridge"][-1]
    add("incident", "observed",
        f"{incident['anchor_metric'].replace('_', ' ')} moved {incident['direction']} from {start} to {end}.",
        metric=incident["anchor_metric"], direction=incident["direction"], start=start, end=end)
    add("bridge_change", "observed",
        f"Net revenue averaged {net['current']:.2f} per day versus {net['baseline']:.2f} in the baseline ({net['change']:+.2f}).",
        baseline=net["baseline"], current=net["current"], change=net["change"])
    lines = sorted(dec["bridge"][:-1], key=lambda x: abs(x["change"]), reverse=True)
    add("bridge_line", "attributed", f"The largest bridge line change was {lines[0]['label'].lower()} ({lines[0]['change']:+.2f} per day).",
        line=lines[0]["line"], change=lines[0]["change"])

    top = max(dec["core"], key=lambda x: abs(x["contribution"]))
    add("driver", "attributed",
        f"Of the change in attributed gross sales, {FACTOR_LABEL[top['factor']]} accounts for {top['contribution']:+.2f} per day "
        f"(it moved {top['relative_change']:+.1%}).",
        factor=top["factor"], contribution=top["contribution"], relative_change=top["relative_change"],
        core_change=dec["core_total"]["change"])

    if primary:
        add("segment", "attributed",
            f"{primary['share']:.0%} of the {primary['dimension']} breakdown of the change is in {primary['segment']}.",
            dimension=primary["dimension"], segment=primary["segment"], share=primary["share"], noise_score=primary["noise_score"])
    else:
        add("segment", "attributed", "The change is spread across segments; no single segment stands out from noise.",
            dimension=None, segment=None, share=None)

    dq_overlap = bool(len(window.intersection(dq_days)))
    cal_overlap = bool(len(window.intersection(known_days)))
    ruled_out = [
        {"alternative": "data-quality problem", "ruled_out": not dq_overlap,
         "reason": "no tracking or reconciliation issue in the window" if not dq_overlap else "a data-quality issue overlaps the window"},
        {"alternative": "calendar event", "ruled_out": not cal_overlap,
         "reason": "no holiday window overlaps" if not cal_overlap else "a holiday window overlaps"},
    ]
    for r in ruled_out:
        add("ruled_out", "observed", f"{r['alternative'].capitalize()}: {'ruled out' if r['ruled_out'] else 'not ruled out'} ({r['reason']}).",
            alternative=r["alternative"], ruled_out=r["ruled_out"])

    for ev in events:
        if ev["match"] == "scope_mismatch":
            continue
        add("event", "associated",
            f"'{ev['description']}' ({ev['type']}) was recorded {ev['hours_before_change']:+.1f} hours before the change began"
            + (f", scoped to {ev['scope']}." if ev["scope"] else ", with no scope."),
            event_id=ev["event_id"], match=ev["match"], hours_before_change=ev["hours_before_change"])

    level, reasons = evidence_level(primary["share"] if primary else None, events, all(r["ruled_out"] for r in ruled_out))
    best_event = next((e for e in events if e["match"] in ("scope_match", "unscoped")), None)
    cause = None
    if best_event and level in ("Strong", "Moderate", "Weak"):
        cause = {"event_id": best_event["event_id"], "description": best_event["description"], "type": best_event["type"]}
        add("hypothesis", "hypothesis", f"The recorded change '{best_event['description']}' may explain the movement; the data cannot confirm it.",
            event_id=best_event["event_id"])
    add("alternative", "hypothesis", "An unrecorded change (competitor, outage, external demand) could also explain it.")

    out = {
        "incident_id": incident["incident_id"],
        "window": dec["window"],
        "decomposition": dec,
        "drilldown": {k: v for k, v in dd.items() if k != "second_level"} | {"second_level": dd["second_level"]},
        "events": events,
        "ruled_out": ruled_out,
        "findings": findings,
        "explanation_evidence": {"level": level, "reasons": reasons},
        "driver": top["factor"],
        "driver_group": "conversion" if top["factor"] in CONVERSION_FACTORS else top["factor"],
        "segment": {"dimension": primary["dimension"], "segment": primary["segment"]} if primary else None,
        "cause_event": cause,
    }
    out["validation"] = validate(out)
    return out


def validate(inv: dict) -> list[dict]:
    """Recompute every number a finding states from the computed results."""
    checks = []
    dec = inv["decomposition"]

    def check(name, ok, detail=""):
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    br = dec["bridge"]
    check("bridge_sums", abs(sum(x["change"] for x in br[:-1]) - br[-1]["change"]) < 1e-6)
    check("shapley_sums", abs(sum(x["contribution"] for x in dec["core"]) - dec["core_total"]["change"]) < 1e-6 * max(1, abs(dec["core_total"]["change"])))
    for f in inv["findings"]:
        v = f["values"]
        if f["type"] == "driver":
            c = next(x for x in dec["core"] if x["factor"] == v["factor"])
            check(f"{f['finding_id']}_driver_value", c["contribution"] == v["contribution"])
            check(f"{f['finding_id']}_driver_is_largest", abs(c["contribution"]) == max(abs(x["contribution"]) for x in dec["core"]))
        if f["type"] == "segment" and v.get("segment"):
            d = inv["drilldown"]["dimensions"][v["dimension"]]
            row = next(r for r in d["rows"] if r["segment"] == v["segment"])
            check(f"{f['finding_id']}_segment_share", abs(row["change"] / d["total_change"] - v["share"]) < 1e-9)
        if f["type"] == "event":
            check(f"{f['finding_id']}_event_in_window", -EVENT_WINDOW_AFTER.total_seconds() / 3600 < v["hours_before_change"] <= 24)
        check(f"{f['finding_id']}_status_allowed", f["status"] in STATUS_ORDER)
    return checks
