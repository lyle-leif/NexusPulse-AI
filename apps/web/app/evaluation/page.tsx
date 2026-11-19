import { getEvaluation, type EvalSummary, type InvestigationSummary, type Rate } from "@/lib/api";
import { pct, shortDate } from "@/lib/format";
import Nav from "../components/Nav";

const CONFIG_LABEL: Record<string, string> = {
  robust: "Robust fit (default)",
  robust_masked: "Robust fit + incident masking",
  plain: "Plain fit",
};
const SLICES = ["heldout/main", "heldout/low_volume", "dev/main", "dev/low_volume"];
const SLICE_LABEL: Record<string, string> = {
  "heldout/main": "Held-out · main store",
  "heldout/low_volume": "Held-out · low-volume store",
  "dev/main": "Dev · main store",
  "dev/low_volume": "Dev · low-volume store",
};

const rate = (r: Rate) => (r.n ? `${Math.round(100 * (r.rate ?? 0))}% (${r.correct}/${r.n})` : "n/a");

function InvestigationScorecard({ results }: { results: Record<string, { oracle: InvestigationSummary; end_to_end: InvestigationSummary }> }) {
  const slices = SLICES.filter((k) => results[k]);
  const main = results["heldout/main"]?.oracle;
  return (
    <section aria-labelledby="inv" className="card">
      <h2 id="inv" className="section-title">Investigation accuracy</h2>
      <p className="muted mb-3">
        Oracle: investigation run on the true scenario window, which measures the investigation alone. End to end: run on the incident the detector actually
        raised, so it only covers detected scenarios. Cause is correct when the recorded change that caused it is named, or when none is named and there was none.
      </p>
      <div className="overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Slice</th>
              <th scope="col">Mode</th>
              <th scope="col" className="num">Driver</th>
              <th scope="col" className="num">Segment</th>
              <th scope="col" className="num">Cause or none</th>
              <th scope="col" className="num">Red herrings rejected</th>
              <th scope="col" className="num">Validation passed</th>
            </tr>
          </thead>
          <tbody>
            {slices.flatMap((k) =>
              (["oracle", "end_to_end"] as const).map((m) => {
                const r = results[k][m];
                return (
                  <tr key={`${k}-${m}`}>
                    <td>{SLICE_LABEL[k]}</td>
                    <td>{m === "oracle" ? "Oracle" : "End to end"}</td>
                    <td className="num">{rate(r.driver)}</td>
                    <td className="num">{rate(r.segment)}</td>
                    <td className="num">{rate(r.cause_or_none)}</td>
                    <td className="num">{m === "oracle" ? rate(r.red_herring_rejected) : "n/a"}</td>
                    <td className="num">{rate(r.validation_passed)}</td>
                  </tr>
                );
              }),
            )}
          </tbody>
        </table>
      </div>
      {main ? (
        <>
          <h3 className="sub-title">Is stronger evidence right more often? (held-out, main store, oracle)</h3>
          <ul className="space-y-3">
            {Object.entries(main.cause_correct_by_evidence).map(([lvl, v]) => (
              <li key={lvl}>
                <div className="flex justify-between text-sm">
                  <span>{lvl}</span>
                  <span className="muted">{v.n ? `${v.cause_correct}/${v.n} cause correct` : "no cases"}</span>
                </div>
                <div className="meter" role="img" aria-label={`${lvl}: ${v.cause_correct} of ${v.n} correct`}>
                  <span style={{ width: `${v.n ? (100 * v.cause_correct) / v.n : 0}%` }} />
                </div>
              </li>
            ))}
          </ul>
          <p className="muted mt-2 text-xs">For None, correct means no cause was named and the scenario had no recorded cause.</p>
        </>
      ) : null}
    </section>
  );
}

const fmt = (v: number | null, digits = 2) => (v === null ? "n/a" : v.toFixed(digits));

function Headline({ s }: { s: EvalSummary }) {
  const tiles = [
    { label: "Recall", value: s.recall === null ? "n/a" : pct(s.recall, 0), note: "Planted business changes detected" },
    { label: "Precision", value: s.precision === null ? "n/a" : pct(s.precision, 0), note: "Alerts that matched a real change" },
    { label: "False alerts per 30 days", value: fmt(s.false_alerts_per_30d), note: "Alerts matching no planted change" },
    { label: "Median detection delay", value: s.median_delay_days === null ? "n/a" : `${s.median_delay_days} days`, note: "From change start to incident start" },
    { label: "Data-quality and red herrings", value: s.non_business_handled, note: "Correctly not alerted as business changes" },
    { label: "Forecast band coverage", value: pct(s.forecast_coverage, 0), note: "Target 95%; below means bands are too narrow" },
  ];
  return (
    <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {tiles.map((t) => (
        <li key={t.label} className="card">
          <p className="tile-label">{t.label}</p>
          <p className="stat">{t.value}</p>
          <p className="muted text-xs">{t.note}</p>
        </li>
      ))}
    </ul>
  );
}

