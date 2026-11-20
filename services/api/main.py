"""NexusPulse analytics API. Serves precomputed results; heavy work stays out of requests.

Isolation: this service imports only the analytics package and connects with the
np_pipeline role. It never imports the generator or eval packages.
Run: uv run uvicorn main:app --app-dir services/api --port 8000
"""
from __future__ import annotations

import os
import pathlib
import sys
from functools import lru_cache

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "analytics" / "src"))

import pandas as pd  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from nexuspulse_analytics import daily_kpis, run_reconciliation, unattributed_share_flags  # noqa: E402
from nexuspulse_analytics.db import read_tables  # noqa: E402
from nexuspulse_analytics.kpis import channel_sales  # noqa: E402
from nexuspulse_analytics.investigate import investigate  # noqa: E402
from nexuspulse_analytics.narrate import OllamaProvider, narrate  # noqa: E402
from nexuspulse_analytics.report import build_report  # noqa: E402
from nexuspulse_analytics.monitor import known_event_days  # noqa: E402
from nexuspulse_analytics.pipeline import analyze  # noqa: E402

EVAL_RESULTS = ROOT / "eval_results" / "detection.json"
INV_RESULTS = ROOT / "eval_results" / "investigation.json"
NAR_RESULTS = ROOT / "eval_results" / "narration.json"
EXT_RESULTS = ROOT / "eval_results" / "external.json"

# Workspace configuration (a workspace table comes with multi-tenancy later).
WORKSPACES = {
    "demo": {"name": "Demo fashion boutique", "timezone": "Asia/Manila", "currency": "USD", "batch": "v1"},
}

app = FastAPI(title="NexusPulse API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://localhost:3001"], allow_methods=["GET"])


def _dollars(cents) -> float:
    return round(float(cents) / 100.0, 2)


def _period(d: pd.DataFrame) -> dict:
    s = d.sum()
    sessions = int(s["sessions"])
    conv = s["converting_sessions"] / sessions if sessions else 0.0
    aov = s["attributed_gross_session_date"] / s["attributed_orders"] if s["attributed_orders"] else 0.0
    return {
        "net_revenue": _dollars(s["net_revenue_bridge"]),
        "sessions": sessions,
        "orders": int(s["orders"]),
        "session_conversion_rate": round(float(conv), 5),
        "attributed_aov": _dollars(aov),
        "unattributed_share": round(float(s["unattributed_orders"] / s["orders"]), 5) if s["orders"] else 0.0,
    }


def _bridge(d: pd.DataFrame) -> list[dict]:
    s = d.sum()
    lines = [
        ("Attributed gross sales", s["attributed_gross_session_date"], 1),
        ("Timing difference", s["timing_difference"], 1),
        ("Unattributed gross sales", s["unattributed_gross"], 1),
        ("Discounts", s["discounts"], -1),
        ("Refunds", s["refunds"], -1),
    ]
    out = [{"label": n, "amount": _dollars(v * sign)} for n, v, sign in lines]
    out.append({"label": "Net revenue", "amount": _dollars(s["net_revenue_bridge"]), "total": True})
    return out


def _runs(flags: pd.Series) -> list[dict]:
    runs, start, prev = [], None, None
    for day, on in flags.items():
        if on and start is None:
            start = day
        if not on and start is not None:
            runs.append({"start": start.date().isoformat(), "end": prev.date().isoformat()})
            start = None
        prev = day
    if start is not None:
        runs.append({"start": start.date().isoformat(), "end": prev.date().isoformat(), "open": True})
    return runs


@lru_cache(maxsize=4)
def _state(workspace: str) -> dict:
    """Load and analyse a workspace once; shared by overview and investigations."""
    cfg = WORKSPACES[workspace]
    tables = read_tables(workspace, cfg["batch"])
    tz = cfg["timezone"]
    daily, monitor = analyze(tables, tz, record_timeline=True)
    flags = unattributed_share_flags(tables, tz)
    return {"tables": tables, "tz": tz, "daily": daily, "monitor": monitor, "flags": flags,
            "dq_days": flags.index[flags["flag"]], "known_days": known_event_days(tables["change_events"], tz)}


