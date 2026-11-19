import { getOverview, type PeriodSummary } from "@/lib/api";
import { change, int, money, pct, shortDate } from "@/lib/format";
import IncidentsPanel from "./components/IncidentsPanel";
import Nav from "./components/Nav";
import TrendPanel from "./components/TrendPanel";

function Delta({ cur, prev, kind = "relative" }: { cur: number; prev: number; kind?: "relative" | "points" }) {
  if (kind === "points") {
    const pts = (cur - prev) * 100;
    return <span className="delta">{`${pts >= 0 ? "+" : ""}${pts.toFixed(2)} pts vs prior 28 days`}</span>;
  }
  const c = change(cur, prev);
  if (c === null) return <span className="delta">No prior data</span>;
  return <span className="delta">{`${c >= 0 ? "+" : ""}${(c * 100).toFixed(1)}% vs prior 28 days`}</span>;
}

function Tiles({ cur, prev, currency }: { cur: PeriodSummary; prev: PeriodSummary; currency: string }) {
  const tiles = [
    { label: "Net revenue", value: money(cur.net_revenue, currency), d: <Delta cur={cur.net_revenue} prev={prev.net_revenue} /> },
    { label: "Sessions", value: int(cur.sessions), d: <Delta cur={cur.sessions} prev={prev.sessions} /> },
    { label: "Orders", value: int(cur.orders), d: <Delta cur={cur.orders} prev={prev.orders} /> },
    {
      label: "Session conversion rate",
      value: pct(cur.session_conversion_rate),
      d: <Delta cur={cur.session_conversion_rate} prev={prev.session_conversion_rate} kind="points" />,
    },
    { label: "Attributed average order value", value: money(cur.attributed_aov, currency, 2), d: <Delta cur={cur.attributed_aov} prev={prev.attributed_aov} /> },
    {
      label: "Unattributed order share",
      value: pct(cur.unattributed_share, 1),
      d: <Delta cur={cur.unattributed_share} prev={prev.unattributed_share} kind="points" />,
    },
  ];
  return (
    <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {tiles.map((t) => (
        <li key={t.label} className="card">
          <p className="tile-label">{t.label}</p>
          <p className="tile-value">{t.value}</p>
          {t.d}
        </li>
      ))}
    </ul>
  );
}

export default async function Page() {
  const data = await getOverview("demo");
  const { current_period: cur, previous_period: prev, workspace } = data;
  const failed = data.reconciliation.filter((c) => !c.passed);

  return (
    <main className="mx-auto w-full max-w-6xl space-y-8 px-4 py-8 sm:px-6">
      <Nav active="overview" />
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">NexusPulse AI</p>
          <h1 className="text-2xl font-semibold tracking-tight">{workspace.name}</h1>
          <p className="muted">
            Last 28 days: {shortDate(cur.start)} to {shortDate(cur.end)} · Timezone {workspace.timezone} · {workspace.currency}
          </p>
        </div>
        <span className="pill" title="Where this data comes from">
          Data: {data.data_label}
        </span>
      </header>

      <section aria-label="Key metrics">
        <Tiles cur={cur} prev={prev} currency={workspace.currency} />
      </section>

      <div className="grid gap-6 lg:grid-cols-5">
        <section aria-labelledby="bridge" className="card lg:col-span-3">
          <h2 id="bridge" className="section-title">Revenue bridge, last 28 days</h2>
          <p className="muted mb-3">How net revenue is assembled. Each line is computed from the data; the lines sum exactly to net revenue.</p>
          <table className="bridge">
            <tbody>
              {data.revenue_bridge.map((l) => (
                <tr key={l.label} className={l.total ? "total" : undefined}>
                  <th scope="row">{l.label}</th>
                  <td>{money(l.amount, workspace.currency, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section aria-labelledby="dq" className="card lg:col-span-2">
          <h2 id="dq" className="section-title">Data quality</h2>
          <p className="status-line">
            <span aria-hidden className={failed.length ? "status-icon fail" : "status-icon ok"}>{failed.length ? "!" : "✓"}</span>
            {failed.length ? `${failed.length} reconciliation check(s) failed` : `All ${data.reconciliation.length} reconciliation checks passed`}
          </p>
          <h3 className="sub-title">Incidents</h3>
          {data.data_quality_incidents.length === 0 ? (
            <p className="muted">No data-quality incidents.</p>
          ) : (
            <ul className="space-y-3">
              {data.data_quality_incidents.map((i) => (
                <li key={i.start} className="incident">
                  <p className="font-medium">
                    <span aria-hidden className="status-icon warn">!</span> Unattributed order share above {pct(i.threshold, 0)}
                  </p>
                  <p className="muted">
                    {shortDate(i.start)} to {shortDate(i.end)}
                    {i.open ? " (ongoing)" : ""}
                  </p>
                  <p className="muted text-xs">
                    Orders are arriving without a tracked session, which suggests a tracking problem rather than a change in customer behavior. Conversion
                    figures in this window are understated. The end date trails the actual recovery by up to 14 days because the check uses a 14-day window.
                  </p>
                </li>
              ))}
            </ul>
          )}
          <details className="mt-4">
            <summary className="cursor-pointer text-sm">Reconciliation checks</summary>
            <ul className="mt-2 space-y-1 text-sm">
              {data.reconciliation.map((c) => (
                <li key={c.name}>
                  <span aria-hidden>{c.passed ? "✓" : "✗"}</span> {c.name.replaceAll("_", " ")}
                  {c.detail ? <span className="muted"> ({c.detail})</span> : null}
                </li>
              ))}
            </ul>
          </details>
        </section>
      </div>

      <IncidentsPanel incidents={data.incidents} currency={workspace.currency} />

      <TrendPanel data={data} />

      <footer className="muted space-y-1 border-t pt-4 text-xs" style={{ borderColor: "var(--border)" }}>
        {data.notes.map((n) => (
          <p key={n}>{n}</p>
        ))}
        <p>Incidents use as-of forecasts: each day is judged against a forecast issued before it.</p>
      </footer>
    </main>
  );
}
