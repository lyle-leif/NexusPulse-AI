import Link from "next/link";
import { API_URL, STATIC_DEMO, getInvestigation, getReport, type Investigation, type Overview, type Report } from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import { METRIC_PLAIN } from "../../components/IssueCard";
import { EvidenceMeter } from "../../components/Mini";
import Nav from "../../components/Nav";

const FACTOR: Record<string, string> = {
  sessions: "Number of visits",
  cart_rate: "Visits adding to cart",
  checkout_rate: "Carts reaching checkout",
  purchase_rate: "Checkouts completed",
  orders_per_converting_session: "Orders per buying visit",
  attributed_aov: "Average order value",
};
const STATUS_LABEL: Record<string, string> = {
  observed: "Seen in the data",
  attributed: "Measured breakdown",
  associated: "Happened at the same time",
  hypothesis: "Possible explanations (not confirmed)",
};
const DIM: Record<string, string> = { channel: "Traffic source", device: "Device", region: "Region", category: "Product category" };
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
                  background: neg ? "var(--warn)" : "var(--accent)",
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
        What happened{" "}
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
      <ol className="lead space-y-3">
        {rep.summary.map((s, i) => (
          <li key={i}>
            {s.text}{" "}
            <span className="faint text-xs">
              [{STATUS_LABEL[s.status]?.toLowerCase() ?? s.status} ·{" "}
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
  // Pre-renders the incident pages for the static demo build. Uses a plain fetch:
  // generateStaticParams runs without a request, so request-time helpers cannot be used here.
  const ov: Overview = await fetch(`${API_URL}/api/overview?workspace=demo`).then((r) => r.json());
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

  const segRows = primary ? inv.drilldown.dimensions[primary.dimension].rows : [];
  const segMax = Math.max(1, ...segRows.map((r) => Math.abs(r.change)));
  const title = `${METRIC_PLAIN[inv.incident.anchor_metric] ?? inv.incident.anchor_metric} ${inv.incident.direction === "up" ? "higher" : "lower"} than expected`;

  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 px-4 py-6 sm:px-6">
      <Nav active="overview" />
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">
            <Link href="/" className="link">Overview</Link> / Issue
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">{title}</h1>
          <p className="muted mt-1">
            {shortDate(inv.window.start)} to {shortDate(inv.window.end)} ({inv.window.days} days), compared with the same weekdays in the 4 weeks before
          </p>
        </div>
        <span className="chip">Data: {inv.data_label}</span>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <Summary rep={rep} id={id} ai={wantAi} />
        <section aria-labelledby="evidence" className="card">
          <h2 id="evidence" className="section-title">How well we can explain it</h2>
          <EvidenceMeter level={ev.level} />
          <ul className="muted mt-3 list-disc space-y-1 pl-5 text-sm">
            {ev.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          <details className="more">
            <summary>The rule</summary>
            <p className="muted mt-2 text-xs">{EVIDENCE_RULES} This is a rule, not a probability.</p>
          </details>
        </section>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="where" className="card">
          <h2 id="where" className="section-title">Where it changed</h2>
          {primary ? (
            <>
              <p className="mb-3 text-sm">
                <strong>{Math.round(primary.share * 100)}%</strong> of the change is in <strong>{primary.segment}</strong>{" "}
                <span className="muted">({(DIM[primary.dimension] ?? primary.dimension).toLowerCase()})</span>
              </p>
              <ul className="space-y-2" aria-label={`Change in revenue per day by ${primary.dimension}`}>
                {segRows.map((r) => {
                  const w = (50 * Math.abs(r.change)) / segMax;
                  const hot = r.segment === primary.segment;
                  return (
                    <li key={r.segment} className="grid grid-cols-[minmax(0,8rem)_1fr_5.5rem] items-center gap-3 text-sm">
                      <span className={hot ? "font-semibold" : ""}>{r.segment}</span>
                      <span className="relative h-3" aria-hidden>
                        <span className="absolute inset-y-0 left-1/2 w-px" style={{ background: "var(--border)" }} />
                        <span
                          className="absolute inset-y-0 rounded-sm"
                          style={{
                            left: r.change < 0 ? `${50 - w}%` : "50%",
                            width: `${Math.max(w, 0.5)}%`,
                            background: hot ? (r.change < 0 ? "var(--warn)" : "var(--accent)") : "var(--text-muted)",
                          }}
                        />
                      </span>
                      <span className="num text-right">{money(r.change, cur)}</span>
                    </li>
                  );
                })}
              </ul>
              <p className="faint mt-2 text-xs">Change in revenue per day versus the comparison weeks.</p>
            </>
          ) : (
            <p className="muted">No single segment stands out from normal day-to-day variation.</p>
          )}
          <details className="more">
            <summary>All breakdowns (traffic vs rate, noise score)</summary>
            <p className="faint mt-2 text-xs">
              Traffic and rate parts split each segment&apos;s change exactly. The noise score compares the change with the segment&apos;s own daily variation;
              2 or more stands out.
            </p>
            {dims.map((d) => {
              const v = inv.drilldown.dimensions[d];
              return (
                <div key={d} className="mt-3 overflow-x-auto">
                  <p className="sub-title">{DIM[d] ?? d}</p>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th scope="col">Segment</th>
                        <th scope="col" className="num">Before / day</th>
                        <th scope="col" className="num">During / day</th>
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
                            {!r.volume_ok ? <span className="faint"> (low volume)</span> : null}
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
              );
            })}
          </details>
        </section>

        <section aria-labelledby="factors" className="card">
          <h2 id="factors" className="section-title">What moved</h2>
          <p className="mb-3 text-sm">
            Sales from tracked visits changed by <strong className="num">{money(inv.decomposition.core_total.change, cur)}</strong> per day. Each bar is one
            factor&apos;s exact share; together they add up to that change.
          </p>
          <Waterfall inv={inv} currency={cur} />
          <p className="faint mt-2 text-xs">This shows what moved, not why.</p>
          <details className="more">
            <summary>Full revenue bridge, per day</summary>
            <div className="mt-2 overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Line</th>
                    <th scope="col" className="num">Before</th>
                    <th scope="col" className="num">During</th>
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
            <p className="faint mt-2 text-xs">
              Comparison days: {inv.decomposition.baseline.days} ({inv.decomposition.baseline.rule}).
            </p>
          </details>
        </section>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="events" className="card">
          <h2 id="events" className="section-title">What happened around then</h2>
          {inv.events.length === 0 ? (
            <p className="muted">No recorded changes (releases, prices, campaigns) within 24 hours of the start.</p>
          ) : (
            <ol className="space-y-4 border-l pl-4" style={{ borderColor: "var(--border)" }}>
              {inv.events.map((e) => (
                <li key={e.event_id} className="relative">
                  <span
                    aria-hidden
                    className="absolute top-1.5 h-2 w-2 rounded-full"
                    style={{ left: -21, background: e.match === "scope_match" ? "var(--accent)" : "var(--text-muted)" }}
                  />
                  <p className="text-sm font-medium">{e.description}</p>
                  <p className="faint text-xs">
                    {e.hours_before_change > 0 ? `${e.hours_before_change} hours before` : `${-e.hours_before_change} hours after`} the change started ·{" "}
                    {e.match === "scope_match" ? "affects the same segment" : e.match === "unscoped" ? "store-wide" : "affects a different segment"}
                  </p>
                </li>
              ))}
            </ol>
          )}
          <p className="sub-title">Other explanations checked</p>
          <ul className="space-y-2 text-sm">
            {inv.ruled_out.map((r) => (
              <li key={r.alternative}>
                <span aria-hidden className={`status-icon ${r.ruled_out ? "ok" : "warn"}`}>{r.ruled_out ? "✓" : "!"}</span>
                {r.alternative}: {r.ruled_out ? "ruled out" : "not ruled out"} <span className="faint">({r.reason})</span>
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="findings" className="card">
          <h2 id="findings" className="section-title">Findings behind the summary</h2>
          <p className="status-line">
            <span aria-hidden className={`status-icon ${allValid ? "ok" : "fail"}`}>{allValid ? "✓" : "!"}</span>
            {allValid ? `All ${inv.validation.length} numbers re-checked` : "Some checks failed"}
          </p>
          {byStatus.map(([s, fs]) => (
            <details key={s} className="more" open={s === "observed"}>
              <summary>
                {STATUS_LABEL[s]} ({fs.length})
              </summary>
              {fs.length === 0 ? (
                <p className="faint mt-2 text-sm">None.</p>
              ) : (
                <ul className="mt-2 space-y-2 text-sm">
                  {fs.map((f) => (
                    <li key={f.finding_id} id={f.finding_id} className="scroll-mt-4">
                      <span className="faint mr-1 font-mono text-xs">{f.finding_id}</span>
                      {f.text}
                    </li>
                  ))}
                </ul>
              )}
            </details>
          ))}
        </section>
      </div>

      <footer className="faint border-t pt-4 text-xs" style={{ borderColor: "var(--border)" }}>
        The summary is built only from the findings on this page. Numbers, tables and evidence levels never come from a language model.
      </footer>
    </main>
  );
}
