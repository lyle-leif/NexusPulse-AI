"use client";

import { useState } from "react";
import type { Overview } from "@/lib/api";
import { int, money, pct } from "@/lib/format";
import LineChart, { type Band } from "./LineChart";

const RANGES = [
  { label: "90 days", days: 90 },
  { label: "180 days", days: 180 },
  { label: "All", days: Infinity },
];

export default function TrendPanel({ data }: { data: Overview }) {
  const [range, setRange] = useState(180);
  const series = range === Infinity ? data.series : data.series.slice(-range);
  const bands: Band[] = data.data_quality_incidents.map((i) => ({ start: i.start, end: i.end, label: "Data-quality incident" }));
  const cur = data.workspace.currency;

  return (
    <section aria-labelledby="trends" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="trends" className="section-title">Daily trends</h2>
        <div role="group" aria-label="Time range" className="segmented">
          {RANGES.map((r) => (
            <button key={r.label} type="button" aria-pressed={range === r.days} onClick={() => setRange(r.days)}>
              {r.label}
            </button>
          ))}
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <LineChart title="Net revenue (order date)" data={series.map((s) => ({ date: s.date, value: s.net_revenue }))} format={(v) => money(v, cur)} bands={bands} />
        <LineChart title="Sessions" data={series.map((s) => ({ date: s.date, value: s.sessions }))} format={int} bands={bands} />
        <LineChart
          title="Session conversion rate"
          data={series.map((s) => ({ date: s.date, value: s.session_conversion_rate }))}
          format={(v) => pct(v, 1)}
          bands={bands}
        />
        <LineChart
          title="Unattributed order share (14-day trailing)"
          data={series.map((s) => ({ date: s.date, value: s.unattributed_share }))}
          format={(v) => pct(v, 0)}
          threshold={{ value: 0.1, label: "Alert threshold 10%" }}
          bands={bands}
        />
      </div>
    </section>
  );
}
