export const money = (v: number, currency = "USD", digits = 0) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: digits, minimumFractionDigits: digits }).format(v);

export const int = (v: number) => new Intl.NumberFormat("en-US").format(Math.round(v));

export const pct = (v: number, digits = 2) => `${(v * 100).toFixed(digits)}%`;

export const change = (cur: number, prev: number) => (prev === 0 ? null : (cur - prev) / prev);

export const shortDate = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
