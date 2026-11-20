"use client";

import { useState } from "react";
import { money, pct } from "@/lib/format";

export type DonutRow = { key: string; label: string; value: number; change: number | null };

/*
 * One lime ramp, brightest for the largest share. The ramp encodes size order; identity
 * always comes from the table beside it (each row has the same swatch, name and value), and
 * hovering a slice highlights its row and the other way round. Colour is never the only cue.
 */
const RAMP = ["#c9ff7a", "#a8f03c", "#86c92e", "#679f24", "#4c7b1b", "#3a5f16"];
const RAMP_LIGHT = ["#2f5208", "#3f6b0b", "#56861a", "#71a032", "#8fb85a", "#adcf86"];

export default function Donut({ rows, currency, centerLabel }: { rows: DonutRow[]; currency: string; centerLabel: string }) {
  const [hot, setHot] = useState<string | null>(null);
  const sorted = [...rows].sort((a, b) => b.value - a.value);
  const total = sorted.reduce((a, r) => a + Math.max(0, r.value), 0) || 1;
  const S = 168, R = 70, W = 18;
  const C = 2 * Math.PI * R;
  const gap = 2;
  let acc = 0;

  return (
    <div className="grid items-center gap-5 sm:grid-cols-[auto_1fr]">
      <div className="relative mx-auto" style={{ width: S, height: S }}>
        <svg width={S} height={S} viewBox={`0 0 ${S} ${S}`} aria-hidden style={{ overflow: "visible" }}>
          <circle cx={S / 2} cy={S / 2} r={R + W / 2 + 6} fill="none" stroke="var(--accent)" strokeOpacity={0.25} strokeDasharray="2 4" />
          {sorted.map((r, i) => {
            const len = (Math.max(0, r.value) / total) * C;
            const seg = (
              <circle
                key={r.key}
                cx={S / 2}
                cy={S / 2}
                r={R}
                fill="none"
                strokeWidth={hot === r.key ? W + 4 : W}
                strokeDasharray={`${Math.max(0, len - gap)} ${C}`}
                strokeDashoffset={-acc}
                transform={`rotate(-90 ${S / 2} ${S / 2})`}
                className={`donut-seg seg-${i}`}
                style={{ transition: "stroke-width .15s", cursor: "pointer" }}
                onMouseEnter={() => setHot(r.key)}
                onMouseLeave={() => setHot(null)}
              />
            );
            acc += len;
            return seg;
          })}
        </svg>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className="faint text-xs">{centerLabel}</span>
          <span className="display text-xl font-semibold" style={{ color: "var(--accent)" }}>
            {money(total, currency)}
          </span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="data-table">
          <caption className="sr-only">{centerLabel} by channel, last 28 days, with the change versus the 28 days before</caption>
          <thead>
            <tr>
              <th scope="col">Channel</th>
              <th scope="col" className="num">Sales</th>
              <th scope="col" className="num">Share</th>
              <th scope="col" className="num">Change</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, i) => (
              <tr key={r.key} className={hot === r.key ? "hot" : undefined} onMouseEnter={() => setHot(r.key)} onMouseLeave={() => setHot(null)}>
                <th scope="row" className="font-normal">
                  <span aria-hidden className={`mr-2 inline-block h-2.5 w-2.5 rounded-sm align-middle donut-swatch seg-${i}`} />
                  {r.label}
                </th>
                <td className="num">{money(r.value, currency)}</td>
                <td className="num">{pct(r.value / total, 1)}</td>
                <td className={`num ${r.change === null ? "faint" : r.change < 0 ? "delta down" : "delta up"}`}>
                  {r.change === null ? "n/a" : `${r.change >= 0 ? "+" : ""}${(r.change * 100).toFixed(1)}%`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <style>
        {RAMP.map((c, i) => `.seg-${i}.donut-seg{stroke:${c}}.seg-${i}.donut-swatch{background:${c}}`).join("") +
          RAMP_LIGHT.map(
            (c, i) => `:root[data-theme="light"] .seg-${i}.donut-seg{stroke:${c}}:root[data-theme="light"] .seg-${i}.donut-swatch{background:${c}}`,
          ).join("")}
      </style>
    </div>
  );
}
