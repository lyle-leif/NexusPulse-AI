"""Detection evaluation runner.

For each (suite, profile, seed): sample scenarios from the suite spec, generate the
store, run the inference pipeline (which never sees labels), then score incidents
against the labels. Only this module joins the two.

Matching rules (published):
- Business scenario detected: a non-suppressed incident with the expected direction
  that starts no earlier than 2 days before the scenario and no later than its end
  (or start + 14 days for permanent changes). Delay = incident start - scenario start
  is reported, clipped at 0, plus the alert delay (first day the monitor could know).
- Data-quality scenario handled: an overlapping incident is suppressed, or none is raised.
- Red herring passed: no non-suppressed incident overlaps its window.
- False alert: a non-suppressed incident that matches no scenario.
- Effect size: relative change of net sales in the scenario window versus the same
  seed generated without scenarios (the counterfactual).
"""
from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from nexuspulse_analytics import daily_kpis
from nexuspulse_analytics.forecast import metric_frame
from nexuspulse_analytics.monitor import MonitorConfig
from nexuspulse_analytics.pipeline import analyze
from nexuspulse_generator import LOW_VOLUME_FASHION, MAIN_FASHION, generate_store, load_spec, sample_scenarios

PROFILES = {"main": MAIN_FASHION, "low_volume": LOW_VOLUME_FASHION}
CONFIGS = {
    "robust": MonitorConfig(),
    "robust_masked": MonitorConfig(masking=True),
    "plain": MonitorConfig(robust=False),
}
SUITE_SEEDS = {"dev": range(101, 106), "heldout": range(901, 906)}


def _window(label) -> tuple[pd.Timestamp, pd.Timestamp]:
    s = pd.Timestamp(label["start"])
    e = pd.Timestamp(label["end"]) if label["end"] else s + pd.Timedelta(days=14)
    return s, e


def score_store(labels: list[dict], incidents: list[dict], daily: pd.DataFrame, counterfactual: pd.Series,
                monitored_days: int) -> dict:
    used: set[int] = set()
    rows = []
    for lab in labels:
        s, e = _window(lab)
        exp = lab["expected"]
        overl = [
            (k, i) for k, i in enumerate(incidents)
            if pd.Timestamp(i["start"]) <= e and pd.Timestamp(i["end"] or "2100-01-01") >= s - pd.Timedelta(days=2)
        ]
        live = [(k, i) for k, i in overl if i["status"] != "suppressed_data_quality"]
        # factual/counterfactual ratio in the window, normalised by the same ratio in the
        # 28 days before (sample paths drift apart once effects change the random draws)
        ratio = daily["net_sales"] / counterfactual
        before = ratio.loc[s - pd.Timedelta(days=28): s - pd.Timedelta(days=1)].median()
        effect = ratio.loc[s:e].median() / before - 1 if before else np.nan
        row = {"kind": lab["kind"], "start": lab["start"], "end": lab["end"],
               "effect_pct": round(100 * float(effect), 1) if np.isfinite(effect) else None}
        if exp["business_anomaly"]:
            hits = [(k, i) for k, i in live if i["direction"] == exp["direction"]
                    and s - pd.Timedelta(days=2) <= pd.Timestamp(i["start"]) <= e]
            row["outcome"] = "detected" if hits else "missed"
            if hits:
                k, i = hits[0]
                row["delay_days"] = max(0, (pd.Timestamp(i["start"]) - s).days)
                row["incident"] = i["incident_id"]
                row["strength"] = i["strength"]
            used.update(k for k, _ in hits)
        elif exp["data_quality_incident"]:
            row["outcome"] = "suppressed" if not live else "alerted_wrongly"
            used.update(k for k, _ in overl)
        else:  # red herring
            row["outcome"] = "passed" if not live else "alerted_wrongly"
        rows.append(row)
    false = [i for k, i in enumerate(incidents) if k not in used and i["status"] != "suppressed_data_quality"
             and not any(r["kind"] == "red_herring" and r["outcome"] == "alerted_wrongly" and _overlap_lab(i, r) for r in rows)]
    return {"scenarios": rows, "false_alerts": len(false), "monitored_days": monitored_days,
            "false_alert_list": [{"start": i["start"], "anchor": i["anchor_metric"], "direction": i["direction"]} for i in false]}


