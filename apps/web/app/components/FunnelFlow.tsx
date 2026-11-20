"use client";

import { useEffect, useId, useRef, useState } from "react";
import { int, money } from "@/lib/format";

export type FunnelPeriod = {
  sessions: number;
  reached_cart: number;
  reached_checkout: number;
  converting_sessions: number;
  orders: number;
  net_revenue: number;
};

const STAGES = [
  { key: "sessions", label: "Visits" },
  { key: "reached_cart", label: "Added to cart" },
  { key: "reached_checkout", label: "Reached checkout" },
  { key: "converting_sessions", label: "Bought" },
] as const;

/**
 * Visits narrow to purchases, then to revenue. Bar heights are linear in the counts
 * (no rescaling), so the real drop-off is visible. The step with the largest fall in
 * its pass-through rate versus the prior period is highlighted.
 */
export default function FunnelFlow({ cur, prev, currency }: { cur: FunnelPeriod; prev: FunnelPeriod; currency: string }) {
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

  const counts = STAGES.map((s) => cur[s.key]);
  const prevCounts = STAGES.map((s) => prev[s.key]);
  const steps = counts.slice(1).map((c, i) => ({ rate: c / counts[i], prevRate: prevCounts[i + 1] / prevCounts[i] }));
  const worst = steps.reduce((w, s, i) => (s.rate / s.prevRate - 1 < steps[w].rate / steps[w].prevRate - 1 ? i : w), 0);
  // Only call out a step when its pass-through rate fell by more than 5% (relative); smaller moves are noise.
  const worstFell = steps[worst].rate < steps[worst].prevRate * 0.95;
  const revChange = prev.net_revenue ? cur.net_revenue / prev.net_revenue - 1 : null;

  // A table ignores width:1px, so the sr-only box goes on a wrapper div.
  const table = (
    <div className="sr-only">
    <table>
      <caption>Visits to purchases, last 28 days, with the share that continued at each step</caption>
      <tbody>
        {STAGES.map((s, i) => (
          <tr key={s.key}>
            <th scope="row">{s.label}</th>
            <td>{int(counts[i])}</td>
            <td>{i ? `${(steps[i - 1].rate * 100).toFixed(1)}% continued (prior ${(steps[i - 1].prevRate * 100).toFixed(1)}%)` : ""}</td>
          </tr>
        ))}
        <tr>
          <th scope="row">Net revenue</th>
          <td>{money(cur.net_revenue, currency)}</td>
        </tr>
      </tbody>
    </table>
    </div>
  );

  // Narrow screens: a vertical list keeps labels readable.
  if (width < 560) {
    return (
      <div ref={wrap} className="w-full min-w-0 overflow-hidden">
        {table}
        <ol className="space-y-3" aria-hidden>
          {STAGES.map((s, i) => (
            <li key={s.key}>
              <div className="flex justify-between text-sm">
                <span>{s.label}</span>
                <span className="num">{int(counts[i])}</span>
              </div>
              <div className="meter mt-1">
                <span style={{ width: `${Math.max(1, (100 * counts[i]) / counts[0])}%` }} />
              </div>
              {i ? (
                <p className={`mt-1 text-xs ${i - 1 === worst && worstFell ? "delta down" : "faint"}`}>
                  {(steps[i - 1].rate * 100).toFixed(1)}% continued from the step before (prior {(steps[i - 1].prevRate * 100).toFixed(1)}%)
                </p>
              ) : null}
            </li>
          ))}
          <li className="text-sm">
            Net revenue <span className="num font-semibold">{money(cur.net_revenue, currency)}</span>
          </li>
        </ol>
      </div>
    );
  }

  const H = 230;
  const node = 108; // revenue node diameter
  const left = 8;
  const right = width - node - 32;
  const colW = 10;
  const xs = STAGES.map((_, i) => left + (i * (right - left)) / (STAGES.length - 1));
  const maxH = H - 70;
  const mid = 40 + maxH / 2;
  const h = counts.map((c) => Math.max(3, (c / counts[0]) * maxH));
  const band = (i: number) => {
    const x0 = xs[i] + colW, x1 = xs[i + 1];
    const a0 = mid - h[i] / 2, a1 = mid + h[i] / 2;
    const b0 = mid - h[i + 1] / 2, b1 = mid + h[i + 1] / 2;
    const cx = (x0 + x1) / 2;
    return `M${x0},${a0} C${cx},${a0} ${cx},${b0} ${x1},${b0} L${x1},${b1} C${cx},${b1} ${cx},${a1} ${x0},${a1} Z`;
  };
  const lastX = xs.at(-1)! + colW;
  const cx = width - node / 2 - 8;
  const endBand = `M${lastX},${mid - h[3] / 2} C${(lastX + cx) / 2},${mid - h[3] / 2} ${(lastX + cx) / 2},${mid - 10} ${cx - node / 2},${mid - 10} L${cx - node / 2},${mid + 10} C${(lastX + cx) / 2},${mid + 10} ${(lastX + cx) / 2},${mid + h[3] / 2} ${lastX},${mid + h[3] / 2} Z`;

  return (
    <div ref={wrap} className="relative w-full min-w-0 overflow-hidden">
      {table}
      <svg width={width} height={H} aria-hidden onMouseLeave={() => setHover(null)} style={{ overflow: "visible" }}>
        <defs>
          <linearGradient id={`band-${uid}`} x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.3} />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.1} />
          </linearGradient>
          <radialGradient id={`node-${uid}`}>
            <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.18} />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
          </radialGradient>
        </defs>
        {STAGES.slice(0, -1).map((s, i) => {
          const hot = i === worst && worstFell;
          return (
            <path key={s.key} d={band(i)} fill={hot ? "var(--warn-soft)" : `url(#band-${uid})`} stroke={hot ? "var(--warn)" : "var(--accent)"} strokeOpacity={hot ? 1 : 0.45} strokeWidth={1}
              onMouseEnter={() => setHover(i)} />
          );
        })}
        <path d={endBand} fill={`url(#band-${uid})`} stroke="var(--accent)" strokeOpacity={0.45} strokeWidth={1} />
        {STAGES.map((s, i) => (
          <g key={s.key} onMouseEnter={() => setHover(i ? i - 1 : 0)}>
            <rect x={xs[i]} y={mid - h[i] / 2} width={colW} height={h[i]} rx={2} fill="var(--accent)" className="viz-glow" />
            <text x={xs[i]} y={22} className="viz-axis" style={{ textTransform: "uppercase", letterSpacing: "0.06em" }}>
              {s.label}
            </text>
            <text x={xs[i]} y={38} fill="var(--foreground)" fontSize={15} fontWeight={600} className="num">
              {int(counts[i])}
            </text>
            {i ? (
              <text x={(xs[i - 1] + colW + xs[i]) / 2} y={H - 10} textAnchor="middle" fontSize={11}
                fill={i - 1 === worst && worstFell ? "var(--warn-text)" : "var(--text-secondary)"}>
                {(steps[i - 1].rate * 100).toFixed(1)}% continued
              </text>
            ) : null}
          </g>
        ))}
        <circle cx={cx} cy={mid} r={node / 2 + 14} fill={`url(#node-${uid})`} />
        <circle cx={cx} cy={mid} r={node / 2 + 6} fill="none" stroke="var(--accent)" strokeOpacity={0.35} strokeWidth={1} strokeDasharray="2 4" />
        <circle cx={cx} cy={mid} r={node / 2} fill="var(--surface)" stroke="var(--accent)" strokeWidth={1.5} className="viz-glow" />
        <text x={cx} y={mid - 14} textAnchor="middle" className="viz-axis" style={{ textTransform: "uppercase", letterSpacing: "0.06em" }}>
          Net revenue
        </text>
        <text x={cx} y={mid + 6} textAnchor="middle" fill="var(--foreground)" fontSize={17} fontWeight={600} className="num">
          {money(cur.net_revenue, currency)}
        </text>
        {revChange !== null ? (
          <text x={cx} y={mid + 24} textAnchor="middle" fontSize={11} fill={revChange >= 0 ? "var(--accent)" : "var(--warn-text)"}>
            {revChange >= 0 ? "▲" : "▼"} {Math.abs(revChange * 100).toFixed(1)}%
          </text>
        ) : null}
      </svg>
      {hover !== null ? (
        <div className="viz-tooltip" style={{ left: Math.min((xs[hover] + xs[hover + 1]) / 2, width - 220), top: 50 }}>
          <strong>
            {STAGES[hover].label} to {STAGES[hover + 1].label.toLowerCase()}
          </strong>
          <span>
            {(steps[hover].rate * 100).toFixed(1)}% continued, prior 28 days {(steps[hover].prevRate * 100).toFixed(1)}%
          </span>
          <span>
            {int(counts[hover + 1])} of {int(counts[hover])}
          </span>
        </div>
      ) : null}
      <p className="muted mt-1 text-xs">
        {worstFell
          ? `Biggest weakening: ${STAGES[worst].label.toLowerCase()} to ${STAGES[worst + 1].label.toLowerCase()} (${(steps[worst].rate * 100).toFixed(1)}% continued, was ${(steps[worst].prevRate * 100).toFixed(1)}%).`
          : "No step weakened by more than 5% compared with the prior 28 days."}{" "}
        Bar heights are to scale. Orders are counted by visit; one visit can place more than one order.
      </p>
    </div>
  );
}
