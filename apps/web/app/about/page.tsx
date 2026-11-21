import Link from "next/link";
import Nav from "../components/Nav";

export const metadata = { title: "How it works | NexusPulse AI" };

const STEPS: { title: string; text: string; href: string; cta: string }[] = [
  {
    title: "Store data",
    text: "Visits, orders, refunds and recorded changes (releases, prices, campaigns) are loaded every day. Consistency checks confirm the numbers add up before anything else runs.",
    href: "/",
    cta: "See the data checks",
  },
  {
    title: "Expected range",
    text: "For each day, a forecast made before that day sets the range revenue, orders, visits and conversion should fall in. Known holidays and closures are left out.",
    href: "/",
    cta: "See revenue vs expected",
  },
  {
    title: "Issue detected",
    text: "When a number stays outside its range long enough, an issue opens. Tracking problems are told apart from real business changes.",
    href: "/time-machine",
    cta: "Replay it day by day",
  },
  {
    title: "Explained",
    text: "The investigation finds where the change happened (segment), what moved (visits, conversion or order value), and whether a recorded change lines up with it. It says how sure it is.",
    href: "/evaluation",
    cta: "See how often it is right",
  },
];

const NOTES: { id: string; title: string; text: string }[] = [
  {
    id: "data",
    title: "About the data",
    text: "The demo store is generated, with planted changes whose answers the system cannot see. That is what makes the accuracy page possible. A real public retailer dataset is also tested; every result is labelled Synthetic, Semi-synthetic or Real.",
  },
  {
    id: "ai",
    title: "Where AI is used",
    text: "Numbers, tables and confidence levels never come from a language model. Summaries come from templates; an optional local model may reword them, and its text is checked against the findings and replaced if it fails.",
  },
  {
    id: "limits",
    title: "Known limits",
    text: "Store-wide changes under about 25% are often missed unless they are concentrated in one channel, device, region or category. Small stores are watched store-wide only, and their segments are hard to tell apart. The data is daily, not live.",
  },
];

/** The pipeline as a numbered list on a shared rule, then three short notes. */
export default function AboutPage() {
  return (
    <main className="mx-auto w-full max-w-6xl space-y-8 px-4 py-5 sm:px-6">
      <Nav active="about" />
      <header className="max-w-3xl">
        <h1 className="page-title">From daily numbers to a plain explanation</h1>
        <p className="lead muted mt-3">
          NexusPulse is a monitoring and root-cause tool for online stores. It answers three questions: did something change, where, and how sure are we?
        </p>
      </header>

      <section aria-label="The four steps">
        <ol className="grid gap-6 md:grid-cols-4 md:gap-8">
          {STEPS.map((s, i) => (
            <li key={s.title} className="flex flex-col gap-2 border-t pt-4" style={{ borderColor: i === 0 ? "var(--accent)" : "var(--border)", borderTopWidth: 2 }}>
              <p className="faint num text-sm">{i + 1}</p>
              <h2 className="text-lg font-semibold">{s.title}</h2>
              <p className="muted">{s.text}</p>
              <Link href={s.href} className="link mt-auto pt-1 text-sm">
                {s.cta}
              </Link>
            </li>
          ))}
        </ol>
      </section>

      <div className="card grid gap-6 lg:grid-cols-3">
        {NOTES.map((n) => (
          <section key={n.id} aria-labelledby={n.id}>
            <h2 id={n.id} className="section-title">
              {n.title}
            </h2>
            <p className="muted">{n.text}</p>
          </section>
        ))}
      </div>
    </main>
  );
}
