/** Small server-safe marks: sparkline, ring, stat tile, evidence meter. */

export function Sparkline({ values, label, height = 34 }: { values: (number | null)[]; label: string; height?: number }) {
  const v = values.map((x) => (x === null || !Number.isFinite(x) ? null : x));
  const nums = v.filter((x): x is number => x !== null);
  if (nums.length < 2) return null;
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const W = 120;
  const pts = v
    .map((x, i) => (x === null ? null : `${(i * W) / (v.length - 1)},${height - 3 - ((x - min) / (max - min || 1)) * (height - 6)}`))
    .filter(Boolean);
  const last = pts.at(-1)!.split(",");
  return (
    <svg viewBox={`0 0 ${W} ${height}`} width="100%" height={height} preserveAspectRatio="none" role="img" aria-label={label}>
      <polyline points={pts.join(" ")} fill="none" stroke="var(--accent)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      <circle cx={last[0]} cy={last[1]} r={2.5} fill="var(--accent)" />
    </svg>
  );
}

export function Ring({ value, label, size = 44 }: { value: number; label: string; size?: number }) {
  const r = size / 2 - 4;
  const c = 2 * Math.PI * r;
  const f = Math.max(0, Math.min(1, value));
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={label} className="shrink-0">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--grid)" strokeWidth={4} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--accent)" strokeWidth={4} strokeDasharray={`${f * c} ${c}`}
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

export function StatTile({ label, value, delta, children }: { label: string; value: string; delta?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <li className="card flex flex-col gap-1">
      <p className="tile-label">{label}</p>
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
          <span key={l} className="h-2 flex-1 rounded-sm" style={{ background: i < k ? "var(--accent)" : "var(--grid)" }} />
        ))}
      </div>
      <p className="mt-2 text-sm">
        <strong>{level}</strong> <span className="muted">{PLAIN[level] ?? ""}</span>
      </p>
    </div>
  );
}
