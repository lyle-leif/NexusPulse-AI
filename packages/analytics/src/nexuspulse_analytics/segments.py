"""Segment monitoring: the store-wide detector, run on each channel, device, region and category.

Why: a change confined to one segment (a channel losing most of its traffic, a category
selling out) is large inside that segment but often lost in store-wide noise. Each segment
series gets the same forecast, calibration and alert rules as the store, with stricter
thresholds because many more series are watched (more series, more chances of a false alarm).

Series (all by local date, never using labels):
- session dimensions (channel, device, region): visits, and gross sales of the orders
  those visits produced (session date, as in the revenue bridge);
- product category: order-line value by order date.
Small segments are skipped (under 150 visits a day, or under 5 order lines a day and 5% of sales): their day-to-day noise is too large to monitor usefully.
Segments use the window tests only, with each day's contribution capped, leave open alerts
out of training (segment_config), and drop a reversal soon after an alert ends (drop_recoveries).

A segment alert that overlaps a store-wide alert in the same direction is attached to it
(`segments`); otherwise it becomes its own incident with `scope: "segment"`.
"""
from __future__ import annotations

from dataclasses import replace

import pandas as pd

from .kpis import local_date, segment_core, valid_orders
from .monitor import MonitorConfig, run_monitor

SEGMENT_DIMS = ["channel", "device", "region"]
MIN_SEGMENT_SESSIONS = 150  # average visits per day
MIN_CATEGORY_SHARE = 0.05  # share of line value
MIN_CATEGORY_LINES = 5.0  # average order lines per day


SINGLE_DAY_OFF = 99.0  # a z no real day reaches: single-day tests are off for segments
WINDOW_CLIP = 4.0  # each day's z is capped at this inside segment window sums
RECOVERY_DAYS = 14


def segment_config(config: MonitorConfig) -> MonitorConfig:
    """Rules for segment series (segments=False so this never recurses).

    - Window tests only: segment monitoring is for sustained changes; one-day spikes in a
      single segment were mostly noise in development, and short store-wide spikes are
      still caught by the store monitor.
    - Masking on: days inside an open segment alert are left out of that segment's
      training, so a model that saw a channel lose most of its traffic doesn't treat the
      recovery as a new spike.
    """
    return replace(config, segments=False, masking=True, z_flag=SINGLE_DAY_OFF, z_extreme=SINGLE_DAY_OFF,
                   z_window3=config.seg_z_window, z_window7=config.seg_z_window, window_clip=WINDOW_CLIP)


def drop_recoveries(incidents: list[dict], days: int = RECOVERY_DAYS) -> list[dict]:
    """Drop an alert that reverses an earlier one in the same series soon after it ended.

    After a segment loses most of its traffic, the forecast partly learns the low level, so
    the return to normal looks like a spike. A move back within `days` of the earlier alert's
    end is a recovery, not a new change.
    """
    out: list[dict] = []
    for i in sorted(incidents, key=lambda x: x["start"]):
        prev = out[-1] if out else None
        if (prev is not None and prev["end"] is not None and i["direction"] != prev["direction"]
                and pd.Timestamp(i["start"]) <= pd.Timestamp(prev["end"]) + pd.Timedelta(days=days)):
            continue
        out.append(i)
    return out


