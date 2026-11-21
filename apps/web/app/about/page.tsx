import Link from "next/link";
import Icon, { type IconName } from "../components/Icons";
import Nav from "../components/Nav";

export const metadata = { title: "How it works | NexusPulse AI" };

const STEPS: { n: string; title: string; icon: IconName; text: string; href: string; cta: string }[] = [
  {
    n: "01",
    title: "Store data",
    icon: "orders",
    text: "Visits, orders, refunds and recorded changes (releases, prices, campaigns) are loaded every day. Consistency checks confirm the numbers add up before anything else runs.",
    href: "/",
    cta: "See the data checks",
  },
  {
    n: "02",
    title: "Expected range",
    icon: "chart",
    text: "For each day, a forecast made before that day sets the range revenue, orders, visits and conversion should fall in. Known holidays and closures are left out.",
    href: "/",
    cta: "See revenue vs expected",
  },
  {
    n: "03",
    title: "Issue detected",
    icon: "issue",
    text: "When a number stays outside its range long enough, an issue opens. Tracking problems are told apart from real business changes.",
    href: "/time-machine",
    cta: "Replay it day by day",
  },
  {
    n: "04",
    title: "Explained",
    icon: "search",
    text: "The investigation finds where the change happened (segment), what moved (visits, conversion or order value), and whether a recorded change lines up with it. It says how sure it is.",
    href: "/evaluation",
    cta: "See how often it is right",
  },
];

/** Four-step pipeline diagram: boxes joined by a line, drawn with plain HTML and SVG. */
export default function AboutPage() {
  return (
    <main className="mx-auto w-full max-w-6xl space-y-5 px-4 py-5 sm:px-6">
      <Nav active="about" />
      <header className="max-w-3xl">
        <p className="eyebrow">How it works</p>
        <h1 className="page-title mt-2">From daily numbers to a plain explanation</h1>
        <p className="muted mt-2">
          NexusPulse is a monitoring and root-cause tool for online stores. It answers three questions: did something change, where, and how sure are we?
        </p>
      </header>

      <section aria-label="The four steps" className="card bracket">
        <ol className="grid gap-5 md:grid-cols-4">
          {STEPS.map((s, i) => (
            <li key={s.n} className="relative flex flex-col gap-3">
              <div className="flex items-center gap-3">
                <span
                  className="flex h-11 w-11 flex-none items-center justify-center rounded-full"
                  style={{ border: "1px solid var(--accent)", color: "var(--accent)", background: "var(--accent-soft)", boxShadow: "var(--glow-box)" }}
                >
                  <Icon name={s.icon} size={20} />
                </span>
                {i < STEPS.length - 1 ? (
                  <svg aria-hidden className="hidden h-2 flex-1 md:block" preserveAspectRatio="none" viewBox="0 0 100 8">
                    <line x1="0" y1="4" x2="92" y2="4" stroke="var(--accent)" strokeOpacity={0.6} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
                    <path d="M92 0 L100 4 L92 8 Z" fill="var(--accent)" />
                  </svg>
                ) : null}
              </div>
              <div>
                <p className="faint num text-xs">{s.n}</p>
                <h2 className="display text-lg font-semibold">{s.title}</h2>
                <p className="muted mt-1">{s.text}</p>
              </div>
              <Link href={s.href} className="link mt-auto text-sm">
                {s.cta}
              </Link>
            </li>
          ))}
        </ol>
      </section>

      <div className="grid gap-5 lg:grid-cols-3">
        <section aria-labelledby="data" className="card solid">
          <h2 id="data" className="section-title">
            <Icon name="info" /> About the data
          </h2>
          <p className="muted">
            The demo store is generated, with planted changes whose answers the system cannot see. That is what makes the accuracy page possible. A real
            public retailer dataset is also tested; every result is labelled Synthetic, Semi-synthetic or Real.
          </p>
        </section>
        <section aria-labelledby="ai" className="card solid">
          <h2 id="ai" className="section-title">
            <Icon name="check" /> Where AI is used
          </h2>
          <p className="muted">
            Numbers, tables and confidence levels never come from a language model. Summaries come from templates; an optional local model may reword them,
            and its text is checked against the findings and replaced if it fails.
          </p>
        </section>
        <section aria-labelledby="limits" className="card solid">
          <h2 id="limits" className="section-title">
            <Icon name="issue" /> Known limits
          </h2>
          <p className="muted">
            Store-wide changes under about 25% are often missed unless they are concentrated in one channel, device, region or category. Small stores are watched store-wide only, and their segments are hard to tell apart. The data is daily, not live.
          </p>
        </section>
      </div>
    </main>
  );
}
