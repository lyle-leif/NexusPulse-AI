import Link from "next/link";
import type { Incident } from "@/lib/api";
import { money, shortDate } from "@/lib/format";

export const METRIC_PLAIN: Record<string, string> = {
  net_sales: "Revenue",
  orders: "Orders",
  sessions: "Visits",
  session_conversion_rate: "Share of visits that bought",
};

const SEGMENT_PLAIN: Record<string, string> = {
  organic: "organic search",
  paid_search: "paid search",
  paid_social: "paid social",
  email: "email",
  direct: "direct visits",
  mobile: "mobile",
  desktop: "desktop",
  tablet: "tablet",
  north_america: "North America",
  europe: "Europe",
  asia_pacific: "Asia-Pacific",
};

/** Plain name of a segment: "paid social", "mobile", "Dresses". */
export function segmentName(s: { dimension: string; value: string }) {
  return SEGMENT_PLAIN[s.value] ?? (s.dimension === "category" ? s.value : s.value.replace(/_/g, " "));
}

const CLARITY: Record<string, string> = { Strong: "Clear signal", Moderate: "Likely signal", Weak: "Faint signal" };

/** One-line plain description of an issue. */
export function issueTitle(i: Incident) {
  const metric = METRIC_PLAIN[i.anchor_metric] ?? i.anchor_metric;
  const where = i.scope === "segment" && i.segment ? ` from ${segmentName(i.segment)}` : "";
  return `${metric}${where} ${i.direction === "down" ? "lower" : "higher"} than expected`;
}

/** Where else the change was seen, for a store-wide issue ("paid social, mobile"); empty when none. */
export function issueSegments(i: Incident) {
  const names = [...new Set((i.segments ?? []).filter((s) => !(i.segment && s.value === i.segment.value)).map(segmentName))];
  return names.length > 3 ? `${names.slice(0, 3).join(", ")} and ${names.length - 3} more` : names.join(", ");
}

export function issueDates(i: Incident) {
  return `${shortDate(i.start)} to ${i.end ? shortDate(i.end) : "now"}${i.end ? "" : " (still going)"}`;
}

export default function IssueCard({ i, currency, href, action }: { i: Incident; currency: string; href?: string; action?: React.ReactNode }) {
  const dq = i.status === "suppressed_data_quality";
  return (
    <li className={`issue ${dq ? "muted-issue" : i.direction === "up" ? "up" : ""}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium">{dq ? "Tracking problem, not a business change" : issueTitle(i)}</p>
          <p className="muted text-xs">{issueDates(i)}</p>
          {!dq && issueSegments(i) ? <p className="faint text-xs">{i.scope === "segment" ? "Also in" : "Seen in"}: {issueSegments(i)}</p> : null}
        </div>
        <span className="chip" title="Rule: Clear = 3+ days out of range and a strong score; Likely = 2+ days or a strong score; otherwise Faint. Not a probability.">
          {CLARITY[i.strength] ?? i.strength}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="muted">
          {dq
            ? "Overlaps a tracking problem, so it is not investigated."
            : i.impact !== null
              ? `About ${money(Math.abs(i.impact), currency)} ${i.impact < 0 ? "below" : "above"} forecast in total`
              : "Revenue stayed within range"}
          {i.members.length > 1 ? ` · ${i.members.length - 1} related signal${i.members.length > 2 ? "s" : ""}` : ""}
        </span>
        {action ?? (href && !dq ? (
          <Link href={href} className="link text-sm">
            Investigate
          </Link>
        ) : null)}
      </div>
    </li>
  );
}
