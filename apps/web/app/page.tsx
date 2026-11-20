import { getOverview, type Overview } from "@/lib/api";
import { change, int, money, pct, shortDate } from "@/lib/format";
import ForecastChart from "./components/ForecastChart";
import FunnelFlow from "./components/FunnelFlow";
import IssueCard, { issueTitle } from "./components/IssueCard";
import { Delta, Ring, Sparkline, StatTile } from "./components/Mini";
import Nav from "./components/Nav";
import TrendPanel from "./components/TrendPanel";

const dirOf = (c: number | null): "up" | "down" | "flat" => (c === null || Math.abs(c) < 0.005 ? "flat" : c > 0 ? "up" : "down");
const relText = (c: number | null) => (c === null ? "no earlier data" : `${Math.abs(c * 100).toFixed(1)}% vs prior 28 days`);
const shortRel = (c: number | null) => (c === null ? "no earlier data" : `${Math.abs(c * 100).toFixed(1)}%`);

/** One plain sentence: how the last 7 days compare with what was expected, and what is open. */
function statusSentence(d: Overview) {
  const last = d.forecast.series.slice(-7);
  const actual = last.reduce((a, p) => a + p.actual, 0);
  const expected = last.reduce((a, p) => a + p.expected, 0);
  const gap = expected ? actual / expected - 1 : 0;
  const outside = last.filter((p) => p.state === "out_of_range").length;
  const open = d.incidents.filter((i) => i.end === null && i.status !== "suppressed_data_quality");
  const first =
    Math.abs(gap) < 0.05 && outside === 0
      ? "Revenue over the last 7 days is in line with what we expected."
      : `Revenue over the last 7 days is ${Math.abs(gap * 100).toFixed(0)}% ${gap < 0 ? "below" : "above"} what we expected${outside ? `, with ${outside} day${outside > 1 ? "s" : ""} outside the expected range` : ""}.`;
  const second = open.length
    ? ` ${open.length} open issue${open.length > 1 ? "s" : ""}: ${issueTitle(open[0]).toLowerCase()} since ${shortDate(open[0].start)}.`
    : " No open issues.";
  return first + second;
}

