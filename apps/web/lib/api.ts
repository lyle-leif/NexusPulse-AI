import { connection } from "next/server";

export const API_URL = process.env.NEXUSPULSE_API_URL ?? "http://localhost:8000";

export type PeriodSummary = {
  start: string;
  end: string;
  net_revenue: number;
  sessions: number;
  orders: number;
  session_conversion_rate: number;
  attributed_aov: number;
  unattributed_share: number;
};

export type SeriesPoint = {
  date: string;
  net_revenue: number;
  sessions: number;
  orders: number;
  session_conversion_rate: number | null;
  unattributed_share: number | null;
};

export type Overview = {
  workspace: { id: string; name: string; timezone: string; currency: string };
  data_label: "Synthetic" | "Semi-synthetic" | "Real";
  range: { start: string; end: string };
  current_period: PeriodSummary;
  previous_period: PeriodSummary;
  revenue_bridge: { label: string; amount: number; total?: boolean }[];
  series: SeriesPoint[];
  reconciliation: { name: string; passed: boolean; detail: string }[];
  data_quality_incidents: { type: string; threshold: number; start: string; end: string; open?: boolean }[];
  notes: string[];
};

export async function getOverview(workspace = "demo"): Promise<Overview> {
  await connection(); // always render at request time; data comes from the local API
  const res = await fetch(`${API_URL}/api/overview?workspace=${encodeURIComponent(workspace)}`);
  if (!res.ok) throw new Error(`API responded ${res.status}`);
  return res.json();
}
