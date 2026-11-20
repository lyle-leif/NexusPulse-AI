"""External-dataset evaluation (UCI Online Retail II).

Real: the dataset as-is. There are no labels, so every incident is an unlabeled alert
and the alert rate is an upper bound on the false-alert rate. Forecast accuracy and
interval coverage are compared with seasonal naive (same weekday last week).

Semi-synthetic: real data plus injected drops. An injection removes a random fraction of
the orders placed inside a window, so orders and revenue fall together and the real
noise is kept. Windows avoid bank holidays, late December and each other; the injection
configs are stored with the results. A drop counts as detected by the same rule as the
synthetic eval: a down incident starting no earlier than 2 days before the window and no
later than its end. Alerts that also occur on the untouched data are not counted as new.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from nexuspulse_analytics.forecast import metric_frame
from nexuspulse_analytics.monitor import MonitorConfig
from nexuspulse_analytics.pipeline import analyze
from nexuspulse_ingest.uci import TIMEZONE, UK_BANK_HOLIDAYS, load_uci

SEEDS = range(701, 706)
PER_SEED = 6


def forecast_quality(result, metrics: pd.DataFrame) -> dict:
    out = {}
    for m in ("net_sales", "orders"):
        d = result.daily.xs(m, level="metric")
        d = d[d["state"].isin(["in_range", "out_of_range"]) & (d["actual"] > 0)]
        naive = metrics[m].shift(7).reindex(d.index)
        ok = naive > 0
        mape = float((abs(d["actual"] - d["mean"]) / d["actual"]).mean())
        mape_naive = float((abs(d["actual"][ok] - naive[ok]) / d["actual"][ok]).mean())
        cov = float(((d["actual"] >= d["lo"]) & (d["actual"] <= d["hi"])).mean())
        out[m] = {"mape": round(mape, 3), "mape_seasonal_naive": round(mape_naive, 3), "coverage": round(cov, 3), "days": len(d)}
    return out


def _alerts(result) -> list[dict]:
    return [i for i in result.incidents if i["status"] != "suppressed_data_quality"]


def run_real(config: MonitorConfig = MonitorConfig()) -> dict:
    res = {}
    for cal in (True, False):
        tables, notes = load_uci(calendar=cal)
        daily, result = analyze(tables, TIMEZONE, config)
        metrics = metric_frame(daily)
        days = len(metrics) - config.warmup_days
        al = _alerts(result)
        res["with_calendar" if cal else "no_calendar"] = {
            "monitored_days": days, "alerts": len(al), "alerts_per_30d": round(30 * len(al) / days, 3),
            "alert_list": [{"start": i["start"], "end": i["end"], "anchor": i["anchor_metric"], "direction": i["direction"],
                            "strength": i["strength"]} for i in al],
            "forecast": forecast_quality(result, metrics),
        }
    res["notes"] = notes
    return res


def sample_injections(seed: int, days: pd.DatetimeIndex, n: int = PER_SEED) -> list[dict]:
    rng = np.random.default_rng(seed)
    hol = pd.DatetimeIndex(pd.to_datetime(UK_BANK_HOLIDAYS))
    out, taken = [], pd.DatetimeIndex([])
    while len(out) < n:
        dur = int(rng.integers(3, 15))
        start = days[int(rng.integers(0, len(days) - dur))]
        win = pd.date_range(start, periods=dur)
        pad = pd.date_range(start - pd.Timedelta(days=14), periods=dur + 28)
        if len(pad.intersection(taken)) or len(win.intersection(hol)) or any(d.month == 12 and d.day > 15 for d in win):
            continue
        out.append({"start": start.date().isoformat(), "end": win[-1].date().isoformat(), "days": dur,
                    "drop": round(float(rng.uniform(0.15, 0.6)), 2)})
        taken = taken.union(pad)
    return sorted(out, key=lambda x: x["start"])


def inject(tables: dict, injections: list[dict], seed: int) -> dict:
    rng = np.random.default_rng(seed + 10_000)
    o = tables["orders"]
    local = o["placed_at"].dt.tz_convert(TIMEZONE).dt.tz_localize(None).dt.normalize()
    drop = np.zeros(len(o), dtype=bool)
    for inj in injections:
        inside = ((local >= inj["start"]) & (local <= inj["end"])).to_numpy()
        drop |= inside & (rng.random(len(o)) < inj["drop"])
    kept = o[~drop]
    t = dict(tables)
    t["orders"] = kept.reset_index(drop=True)
    t["order_items"] = tables["order_items"][tables["order_items"]["order_id"].isin(kept["order_id"])].reset_index(drop=True)
    return t


def run_semi(config: MonitorConfig = MonitorConfig(), seeds=SEEDS) -> dict:
    tables, _ = load_uci()
    daily, base = analyze(tables, TIMEZONE, config)
    metrics = metric_frame(daily)
    base_starts = {(i["start"], i["direction"]) for i in _alerts(base)}
    candidates = metrics.index[config.warmup_days + 14 : -21]
    rows, new_alerts = [], 0
    for seed in seeds:
        injs = sample_injections(seed, candidates)
        _, res = analyze(inject(tables, injs, seed), TIMEZONE, config)
        al = _alerts(res)
        used: set[int] = set()
        for inj in injs:
            s, e = pd.Timestamp(inj["start"]), pd.Timestamp(inj["end"])
            hits = [k for k, i in enumerate(al) if i["direction"] == "down" and s - pd.Timedelta(days=2) <= pd.Timestamp(i["start"]) <= e]
            used.update(hits)
            row = inj | {"seed": seed, "detected": bool(hits)}
            if hits:
                row["delay_days"] = max(0, (pd.Timestamp(al[hits[0]]["start"]) - s).days)
            rows.append(row)
        new_alerts += sum(1 for k, i in enumerate(al) if k not in used and (i["start"], i["direction"]) not in base_starts)

    def rate(sel):
        return {"detected": sum(r["detected"] for r in sel), "n": len(sel)}

    det = [r for r in rows if r["detected"]]
    return {
        "recall": round(len(det) / len(rows), 3), "n": len(rows),
        "recall_by_drop": {"15-25%": rate([r for r in rows if r["drop"] < 0.25]),
                           "25-40%": rate([r for r in rows if 0.25 <= r["drop"] < 0.4]),
                           "40-60%": rate([r for r in rows if r["drop"] >= 0.4])},
        "recall_by_duration": {"3-6 days": rate([r for r in rows if r["days"] <= 6]),
                               "7-14 days": rate([r for r in rows if r["days"] >= 7])},
        "median_delay_days": float(np.median([r["delay_days"] for r in det])) if det else None,
        "new_alerts_not_injected": new_alerts,
        "injections": rows,
    }


def run_external_eval(out_dir: str | Path = "eval_results") -> dict:
    t = time.time()
    out = {"dataset": "UCI Online Retail II", "real": run_real()}
    print("real done", round(time.time() - t), flush=True)
    out["semi_synthetic"] = run_semi()
    print("semi done", round(time.time() - t), flush=True)
    Path(out_dir).mkdir(exist_ok=True)
    (Path(out_dir) / "external.json").write_text(json.dumps(out, indent=2, default=str))
    return out


if __name__ == "__main__":
    r = run_external_eval()
    for k in ("with_calendar", "no_calendar"):
        v = r["real"][k]
        print(k, v["alerts"], v["alerts_per_30d"], v["forecast"])
    print({k: v for k, v in r["semi_synthetic"].items() if k != "injections"})