def _overlap_lab(inc, row) -> bool:
    s, e = pd.Timestamp(row["start"]), pd.Timestamp(row["end"] or row["start"])
    return pd.Timestamp(inc["start"]) <= e and pd.Timestamp(inc["end"] or "2100-01-01") >= s


def run_one(suite: str, profile: str, seed: int, config: MonitorConfig) -> dict:
    p = PROFILES[profile]
    spec = load_spec(Path("scenarios") / f"{suite}.yaml")
    scen = sample_scenarios(spec, seed, p.start, p.days)
    store = generate_store(p, seed, scenarios=scen)
    base = generate_store(p, seed)
    cf = metric_frame(daily_kpis(base.tables(), p.timezone))["net_sales"]
    daily, result = analyze(store.tables(), p.timezone, config)
    metrics = metric_frame(daily)
    out = score_store(store.labels, result.incidents, metrics, cf, len(metrics) - config.warmup_days)
    out.update(suite=suite, profile=profile, seed=seed)
    # forecast quality on this store (net sales, 1-7 day ahead, in-range days only)
    d = result.daily.xs("net_sales", level="metric")
    d = d[d["state"].isin(["in_range", "out_of_range"])]
    out["coverage"] = float(((d["actual"] >= d["lo"]) & (d["actual"] <= d["hi"])).mean())
    out["mape"] = float((abs(d["actual"] - d["mean"]) / d["actual"]).mean())
    return out


def summarize(runs: list[dict]) -> dict:
    sc = [r | {"suite": run["suite"], "profile": run["profile"], "seed": run["seed"]} for run in runs for r in run["scenarios"]]
    biz = [r for r in sc if r["outcome"] in ("detected", "missed")]
    det = [r for r in biz if r["outcome"] == "detected"]
    nonbiz = [r for r in sc if r["outcome"] in ("suppressed", "passed", "alerted_wrongly")]
    days = sum(run["monitored_days"] for run in runs)
    fa = sum(run["false_alerts"] for run in runs)
    n_alerts = len(det) + fa + sum(r["outcome"] == "alerted_wrongly" for r in nonbiz)
    by_kind = {}
    for r in biz:
        k = by_kind.setdefault(r["kind"], [0, 0])
        k[0] += r["outcome"] == "detected"
        k[1] += 1
    bins = [(0, 10), (10, 20), (20, 35), (35, 1000)]
    by_effect = {}
    for lo, hi in bins:
        sel = [r for r in biz if r["effect_pct"] is not None and lo <= abs(r["effect_pct"]) < hi]
        by_effect[f"{lo}-{hi if hi < 1000 else '+'}%"] = {"detected": sum(r["outcome"] == "detected" for r in sel), "n": len(sel)}
    return {
        "recall": round(len(det) / len(biz), 3) if biz else None,
        "precision": round(len(det) / n_alerts, 3) if n_alerts else None,
        "false_alerts_per_30d": round(30 * fa / days, 3) if days else None,
        "median_delay_days": float(np.median([r["delay_days"] for r in det])) if det else None,
        "non_business_handled": f"{sum(r['outcome'] != 'alerted_wrongly' for r in nonbiz)}/{len(nonbiz)}",
        "recall_by_kind": {k: f"{a}/{b}" for k, (a, b) in sorted(by_kind.items())},
        "recall_by_effect": by_effect,
        "forecast_coverage": round(float(np.mean([r["coverage"] for r in runs])), 3),
        "forecast_mape": round(float(np.mean([r["mape"] for r in runs])), 3),
        "n_stores": len(runs),
        "scenarios": sc,
    }


