"""Scenario effects and sampling.

A scenario changes the simulated store (traffic, funnel, prices, assortment) and may
write a change event that looks like a real log entry. Its ground-truth label is
returned separately and must only ever reach the evaluation runner.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import yaml

CELL_CHANNELS = ["organic", "paid_social", "paid_search", "email", "direct"]
CELL_DEVICES = ["mobile", "desktop"]

PERMANENT_KINDS = {"price_increase", "gradual_conversion_drift"}

# Neutral event templates. Real causes and red herrings share them, so the text
# carries no hint about whether an event mattered.
_EVENT_TEXT = {
    "deploy": ["Checkout page update deployed", "Storefront theme update deployed", "Payment form update deployed"],
    "campaign": ["Campaign settings changed", "Campaign paused", "Campaign budget updated"],
    "price_change": ["Price list updated"],
    "inventory": ["Inventory sync completed"],
}


@dataclass(frozen=True)
class Scenario:
    kind: str
    start: str
    days: int
    params: dict = field(default_factory=dict)


@dataclass
class Effects:
    traffic: np.ndarray  # (days, 10) multiplier on sessions per cell
    cart: np.ndarray  # (days, 10) multiplier on P(cart)
    buy: np.ndarray  # (days, 10) multiplier on P(purchase | checkout)
    price: np.ndarray  # (days,) multiplier on unit prices
    blocked: list[tuple[int, int, str]]  # (first_day, last_day, category) stock-outs
    tracking: list[tuple[int, int, float]]  # (first_day, last_day, lost_share)
    events: list[tuple[pd.Timestamp, str, str, dict]]  # local time, type, text, scope
    labels: list[dict]


def _cell_mask(segment: dict) -> np.ndarray:
    mask = np.ones(10, dtype=bool)
    for c in range(5):
        for d in range(2):
            i = c * 2 + d
            if "channel" in segment and CELL_CHANNELS[c] != segment["channel"]:
                mask[i] = False
            if "device" in segment and CELL_DEVICES[d] != segment["device"]:
                mask[i] = False
    return mask


def build_effects(scenarios: tuple[Scenario, ...], dates: pd.DatetimeIndex, category_share: dict[str, float], rng) -> Effects:
    n = len(dates)
    fx = Effects(np.ones((n, 10)), np.ones((n, 10)), np.ones((n, 10)), np.ones(n), [], [], [], [])
    for i, sc in enumerate(scenarios):
        start = pd.Timestamp(sc.start)
        s = int((start - dates[0]).days)
        if s < 0 or s >= n:
            raise ValueError(f"scenario {sc.kind} starts outside the simulated range: {sc.start}")
        permanent = sc.kind in PERMANENT_KINDS
        e = n - 1 if permanent else min(n - 1, s + sc.days - 1)
        p = sc.params
        seg = p.get("segment", {})
        mask = _cell_mask(seg)
        truth: dict = {"business_anomaly": True, "data_quality_incident": False, "permanent": permanent}
        event_type = None

        if sc.kind == "conversion_drop":
            fx.buy[s : e + 1, mask] *= p["multiplier"]
            truth.update(direction="down", metrics=["net_revenue", "orders", "session_conversion_rate"],
                         driver="session_conversion_rate", stage="checkout_to_purchase", segment=seg)
            event_type = "deploy" if p.get("event", True) else None
        elif sc.kind == "traffic_loss":
            fx.traffic[s : e + 1, mask] *= p["multiplier"]
            truth.update(direction="down", metrics=["sessions", "net_revenue", "orders"], driver="sessions", segment=seg)
            event_type = "campaign" if p.get("event", True) else None
        elif sc.kind == "traffic_spike":
            fx.traffic[s : e + 1, :] *= p["multiplier"]
            truth.update(direction="up", metrics=["sessions", "net_revenue", "orders"], driver="sessions", segment={})
            event_type = "campaign" if p.get("event", False) else None
        elif sc.kind == "stockout":
            cat = p["category"]
            fx.buy[s : e + 1, :] *= 1 - 0.6 * category_share[cat]
            fx.blocked.append((s, e, cat))
            truth.update(direction="down", metrics=["net_revenue", "orders"], driver="session_conversion_rate",
                         segment={"category": cat})
            event_type = "inventory" if p.get("event", False) else None
        elif sc.kind == "price_increase":
            x = p["pct"]
            fx.price[s:] *= 1 + x
            fx.buy[s:, :] *= max(0.05, 1 - p.get("elasticity", 1.5) * x)
            truth.update(direction="down", metrics=["session_conversion_rate", "orders"],
                         driver="session_conversion_rate", segment={})
            event_type = "price_change"
        elif sc.kind == "gradual_conversion_drift":
            ramp = np.ones(n)
            r = min(sc.days, n - s)
            ramp[s : s + r] = np.linspace(1.0, p["multiplier"], r)
            ramp[s + r :] = p["multiplier"]
            fx.buy[:, mask] *= ramp[:, None]
            truth.update(direction="down", metrics=["session_conversion_rate", "orders", "net_revenue"],
                         driver="session_conversion_rate", segment=seg)
        elif sc.kind == "red_herring":
            truth.update(business_anomaly=False, direction=None, metrics=[], segment={})
            event_type = p.get("event_type", "deploy")
        elif sc.kind == "tracking_breakage":
            fx.tracking.append((s, e, p.get("lost_share", 0.6)))
            truth.update(business_anomaly=False, data_quality_incident=True, direction=None, metrics=[], segment={})
        else:
            raise ValueError(f"unsupported scenario kind: {sc.kind}")

        cause_event = None
        if event_type:
            text = _EVENT_TEXT[event_type][int(rng.integers(len(_EVENT_TEXT[event_type])))]
            at = dates[s] + pd.Timedelta(hours=float(p.get("event_offset_hours", -2.0)))
            scope = {k: v for k, v in seg.items()}
            if sc.kind == "stockout":
                scope = {"category": p["category"]}
            fx.events.append((at, event_type, text, scope))
            cause_event = {"occurred_at_local": at.isoformat(), "type": event_type, "text": text}
        truth["cause_event"] = cause_event if sc.kind != "red_herring" else None
        fx.labels.append(
            {
                "scenario_id": f"sc_{i}",
                "kind": sc.kind,
                "start": dates[s].date().isoformat(),
                "end": None if permanent else dates[e].date().isoformat(),
                "ramp_days": sc.days if permanent else None,
                "params": p,
                "red_herring_event": cause_event if sc.kind == "red_herring" else None,
                "expected": truth,
            }
        )
    return fx


# ---------------------------------------------------------------- sampling ---


def _draw(rng, spec):
    if isinstance(spec, list) and len(spec) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in spec):
        lo, hi = spec
        if isinstance(lo, int) and isinstance(hi, int):
            return int(rng.integers(lo, hi + 1))
        return round(float(rng.uniform(lo, hi)), 3)
    if isinstance(spec, list):
        return spec[int(rng.integers(len(spec)))]
    return spec


def load_spec(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _overlaps_calendar(first: pd.Timestamp, length: int) -> bool:
    """True if [first, first+length) touches a holiday window (Black Friday through
    Dec 23, or the Valentine's window Feb 8-14), with a 1-day margin."""
    for d in pd.date_range(first - pd.Timedelta(days=1), periods=length + 2, freq="D"):
        if (d.month == 11 and d.day >= 20) or (d.month == 12 and d.day <= 24) or (d.month == 2 and 8 <= d.day <= 14):
            return True
    return False


def sample_scenarios(spec: dict, seed: int, start: str, days: int) -> tuple[Scenario, ...]:
    """Place sampled scenarios in non-overlapping windows after a warm-up period."""
    rng = np.random.default_rng(seed)
    warmup, gap = spec.get("warmup_days", 120), spec.get("gap_days", 28)
    items = list(spec["scenarios"])
    order = rng.permutation(len(items))
    temporary = [items[i] for i in order if items[i]["kind"] not in PERMANENT_KINDS]
    permanent = [items[i] for i in order if items[i]["kind"] in PERMANENT_KINDS][:1]  # at most one, placed last
    t0 = pd.Timestamp(start)
    cursor = warmup + int(rng.integers(0, gap))
    out: list[Scenario] = []
    for item in temporary + permanent:
        params = {k: _draw(rng, v) for k, v in item.items() if k not in ("kind", "days")}
        params.setdefault("event_offset_hours", round(float(rng.uniform(-10, 2)), 1))
        length = _draw(rng, item.get("days", [7, 14]))
        tail = 60 if item["kind"] in PERMANENT_KINDS else 0
        # Known calendar windows are excluded from detection by design, so a scenario
        # placed inside one could never be found. Move it past them.
        while _overlaps_calendar(t0 + pd.Timedelta(days=cursor), length):
            cursor += 1
        if cursor + length + tail >= days:
            break
        out.append(Scenario(item["kind"], (t0 + pd.Timedelta(days=cursor)).date().isoformat(), length, params))
        cursor += length + gap + int(rng.integers(0, 14))
    return tuple(out)