export default async function Page() {
  const d = await getOverview("demo");
  const { current_period: cur, previous_period: prev, workspace } = d;
  const c = workspace.currency;
  const failed = d.reconciliation.filter((x) => !x.passed);
  const business = d.incidents.filter((i) => i.status !== "suppressed_data_quality");
  const tail = d.series.slice(-28);
  const revC = change(cur.net_revenue, prev.net_revenue);
  const convPts = (cur.session_conversion_rate - prev.session_conversion_rate) * 100;
  const dqOpen = d.data_quality_incidents.filter((i) => i.open);

  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 px-4 py-6 sm:px-6">
      <Nav active="overview" />

      <header className="grid gap-6 lg:grid-cols-[1.1fr_1fr] lg:items-end">
        <div>
          <p className="eyebrow">
            {workspace.name} · last 28 days · {shortDate(cur.start)} to {shortDate(cur.end)}
          </p>
          <p className="label mt-4">Net revenue</p>
          <div className="flex flex-wrap items-baseline gap-3">
            <p className="hero-value">{money(cur.net_revenue, c)}</p>
            <span className={`chip ${dirOf(revC) === "flat" ? "" : dirOf(revC)}`}>
              {dirOf(revC) === "up" ? "▲" : dirOf(revC) === "down" ? "▼" : ""} {relText(revC)}
            </span>
          </div>
        </div>
        <div className="card">
          <p className="label">What is happening</p>
          <p className="status-sentence mt-2">{statusSentence(d)}</p>
          <p className="faint mt-2 text-xs">
            Data: {d.data_label} · {c} · {workspace.timezone}
          </p>
        </div>
      </header>

      <section aria-labelledby="flow" className="card">
        <h2 id="flow" className="section-title">From visits to revenue</h2>
        <FunnelFlow cur={d.funnel.current} prev={d.funnel.previous} currency={c} />
      </section>

      <section aria-label="Key numbers">
        <p className="faint mb-2 text-xs">Changes compare the last 28 days with the 28 days before.</p>
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile label="Orders" value={int(cur.orders)} delta={<Delta dir={dirOf(change(cur.orders, prev.orders))} text={shortRel(change(cur.orders, prev.orders))} />}>
            <Sparkline values={tail.map((s) => s.orders)} label="Daily orders, last 28 days" />
          </StatTile>
          <StatTile label="Visits" value={int(cur.sessions)} delta={<Delta dir={dirOf(change(cur.sessions, prev.sessions))} text={shortRel(change(cur.sessions, prev.sessions))} />}>
            <Sparkline values={tail.map((s) => s.sessions)} label="Daily visits, last 28 days" />
          </StatTile>
          <StatTile
            label="Visits that bought"
            value={pct(cur.session_conversion_rate, 2)}
            delta={<Delta dir={Math.abs(convPts) < 0.01 ? "flat" : convPts > 0 ? "up" : "down"} text={`${Math.abs(convPts).toFixed(2)} pts`} />}
          >
            <div className="flex justify-end">
              <Ring value={cur.session_conversion_rate / 0.05} label={`${pct(cur.session_conversion_rate, 2)} of visits bought (ring full at 5%)`} />
            </div>
          </StatTile>
          <StatTile
            label="Average order value"
            value={money(cur.attributed_aov, c, 2)}
            delta={<Delta dir={dirOf(change(cur.attributed_aov, prev.attributed_aov))} text={shortRel(change(cur.attributed_aov, prev.attributed_aov))} />}
          >
            <Sparkline values={tail.map((s) => (s.orders ? s.net_revenue / s.orders : null))} label="Daily revenue per order, last 28 days" />
          </StatTile>
        </ul>
      </section>

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <section aria-labelledby="fc" className="card">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="fc" className="section-title">Revenue vs expected</h2>
            <span className="faint text-xs">Last 8 weeks and the next 7 days</span>
          </div>
          <ForecastChart
            past={d.forecast.series}
            ahead={d.forecast.forecast_ahead}
            currency={c}
            spans={business.map((i) => ({ id: i.incident_id, start: i.start, end: i.end, direction: i.direction }))}
            label="Daily net revenue for the last 8 weeks with the range expected for each day, and the forecast for the next 7 days"
          />
          <details className="more">
            <summary>How the expected range is made</summary>
            <p className="muted mt-2 text-xs">
              Each day is compared with a forecast made before that day (exponential smoothing with weekly seasonality, refitted weekly). Known calendar
              events are left out. An issue opens when revenue, orders, visits or conversion leaves its range for long enough; see the evaluation page for
              how often that is right.
            </p>
          </details>
        </section>

        <section aria-labelledby="issues" className="card">
          <div className="flex items-baseline justify-between">
            <h2 id="issues" className="section-title">Issues</h2>
            <span className="faint text-xs">{business.length} found</span>
          </div>
          {business.length === 0 ? (
            <p className="muted">Nothing unusual detected.</p>
          ) : (
            <ul className="space-y-2">
              {business.slice(0, 5).map((i) => (
                <IssueCard key={i.incident_id} i={i} currency={c} href={`/incidents/${i.incident_id}`} />
              ))}
            </ul>
          )}
          {business.length > 5 ? <p className="faint mt-2 text-xs">Showing the 5 most recent of {business.length}.</p> : null}
        </section>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <section aria-labelledby="bridge" className="card">
          <h2 id="bridge" className="section-title">Where net revenue comes from</h2>
          <Bridge lines={d.revenue_bridge} currency={c} />
          <details className="more">
            <summary>How this is calculated</summary>
            <p className="muted mt-2 text-xs">
              Sales from tracked visits, plus sales whose visit started the day before, plus orders we could not link to a visit, minus discounts and refunds.
              The lines add up exactly to net revenue.
            </p>
          </details>
        </section>

        <section aria-labelledby="dq" className="card">
          <h2 id="dq" className="section-title">Data health</h2>
          <p className="status-line">
            <span aria-hidden className={`status-icon ${failed.length ? "fail" : dqOpen.length ? "warn" : "ok"}`}>{failed.length || dqOpen.length ? "!" : "✓"}</span>
            {failed.length
              ? `${failed.length} consistency check${failed.length > 1 ? "s" : ""} failed`
              : dqOpen.length
                ? "Tracking problem right now: many orders cannot be linked to a visit"
                : "Data looks consistent"}
          </p>
          <p className="muted mt-2 text-sm">
            {pct(cur.unattributed_share, 1)} of orders could not be linked to a visit (check tracking above 10%).
          </p>
          {d.data_quality_incidents.length ? (
            <ul className="mt-3 space-y-1 text-sm">
              {d.data_quality_incidents.map((i) => (
                <li key={i.start} className="faint">
                  Tracking problem {shortDate(i.start)} to {shortDate(i.end)}
                  {i.open ? " (ongoing)" : ""}
                </li>
              ))}
            </ul>
          ) : null}
          <details className="more">
            <summary>{d.reconciliation.length} consistency checks</summary>
            <ul className="mt-2 space-y-1 text-xs">
              {d.reconciliation.map((x) => (
                <li key={x.name}>
                  <span aria-hidden>{x.passed ? "✓" : "✗"}</span> {x.name.replaceAll("_", " ")}
                  {x.detail ? <span className="faint"> ({x.detail})</span> : null}
                </li>
              ))}
            </ul>
          </details>
        </section>
      </div>

      <TrendPanel data={d} />

      <footer className="faint space-y-1 border-t pt-4 text-xs" style={{ borderColor: "var(--border)" }}>
        {d.notes.map((n) => (
          <p key={n}>{n}</p>
        ))}
      </footer>
    </main>
  );
}

