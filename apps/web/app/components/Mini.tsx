/** Small server-safe marks: sparkline, ring, stat tile, evidence meter. */
import Icon, { type IconName } from "./Icons";

/** Stable id for SVG gradients from a label (server-safe, no hooks). */
const sid = (s: string) => {
  let h = 0;
  for (const ch of s) h = (h * 31 + ch.charCodeAt(0)) | 0;
  return `g${(h >>> 0).toString(36)}`;
};

/** Glowing line over a gradient area; the last point is marked. */
export function Sparkline({ values, label, height = 34 }: { values: (number | null)[]; label: string; height?: number }) {
  const v = values.map((x) => (x === null || !Number.isFinite(x) ? null : x));
  const nums = v.filter((x): x is number => x !== null);
  if (nums.length < 2) return null;
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const W = 120;
  const xy = v
    .map((x, i) => (x === null ? null : ([(i * W) / (v.length - 1), height - 3 - ((x - min) / (max - min || 1)) * (height - 6)] as const)))
    .filter((p): p is readonly [number, number] => p !== null);
  const pts = xy.map(([a, b]) => `${a},${b}`).join(" ");
  const id = sid(label);
  const [lx, ly] = xy.at(-1)!;
  return (
    <svg viewBox={`0 0 ${W} ${height}`} width="100%" height={height} preserveAspectRatio="none" role="img" aria-label={label} style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--area-top)" />
          <stop offset="100%" stopColor="var(--area-top)" stopOpacity={0} />
        </linearGradient>
      </defs>
      <polygon points={`${xy[0][0]},${height} ${pts} ${lx},${height}`} fill={`url(#${id})`} />
      <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth={1.6} vectorEffect="non-scaling-stroke" className="viz-glow" />
      <circle cx={lx} cy={ly} r={2.5} fill="var(--accent)" className="viz-glow" />
    </svg>
  );
}

/** How a share reads: good (accent), middling (neutral) or weak (amber). Used to colour bars by meaning. */
export type Tone = "good" | "mid" | "weak";
export const tone = (share: number): Tone => (share >= 0.8 ? "good" : share >= 0.6 ? "mid" : "weak");
const TONE_COLOR: Record<Tone, string> = { good: "var(--accent-fill)", mid: "var(--neutral-fill)", weak: "var(--warn)" };

/** Horizontal share bar coloured by tone. */
export function Meter({ value, label }: { value: number; label: string }) {
  const f = Math.max(0, Math.min(1, value));
  return (
    <div className={`meter ${tone(f)}`} role="img" aria-label={label}>
      <span style={{ width: `${100 * f}%` }} />
    </div>
  );
}

/** Progress ring on a plain track; `toned` colours it by result (only for scores where higher is better). */
export function Ring({ value, label, size = 44, toned = false }: { value: number; label: string; size?: number; toned?: boolean }) {
  const r = size / 2 - 4;
  const c = 2 * Math.PI * r;
  const f = Math.max(0, Math.min(1, value));
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={label} className="shrink-0">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--track)" strokeWidth={4} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={toned ? TONE_COLOR[tone(f)] : "var(--accent-fill)"} strokeWidth={4} strokeLinecap="round" strokeDasharray={`${f * c} ${c}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`} />
    </svg>
  );
}

export function Delta({ text, dir }: { text: string; dir: "up" | "down" | "flat" }) {
  return (
    <span className={`delta ${dir === "flat" ? "" : dir}`}>
      <span aria-hidden>{dir === "up" ? "▲ " : dir === "down" ? "▼ " : ""}</span>
      {text}
    </span>
  );
}

export function StatTile({ label, value, delta, children, icon }: { label: string; value: string; delta?: React.ReactNode; children?: React.ReactNode; icon?: IconName }) {
  return (
    <li className="card flex flex-col justify-between gap-1">
      <p className="tile-label">
        {icon ? <Icon name={icon} /> : null}
        {label}
      </p>
      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="tile-value">{value}</p>
          {delta}
        </div>
        {children ? <div className="w-24 shrink-0">{children}</div> : null}
      </div>
    </li>
  );
}

const LEVELS = ["None", "Weak", "Moderate", "Strong"] as const;
const PLAIN: Record<string, string> = {
  None: "Nothing stands out",
  Weak: "Partly located, no matching change",
  Moderate: "Located, with some supporting evidence",
  Strong: "Located, with a matching recorded change",
};

/** Four-step meter for "how well we can explain it". A rule, not a probability. */
export function EvidenceMeter({ level }: { level: string }) {
  const k = Math.max(0, LEVELS.indexOf(level as (typeof LEVELS)[number]));
  return (
    <div>
      <div className="flex gap-1" role="img" aria-label={`Explanation evidence: ${level} (${k} of 3)`}>
        {LEVELS.slice(1).map((l, i) => (
          <span key={l} className="h-2 flex-1 rounded-sm" style={{ background: i < k ? "linear-gradient(90deg, var(--accent-fill), var(--accent-fill-top))" : "var(--grid)", boxShadow: i < k ? "inset -2px 0 0 var(--accent)" : "none" }} />
        ))}
      </div>
      <p className="mt-2 text-sm">
        <strong>{level}</strong> <span className="muted">{PLAIN[level] ?? ""}</span>
      </p>
    </div>
  );
}
