import Link from "next/link";
import Icon, { type IconName } from "./Icons";
import Logo from "./Logo";
import ThemeToggle from "./ThemeToggle";

type Key = "overview" | "time-machine" | "evaluation" | "about";

const ITEMS: { href: string; key: Key; label: string; short: string; icon: IconName }[] = [
  { href: "/", key: "overview", label: "Overview", short: "Overview", icon: "home" },
  { href: "/time-machine", key: "time-machine", label: "Time Machine", short: "Replay", icon: "clock" },
  { href: "/evaluation", key: "evaluation", label: "How accurate is it", short: "Accuracy", icon: "target" },
  { href: "/about", key: "about", label: "How it works", short: "About", icon: "info" },
];

/** Glass top bar; on phones the links move to a fixed bottom bar. */
export default function Nav({ active }: { active: Key }) {
  return (
    <>
      <div className="card nav-bar">
        <Link href="/" aria-label="NexusPulse home">
          <Logo />
        </Link>
        <nav aria-label="Main" className="nav-seg">
          {ITEMS.map((i) => (
            <Link key={i.key} href={i.href} className={i.key === active ? "nav-link active" : "nav-link"} aria-current={i.key === active ? "page" : undefined}>
              {i.label}
            </Link>
          ))}
        </nav>
        <ThemeToggle />
      </div>
      <nav aria-label="Main" className="card bottom-nav">
        {ITEMS.map((i) => (
          <Link key={i.key} href={i.href} aria-current={i.key === active ? "page" : undefined}>
            <Icon name={i.icon} size={20} />
            {i.short}
          </Link>
        ))}
      </nav>
    </>
  );
}
