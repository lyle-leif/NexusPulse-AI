"""NexusPulse analytics API. Serves precomputed results; heavy work stays out of requests.

Isolation: this service imports only the analytics package and connects with the
np_pipeline role. It never imports the generator or eval packages.
Run: uv run uvicorn main:app --app-dir services/api --port 8000
"""
from __future__ import annotations

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
from nexuspulse_analytics.investigate import investigate  # noqa: E402
from nexuspulse_analytics.monitor import known_event_days  # noqa: E402
from nexuspulse_analytics.pipeline import analyze  # noqa: E402

EVAL_RESULTS = ROOT / "eval_results" / "detection.json"

# Workspace configuration (a workspace table comes with multi-tenancy later).
WORKSPACES = {
    "demo": {"name": "Demo fashion boutique", "timezone": "Asia/Manila", "currency": "USD", "batch": "v1"},
}

app = FastAPI(title="NexusPulse API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["GET"])


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
    daily, monitor = analyze(tables, tz)
    flags = unattributed_share_flags(tables, tz)
    return {"tables": tables, "tz": tz, "daily": daily, "monitor": monitor, "flags": flags,
            "dq_days": flags.index[flags["flag"]], "known_days": known_event_days(tables["change_events"], tz)}


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
    return _compute(workspace)


@app.get("/api/evaluation")
def evaluation() -> dict:
    """Published evaluation results (written by the eval runner; contains scores, not raw labels)."""
    if not EVAL_RESULTS.exists():
        raise HTTPException(404, "no evaluation results yet; run the eval runner")
    import json

    return json.loads(EVAL_RESULTS.read_text(encoding="utf-8"))


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
