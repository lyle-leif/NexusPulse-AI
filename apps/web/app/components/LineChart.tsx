"use client";

import { useEffect, useMemo, useRef, useState } from "react";

export type Point = { date: string; value: number | null };
export type Band = { start: string; end: string; label: string };

type Props = {
  title: string;
  data: Point[];
  format: (v: number) => string;
  threshold?: { value: number; label: string };
  bands?: Band[];
  height?: number;
};

const PAD = { top: 12, right: 16, bottom: 26, left: 64 };

function niceTicks(min: number, max: number, count = 4) {
  if (min === max) return [min];
  const raw = (max - min) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const ticks: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-12; v += step) ticks.push(Number(v.toPrecision(12)));
  return ticks;
}

export default function LineChart({ title, data, format, threshold, bands = [], height = 200 }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, Math.floor(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const geo = useMemo(() => {
    const vals = data.map((d) => d.value).filter((v): v is number => v !== null);
    let lo = Math.min(0, ...vals);
    let hi = Math.max(...vals, threshold?.value ?? -Infinity);
    if (!isFinite(hi)) hi = 1;
    hi = hi + (hi - lo) * 0.08;
    const ticks = niceTicks(lo, hi);
    lo = Math.min(lo, ticks[0]);
    hi = Math.max(hi, ticks[ticks.length - 1]);
    const iw = width - PAD.left - PAD.right;
    const ih = height - PAD.top - PAD.bottom;
    const x = (i: number) => PAD.left + (data.length <= 1 ? 0 : (i / (data.length - 1)) * iw);
    const y = (v: number) => PAD.top + ih - ((v - lo) / (hi - lo || 1)) * ih;
    let path = "";
    let pen = false;
    data.forEach((d, i) => {
      if (d.value === null) {
        pen = false;
        return;
      }
      path += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(d.value).toFixed(1)}`;
      pen = true;
    });
    const idx = new Map(data.map((d, i) => [d.date, i]));
    const bandRects = bands
      .map((b) => {
        const s = idx.get(b.start) ?? (b.start < data[0]?.date ? 0 : undefined);
        const e = idx.get(b.end) ?? (b.end > data[data.length - 1]?.date ? data.length - 1 : undefined);
        if (s === undefined || e === undefined || b.end < data[0]?.date || b.start > data[data.length - 1]?.date) return null;
        return { x: x(s), w: Math.max(2, x(e) - x(s)), label: b.label };
      })
      .filter((b): b is { x: number; w: number; label: string } => b !== null);
    const xTicks = [0, Math.floor((data.length - 1) / 2), data.length - 1].filter((v, i, a) => a.indexOf(v) === i && v >= 0);
    return { ticks, x, y, path, iw, ih, bandRects, xTicks };
  }, [data, width, height, threshold, bands]);

  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const r = (e.currentTarget as SVGRectElement).getBoundingClientRect();
    const rel = (e.clientX - r.left) / r.width;
    setHover(Math.max(0, Math.min(data.length - 1, Math.round(rel * (data.length - 1)))));
  };

  const h = hover !== null ? data[hover] : null;

  return (
    <figure className="viz" aria-label={title}>
      <figcaption className="viz-title">{title}</figcaption>
      <div ref={wrap} className="relative w-full min-w-0 overflow-hidden">
        <svg width={width} height={height} role="img" aria-label={`${title} line chart`}>
          {geo.bandRects.map((b, i) => (
            <g key={i}>
              <rect x={b.x} y={PAD.top} width={b.w} height={geo.ih} className="viz-band" />
              <text x={b.x + 4} y={PAD.top + 12} className="viz-band-label">
                {b.label}
              </text>
            </g>
          ))}
          {geo.ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={width - PAD.right} y1={geo.y(t)} y2={geo.y(t)} className="viz-grid" />
              <text x={PAD.left - 8} y={geo.y(t)} dy="0.32em" textAnchor="end" className="viz-axis">
                {format(t)}
              </text>
            </g>
          ))}
          {geo.xTicks.map((i) => (
            <text key={i} x={geo.x(i)} y={height - 8} textAnchor={i === 0 ? "start" : i === data.length - 1 ? "end" : "middle"} className="viz-axis">
              {data[i]?.date}
            </text>
          ))}
          {threshold && (
            <g>
              <line x1={PAD.left} x2={width - PAD.right} y1={geo.y(threshold.value)} y2={geo.y(threshold.value)} className="viz-threshold" />
              <text x={width - PAD.right} y={geo.y(threshold.value) - 5} textAnchor="end" className="viz-axis">
                {threshold.label}
              </text>
            </g>
          )}
          <path d={geo.path} className="viz-line" />
          {h && h.value !== null && hover !== null && (
            <g>
              <line x1={geo.x(hover)} x2={geo.x(hover)} y1={PAD.top} y2={PAD.top + geo.ih} className="viz-crosshair" />
              <circle cx={geo.x(hover)} cy={geo.y(h.value)} r={4} className="viz-dot" />
            </g>
          )}
          <rect
            x={PAD.left}
            y={PAD.top}
            width={geo.iw}
            height={geo.ih}
            fill="transparent"
            onPointerMove={onMove}
            onPointerLeave={() => setHover(null)}
          />
        </svg>
        {h && hover !== null && (
          <div
            className="viz-tooltip"
            style={{ left: Math.min(Math.max(geo.x(hover) + 10, 0), width - 170), top: PAD.top }}
            role="status"
          >
            <strong>{h.value === null ? "No data" : format(h.value)}</strong>
            <span>{h.date}</span>
          </div>
        )}
      </div>
    </figure>
  );
}
