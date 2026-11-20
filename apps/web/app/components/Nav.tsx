import Link from "next/link";
import ThemeToggle from "./ThemeToggle";

type Key = "overview" | "time-machine" | "evaluation";

export default function Nav({ active }: { active: Key }) {
  const items = [
    { href: "/", key: "overview", label: "Overview" },
    { href: "/time-machine", key: "time-machine", label: "Time Machine" },
    { href: "/evaluation", key: "evaluation", label: "How accurate is it" },
  ] as const;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-3" style={{ borderColor: "var(--border)" }}>
      <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
        <span aria-hidden className="inline-block h-3 w-3 rounded-sm" style={{ background: "var(--accent)" }} />
        NexusPulse
      </Link>
      <nav aria-label="Main" className="flex flex-wrap items-center gap-1">
        {items.map((i) => (
          <Link key={i.key} href={i.href} className={i.key === active ? "nav-link active" : "nav-link"} aria-current={i.key === active ? "page" : undefined}>
            {i.label}
          </Link>
        ))}
        <ThemeToggle />
      </nav>
    </div>
  );
}