def _funnel(tables: dict, tz: str, daily: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Visitors to revenue for one period, by session date (orders and revenue by order date)."""
    s = tables["sessions"]
    day = s["started_at"].dt.tz_convert(tz).dt.tz_localize(None).dt.normalize()
    s = s[(day >= start) & (day <= end)]
    d = daily.loc[start:end].sum()
    return {
        "sessions": int(len(s)),
        "reached_cart": int(s["reached_cart"].sum()),
        "reached_checkout": int(s["reached_checkout"].sum()),
        "converting_sessions": int(d["converting_sessions"]),
        "orders": int(d["orders"]),
        "net_revenue": _dollars(d["net_revenue_bridge"]),
    }


CHANNEL_LABEL = {"organic": "Organic search", "paid_search": "Paid search", "paid_social": "Paid social", "email": "Email", "direct": "Direct"}


def _channels(tables: dict, tz: str, daily: pd.DataFrame, cur: pd.DataFrame, prev: pd.DataFrame) -> list[dict]:
    """Gross sales by channel (session date, as in the bridge) plus orders not linked to a visit (order date)."""
    a = channel_sales(tables, tz, cur.index[0], cur.index[-1])
    b = channel_sales(tables, tz, prev.index[0], prev.index[-1])
    rows = []
    for ch, r in a.iterrows():
        before = float(b["attributed_gross"].get(ch, 0))
        rows.append({"key": ch, "label": CHANNEL_LABEL.get(ch, str(ch).replace("_", " ").title()), "visits": int(r["sessions"]),
                     "orders": int(r["attributed_orders"]), "value": _dollars(r["attributed_gross"]),
                     "change": round(float(r["attributed_gross"]) / before - 1, 4) if before else None})
    u_now, u_before = float(cur["unattributed_gross"].sum()), float(prev["unattributed_gross"].sum())
    rows.append({"key": "unlinked", "label": "Orders not linked to a visit", "visits": None, "orders": int(cur["unattributed_orders"].sum()),
                 "value": _dollars(u_now), "change": round(u_now / u_before - 1, 4) if u_before else None})
    return rows


def _forecast_view(monitor, day: pd.Timestamp, window: int) -> dict:
    """As-of forecast band for the last `window` days and the forecast issued for the days after `day`."""
    ns = monitor.daily.xs("net_sales", level="metric")
    past = ns.loc[day - pd.Timedelta(days=window - 1): day]
    series = [{"date": i.date().isoformat(), "actual": round(float(r["actual"]), 2), "expected": round(float(r["mean"]), 2),
               "lo": round(float(r["lo"]), 2), "hi": round(float(r["hi"]), 2), "state": r["state"]} for i, r in past.iterrows()]
    issued = [f for f in monitor.forecasts if f.metric == "net_sales" and f.as_of <= day and f.frame.index[-1] > day]
    ahead = []
    if issued:
        fc = issued[-1]
        ahead = [{"date": i.date().isoformat(), "expected": round(float(r["mean"]), 2), "lo": round(float(r["lo"]), 2),
                  "hi": round(float(r["hi"]), 2)} for i, r in fc.frame[fc.frame.index > day].iterrows()]
    return {"series": series, "forecast_ahead": ahead}


def _overview_forecast(st: dict) -> dict:
    """As-of band for the last 56 days plus a 7-day forecast issued from all data up to today."""
    from nexuspulse_analytics.forecast import fit_forecast, metric_frame

    mon = st["monitor"]
    view = _forecast_view(mon, mon.daily.index.get_level_values("date").max(), 56)
    if not view["forecast_ahead"]:
        hist = metric_frame(st["daily"])["net_sales"]
        fc = fit_forecast(hist, "net_sales", 7, model=mon.config.model, robust=mon.config.robust, exclude_days=st["known_days"])
        view["forecast_ahead"] = [{"date": i.date().isoformat(), "expected": round(float(r["mean"]), 2), "lo": round(float(r["lo"]), 2),
                                   "hi": round(float(r["hi"]), 2)} for i, r in fc.frame.iterrows()]
    return view


@lru_cache(maxsize=4)
def _compute(workspace: str) -> dict:
    cfg = WORKSPACES[workspace]
    st = _state(workspace)
    tables, tz, daily, flags, monitor = st["tables"], st["tz"], st["daily"], st["flags"], st["monitor"]
    checks = run_reconciliation(tables, tz)

    cur, prev = daily.iloc[-28:], daily.iloc[-56:-28]
    series = pd.DataFrame(
        {
            "date": daily.index.strftime("%Y-%m-%d"),
            "net_revenue": (daily["net_revenue_bridge"] / 100).round(2),
            "sessions": daily["sessions"],
            "orders": daily["orders"],
            "session_conversion_rate": (daily["converting_sessions"] / daily["sessions"].where(daily["sessions"] > 0)).round(5),
            "unattributed_share": flags["share"].round(5),
        }
    ).astype(object).where(lambda x: x.notna(), None)

    return {
        "workspace": {"id": workspace, **{k: v for k, v in cfg.items() if k != "batch"}},
        "data_label": "Synthetic",
        "range": {"start": daily.index[0].date().isoformat(), "end": daily.index[-1].date().isoformat()},
        "current_period": {"start": cur.index[0].date().isoformat(), "end": cur.index[-1].date().isoformat(), **_period(cur)},
        "previous_period": {"start": prev.index[0].date().isoformat(), "end": prev.index[-1].date().isoformat(), **_period(prev)},
        "revenue_bridge": _bridge(cur),
        "series": series.to_dict(orient="records"),
        "reconciliation": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks],
        "data_quality_incidents": [
            {"type": "unattributed_order_share", "threshold": 0.10, **r} for r in _runs(flags["flag"])
        ],
        "incidents": sorted(monitor.incidents, key=lambda i: i["start"], reverse=True),
        "funnel": {"current": _funnel(tables, tz, daily, cur.index[0], cur.index[-1]),
                   "previous": _funnel(tables, tz, daily, prev.index[0], prev.index[-1])},
        "forecast": _overview_forecast(st),
        "channels": _channels(tables, tz, daily, cur, prev),
        "monitor_config": monitor.config.as_dict(),
        "notes": [
            "Recent refunds are restated as they arrive, so the latest days may understate refunds.",
            "Net revenue is bucketed by order date in the workspace timezone.",
        ],
    }


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/overview")
def overview(workspace: str = "demo") -> dict:
    if workspace not in WORKSPACES:
        raise HTTPException(404, f"unknown workspace {workspace!r}")
    return _clean(_compute(workspace))


@app.get("/api/evaluation")
def evaluation() -> dict:
    """Published evaluation results (written by the eval runner; contains scores, not raw labels)."""
    if not EVAL_RESULTS.exists():
        raise HTTPException(404, "no evaluation results yet; run the eval runner")
    import json

    out = json.loads(EVAL_RESULTS.read_text(encoding="utf-8"))
    if INV_RESULTS.exists():
        out["investigation"] = json.loads(INV_RESULTS.read_text(encoding="utf-8"))
    if NAR_RESULTS.exists():
        out["narration"] = json.loads(NAR_RESULTS.read_text(encoding="utf-8"))
    if EXT_RESULTS.exists():
        ext = json.loads(EXT_RESULTS.read_text(encoding="utf-8"))
        ext["semi_synthetic"].pop("injections", None)
        out["external"] = ext
    return out


@lru_cache(maxsize=64)
def _investigation(workspace: str, incident_id: str) -> dict:
    st = _state(workspace)
    inc = next((i for i in st["monitor"].incidents if i["incident_id"] == incident_id), None)
    if inc is None:
        raise HTTPException(404, f"unknown incident {incident_id!r}")
    if inc["status"] == "suppressed_data_quality":
        raise HTTPException(409, "incident is suppressed because of a data-quality issue; it is not investigated as a business change")
    inv = investigate(st["tables"], st["tz"], inc, st["dq_days"], st["known_days"], st["daily"])
    out = {"incident": inc, "workspace": {"id": workspace, **{k: v for k, v in WORKSPACES[workspace].items() if k != "batch"}},
           "data_label": "Synthetic", **inv}
    return _clean(out)


def _clean(o):
    """JSON-safe copy: numpy scalars to Python, NaN/inf to None."""
    import math

    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if hasattr(o, "item") and not isinstance(o, (str, bytes)):
        o = o.item()
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


@app.get("/api/incidents/{incident_id}/investigation")
def investigation(incident_id: str, workspace: str = "demo") -> dict:
    if workspace not in WORKSPACES:
        raise HTTPException(404, f"unknown workspace {workspace!r}")
    return _investigation(workspace, incident_id)


# Optional AI narration model (local Ollama). Reports default to the template.
LLM_MODEL = os.environ.get("NEXUSPULSE_LLM", "llama3.1:8b")  # chosen by the narration eval


@lru_cache(maxsize=64)
def _report(workspace: str, incident_id: str, mode: str) -> dict:
    inv = _investigation(workspace, incident_id)
    provider = None
    note = None
    if mode != "template":
        p = OllamaProvider(LLM_MODEL)
        if p.available():
            provider = p
        else:
            note = f"No local model available ({LLM_MODEL}); showing the template report."
    rep = build_report(inv, WORKSPACES[workspace]["currency"], narration=narrate(inv, provider))
    rep["narration"]["note"] = note
    return _clean(rep)


@app.get("/api/incidents/{incident_id}/report")
def report(incident_id: str, workspace: str = "demo", narration: str = "template") -> dict:
    """Template by default (the narration eval found it clearer and instant); narration=ai asks the local model."""
    if workspace not in WORKSPACES:
        raise HTTPException(404, f"unknown workspace {workspace!r}")
    return _report(workspace, incident_id, "ai" if narration == "ai" else "template")


# ---------------------------------------------------------------- Time Machine
# The monitor processes one day at a time and records its incident list after each day,
# so the view for day D is exactly what a run stopped on D reports (tested in
# tests/test_timemachine.py). Investigations for day D run on data up to the end of D.


def _truncate(tables: dict, tz: str, day: str) -> dict:
    cutoff = (pd.Timestamp(day) + pd.Timedelta(days=1)).tz_localize(tz).tz_convert("UTC")
    cols = {"sessions": "started_at", "orders": "placed_at", "refunds": "refunded_at", "change_events": "occurred_at"}
    out = dict(tables)
    for t, c in cols.items():
        out[t] = tables[t][tables[t][c] < cutoff].reset_index(drop=True)
    out["order_items"] = tables["order_items"][tables["order_items"]["order_id"].isin(out["orders"]["order_id"])]
    out["marketing_spend"] = tables["marketing_spend"][pd.to_datetime(tables["marketing_spend"]["spend_date"]) <= pd.Timestamp(day)]
    return out


@app.get("/api/timemachine")
def timemachine(day: str | None = None, workspace: str = "demo", window: int = 120) -> dict:
    if workspace not in WORKSPACES:
        raise HTTPException(404, f"unknown workspace {workspace!r}")
    st = _state(workspace)
    mon = st["monitor"]
    days = sorted(mon.timeline)
    if not days:
        raise HTTPException(404, "no timeline recorded")
    day = day if day in mon.timeline else days[0]
    d = pd.Timestamp(day)
    fv = _forecast_view(mon, d, window)
    series, ahead = fv["series"], fv["forecast_ahead"]
    ev = st["tables"]["change_events"]
    cutoff = (d + pd.Timedelta(days=1)).tz_localize(st["tz"]).tz_convert("UTC")
    recent = ev[(ev["occurred_at"] < cutoff) & (ev["occurred_at"] >= cutoff - pd.Timedelta(days=30))]
    incidents = sorted(mon.timeline[day], key=lambda i: i["start"], reverse=True)
    next_new = next((x for x in days if x > day and len(mon.timeline[x]) > len(mon.timeline[day])), None)
    return _clean({
        "workspace": {"id": workspace, **{k: v for k, v in WORKSPACES[workspace].items() if k != "batch"}},
        "data_label": "Synthetic", "day": day, "first_day": days[0], "last_day": days[-1], "next_incident_day": next_new,
        "series": series, "forecast_ahead": ahead,
        "incidents": incidents,
        "events": [{"occurred_at": r["occurred_at"].isoformat(), "event_type": r["event_type"], "description": r["description"]}
                   for _, r in recent.iterrows()],
    })


@lru_cache(maxsize=128)
def _tm_report(workspace: str, day: str, incident_id: str) -> dict:
    st = _state(workspace)
    inc = next((i for i in st["monitor"].timeline.get(day, []) if i["incident_id"] == incident_id), None)
    if inc is None:
        raise HTTPException(404, f"incident {incident_id!r} is not known on {day}")
    if inc["status"] == "suppressed_data_quality":
        raise HTTPException(409, "incident is suppressed because of a data-quality issue")
    tables = _truncate(st["tables"], st["tz"], day)
    inc_as_of = dict(inc, end=inc["end"] or day)  # an open incident is investigated up to the selected day
    dq = st["dq_days"][st["dq_days"] <= pd.Timestamp(day)]
    known = st["known_days"][st["known_days"] <= pd.Timestamp(day)]
    inv = investigate(tables, st["tz"], inc_as_of, dq, known)
    rep = build_report(inv, WORKSPACES[workspace]["currency"], narration=narrate(inv, None))
    return _clean({"day": day, "incident": inc, "evidence": inv["explanation_evidence"], "report": rep})


@app.get("/api/timemachine/report")
def timemachine_report(day: str, incident_id: str, workspace: str = "demo") -> dict:
    if workspace not in WORKSPACES:
        raise HTTPException(404, f"unknown workspace {workspace!r}")
    return _tm_report(workspace, day, incident_id)
