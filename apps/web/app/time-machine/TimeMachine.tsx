"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { STATIC_DEMO, getTimeMachineDay, getTimeMachineReport, type TimeMachineDay, type TmReport } from "@/lib/api";
import { money, shortDate } from "@/lib/format";

const addDays = (iso: string, n: number) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

const METRIC: Record<string, string> = {
  net_sales: "Net sales",
  orders: "Orders",
  sessions: "Sessions",
  session_conversion_rate: "Conversion rate",
};

function Chart({ tm }: { tm: TimeMachineDay }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);
  const [hover, setHover] = useState<number | null>(null);
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(300, Math.floor(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const H = 240;
  const P = { top: 12, right: 12, bottom: 24, left: 64 };
  const past = tm.series;
  const ahead = tm.forecast_ahead;
  const n = past.length + ahead.length;
  const all = [...past.flatMap((p) => [p.actual, p.lo, p.hi]), ...ahead.flatMap((p) => [p.lo, p.hi])];
  const lo = Math.min(0, ...all);
  const hi = Math.max(...all) * 1.05;
  const x = (i: number) => P.left + (i * (width - P.left - P.right)) / Math.max(1, n - 1);
  const y = (v: number) => P.top + (1 - (v - lo) / (hi - lo || 1)) * (H - P.top - P.bottom);
  const area = (pts: { lo: number; hi: number }[], off: number) =>
    pts.length
      ? `M${pts.map((p, i) => `${x(i + off)},${y(p.hi)}`).join("L")}L${pts
          .map((p, i) => [x(i + off), y(p.lo)] as const)
          .reverse()
          .map(([a, b]) => `${a},${b}`)
          .join("L")}Z`
      : "";
  const line = past.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.actual)}`).join("");
  const today = past.length - 1;
  const ticks = [lo, (lo + hi) / 2, hi];
  const cur = tm.workspace.currency;
  const spans = tm.incidents
    .map((inc) => {
      const s = past.findIndex((p) => p.date >= inc.start);
      const e = inc.end ? past.findIndex((p) => p.date > inc.end!) : -1;
      return s < 0 ? null : { id: inc.incident_id, s, e: e < 0 ? today : e - 1, dir: inc.direction };
    })
    .filter((v): v is { id: string; s: number; e: number; dir: "up" | "down" } => v !== null);
  const hp = hover !== null && hover < past.length ? past[hover] : null;
  const ha = hover !== null && hover >= past.length ? ahead[hover - past.length] : null;

  return (
    <div ref={wrap} className="relative">
      <svg
        width={width}
        height={H}
        role="img"
        aria-label={`Net sales up to ${tm.day} with the forecast range issued before each day, and the forecast for the next days`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const i = Math.round(((e.clientX - r.left - P.left) / (width - P.left - P.right)) * (n - 1));
          setHover(i >= 0 && i < n ? i : null);
        }}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={P.left} x2={width - P.right} y1={y(t)} y2={y(t)} stroke="var(--border)" />
            <text x={P.left - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--text-secondary)">
              {money(t, cur)}
            </text>
          </g>
        ))}
        {spans.map((s) => (
          <rect key={s.id} x={x(s.s) - 2} width={Math.max(4, x(s.e) - x(s.s) + 4)} y={P.top} height={H - P.top - P.bottom}
            fill={s.dir === "down" ? "var(--neg)" : "var(--pos)"} opacity={0.12} />
        ))}
        <path d={area(past, 0)} fill="var(--band)" />
        <path d={area(ahead, past.length)} fill="var(--band)" stroke="var(--text-secondary)" strokeDasharray="3 3" strokeWidth={1} />
        <path d={line} fill="none" stroke="var(--series-1)" strokeWidth={2} />
        <line x1={x(today)} x2={x(today)} y1={P.top} y2={H - P.bottom} stroke="var(--foreground)" strokeWidth={1} />
        <text x={x(today) - 4} y={P.top + 10} fontSize="11" textAnchor="end" fill="var(--foreground)">
          today
        </text>
        <text x={P.left} y={H - 6} fontSize="11" fill="var(--text-secondary)">
          {shortDate(past[0]?.date ?? tm.day)}
        </text>
        <text x={width - P.right} y={H - 6} fontSize="11" textAnchor="end" fill="var(--text-secondary)">
          {shortDate(ahead.at(-1)?.date ?? tm.day)}
        </text>
        {hover !== null ? <line x1={x(hover)} x2={x(hover)} y1={P.top} y2={H - P.bottom} stroke="var(--text-secondary)" strokeDasharray="2 2" /> : null}
      </svg>
      {hp || ha ? (
        <div className="viz-tooltip" style={{ left: Math.min(x(hover!) + 8, width - 200), top: 8 }}>
          <div className="font-medium">{shortDate((hp ?? ha)!.date)}</div>
          {hp ? <div>Actual {money(hp.actual, cur)}</div> : <div className="muted">Not yet happened</div>}
          <div>
            Expected {money((hp ?? ha)!.expected, cur)} ({money((hp ?? ha)!.lo, cur)} to {money((hp ?? ha)!.hi, cur)})
          </div>
          {hp && hp.state !== "in_range" ? <div className="muted">{hp.state.replaceAll("_", " ")}</div> : null}
        </div>
      ) : null}
    </div>
  );
}

export default function TimeMachine() {
  const [day, setDay] = useState<string | undefined>(undefined);
  const [tm, setTm] = useState<TimeMachineDay | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [rep, setRep] = useState<TmReport | null>(null);
  const [repErr, setRepErr] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    let live = true;
    getTimeMachineDay(day)
      .then((d) => live && (setTm(d), setErr(null)))
      .catch((e) => live && setErr(String(e.message ?? e)));
    return () => {
      live = false;
    };
  }, [day]);

  useEffect(() => {
    setRep(null);
    setRepErr(null);
    if (!sel || !tm) return;
    let live = true;
    // The static demo stores investigations for the day an incident is first detected and
    // the day it ends; it shows the latest of those up to the selected day.
    const inc = tm.incidents.find((i) => i.incident_id === sel);
    const repDay = STATIC_DEMO ? inc?.static_report_day : tm.day;
    if (!repDay) {
      setRepErr(STATIC_DEMO ? "Not investigated in the static demo (data-quality incident)." : "Unknown incident.");
      return;
    }
    getTimeMachineReport(repDay, sel)
      .then((r) => live && setRep(r))
      .catch((e) => live && setRepErr(String(e.message ?? e)));
    return () => {
      live = false;
    };
  }, [sel, tm]);

  const go = useCallback(
    (d: string) => {
      if (!tm) return;
      setDay(d < tm.first_day ? tm.first_day : d > tm.last_day ? tm.last_day : d);
    },
    [tm],
  );

  useEffect(() => {
    if (!playing || !tm) return;
    if (tm.day >= tm.last_day) {
      setPlaying(false);
      return;
    }
    const t = setTimeout(() => go(addDays(tm.day, 1)), 600);
    return () => clearTimeout(t);
  }, [playing, tm, go]);

  if (err) return <p role="alert">Could not load the Time Machine: {err}. Is the API running?</p>;
  if (!tm) return <p className="muted">Loading...</p>;
  const cur = tm.workspace.currency;
  const dayIdx = Math.round((Date.parse(tm.day) - Date.parse(tm.first_day)) / 86400000);
  const total = Math.round((Date.parse(tm.last_day) - Date.parse(tm.first_day)) / 86400000);

  return (
    <div className="space-y-6">
      <section className="card" aria-labelledby="ctl">
        <h2 id="ctl" className="sr-only">
          Controls
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-lg font-semibold">{shortDate(tm.day)}</span>
          <span className="muted text-sm">
            day {dayIdx + 1} of {total + 1}
          </span>
          <span className="grow" />
          <button className="pill" onClick={() => go(addDays(tm.day, -1))} disabled={tm.day <= tm.first_day}>
            Back 1 day
          </button>
          <button className="pill" onClick={() => setPlaying((p) => !p)} aria-pressed={playing}>
            {playing ? "Pause" : "Play"}
          </button>
          <button className="pill" onClick={() => go(addDays(tm.day, 1))} disabled={tm.day >= tm.last_day}>
            Next day
          </button>
          <button className="pill" onClick={() => go(addDays(tm.day, 7))} disabled={tm.day >= tm.last_day}>
            Next week
          </button>
          <button className="pill" onClick={() => tm.next_incident_day && go(tm.next_incident_day)} disabled={!tm.next_incident_day}>
            Next new incident
          </button>
        </div>
        <label className="mt-3 block text-sm">
          <span className="sr-only">Day</span>
          <input type="range" min={0} max={total} value={dayIdx} className="w-full" onChange={(e) => go(addDays(tm.first_day, Number(e.target.value)))} />
        </label>
      </section>

      <section className="card" aria-labelledby="chart">
        <h2 id="chart" className="section-title">
          Net sales as of {shortDate(tm.day)}
        </h2>
        <p className="muted mb-2 text-sm">
          Line: actual. Shaded band: the forecast range issued before each day. Dashed band: the forecast for the coming days. Tinted spans: incidents.
        </p>
        <Chart tm={tm} />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card" aria-labelledby="inc">
          <h2 id="inc" className="section-title">
            Incidents known on this day ({tm.incidents.length})
          </h2>
          {tm.incidents.length === 0 ? (
            <p className="muted text-sm">Nothing unusual detected yet.</p>
          ) : (
            <ul className="divide-y" style={{ borderColor: "var(--border)" }}>
              {tm.incidents.slice(0, 12).map((i) => (
                <li key={i.incident_id} className="py-2">
                  <button className="w-full text-left" onClick={() => setSel(i.incident_id)} aria-pressed={sel === i.incident_id}>
                    <span className="font-medium">
                      {METRIC[i.anchor_metric] ?? i.anchor_metric} {i.direction === "down" ? "below" : "above"} expected
                    </span>{" "}
                    <span className="muted text-sm">
                      from {shortDate(i.start)}, {i.end ? `ended ${shortDate(i.end)}` : "still open"}, {i.strength}
                      {i.status === "suppressed_data_quality" ? ", suppressed (data quality)" : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card" aria-labelledby="rep" aria-live="polite">
          <h2 id="rep" className="section-title">
            Investigation as of {shortDate(rep?.day ?? tm.day)}
          </h2>
          {STATIC_DEMO && rep && rep.day !== tm.day ? (
            <p className="muted mb-2 text-xs">Static demo: investigations are stored for the detection day and the end day. The live app runs one for any day.</p>
          ) : null}
          {!sel ? (
            <p className="muted text-sm">Select an incident. It is investigated with data up to the end of this day only.</p>
          ) : repErr ? (
            <p className="text-sm">{repErr}</p>
          ) : !rep ? (
            <p className="muted text-sm">Investigating...</p>
          ) : (
            <div className="space-y-3 text-sm">
              <p>
                <span className="pill">Explanation evidence: {rep.evidence.level}</span>
              </p>
              <ul className="muted list-disc pl-5">
                {rep.evidence.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              <ul className="space-y-1">
                {rep.report.summary.map((s, k) => (
                  <li key={k}>{s.text}</li>
                ))}
              </ul>
              {rep.report.next_steps.length ? (
                <>
                  <h3 className="sub-title">Next steps to verify</h3>
                  <ul className="list-disc pl-5">
                    {rep.report.next_steps.map((s) => (
                      <li key={s.id}>{s.text}</li>
                    ))}
                  </ul>
                </>
              ) : null}
            </div>
          )}
        </section>
      </div>

      <section className="card" aria-labelledby="ev">
        <h2 id="ev" className="section-title">
          Recorded changes in the last 30 days
        </h2>
        {tm.events.length === 0 ? (
          <p className="muted text-sm">None.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {tm.events.map((e) => (
              <li key={e.occurred_at + e.description}>
                <span className="muted">{shortDate(e.occurred_at.slice(0, 10))}</span> {e.event_type.replaceAll("_", " ")}: {e.description}
              </li>
            ))}
          </ul>
        )}
      </section>
      <p className="muted text-xs">
        {tm.data_label} data. Each day shows exactly what the monitor knew at the end of that day: forecasts are issued before the days they cover, and
        investigations use no later data. Money in {cur}.
      </p>
    </div>
  );
}
