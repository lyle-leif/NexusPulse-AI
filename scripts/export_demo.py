"""Precompute the Time Machine JSON for the static GitHub Pages demo.

Reads from the running local API (http://localhost:8000) and writes
apps/web/public/demo/tm/{day}.json, start.json and report/{day}_{incident}.json.

Investigations are stored for the day each incident is first detected and the day it
ends (or the last day it is listed); each day file records which stored investigation applies.
Run: uv run python scripts/export_demo.py
"""
from __future__ import annotations

import json
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = "http://localhost:8000"
OUT = Path("apps/web/public/demo/tm")


def get(path: str, **q) -> dict:
    url = f"{API}{path}" + (f"?{urllib.parse.urlencode(q)}" if q else "")
    with urllib.request.urlopen(url, timeout=600) as r:
        return json.load(r)


def main() -> int:
    first = get("/api/timemachine")
    d, last = first["first_day"], first["last_day"]
    days = []
    while True:
        days.append(d)
        if d == last:
            break
        d = str((__import__("datetime").date.fromisoformat(d) + __import__("datetime").timedelta(days=1)))
    views = {}
    for i, day in enumerate(days):
        views[day] = get("/api/timemachine", day=day)
        if i % 50 == 0:
            print("day", day, flush=True)

    # report days per incident: first day known, and the day it ends (or the last day it is listed)
    seen: dict[str, dict] = {}
    for day in days:
        for inc in views[day]["incidents"]:
            s = seen.setdefault(inc["incident_id"], {"first": day, "suppressed": False})
            s["suppressed"] = inc["status"] == "suppressed_data_quality"
            s["last_seen"] = day  # ids can disappear when an incident is merged into another
            if inc["end"] is not None and "final" not in s:
                s["final"] = day
    report_days: dict[str, list[str]] = {}
    for iid, s in seen.items():
        if s["suppressed"]:
            continue
        report_days[iid] = sorted({s["first"], s.get("final", s["last_seen"])})

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "report").mkdir(parents=True)
    n = 0
    for iid, rds in report_days.items():
        for day in rds:
            try:
                rep = get("/api/timemachine/report", day=day, incident_id=iid)
            except Exception as e:  # e.g. suppressed on that day
                print("skip", iid, day, e)
                continue
            (OUT / "report" / f"{day}_{iid}.json").write_text(json.dumps(rep, separators=(",", ":")))
            n += 1
    stored = {p.stem for p in (OUT / "report").glob("*.json")}
    for day, v in views.items():
        for inc in v["incidents"]:
            ok = [x for x in report_days.get(inc["incident_id"], []) if x <= day and f"{x}_{inc['incident_id']}" in stored]
            inc["static_report_day"] = ok[-1] if ok else None
        (OUT / f"{day}.json").write_text(json.dumps(v, separators=(",", ":")))
    (OUT / "start.json").write_text(json.dumps(views[days[0]], separators=(",", ":")))
    print(f"{len(days)} days, {n} investigations ->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
