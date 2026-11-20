import { connection } from "next/server";

export const API_URL = process.env.NEXUSPULSE_API_URL ?? "http://localhost:8000";

// Static demo build (GitHub Pages): pages are rendered once at build time and the Time
// Machine reads precomputed JSON. No server, database or model at view time.
export const STATIC_DEMO = process.env.NEXT_PUBLIC_STATIC_DEMO === "1";
export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

async function dynamicData() {
  if (!STATIC_DEMO) await connection();
}

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

export type FunnelCounts = {
  sessions: number;
  reached_cart: number;
  reached_checkout: number;
  converting_sessions: number;
  orders: number;
  net_revenue: number;
};

export type Overview = {
  workspace: { id: string; name: string; timezone: string; currency: string };
  data_label: "Synthetic" | "Semi-synthetic" | "Real";
  range: { start: string; end: string };
  current_period: PeriodSummary;
  previous_period: PeriodSummary;
  revenue_bridge: { label: string; amount: number; total?: boolean }[];
  funnel: { current: FunnelCounts; previous: FunnelCounts };
  forecast: {
    series: { date: string; actual: number; expected: number; lo: number; hi: number; state: string }[];
    forecast_ahead: { date: string; expected: number; lo: number; hi: number }[];
  };
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

export type NarrationEval = {
  suite: string;
  n_investigations: number;
  adversarial: { catch_rate: number; caught: number; n: number; by_case: Record<string, { targets: string; caught: number; n: number }> };
  modes: Record<string, { available: boolean; note?: string; n?: number; first_pass?: number; passed_after_retry?: number; fallback?: number; seconds_per_report?: number }>;
};

type DetRate = { detected: number; n: number };
type FcQuality = { mape: number; mape_seasonal_naive: number; coverage: number; days: number };
type RealRun = { monitored_days: number; alerts: number; alerts_per_30d: number; forecast: Record<"net_sales" | "orders", FcQuality> };
export type ExternalEval = {
  dataset: string;
  real: { with_calendar: RealRun; no_calendar: RealRun; notes: { orders: number; first_order: string; last_order: string } };
  semi_synthetic: {
    recall: number;
    n: number;
    recall_by_drop: Record<string, DetRate>;
    recall_by_duration: Record<string, DetRate>;
    median_delay_days: number | null;
    new_alerts_not_injected: number;
  };
};

export type Evaluation = {
  external?: ExternalEval;
  narration?: NarrationEval;
  investigation?: { generated_at: string; results: Record<string, { oracle: InvestigationSummary; end_to_end: InvestigationSummary }> };
  generated_at: string;
  results: Record<string, { config: Record<string, unknown> } & Record<string, EvalSummary | Record<string, unknown>>>;
};

export async function getEvaluation(): Promise<Evaluation> {
  await dynamicData();
  const res = await fetch(`${API_URL}/api/evaluation`);
  if (!res.ok) throw new Error(`API responded ${res.status}`);
  return res.json();
}

export async function getOverview(workspace = "demo"): Promise<Overview> {
  await dynamicData(); // always render at request time; data comes from the local API
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
  await dynamicData();
  const res = await fetch(`${API_URL}/api/incidents/${encodeURIComponent(id)}/investigation?workspace=${encodeURIComponent(workspace)}`);
  if (!res.ok) throw new Error(`API responded ${res.status}`);
  return res.json();
}

export type Report = {
  incident_id: string;
  headline: string;
  summary: { text: string; finding_ids: string[]; status: string; source: "template" | "model" }[];
  next_steps: { id: string; text: string; source: "template" | "model" }[];
  narration: { mode: string; model: string | null; fallback: boolean; attempts: number; note?: string | null; prompt_version?: string };
};

export async function getReport(id: string, ai = false, workspace = "demo"): Promise<Report> {
  await dynamicData();
  const res = await fetch(
    `${API_URL}/api/incidents/${encodeURIComponent(id)}/report?workspace=${encodeURIComponent(workspace)}&narration=${ai ? "ai" : "template"}`,
  );
  if (!res.ok) throw new Error(`API responded ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------- Time Machine (fetched from the browser)
export const PUBLIC_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type TmPoint = { date: string; actual: number; expected: number; lo: number; hi: number; state: string };
export type TimeMachineDay = {
  workspace: { id: string; name: string; currency: string; timezone: string };
  data_label: string;
  day: string;
  first_day: string;
  last_day: string;
  next_incident_day: string | null;
  series: TmPoint[];
  forecast_ahead: { date: string; expected: number; lo: number; hi: number }[];
  incidents: (Incident & { static_report_day?: string | null })[];
  events: { occurred_at: string; event_type: string; description: string }[];
};
export type TmReport = { day: string; incident: Incident; evidence: { level: string; reasons: string[] }; report: Report };

export async function getTimeMachineDay(day?: string): Promise<TimeMachineDay> {
  const res = await fetch(
    STATIC_DEMO ? `${BASE_PATH}/demo/tm/${day ?? "start"}.json` : `${PUBLIC_API_URL}/api/timemachine${day ? `?day=${day}` : ""}`,
  );
  if (!res.ok) throw new Error(`API responded ${res.status}`);
  return res.json();
}

export async function getTimeMachineReport(day: string, id: string): Promise<TmReport> {
  const res = await fetch(
    STATIC_DEMO
      ? `${BASE_PATH}/demo/tm/report/${day}_${id}.json`
      : `${PUBLIC_API_URL}/api/timemachine/report?day=${day}&incident_id=${encodeURIComponent(id)}`,
  );
  if (!res.ok) throw new Error((await res.json().catch(() => ({})))?.detail ?? `API responded ${res.status}`);
  return res.json();
}
