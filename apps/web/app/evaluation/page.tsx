import { getEvaluation, type EvalSummary, type ExternalEval, type InvestigationSummary, type NarrationEval, type Rate } from "@/lib/api";
import { pct, shortDate } from "@/lib/format";
import { Ring, StatTile } from "../components/Mini";
import Icon from "../components/Icons";
import Nav from "../components/Nav";

export const metadata = { title: "How accurate is it | NexusPulse AI" };

const days = (d: number | null) => (d === null ? "n/a" : `${d} day${d === 1 ? "" : "s"}`);

const CONFIG_LABEL: Record<string, string> = {
  robust: "Robust fit (default)",
  robust_masked: "Robust fit + issue masking",
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
const fmt = (v: number | null, digits = 2) => (v === null ? "n/a" : v.toFixed(digits));
const Data = ({ kind }: { kind: "Synthetic" | "Semi-synthetic" | "Real" }) => <span className="chip">Data: {kind}</span>;

/** A labelled bar list: one row per bucket, the bar is the share that was right. */
function Bars({ rows, label }: { rows: { name: string; ok: number; n: number; note: string }[]; label: string }) {
  return (
    <ul className="space-y-3" aria-label={label}>
      {rows.map((r) => (
        <li key={r.name}>
          <div className="flex justify-between gap-3 text-sm">
            <span>{r.name}</span>
            <span className="muted num">{r.note}</span>
          </div>
          <div className="meter mt-1" role="img" aria-label={`${r.name}: ${r.note}`}>
            <span style={{ width: `${r.n ? (100 * r.ok) / r.n : 0}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function RingTile({ label, r, note }: { label: string; r: { rate: number | null; text: string }; note: string }) {
  return (
    <StatTile label={label} value={r.rate === null ? "n/a" : pct(r.rate, 0)} delta={<span className="faint text-xs">{note}</span>}>
      <div className="flex justify-end">
        <Ring value={r.rate ?? 0} label={`${label}: ${r.text}`} />
      </div>
    </StatTile>
  );
}

function plainSentence(s: EvalSummary, inv?: InvestigationSummary) {
  const a = `On stores it was never tuned on, it caught ${s.recall === null ? "an unknown share" : pct(s.recall, 0)} of the planted business changes, and ${
    s.precision === null ? "an unknown share" : pct(s.precision, 0)
  } of its alerts were real changes.`;
  const b =
    inv && inv.segment.n
      ? ` When pointed at a change, it named the right segment ${Math.round(100 * (inv.segment.rate ?? 0))}% of the time and the right cause (or correctly none) ${Math.round(100 * (inv.cause_or_none.rate ?? 0))}% of the time.`
      : "";
  return a + b;
}

function InvestigationDetail({ results }: { results: Record<string, { oracle: InvestigationSummary; end_to_end: InvestigationSummary }> }) {
  const slices = SLICES.filter((k) => results[k]);
  const main = results["heldout/main"]?.oracle;
  return (
    <section aria-labelledby="inv" className="card solid">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="inv" className="section-title"><Icon name="target" /> Does a stronger explanation mean a right one?</h2>
        <Data kind="Synthetic" />
      </div>
      {main ? (
        <>
          <p className="muted mb-3 text-sm">Held-out main store. How often the cause was right, grouped by how well the system said it could explain the change.</p>
          <Bars
            label="Cause correct by explanation strength"
            rows={Object.entries(main.cause_correct_by_evidence).map(([lvl, v]) => ({
              name: lvl,
              ok: v.cause_correct,
              n: v.n,
              note: v.n ? `${v.cause_correct}/${v.n} right` : "no cases",
            }))}
          />
          <p className="faint mt-2 text-xs">For None, right means no cause was named and the scenario had no recorded cause.</p>
        </>
      ) : null}
      <details className="more">
        <summary>Every slice, oracle and end to end</summary>
        <p className="faint mt-2 text-xs">
          Oracle runs the investigation on the true scenario window, which measures the investigation alone. End to end runs it on the issue the detector
          actually raised, so it covers only detected scenarios.
        </p>
        <div className="mt-2 overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Slice</th>
                <th scope="col">Mode</th>
                <th scope="col" className="num">What moved</th>
                <th scope="col" className="num">Segment</th>
                <th scope="col" className="num">Cause or none</th>
                <th scope="col" className="num">Red herrings rejected</th>
                <th scope="col" className="num">Numbers re-checked</th>
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
      </details>
    </section>
  );
}

function NarrationDetail({ n }: { n: NarrationEval }) {
  const cases = Object.entries(n.adversarial.by_case);
  return (
    <section aria-labelledby="nar" className="card solid">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="nar" className="section-title"><Icon name="check" /> Can a misleading summary slip through?</h2>
        <Data kind="Synthetic" />
      </div>
      <p className="text-sm">
        The checker caught <strong className="num">{Math.round(100 * n.adversarial.catch_rate)}%</strong> of misleading summaries ({n.adversarial.caught} of{" "}
        {n.adversarial.n}) that had correct numbers.
      </p>
      <p className="muted mt-1 text-sm">
        Summaries come from a template. A local model may only reword the short summary and pick next steps from a fixed list; if its text fails the checks
        twice, the template is used.
      </p>
      <details className="more">
        <summary>Each misleading case</summary>
        <p className="faint mt-2 text-xs">Cases marked semantic contain no forbidden word or wrong number; they show what rule-based checks cannot catch.</p>
        <ul className="mt-2 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
          {cases.map(([k, v]) => (
            <li key={k} className="flex justify-between gap-3">
              <span>
                {k.replaceAll("_", " ")} <span className="faint">({v.targets})</span>
              </span>
              <span className={`num ${v.caught === v.n ? "" : "delta down"}`}>
                {v.caught}/{v.n} caught
              </span>
            </li>
          ))}
        </ul>
      </details>
      <details className="more">
        <summary>Narration modes ({n.n_investigations} held-out investigations)</summary>
        <div className="mt-2 overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Mode</th>
                <th scope="col" className="num">Passed first try</th>
                <th scope="col" className="num">Passed after retry</th>
                <th scope="col" className="num">Used the template</th>
                <th scope="col" className="num">Seconds per report</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(n.modes).map(([m, v]) => (
                <tr key={m}>
                  <td>{m === "template" ? "Template only (no AI)" : m.replace("ollama:", "Local model ")}</td>
                  {v.available ? (
                    <>
                      <td className="num">{v.first_pass}/{v.n}</td>
                      <td className="num">{v.passed_after_retry}/{v.n}</td>
                      <td className="num">{v.fallback}/{v.n}</td>
                      <td className="num">{v.seconds_per_report ?? "-"}</td>
                    </>
                  ) : (
                    <td colSpan={4} className="muted">Not run: {v.note}</td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

/** The real-store results up front: the generated stores are where answers are known, this is where the data is real. */
function RealStrip({ x }: { x: ExternalEval }) {
  const r = x.real.with_calendar;
  const ns = r.forecast.net_sales;
  const p = (v: number) => `${Math.round(100 * v)}%`;
  return (
    <section aria-labelledby="real-head" className="card bracket">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="real-head" className="section-title" style={{ marginBottom: 0 }}>
          <Icon name="orders" /> On a real store
        </h2>
        <a href="#ext" className="link text-sm">
          Details
        </a>
      </div>
      <p className="muted mt-1 text-sm">
        {x.dataset}: a UK online gift retailer, {x.real.notes.orders.toLocaleString()} orders over two years. Orders only, so causes cannot be checked.
      </p>
      <ul className="mt-4 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          icon="chart"
          label="Daily sales forecast error"
          value={p(ns.mape)}
          delta={<span className="faint text-xs">vs {p(ns.mape_seasonal_naive)} for same day last week · Real</span>}
        />
        <StatTile icon="check" label="Expected range held" value={p(ns.coverage)} delta={<span className="faint text-xs">of days, target 95% · Real</span>} />
        <StatTile
          icon="issue"
          label="Alerts"
          value={r.alerts_per_30d.toFixed(2)}
          delta={<span className="faint text-xs">per 30 days, an upper bound on false alerts · Real</span>}
        />
        <StatTile
          icon="search"
          label="Planted order drops caught"
          value={p(x.semi_synthetic.recall)}
          delta={<span className="faint text-xs">{x.semi_synthetic.n} drops of 15-60% · Semi-synthetic</span>}
        />
      </ul>
    </section>
  );
}

function ExternalDetail({ x }: { x: ExternalEval }) {
  const r = x.real.with_calendar;
  const p = (v: number) => `${Math.round(100 * v)}%`;
  const ns = r.forecast.net_sales;
  return (
    <section aria-labelledby="ext" className="card solid">
      <h2 id="ext" className="section-title"><Icon name="orders" /> On a real store: {x.dataset}</h2>
      <p className="muted mb-4 text-sm">
        A real UK online gift retailer, {x.real.notes.orders.toLocaleString()} orders. It has orders only (no visits, funnel, channels or change log), so only
        net sales and orders are monitored and causes cannot be checked.
      </p>
      <div className="grid gap-5 lg:grid-cols-2">
        <div>
          <div className="flex items-baseline justify-between gap-2">
            <p className="sub-title" style={{ marginTop: 0 }}>The data as it is</p>
            <Data kind="Real" />
          </div>
          <p className="text-sm">
            Daily net sales forecasts were off by <strong className="num">{p(ns.mape)}</strong> on average, versus {p(ns.mape_seasonal_naive)} for
            &quot;same day last week&quot;. The expected range held the real value on {p(ns.coverage)} of days.
          </p>
          <p className="mt-2 text-sm">
            <strong className="num">{r.alerts_per_30d.toFixed(2)}</strong> alerts per 30 days with the bank-holiday calendar,{" "}
            {x.real.no_calendar.alerts_per_30d.toFixed(2)} without it.
          </p>
          <p className="faint mt-1 text-xs">There are no labels, so this is an upper bound on false alerts: some may be real events.</p>
          <details className="more">
            <summary>Forecast error by metric</summary>
            <div className="mt-2 overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Metric</th>
                    <th scope="col" className="num">Forecast error (MAPE)</th>
                    <th scope="col" className="num">Same day last week</th>
                    <th scope="col" className="num">Range held</th>
                  </tr>
                </thead>
                <tbody>
                  {(["net_sales", "orders"] as const).map((m) => (
                    <tr key={m}>
                      <td>{m === "net_sales" ? "Net sales" : "Orders"}</td>
                      <td className="num">{p(r.forecast[m].mape)}</td>
                      <td className="num">{p(r.forecast[m].mape_seasonal_naive)}</td>
                      <td className="num">{p(r.forecast[m].coverage)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="faint mt-2 text-xs">
              {r.alerts} alerts in {r.monitored_days} monitored days with the calendar; {x.real.no_calendar.alerts} without it.
            </p>
          </details>
        </div>
        <div>
          <div className="flex items-baseline justify-between gap-2">
            <p className="sub-title" style={{ marginTop: 0 }}>With planted order drops</p>
            <Data kind="Semi-synthetic" />
          </div>
          <p className="mb-3 text-sm">
            Caught <strong className="num">{p(x.semi_synthetic.recall)}</strong> of {x.semi_synthetic.n} planted drops, {x.semi_synthetic.median_delay_days === 0 ? "typically on the day they began" : `typically ${days(x.semi_synthetic.median_delay_days)} after they began`}, with {x.semi_synthetic.new_alerts_not_injected} extra alerts.
          </p>
          <Bars
            label="Planted drops caught, by size"
            rows={Object.entries(x.semi_synthetic.recall_by_drop).map(([k, v]) => ({ name: `${k} of orders removed`, ok: v.detected, n: v.n, note: `${v.detected}/${v.n}` }))}
          />
          <details className="more">
            <summary>By how long the drop lasted</summary>
            <div className="mt-2">
              <Bars
                label="Planted drops caught, by duration"
                rows={Object.entries(x.semi_synthetic.recall_by_duration).map(([k, v]) => ({ name: `Lasting ${k}`, ok: v.detected, n: v.n, note: `${v.detected}/${v.n}` }))}
              />
            </div>
          </details>
        </div>
      </div>
    </section>
  );
}

export default async function EvaluationPage() {
  const ev = await getEvaluation();
  const configs = Object.keys(ev.results);
  const main = ev.results.robust?.["heldout/main"] as EvalSummary | undefined;
  const inv = ev.investigation?.results["heldout/main"]?.oracle;
  const r = (x: Rate | undefined) => ({ rate: x && x.n ? x.rate : null, text: x && x.n ? `${x.correct} of ${x.n}` : "no cases" });

  return (
    <main className="mx-auto w-full max-w-6xl space-y-5 px-4 py-5 sm:px-6">
      <Nav active="evaluation" />
      <header className="grid gap-6 lg:grid-cols-[1fr_1.1fr] lg:items-end">
        <div>
          <p className="eyebrow">
            Test run {shortDate(ev.generated_at.slice(0, 10))} · {main?.n_stores ?? 0} generated stores per slice
          </p>
          <h1 className="page-title mt-2">How accurate is it?</h1>
          <p className="muted mt-1">Scored on stores where we planted the changes and know the answers.</p>
        </div>
        {main ? (
          <div className="card bracket">
            <div className="flex items-baseline justify-between gap-2">
              <p className="label">In plain words</p>
              <Data kind="Synthetic" />
            </div>
            <p className="status-sentence mt-2">{plainSentence(main, inv)}</p>
          </div>
        ) : null}
      </header>

      {main ? (
        <section aria-labelledby="head">
          <h2 id="head" className="sr-only">Headline scores</h2>
          <p className="faint mb-2 text-xs">Held-out stores, default settings. Rings fill to 100%.</p>
          <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-5">
            <RingTile label="Changes caught" r={{ rate: main.recall, text: main.recall === null ? "n/a" : pct(main.recall, 0) }} note="Recall" />
            <RingTile label="Alerts that were real" r={{ rate: main.precision, text: main.precision === null ? "n/a" : pct(main.precision, 0) }} note="Precision" />
            {inv ? (
              <>
                <RingTile label="Right metric moved" r={r(inv.driver)} note={r(inv.driver).text} />
                <RingTile label="Right segment" r={r(inv.segment)} note={r(inv.segment).text} />
                <RingTile label="Right cause, or none" r={r(inv.cause_or_none)} note={r(inv.cause_or_none).text} />
              </>
            ) : null}
          </ul>
          <ul className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile icon="issue" label="False alerts" value={fmt(main.false_alerts_per_30d)} delta={<span className="faint text-xs">per 30 days</span>} />
            <StatTile
              icon="clock"
              label="Time to detect"
              value={days(main.median_delay_days)}
              delta={<span className="faint text-xs">median, from the change starting</span>}
            />
            <StatTile icon="check" label="Tracking problems and decoys" value={main.non_business_handled} delta={<span className="faint text-xs">correctly not called business changes</span>} />
            <StatTile icon="chart" label="Expected range held" value={pct(main.forecast_coverage, 0)} delta={<span className="faint text-xs">target 95%</span>}>
              <div className="flex justify-end">
                <Ring value={main.forecast_coverage} label={`Expected range held on ${pct(main.forecast_coverage, 0)} of days, target 95%`} />
              </div>
            </StatTile>
          </ul>
        </section>
      ) : (
        <p className="muted">No held-out results.</p>
      )}

      {ev.external ? <RealStrip x={ev.external} /> : null}

      {main ? (
        <div className="grid gap-5 lg:grid-cols-2">
          <section aria-labelledby="kind" className="card">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 id="kind" className="section-title"><Icon name="issue" /> What kinds of change it catches</h2>
              <Data kind="Synthetic" />
            </div>
            <Bars
              label="Changes caught by kind"
              rows={Object.entries(main.recall_by_kind).map(([k, v]) => {
                const [a, b] = v.split("/").map(Number);
                return { name: k.replaceAll("_", " "), ok: a, n: b, note: `${v} caught` };
              })}
            />
          </section>
          <section aria-labelledby="effect" className="card">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 id="effect" className="section-title"><Icon name="bridge" /> How big a change it needs</h2>
              <Data kind="Synthetic" />
            </div>
            <Bars
              label="Changes caught by size"
              rows={Object.entries(main.recall_by_effect).map(([k, v]) => ({ name: k, ok: v.detected, n: v.n, note: v.n ? `${v.detected}/${v.n} caught` : "none planted" }))}
            />
            <p className="faint mt-2 text-xs">Size is the approximate change in net sales; the estimate is rough (about ±12%).</p>
          </section>
        </div>
      ) : null}

      {ev.investigation ? <InvestigationDetail results={ev.investigation.results} /> : null}
      {ev.narration ? <NarrationDetail n={ev.narration} /> : null}
      {ev.external ? <ExternalDetail x={ev.external} /> : null}

      <section aria-labelledby="method" className="card solid">
        <h2 id="method" className="section-title"><Icon name="info" /> How it was tested</h2>
        <p className="muted text-sm">
          Each store is generated with planted changes whose answers are kept where the system cannot read them. Settings were tuned on a separate dev set;
          the held-out stores use different segments, smaller changes and one kind of change never seen in tuning, so their numbers are the honest ones.
        </p>
        <details className="more">
          <summary>Settings compared, every slice</summary>
          <p className="faint mt-2 text-xs">Masking leaves open issues out of model training. It is kept only if it measurably helps; it currently does not.</p>
          <div className="mt-2 overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Settings</th>
                  <th scope="col">Slice</th>
                  <th scope="col" className="num">Recall</th>
                  <th scope="col" className="num">Precision</th>
                  <th scope="col" className="num">False alerts / 30 d</th>
                  <th scope="col" className="num">Median delay</th>
                  <th scope="col" className="num">Non-business handled</th>
                  <th scope="col" className="num">Range held</th>
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
        </details>
        {main ? (
          <details className="more">
            <summary>Every held-out scenario, main store ({main.scenarios.length})</summary>
            <div className="mt-2 overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Store seed</th>
                    <th scope="col">Change planted</th>
                    <th scope="col">Dates</th>
                    <th scope="col" className="num">Approx. size</th>
                    <th scope="col">Outcome</th>
                    <th scope="col" className="num">Delay</th>
                  </tr>
                </thead>
                <tbody>
                  {main.scenarios.map((s) => {
                    const ok = ["detected", "suppressed", "passed"].includes(s.outcome);
                    return (
                      <tr key={`${s.seed}-${s.kind}-${s.start}`}>
                        <td>{s.seed}</td>
                        <td>{s.kind.replaceAll("_", " ")}</td>
                        <td>
                          {shortDate(s.start)} to {s.end ? shortDate(s.end) : "permanent"}
                        </td>
                        <td className="num">{s.effect_pct === null ? "n/a" : `${s.effect_pct > 0 ? "+" : ""}${s.effect_pct}%`}</td>
                        <td>
                          <span aria-hidden className={`status-icon ${ok ? "ok" : "fail"}`}>{ok ? "✓" : "✗"}</span> {s.outcome.replaceAll("_", " ")}
                        </td>
                        <td className="num">{s.delay_days === undefined ? "" : `${s.delay_days} d`}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </details>
        ) : null}
      </section>

      <footer className="faint border-t pt-4 text-xs" style={{ borderColor: "var(--border)" }}>
        Known limits: store-wide detection misses many 10-30% changes. Detection,
        investigation and narration scores come from generated stores; the real-store section is labelled Real or Semi-synthetic.
      </footer>
    </main>
  );
}
