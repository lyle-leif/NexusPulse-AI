import Link from "next/link";
import type { Incident } from "@/lib/api";
import { money, shortDate } from "@/lib/format";

const METRIC = {
  net_sales: "Net sales",
  orders: "Orders",
  sessions: "Sessions",
  session_conversion_rate: "Session conversion rate",
} as Record<string, string>;

const STATUS = {
  open: "Open",
  resolved: "Resolved",
  level_shift: "Level shift (new normal)",
  suppressed_data_quality: "Suppressed: data-quality issue",
} as Record<string, string>;

export default function IncidentsPanel({ incidents, currency }: { incidents: Incident[]; currency: string }) {
  const business = incidents.filter((i) => i.status !== "suppressed_data_quality");
  const suppressed = incidents.length - business.length;
  return (
    <section aria-labelledby="incidents" className="card">
      <h2 id="incidents" className="section-title">Business incidents</h2>
      <p className="muted mb-3">
        Days where a metric left the range forecast before it happened. Strength is a rule, not a probability: Strong = 3 or more days out of range and a
        score of 5 or more; Moderate = 2 or more days or a score of 5 or more; otherwise Weak.
        {suppressed ? ` ${suppressed} incident(s) overlapping a data-quality issue are suppressed and not shown as business changes.` : ""}
      </p>
      {business.length === 0 ? (
        <p className="muted">No business incidents detected.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Dates</th>
                <th scope="col">Metric</th>
                <th scope="col">Direction</th>
                <th scope="col">Strength</th>
                <th scope="col">Status</th>
                <th scope="col" className="num">Net sales vs forecast</th>
              </tr>
            </thead>
            <tbody>
              {business.map((i) => (
                <tr key={i.incident_id}>
                  <td>
                    <Link href={`/incidents/${i.incident_id}`} className="underline underline-offset-2">
                      {shortDate(i.start)} to {i.end ? shortDate(i.end) : "ongoing"}
                    </Link>
                  </td>
                  <td>
                    {METRIC[i.anchor_metric] ?? i.anchor_metric}
                    {i.members.length > 1 ? <span className="muted"> + {i.members.length - 1} related</span> : null}
                  </td>
                  <td>{i.direction === "up" ? "Above forecast" : "Below forecast"}</td>
                  <td>
                    <span className={`badge ${i.strength.toLowerCase()}`}>{i.strength}</span>
                  </td>
                  <td>{STATUS[i.status] ?? i.status}</td>
                  <td className="num">{i.impact === null ? <span className="muted">net sales in range</span> : money(i.impact, currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted mt-3 text-xs">Open an incident to see its investigation.</p>
    </section>
  );
}