def segment_series(tables: dict[str, pd.DataFrame], tz: str, index: pd.DatetimeIndex) -> dict[tuple[str, str], pd.DataFrame]:
    out: dict[tuple[str, str], pd.DataFrame] = {}
    sessions = tables.get("sessions")
    if sessions is not None and len(sessions):
        for dim in SEGMENT_DIMS:
            if dim not in sessions.columns:
                continue
            seg = segment_core(tables, tz, dim)
            for value, g in seg.groupby(level=dim):
                g = g.droplevel(dim).reindex(index, fill_value=0)
                if g["sessions"].mean() < MIN_SEGMENT_SESSIONS:
                    continue
                out[(dim, str(value))] = pd.DataFrame(
                    {"net_sales": g["attributed_gross"] / 100.0, "sessions": g["sessions"].astype(float)}, index=index)
    products = tables.get("products")
    if products is not None and "category" in products.columns and len(tables["order_items"]):
        o = valid_orders(tables["orders"])[["order_id", "placed_at"]].copy()
        o["date"] = local_date(o["placed_at"], tz)
        it = tables["order_items"].merge(o[["order_id", "date"]], on="order_id").merge(products[["product_id", "category"]], on="product_id")
        unit = 100.0 if pd.api.types.is_integer_dtype(tables["order_items"]["unit_price"]) else 1.0  # cents -> dollars
        it["value"] = it["quantity"] * it["unit_price"].astype(float) / unit
        daily = it.groupby(["date", "category"])["value"].sum().unstack(fill_value=0.0).reindex(index, fill_value=0.0)
        lines = it.groupby(["date", "category"]).size().unstack(fill_value=0).reindex(index, fill_value=0)
        total = daily.to_numpy().sum() or 1.0
        for cat in daily.columns:
            if daily[cat].sum() / total >= MIN_CATEGORY_SHARE and lines[cat].mean() >= MIN_CATEGORY_LINES:
                out[("category", str(cat))] = pd.DataFrame({"net_sales": daily[cat]}, index=index)
    return out


def _tag(incidents: list[dict], dim: str, value: str) -> list[dict]:
    out = []
    for i in incidents:
        i = dict(i)
        i["incident_id"] = f"{i['incident_id']}_{dim}-{value}".replace(" ", "_")
        i["scope"] = "segment"
        i["segment"] = {"dimension": dim, "value": value}
        out.append(i)
    return out


def monitor_segments(tables, tz, index, known_days, dq_days, config: MonitorConfig, record_timeline: bool = False):
    """Run the detector per segment. Returns (incidents, timeline day -> incidents)."""
    cfg = segment_config(config)
    incidents: list[dict] = []
    timeline: dict[str, list[dict]] = {}
    for (dim, value), frame in segment_series(tables, tz, index).items():
        res = run_monitor(frame, known_days, dq_days, cfg, record_timeline)
        incidents += _tag(drop_recoveries(res.incidents), dim, value)
        for day, incs in res.timeline.items():
            timeline.setdefault(day, []).extend(_tag(drop_recoveries(incs), dim, value))
    return incidents, timeline


def _overlaps(a: dict, b: dict, last_day: str) -> bool:
    pad = pd.Timedelta(days=2)
    a0, a1 = pd.Timestamp(a["start"]), pd.Timestamp(a["end"] or last_day)
    b0, b1 = pd.Timestamp(b["start"]), pd.Timestamp(b["end"] or last_day)
    return a["direction"] == b["direction"] and a0 <= b1 + pad and b0 <= a1 + pad


def merge_incidents(store: list[dict], segment: list[dict], last_day: str) -> list[dict]:
    """Attach segment incidents to an overlapping store-wide incident; keep the rest as their own."""
    out = [dict(i, scope=i.get("scope", "store"), segments=list(i.get("segments", []))) for i in store]
    alone = []
    for s in segment:
        if s["status"] == "suppressed_data_quality":
            continue
        host = next((i for i in out if i["scope"] == "store" and _overlaps(i, s, last_day)), None)
        if host is not None:
            host["segments"].append({**s["segment"], "start": s["start"], "end": s["end"], "anchor_metric": s["anchor_metric"]})
        else:
            alone.append(s)
    # Overlapping segment-only incidents in the same direction are one incident: keep the earliest.
    merged: list[dict] = []
    for s in sorted(alone, key=lambda i: i["start"]):
        host = next((m for m in merged if _overlaps(m, s, last_day)), None)
        if host is not None:
            host["segments"].append({**s["segment"], "start": s["start"], "end": s["end"], "anchor_metric": s["anchor_metric"]})
        else:
            merged.append(dict(s, segments=[{**s["segment"], "start": s["start"], "end": s["end"], "anchor_metric": s["anchor_metric"]}]))
    return sorted(out + merged, key=lambda i: i["start"])
