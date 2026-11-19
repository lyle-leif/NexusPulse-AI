import Link from "next/link";

export default function Nav({ active }: { active: "overview" | "evaluation" }) {
  const items = [
    { href: "/", key: "overview", label: "Overview" },
    { href: "/evaluation", key: "evaluation", label: "Evaluation" },
  ] as const;
  return (
    <nav aria-label="Main" className="flex gap-1 text-sm">
      {items.map((i) => (
        <Link key={i.key} href={i.href} className={i.key === active ? "nav-link active" : "nav-link"} aria-current={i.key === active ? "page" : undefined}>
          {i.label}
        </Link>
      ))}
    </nav>
  );
}