export default async function EvaluationPage() {
  const ev = await getEvaluation();
  const configs = Object.keys(ev.results);
  const main = ev.results.robust?.["heldout/main"] as EvalSummary | undefined;

  return (
    <main className="mx-auto w-full max-w-6xl space-y-8 px-4 py-8 sm:px-6">
      <Nav active="evaluation" />
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">NexusPulse AI</p>
          <h1 className="text-2xl font-semibold tracking-tight">Detection evaluation</h1>
          <p className="muted">
            Held-out scorecard, default configuration · {main?.n_stores ?? 0} synthetic stores per slice · run {shortDate(ev.generated_at.slice(0, 10))}
          </p>
        </div>
        <span className="pill">Data: Synthetic</span>
      </header>

      <p className="muted max-w-3xl text-sm">
        Each store is generated with planted scenarios whose labels live in an isolated store the pipeline cannot read. Thresholds were tuned on the dev
        suite only; the held-out suite uses different segments, smaller effects and one scenario kind never seen in tuning, so its numbers are the honest
        ones.
      </p>

      {main ? <Headline s={main} /> : <p className="muted">No held-out results.</p>}

      <section aria-labelledby="compare" className="card">
        <h2 id="compare" className="section-title">Configurations compared</h2>
        <p className="muted mb-3">Masking excludes open incidents from model training. It is kept only if it measurably helps; it currently does not.</p>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Configuration</th>
                <th scope="col">Slice</th>
                <th scope="col" className="num">Recall</th>
                <th scope="col" className="num">Precision</th>
                <th scope="col" className="num">False alerts / 30 d</th>
                <th scope="col" className="num">Median delay</th>
                <th scope="col" className="num">Non-business handled</th>
                <th scope="col" className="num">Band coverage</th>
              </tr>
            </thead>
            <tbody>
              {configs.flatMap((c) =>
                SLICES.filter((k) => ev.results[c][k]).map((k) => {
                  const s = ev.results[c][k] as EvalSummary;
                  return (
                    <tr key={`${c}-${k}`}>
                      <td>{CONFIG_LABEL[c] ?? c}</td>
                      <td>{SLICE_LABEL[k]}</td>
                      <td className="num">{fmt(s.recall)}</td>
                      <td className="num">{fmt(s.precision)}</td>
                      <td className="num">{fmt(s.false_alerts_per_30d)}</td>
                      <td className="num">{s.median_delay_days === null ? "n/a" : `${s.median_delay_days} d`}</td>
                      <td className="num">{s.non_business_handled}</td>
                      <td className="num">{pct(s.forecast_coverage, 0)}</td>
                    </tr>
                  );
                }),
              )}
            </tbody>
          </table>
        </div>
      </section>

      {main ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <section aria-labelledby="kind" className="card">
            <h2 id="kind" className="section-title">Recall by scenario kind</h2>
            <p className="muted mb-3">Held-out, main store.</p>
            <ul className="space-y-3">
              {Object.entries(main.recall_by_kind).map(([k, v]) => {
                const [a, b] = v.split("/").map(Number);
                return (
                  <li key={k}>
                    <div className="flex justify-between text-sm">
                      <span>{k.replaceAll("_", " ")}</span>
                      <span className="muted">{v} detected</span>
                    </div>
                    <div className="meter" role="img" aria-label={`${k}: ${v} detected`}>
                      <span style={{ width: `${b ? (100 * a) / b : 0}%` }} />
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
          <section aria-labelledby="effect" className="card">
            <h2 id="effect" className="section-title">Recall by effect size</h2>
            <p className="muted mb-3">
              Approximate change in net sales during the scenario versus the same store without it. The estimate is noisy (about ±12%), so treat bins as
              rough.
            </p>
            <ul className="space-y-3">
              {Object.entries(main.recall_by_effect).map(([k, v]) => (
                <li key={k}>
                  <div className="flex justify-between text-sm">
                    <span>{k}</span>
                    <span className="muted">{v.n ? `${v.detected}/${v.n} detected` : "no scenarios"}</span>
                  </div>
                  <div className="meter" role="img" aria-label={`${k}: ${v.detected} of ${v.n} detected`}>
                    <span style={{ width: `${v.n ? (100 * v.detected) / v.n : 0}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </div>
      ) : null}

      {main ? (
        <section aria-labelledby="scen" className="card">
          <h2 id="scen" className="section-title">Every held-out scenario (main store)</h2>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Store seed</th>
                  <th scope="col">Scenario</th>
                  <th scope="col">Dates</th>
                  <th scope="col" className="num">Approx. effect</th>
                  <th scope="col">Outcome</th>
                  <th scope="col" className="num">Delay</th>
                </tr>
              </thead>
              <tbody>
                {main.scenarios.map((s) => (
                  <tr key={`${s.seed}-${s.kind}-${s.start}`}>
                    <td>{s.seed}</td>
                    <td>{s.kind.replaceAll("_", " ")}</td>
                    <td>
                      {shortDate(s.start)} to {s.end ? shortDate(s.end) : "permanent"}
                    </td>
                    <td className="num">{s.effect_pct === null ? "n/a" : `${s.effect_pct > 0 ? "+" : ""}${s.effect_pct}%`}</td>
                    <td>
                      <span aria-hidden className={`status-icon ${["detected", "suppressed", "passed"].includes(s.outcome) ? "ok" : "fail"}`}>
                        {["detected", "suppressed", "passed"].includes(s.outcome) ? "✓" : "✗"}
                      </span>{" "}
                      {s.outcome.replaceAll("_", " ")}
                    </td>
                    <td className="num">{s.delay_days === undefined ? "" : `${s.delay_days} d`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {ev.investigation ? <InvestigationScorecard results={ev.investigation.results} /> : null}

      <footer className="muted border-t pt-4 text-xs" style={{ borderColor: "var(--border)" }}>
        Known limits: forecast bands are too narrow (coverage below 95%); store-level detection misses many 10-30% changes, which segment-level analysis
        in the next step targets. Results are from synthetic data only.
      </footer>
    </main>
  );
}
