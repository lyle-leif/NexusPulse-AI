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

export type Rate = { correct: number; n: number; rate: number | null };
export type InvestigationSummary = {
  driver: Rate;
  segment: Rate;
  cause_or_none: Rate;
  red_herring_rejected: Rate;
  validation_passed: Rate;
  cause_correct_by_evidence: Record<string, { n: number; cause_correct: number }>;
  by_kind: Record<string, { n: number; driver: number; segment: number; cause: number }>;
};

export type Evaluation = {
  investigation?: { generated_at: string; results: Record<string, { oracle: InvestigationSummary; end_to_end: InvestigationSummary }> };
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

export type Finding = {
  finding_id: string;
  type: string;
  status: "observed" | "attributed" | "associated" | "hypothesis";
  text: string;
  values: Record<string, unknown>;
};

export type SegmentRow = {
  dimension: string;
  segment: string;
  baseline_per_day: number;
  current_per_day: number;
  change: number;
  traffic_part?: number;
  rate_part?: number;
  noise_score: number;
  volume_ok: boolean;
};

export type Investigation = {
  incident: Incident;
  workspace: { id: string; name: string; timezone: string; currency: string };
  data_label: string;
  window: { start: string; end: string; days: number };
  decomposition: {
    baseline: { days: number; rule: string };
    bridge: { line: string; label: string; baseline: number; current: number; change: number; total?: boolean }[];
    core: { factor: string; baseline: number; current: number; relative_change: number | null; contribution: number }[];
    core_total: { baseline: number; current: number; change: number };
  };
  drilldown: {
    dimensions: Record<string, { rows: SegmentRow[]; total_change: number; concentration: { segment: string; share: number; noise_score: number } | null }>;
    primary: { dimension: string; segment: string; share: number; noise_score: number } | null;
  };
  events: { event_id: string; occurred_at_local: string; type: string; description: string; scope: Record<string, string>; match: string; hours_before_change: number }[];
  ruled_out: { alternative: string; ruled_out: boolean; reason: string }[];
  findings: Finding[];
  explanation_evidence: { level: "Strong" | "Moderate" | "Weak" | "None"; reasons: string[] };
  validation: { check: string; passed: boolean; detail: string }[];
};

export async function getInvestigation(id: string, workspace = "demo"): Promise<Investigation> {
  await connection();
  const res = await fetch(`${API_URL}/api/incidents/${encodeURIComponent(id)}/investigation?workspace=${encodeURIComponent(workspace)}`);
  if (!res.ok) throw new Error(`API responded ${res.status}`);
  return res.json();
}
