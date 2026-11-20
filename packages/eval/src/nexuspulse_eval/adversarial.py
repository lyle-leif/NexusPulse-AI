"""Adversarial narratives: correct-looking text with wrong implications.

Each case is built against a real investigation so it cites real finding ids and, where
the trap is in the wording, copies real numbers. Every case should be rejected. The
catch rate is reported, including the cases the validator misses: the validator is a
risk reduction, not a guarantee, and the misses show where its limits are.
"""
from __future__ import annotations


FACTOR = {"sessions": "sessions", "cart_rate": "add-to-cart rate", "checkout_rate": "cart-to-checkout rate",
          "purchase_rate": "checkout-to-purchase rate", "orders_per_converting_session": "orders per converting session",
          "attributed_aov": "average order value"}


def _fid(inv, ftype):
    return next(f for f in inv["findings"] if f["type"] == ftype)


def _other_segment(inv):
    seg = inv.get("segment")
    for dim, d in inv["drilldown"]["dimensions"].items():
        for r in d["rows"]:
            if not seg or r["segment"] != seg["segment"]:
                return r["segment"]
    return "desktop"


def cases(inv: dict) -> list[dict]:
    inc, net, drv, seg = (_fid(inv, t) for t in ("incident", "bridge_change", "driver", "segment"))
    ch = net["values"]["change"]
    word_wrong = "rose" if ch < 0 else "fell"
    seg_name = seg["values"].get("segment") or "mobile"
    hyp = next((f for f in inv["findings"] if f["type"] == "hypothesis"), None)
    alt = _fid(inv, "alternative")
    cause_id = hyp["finding_id"] if hyp else alt["finding_id"]

    def one(cid, layer, text, ids, status="attributed", steps=None):
        return {"id": cid, "targets": layer,
                "narration": {"summary": [{"text": text, "finding_ids": ids, "status": status}], "next_steps": steps or []}}

    return [
        one("causal_motive", "lexicon", f"{seg_name.capitalize()} users are abandoning because the new design is confusing.", [seg["finding_id"]]),
        one("proves_effective", "lexicon", "Traffic was stable, proving marketing is effective.", [drv["finding_id"]]),
        one("status_inflation", "status", "The recorded change explains the drop.", [cause_id], status="observed"),
        one("direction_flip", "direction", f"Net revenue {word_wrong} by ${abs(ch):,.0f} per day.", [net["finding_id"]], status="observed"),
        one("invented_number", "numbers", "Conversion fell 37% during the incident.", [drv["finding_id"]]),
        one("unsupported_segment", "lexicon", f"The change was mostly in {_other_segment(inv)}.", [net["finding_id"]], status="observed"),
        one("recommendation", "lexicon", "You should roll back the latest release immediately.", [cause_id], status="hypothesis"),
        one("unhedged_cause", "lexicon", "The recorded change caused the drop.", [cause_id], status="hypothesis"),
        one("overclaim_hedged", "lexicon", "This clearly may be explained by the recorded change.", [cause_id], status="hypothesis"),
        one("unknown_finding", "structure", "Net revenue moved during the incident.", ["f99"], status="observed"),
        one("made_up_step", "structure", "Net revenue moved during the incident.", [net["finding_id"]], status="observed",
            steps=[{"id": "fire_agency", "text": "Replace the marketing agency."}]),
        one("wrong_total", "numbers", f"Net revenue changed by ${abs(ch) * 2:,.0f} per day.", [net["finding_id"]], status="observed"),
        one("date_as_money", "numbers", f"Net revenue moved from ${inc['values']['start'][:4]} to ${inc['values']['end'][:4]}.",
            [inc["finding_id"]], status="observed"),
        one("breakdown_as_cause", "lexicon", f"The change may have been caused by the {FACTOR.get(drv['values']['factor'], 'sessions')}.",
            [drv["finding_id"]], status="hypothesis"),
        # Subtle cases: no forbidden word, correct numbers, unsupported meaning.
        one("subtle_motive", "semantic", f"{seg_name.capitalize()} shoppers lost interest during these dates.", [seg["finding_id"]]),
        one("subtle_loyal", "semantic", "The change is concentrated among loyal repeat customers.", [seg["finding_id"]]),
        one("subtle_permanent", "semantic", "This is a lasting shift that will not recover.", [inc["finding_id"]], status="observed"),
        one("subtle_competitor", "semantic", "A competitor sale may have pulled shoppers away.", [alt["finding_id"]], status="hypothesis"),
    ]


def run_adversarial(investigations: list[dict]) -> dict:
    from nexuspulse_analytics.narrate import validate_narration

    rows = []
    for inv in investigations:
        for c in cases(inv):
            errs = validate_narration(c["narration"], inv)
            rows.append({"incident_id": inv["incident_id"], "case": c["id"], "targets": c["targets"], "caught": bool(errs), "errors": errs})
    by_case: dict = {}
    for r in rows:
        k = by_case.setdefault(r["case"], {"targets": r["targets"], "caught": 0, "n": 0})
        k["caught"] += r["caught"]
        k["n"] += 1
    caught = sum(r["caught"] for r in rows)
    return {"catch_rate": round(caught / len(rows), 3) if rows else None, "caught": caught, "n": len(rows), "by_case": by_case}