/** Horizontal waterfall: each line is a bar from the running total; the last bar is net revenue. */
function Bridge({ lines, currency }: { lines: { label: string; amount: number; total?: boolean }[]; currency: string }) {
  const max = Math.max(...lines.map((l) => Math.abs(l.amount)), 1);
  let run = 0;
  const LABEL: Record<string, string> = {
    "Attributed gross sales": "Sales from tracked visits",
    "Timing difference": "Visits that ordered the next day",
    "Unattributed gross sales": "Orders not linked to a visit",
    Discounts: "Discounts",
    Refunds: "Refunds",
    "Net revenue": "Net revenue",
  };
  return (
    <ul className="space-y-2">
      {lines.map((l) => {
        const start = l.total ? 0 : Math.min(run, run + l.amount);
        const w = Math.abs(l.total ? l.amount : l.amount);
        if (!l.total) run += l.amount;
        const neg = l.amount < 0;
        return (
          <li key={l.label} className="grid grid-cols-[minmax(0,11rem)_1fr_6.5rem] items-center gap-3 text-sm">
            <span className={l.total ? "font-semibold" : ""}>{LABEL[l.label] ?? l.label}</span>
            <span className="relative h-3" aria-hidden>
              <span
                className="absolute inset-y-0 rounded-sm"
                style={{
                  left: `${(100 * start) / max}%`,
                  width: `${Math.max(0.4, (100 * w) / max)}%`,
                  background: l.total ? "var(--accent-fill)" : neg ? "var(--warn)" : "var(--accent-soft)",
                  border: l.total || neg ? "none" : "1px solid var(--accent)",
                }}
              />
            </span>
            <span className={`num text-right ${l.total ? "font-semibold" : ""}`}>{money(l.amount, currency)}</span>
          </li>
        );
      })}
    </ul>
  );
}
