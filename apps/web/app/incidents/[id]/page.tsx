import Link from "next/link";
import { STATIC_DEMO, getInvestigation, getOverview, getReport, type Investigation, type Report } from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import Nav from "../../components/Nav";

const FACTOR: Record<string, string> = {
  sessions: "Sessions",
  cart_rate: "Add-to-cart rate",
  checkout_rate: "Cart-to-checkout rate",
  purchase_rate: "Checkout-to-purchase rate",
  orders_per_converting_session: "Orders per converting session",
  attributed_aov: "Attributed average order value",
};
const STATUS_LABEL: Record<string, string> = {
  observed: "Observed",
  attributed: "Measured breakdown",
  associated: "Associated (time and scope)",
  hypothesis: "Hypotheses (not confirmed)",
};
const EVIDENCE_RULES =
  "Strong: 80% or more of the change in one segment, a recorded change with the same scope within 24 hours of the start, and data quality and calendar ruled out. Moderate: 50% or more in one segment with a scoped recorded change, or 80% or more without one. Weak: 50% or more in one segment, or only a store-wide recorded change. None: nothing stands out.";

function Waterfall({ inv, currency }: { inv: Investigation; currency: string }) {
  const core = inv.decomposition.core;
  const max = Math.max(...core.map((c) => Math.abs(c.contribution)), 1);
  return (
    <ul className="space-y-2" aria-label="Contribution of each factor to the change in attributed gross sales per day">
      {core.map((c) => {
        const w = (50 * Math.abs(c.contribution)) / max;
        const neg = c.contribution < 0;
        return (
          <li key={c.factor} className="grid grid-cols-[minmax(0,12rem)_1fr_6rem] items-center gap-3 text-sm">
            <span>{FACTOR[c.factor]}</span>
            <span className="relative h-4" title={`${FACTOR[c.factor]}: ${money(c.contribution, currency, 2)} per day`}>
              <span className="absolute inset-y-0 left-1/2 w-px" style={{ background: "var(--border)" }} />
              <span
                className="absolute inset-y-0 rounded"
                style={{
                  left: neg ? `${50 - w}%` : "50%",
                  width: `${Math.max(w, 0.5)}%`,
                  background: neg ? "var(--neg)" : "var(--pos)",
                }}
              />
            </span>
            <span className="num text-right tabular-nums">{money(c.contribution, currency, 0)}</span>
          </li>
        );
      })}
    </ul>
  );
}

function Summary({ rep, id, ai: wantAi }: { rep: Report; id: string; ai: boolean }) {
  const ai = rep.summary.some((s) => s.source === "model");
  const n = rep.narration;
  return (
    <section aria-labelledby="summary" className="card">
      <h2 id="summary" className="section-title">
        Summary{" "}
        <span className="badge" title="Who wrote these sentences">
          {ai ? `AI-written (${n.model}), validated` : "Template, no AI"}
        </span>
      </h2>
      <p className="mb-3 text-xs">
        {STATIC_DEMO ? (
          <span className="muted">The optional AI summary runs on a local model and is available in the local app, not in this static demo.</span>
        ) : wantAi ? (
          <Link href={`/incidents/${id}`} className="underline underline-offset-2">Show the template summary</Link>
        ) : (
          <Link href={`/incidents/${id}?ai=1`} prefetch={false} className="underline underline-offset-2">
            Try an AI-written summary (local model, about 30 seconds; falls back to the template if it fails validation)
          </Link>
        )}
      </p>
      <ol className="space-y-2 text-sm">
        {rep.summary.map((s, i) => (
          <li key={i}>
            {s.text}{" "}
            <span className="muted text-xs">
              [{s.status === "attributed" ? "measured breakdown" : s.status} ·{" "}
              {s.finding_ids.map((f, j) => (
                <span key={f}>
                  {j ? ", " : ""}
                  <a href={`#${f}`} className="underline underline-offset-2">{f}</a>
                </span>
              ))}
              ]
            </span>
          </li>
        ))}
      </ol>
      <h3 className="sub-title">Suggested next steps</h3>
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {rep.next_steps.map((s) => (
          <li key={s.id}>{s.text}</li>
        ))}
      </ul>
      <p className="muted mt-3 text-xs">
        {ai
          ? `Each AI sentence passed checks on numbers, cited findings, status, direction and wording (attempts: ${n.attempts}). The checks reduce risk; they cannot guarantee meaning.`
          : n.fallback
            ? "The AI draft failed validation twice, so the template text is shown."
            : n.note ?? "Written from the findings by fixed templates."}
      </p>
    </section>
  );
}

