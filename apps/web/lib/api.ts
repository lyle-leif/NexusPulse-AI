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
  incidents: Incident[];
  monitor_config: Record<string, number | string | boolean>;
  notes: string[];
};

export type Incident = {
  incident_id: string;
  start: string;
  end: string | null;
  status: "open" | "resolved" | "level_shift" | "suppressed_data_quality";
  anchor_metric: string;
  direction: "up" | "down";
  strength: "Strong" | "Moderate" | "Weak";
  impact: number | null;
  members: { metric: string; direction: string; start: string; end: string | null; status: string; strength: string; max_abs_z: number; max_window_z: number; trigger: string }[];
};

export type ScenarioScore = {
  kind: string;
  start: string;
  end: string | null;
  effect_pct: number | null;
  outcome: "detected" | "missed" | "suppressed" | "passed" | "alerted_wrongly";
  delay_days?: number;
  strength?: string;
  suite: string;
  profile: string;
  seed: number;
};

export type EvalSummary = {
  recall: number | null;
  precision: number | null;
  false_alerts_per_30d: number | null;
  median_delay_days: number | null;
  non_business_handled: string;
  recall_by_kind: Record<string, string>;
  recall_by_effect: Record<string, { detected: number; n: number }>;
  forecast_coverage: number;
  forecast_mape: number;
  n_stores: number;
  scenarios: ScenarioScore[];
};

export type Evaluation = {
  generated_at: string;
  results: Record<string, { config: Record<string, unknown> } & Record<string, EvalSummary | Record<string, unknown>>>;
};

export async function getEvaluation(): Promise<Evaluation> {
  await connection();
  const res = await fetch(`${API_URL}/api/evaluation`);
  if (!res.ok) throw new Error(`API responded ${res.status}`);
  return res.json();
}

export async function getOverview(workspace = "demo"): Promise<Overview> {
  await connection(); // always render at request time; data comes from the local API
  const res = await fetch(`${API_URL}/api/overview?workspace=${encodeURIComponent(workspace)}`);
  if (!res.ok) throw new Error(`API responded ${res.status}`);
  return res.json();
}
