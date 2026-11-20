"use client";

import { useEffect, useId, useRef, useState } from "react";
import { money, shortDate } from "@/lib/format";

export type FcPoint = { date: string; actual: number; expected: number; lo: number; hi: number; state?: string };
export type FcAhead = { date: string; expected: number; lo: number; hi: number };
export type FcSpan = { id: string; start: string; end: string | null; direction: "up" | "down" };

type Props = { past: FcPoint[]; ahead: FcAhead[]; currency: string; spans?: FcSpan[]; height?: number; label: string };

/** Actual line, the forecast range issued before each day, and the forecast for the coming days. */
export default function ForecastChart({ past, ahead, currency, spans = [], height = 240, label }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);
  const [hover, setHover] = useState<number | null>(null);
  const uid = useId().replace(/:/g, "");
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, Math.floor(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const H = height;
  const P = { top: 14, right: 8, bottom: 24, left: 58 };
  const n = past.length + ahead.length;
  const vals = [...past.flatMap((p) => [p.actual, p.hi]), ...ahead.map((p) => p.hi)];
  const lo = 0;
  const hi = Math.max(1, ...vals) * 1.05;
  const x = (i: number) => P.left + (i * (width - P.left - P.right)) / Math.max(1, n - 1);
  const y = (v: number) => P.top + (1 - (v - lo) / (hi - lo)) * (H - P.top - P.bottom);
  const area = (pts: { lo: number; hi: number }[], off: number) =>
    pts.length
      ? `M${pts.map((p, i) => `${x(i + off)},${y(p.hi)}`).join("L")}L${pts
          .map((p, i) => [x(i + off), y(p.lo)] as const)
          .reverse()
          .map(([a, b]) => `${a},${b}`)
          .join("L")}Z`
      : "";
  const line = past.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.actual)}`).join("");
  const under = past.length ? `${line}L${x(past.length - 1)},${y(0)}L${x(0)},${y(0)}Z` : "";
  const edge = (k: "lo" | "hi") => past.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p[k])}`).join("");
  const aheadLine = ahead.length && past.length
    ? `M${x(past.length - 1)},${y(past[past.length - 1].actual)}` + ahead.map((p, i) => `L${x(past.length + i)},${y(p.expected)}`).join("")
    : "";
  const today = past.length - 1;
  const ticks = [0, hi / 2, hi].map((t) => Math.round(t / 100) * 100);
  const rects = spans
    .map((s) => {
      const a = past.findIndex((p) => p.date >= s.start);
      const b = s.end ? past.findIndex((p) => p.date > s.end!) : -1;
      return a < 0 ? null : { ...s, a, b: b < 0 ? today : b - 1 };
    })
    .filter((v): v is FcSpan & { a: number; b: number } => v !== null);
  const hp = hover !== null && hover < past.length ? past[hover] : null;
  const ha = hover !== null && hover >= past.length ? ahead[hover - past.length] : null;
  const cur = hp ?? ha;

  return (
    <div ref={wrap} className="relative w-full min-w-0 overflow-hidden">
      <svg
        width={width}
        height={H}
        role="img"
        aria-label={label}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const i = Math.round(((e.clientX - r.left - P.left) / (width - P.left - P.right)) * (n - 1));
          setHover(i >= 0 && i < n ? i : null);
        }}
      >
        <defs>
          <linearGradient id={`area-${uid}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--area-top)" />
            <stop offset="100%" stopColor="var(--area-top)" stopOpacity={0} />
          </linearGradient>
        </defs>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={P.left} x2={width - P.right} y1={y(t)} y2={y(t)} className="viz-grid" />
            <text x={P.left - 8} y={y(t) + 4} textAnchor="end" className="viz-axis">
              {money(t, currency)}
            </text>
          </g>
        ))}
        {rects.map((s) => (
          <rect key={s.id} x={x(s.a) - 2} width={Math.max(4, x(s.b) - x(s.a) + 4)} y={P.top} height={H - P.top - P.bottom}
            fill={s.direction === "down" ? "var(--warn-soft)" : "var(--accent-soft)"} />
        ))}
        <path d={area(past, 0)} fill="var(--band)" />
        <path d={edge("hi")} fill="none" stroke="var(--accent)" strokeOpacity={0.35} strokeDasharray="1 3" strokeWidth={1} />
        <path d={edge("lo")} fill="none" stroke="var(--accent)" strokeOpacity={0.35} strokeDasharray="1 3" strokeWidth={1} />
        <path d={under} fill={`url(#area-${uid})`} />
        {ahead.length ? <path d={area(ahead, past.length)} fill="var(--band-ahead)" stroke="var(--text-muted)" strokeDasharray="3 3" strokeWidth={1} /> : null}
        {aheadLine ? <path d={aheadLine} fill="none" stroke="var(--text-secondary)" strokeDasharray="4 4" strokeWidth={1.5} /> : null}
        <path d={line} className="viz-line" />
        {past.length ? (
          <>
            <line x1={x(today)} x2={x(today)} y1={P.top} y2={H - P.bottom} stroke="var(--accent)" strokeOpacity={0.4} strokeWidth={1} strokeDasharray="2 3" />
            <circle cx={x(today)} cy={y(past[today].actual)} r={4} fill="var(--accent)" className="pulse-ring" />
            <circle cx={x(today)} cy={y(past[today].actual)} r={4.5} className="viz-dot viz-glow" />
            <text x={x(today) - 6} y={P.top + 10} textAnchor="end" className="viz-axis">
              today
            </text>
          </>
        ) : null}
        <text x={P.left} y={H - 6} className="viz-axis">
          {past[0] ? shortDate(past[0].date) : ""}
        </text>
        <text x={width - P.right} y={H - 6} textAnchor="end" className="viz-axis">
          {shortDate((ahead.at(-1) ?? past.at(-1))?.date ?? "")}
        </text>
        {hover !== null ? <line x1={x(hover)} x2={x(hover)} y1={P.top} y2={H - P.bottom} className="viz-crosshair" strokeDasharray="2 2" /> : null}
        {hp ? <circle cx={x(hover!)} cy={y(hp.actual)} r={4} className="viz-dot viz-glow" /> : null}
      </svg>
      {cur ? (
        <div className="viz-tooltip" style={{ left: Math.max(0, Math.min(x(hover!) + 10, width - 190)), top: 6 }}>
          <strong>{shortDate(cur.date)}</strong>
          {hp ? <div>Actual {money(hp.actual, currency)}</div> : <span>Forecast, not yet happened</span>}
          <span>
            Expected {money(cur.expected, currency)} ({money(cur.lo, currency)} to {money(cur.hi, currency)})
          </span>
          {hp?.state === "out_of_range" ? <span>Outside the expected range</span> : null}
        </div>
      ) : null}
      <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs" style={{ color: "var(--text-secondary)" }} aria-hidden>
        <li className="flex items-center gap-2"><span style={{ width: 14, height: 2, background: "var(--accent)", boxShadow: "0 0 6px var(--accent)" }} />Actual</li>
        <li className="flex items-center gap-2"><span style={{ width: 14, height: 8, background: "var(--band)" }} />Expected range</li>
        {ahead.length ? <li className="flex items-center gap-2"><span style={{ width: 14, borderTop: "2px dashed var(--text-secondary)" }} />Forecast ahead</li> : null}
        {rects.length ? <li className="flex items-center gap-2"><span style={{ width: 10, height: 10, background: "var(--warn-soft)" }} />Issue</li> : null}
      </ul>
    </div>
  );
}