export async function generateStaticParams() {
  // Pre-renders the incident pages for the static demo build.
  const ov = await getOverview();
  return ov.incidents.filter((i) => i.status !== "suppressed_data_quality").map((i) => ({ id: i.incident_id }));
}

export default async function IncidentPage({ params, searchParams }: PageProps<"/incidents/[id]">) {
  const { id } = await params;
  const wantAi = STATIC_DEMO ? false : (await searchParams).ai === "1";
  const [inv, rep] = await Promise.all([getInvestigation(id), getReport(id, wantAi)]);
  const cur = inv.workspace.currency;
  const ev = inv.explanation_evidence;
  const byStatus = ["observed", "attributed", "associated", "hypothesis"].map((s) => [s, inv.findings.filter((f) => f.status === s)] as const);
  const allValid = inv.validation.every((v) => v.passed);
  const primary = inv.drilldown.primary;
  const dims = primary ? [primary.dimension, ...Object.keys(inv.drilldown.dimensions).filter((d) => d !== primary.dimension)] : Object.keys(inv.drilldown.dimensions);

  return (
    <main className="mx-auto w-full max-w-6xl space-y-8 px-4 py-8 sm:px-6">
      <Nav active="overview" />
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">
            <Link href="/" className="underline-offset-2 hover:underline">Overview</Link> / Investigation
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">
            {inv.incident.anchor_metric.replaceAll("_", " ")} {inv.incident.direction === "up" ? "above" : "below"} forecast
          </h1>
          <p className="muted">
            {shortDate(inv.window.start)} to {shortDate(inv.window.end)} ({inv.window.days} days) compared with {inv.decomposition.baseline.days} baseline days (
            {inv.decomposition.baseline.rule})
          </p>
        </div>
        <span className="pill">Data: {inv.data_label}</span>
      </header>

      <Summary rep={rep} id={id} ai={wantAi} />

      <section aria-labelledby="evidence" className="card">
        <h2 id="evidence" className="section-title">
          Explanation evidence: <span className={`badge ${ev.level.toLowerCase()}`}>{ev.level}</span>
        </h2>
        <ul className="muted list-disc space-y-1 pl-5">
          {ev.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        <p className="muted mt-2 text-xs">{EVIDENCE_RULES} This is a rule, not a probability.</p>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="bridge" className="card">
          <h2 id="bridge" className="section-title">Revenue bridge, per day</h2>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Line</th>
                  <th scope="col" className="num">Baseline</th>
                  <th scope="col" className="num">Incident</th>
                  <th scope="col" className="num">Change</th>
                </tr>
              </thead>
              <tbody>
                {inv.decomposition.bridge.map((b) => (
                  <tr key={b.line} className={b.total ? "font-semibold" : undefined}>
                    <th scope="row" className="font-normal">{b.label}</th>
                    <td className="num">{money(b.baseline, cur)}</td>
                    <td className="num">{money(b.current, cur)}</td>
                    <td className="num">{money(b.change, cur)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <section aria-labelledby="factors" className="card">
          <h2 id="factors" className="section-title">Measured breakdown of attributed gross sales</h2>
          <p className="muted mb-3">
            Change per day: {money(inv.decomposition.core_total.change, cur)}. Each bar is that factor&apos;s exact share of the change (Shapley); bars sum to the
            total. A breakdown shows what moved, not why.
          </p>
          <Waterfall inv={inv} currency={cur} />
        </section>
      </div>

      <section aria-labelledby="segments" className="card">
        <h2 id="segments" className="section-title">Where the change is concentrated</h2>
        <p className="muted mb-3">
          {primary
            ? `${Math.round(primary.share * 100)}% of the ${primary.dimension} breakdown is in ${primary.segment}.`
            : "No single segment stands out from normal variation."}{" "}
          Traffic and rate parts split each segment&apos;s change exactly. Noise score compares the change with the segment&apos;s own daily variation (2 or more
          stands out).
        </p>
        {dims.map((d) => {
          const v = inv.drilldown.dimensions[d];
          return (
            <details key={d} open={d === primary?.dimension} className="mb-3">
              <summary className="cursor-pointer text-sm font-medium">{d}</summary>
              <div className="overflow-x-auto">
                <table className="data-table mt-2">
                  <thead>
                    <tr>
                      <th scope="col">Segment</th>
                      <th scope="col" className="num">Baseline / day</th>
                      <th scope="col" className="num">Incident / day</th>
                      <th scope="col" className="num">Change</th>
                      {d !== "category" ? <th scope="col" className="num">Traffic part</th> : null}
                      {d !== "category" ? <th scope="col" className="num">Rate part</th> : null}
                      <th scope="col" className="num">Noise score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {v.rows.map((r) => (
                      <tr key={r.segment}>
                        <td>
                          {r.segment}
                          {!r.volume_ok ? <span className="muted"> (low volume)</span> : null}
                        </td>
                        <td className="num">{money(r.baseline_per_day, cur)}</td>
                        <td className="num">{money(r.current_per_day, cur)}</td>
                        <td className="num">{money(r.change, cur)}</td>
                        {d !== "category" ? <td className="num">{money(r.traffic_part ?? 0, cur)}</td> : null}
                        {d !== "category" ? <td className="num">{money(r.rate_part ?? 0, cur)}</td> : null}
                        <td className="num">{r.noise_score.toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          );
        })}
      </section>

      <section aria-labelledby="findings" className="card">
        <h2 id="findings" className="section-title">Findings</h2>
        <p className="muted mb-3">Each finding states how it is known. Observed and measured findings are computed; associations and hypotheses are not proof.</p>
        <div className="grid gap-4 md:grid-cols-2">
          {byStatus.map(([s, fs]) => (
            <div key={s}>
              <h3 className="sub-title">{STATUS_LABEL[s]}</h3>
              {fs.length === 0 ? (
                <p className="muted">None.</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {fs.map((f) => (
                    <li key={f.finding_id} id={f.finding_id} className="scroll-mt-4">
                      <span className="muted mr-1 font-mono text-xs">{f.finding_id}</span>
                      {f.text}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="events" className="card">
          <h2 id="events" className="section-title">Recorded changes near the start</h2>
          {inv.events.length === 0 ? (
            <p className="muted">No recorded changes within 24 hours of the start.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {inv.events.map((e) => (
                <li key={e.event_id}>
                  <span className="font-medium">{e.description}</span> <span className="muted">({e.type})</span>
                  <p className="muted text-xs">
                    {e.hours_before_change > 0 ? `${e.hours_before_change} hours before` : `${-e.hours_before_change} hours after`} the start ·{" "}
                    {Object.keys(e.scope).length ? `scope ${JSON.stringify(e.scope)}` : "store-wide"} ·{" "}
                    {e.match === "scope_match" ? "scope matches the segment" : e.match === "unscoped" ? "no scope" : "scope does not match"}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section aria-labelledby="ruled" className="card">
          <h2 id="ruled" className="section-title">Alternatives checked</h2>
          <ul className="space-y-2 text-sm">
            {inv.ruled_out.map((r) => (
              <li key={r.alternative}>
                <span aria-hidden className={`status-icon ${r.ruled_out ? "ok" : "warn"}`}>{r.ruled_out ? "✓" : "!"}</span>
                {r.alternative}: {r.ruled_out ? "ruled out" : "not ruled out"} <span className="muted">({r.reason})</span>
              </li>
            ))}
          </ul>
          <p className="status-line mt-4">
            <span aria-hidden className={`status-icon ${allValid ? "ok" : "fail"}`}>{allValid ? "✓" : "!"}</span>
            {allValid ? `All ${inv.validation.length} validation checks passed` : "Some validation checks failed"}
          </p>
          <p className="muted text-xs">Every number in the findings is recomputed from the breakdown before this page is shown.</p>
        </section>
      </div>

      <footer className="muted border-t pt-4 text-xs" style={{ borderColor: "var(--border)" }}>
        The summary is built only from the findings on this page. Numbers, tables and evidence levels never come from a language model.
      </footer>
    </main>
  );
}