def run_eval(suites=("dev", "heldout"), profiles=("main", "low_volume"), configs=("robust", "robust_masked", "plain"),
             out_dir: str | Path = "eval_results") -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(exist_ok=True)
    report = {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "results": {}}
    for cname in configs:
        cfg = CONFIGS[cname]
        report["results"][cname] = {"config": cfg.as_dict()}
        for suite in suites:
            for profile in profiles:
                t = time.time()
                runs = [run_one(suite, profile, seed, cfg) for seed in SUITE_SEEDS[suite]]
                summ = summarize(runs)
                report["results"][cname][f"{suite}/{profile}"] = summ
                print(f"{cname:14s} {suite:8s} {profile:10s} recall={summ['recall']} precision={summ['precision']} "
                      f"fa/30d={summ['false_alerts_per_30d']} delay={summ['median_delay_days']} "
                      f"nonbiz={summ['non_business_handled']} cov={summ['forecast_coverage']} ({time.time()-t:.0f}s)", flush=True)
    (out_dir / "detection.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    return report


# ---------------------------------------------------------------- investigation eval
DRIVER_GROUP = {"session_conversion_rate": "conversion", "sessions": "sessions"}


def _score_investigation(inv: dict, lab: dict) -> dict:
    exp = lab["expected"]
    row = {"kind": lab["kind"], "start": lab["start"], "evidence": inv["explanation_evidence"]["level"],
           "found_driver": inv["driver_group"], "found_segment": inv["segment"],
           "found_cause": inv["cause_event"]["description"] if inv["cause_event"] else None,
           "validation_passed": all(c["passed"] for c in inv["validation"])}
    if not exp["business_anomaly"]:  # red herring: a cause must not be claimed with Moderate+ evidence
        row["red_herring_rejected"] = not (inv["cause_event"] and row["evidence"] in ("Strong", "Moderate"))
        return row
    row["driver_correct"] = inv["driver_group"] == DRIVER_GROUP.get(exp["driver"], exp["driver"])
    seg = exp.get("segment") or {}
    if seg:
        (dim, val), = seg.items()
        row["segment_correct"] = inv["segment"] == {"dimension": dim, "segment": val}
    else:  # store-wide change: correct when no segment is singled out
        row["segment_correct"] = inv["segment"] is None or (inv["drilldown"]["primary"] or {}).get("share", 0) < 0.8
    truth = exp.get("cause_event")
    row["cause_correct"] = (inv["cause_event"] is not None and inv["cause_event"]["description"] == truth["text"]) if truth \
        else inv["cause_event"] is None
    row["expected_cause"] = truth["text"] if truth else None
    return row


def run_investigation_one(suite: str, profile: str, seed: int, config: MonitorConfig = MonitorConfig()) -> dict:
    from nexuspulse_analytics.investigate import investigate
    from nexuspulse_analytics.monitor import known_event_days
    from nexuspulse_analytics.reconcile import unattributed_share_flags

    p = PROFILES[profile]
    spec = load_spec(Path("scenarios") / f"{suite}.yaml")
    store = generate_store(p, seed, scenarios=sample_scenarios(spec, seed, p.start, p.days))
    tables = store.tables()
    daily, result = analyze(tables, p.timezone, config)
    known = known_event_days(tables["change_events"], p.timezone)
    flags = unattributed_share_flags(tables, p.timezone)
    dq = flags.index[flags["flag"]]
    oracle, e2e = [], []
    for lab in store.labels:
        if lab["expected"]["data_quality_incident"]:
            continue
        s, e = _window(lab)
        inc = {"incident_id": "oracle", "start": lab["start"], "end": e.date().isoformat(), "anchor_metric": "net_sales",
               "direction": lab["expected"]["direction"] or "down", "members": []}
        oracle.append(_score_investigation(investigate(tables, p.timezone, inc, dq, known, daily), lab) | {"seed": seed})
        if lab["expected"]["business_anomaly"]:
            hits = [i for i in result.incidents if i["status"] != "suppressed_data_quality" and i["direction"] == lab["expected"]["direction"]
                    and s - pd.Timedelta(days=2) <= pd.Timestamp(i["start"]) <= e]
            if hits:
                e2e.append(_score_investigation(investigate(tables, p.timezone, hits[0], dq, known, daily), lab) | {"seed": seed})
    return {"oracle": oracle, "end_to_end": e2e}


def _rate(rows, key):
    vals = [r[key] for r in rows if key in r]
    return {"correct": int(sum(vals)), "n": len(vals), "rate": round(sum(vals) / len(vals), 3) if vals else None}


def summarize_investigation(rows: list[dict]) -> dict:
    biz = [r for r in rows if "driver_correct" in r]
    by_level = {}
    for lvl in ("Strong", "Moderate", "Weak", "None"):
        sel = [r for r in biz if r["evidence"] == lvl]
        by_level[lvl] = {"n": len(sel), "cause_correct": int(sum(r["cause_correct"] for r in sel))}
    by_kind = {}
    for r in biz:
        k = by_kind.setdefault(r["kind"], {"n": 0, "driver": 0, "segment": 0, "cause": 0})
        k["n"] += 1
        k["driver"] += r["driver_correct"]
        k["segment"] += r["segment_correct"]
        k["cause"] += r["cause_correct"]
    return {
        "driver": _rate(biz, "driver_correct"),
        "segment": _rate(biz, "segment_correct"),
        "cause_or_none": _rate(biz, "cause_correct"),
        "red_herring_rejected": _rate(rows, "red_herring_rejected"),
        "validation_passed": _rate(rows, "validation_passed"),
        "cause_correct_by_evidence": by_level,
        "by_kind": by_kind,
        "rows": rows,
    }


def run_investigation_eval(suites=("dev", "heldout"), profiles=("main", "low_volume"), out_dir: str | Path = "eval_results") -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(exist_ok=True)
    report = {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "results": {}}
    for suite in suites:
        for profile in profiles:
            t = time.time()
            runs = [run_investigation_one(suite, profile, seed) for seed in SUITE_SEEDS[suite]]
            res = {mode: summarize_investigation([r for run in runs for r in run[mode]]) for mode in ("oracle", "end_to_end")}
            report["results"][f"{suite}/{profile}"] = res
            o, e = res["oracle"], res["end_to_end"]
            print(f"{suite:8s} {profile:10s} oracle driver={o['driver']['rate']} segment={o['segment']['rate']} cause={o['cause_or_none']['rate']} "
                  f"herring={o['red_herring_rejected']['rate']} | e2e n={e['driver']['n']} driver={e['driver']['rate']} "
                  f"segment={e['segment']['rate']} cause={e['cause_or_none']['rate']} ({time.time()-t:.0f}s)", flush=True)
    (out_dir / "investigation.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    return report


# ---------------------------------------------------------------- narration eval
def collect_investigations(suite: str = "heldout", profile: str = "main") -> list[dict]:
    """Oracle investigations of every business scenario in the suite (inputs to narration)."""
    from nexuspulse_analytics.investigate import investigate
    from nexuspulse_analytics.monitor import known_event_days
    from nexuspulse_analytics.reconcile import unattributed_share_flags
    from nexuspulse_analytics.kpis import daily_kpis as _dk

    p = PROFILES[profile]
    spec = load_spec(Path("scenarios") / f"{suite}.yaml")
    out = []
    for seed in SUITE_SEEDS[suite]:
        store = generate_store(p, seed, scenarios=sample_scenarios(spec, seed, p.start, p.days))
        tables = store.tables()
        daily = _dk(tables, p.timezone)
        known = known_event_days(tables["change_events"], p.timezone)
        flags = unattributed_share_flags(tables, p.timezone)
        dq = flags.index[flags["flag"]]
        for lab in store.labels:
            if not lab["expected"]["business_anomaly"]:
                continue
            s, e = _window(lab)
            inc = {"incident_id": f"{seed}_{lab['scenario_id']}", "start": lab["start"], "end": e.date().isoformat(),
                   "anchor_metric": "net_sales", "direction": lab["expected"]["direction"], "members": []}
            out.append(investigate(tables, p.timezone, inc, dq, known, daily))
    return out


def run_narration_eval(models=("qwen2.5:3b", "llama3.1:8b"), suite: str = "heldout", profile: str = "main",
                       out_dir: str | Path = "eval_results") -> dict:
    from nexuspulse_analytics.narrate import OllamaProvider, narrate, validate_narration
    from nexuspulse_analytics.report import template_summary

    from .adversarial import run_adversarial

    invs = collect_investigations(suite, profile)
    report = {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "suite": f"{suite}/{profile}", "n_investigations": len(invs)}
    report["adversarial"] = run_adversarial(invs)
    tmpl_ok = sum(not validate_narration({"summary": template_summary(i), "next_steps": []}, i) for i in invs)
    modes = {"template": {"available": True, "n": len(invs), "first_pass": tmpl_ok, "passed_after_retry": 0, "fallback": 0,
                          "unsupported_number_rate_shown": 0.0, "first_attempt_errors": {}}}
    for m in models:
        prov = OllamaProvider(m)
        if not prov.available():
            modes[f"ollama:{m}"] = {"available": False, "note": "model not installed; run: ollama pull " + m}
            continue
        first = retry = fb = 0
        err_kinds: dict = {}
        t = time.time()
        for inv in invs:
            n = narrate(inv, prov)
            v = n["validation"]
            if v and v[0]["errors"]:
                for e in v[0]["errors"]:
                    kind = ("number" if "number" in e else "status" if "status" in e else "direction" if "increase" in e or "decrease" in e
                            else "causal" if "causal" in e else "overclaim" if "overclaiming" in e else "segment" if "mentions" in e
                            else "structure")
                    err_kinds[kind] = err_kinds.get(kind, 0) + 1
            if n["fallback"]:
                fb += 1
            elif n["attempts"] == 1:
                first += 1
            else:
                retry += 1
        modes[f"ollama:{m}"] = {"available": True, "digest": prov.digest, "n": len(invs), "first_pass": first, "passed_after_retry": retry,
                                "fallback": fb, "unsupported_number_rate_shown": 0.0, "first_attempt_errors": err_kinds,
                                "seconds_per_report": round((time.time() - t) / max(1, len(invs)), 1)}
    report["modes"] = modes
    print(json.dumps({k: v for k, v in report.items() if k != "adversarial"} | {"adversarial_catch": report["adversarial"]["catch_rate"]}, indent=1))
    Path(out_dir).mkdir(exist_ok=True)
    (Path(out_dir) / "narration.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    return report


if __name__ == "__main__":
    import sys

    args = dict(a.split("=", 1) for a in sys.argv[1:])
    if args.get("mode") == "narration":
        run_narration_eval(models=tuple(m for m in args.get("models", "qwen2.5:3b,llama3.1:8b").split(",") if m))
        sys.exit(0)
    if args.get("mode") == "investigation":
        run_investigation_eval(suites=tuple(args.get("suites", "dev,heldout").split(",")),
                               profiles=tuple(args.get("profiles", "main,low_volume").split(",")))
        sys.exit(0)
    run_eval(
        suites=tuple(args.get("suites", "dev,heldout").split(",")),
        profiles=tuple(args.get("profiles", "main,low_volume").split(",")),
        configs=tuple(args.get("configs", "robust,robust_masked,plain").split(",")),
    )
