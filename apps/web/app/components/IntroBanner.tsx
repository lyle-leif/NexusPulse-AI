"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Icon from "./Icons";

const KEY = "np-intro-seen";

/**
 * First-visit explainer for people opening the demo cold. Dismissal is remembered in this browser only.
 * It is in the server HTML so the page doesn't jump when it appears; for returning visitors the
 * inline script in the layout sets data-intro="seen" before first paint and CSS hides it.
 */
export default function IntroBanner() {
  const [show, setShow] = useState(true);
  useEffect(() => {
    try {
      if (localStorage.getItem(KEY) === "1") setShow(false);
    } catch {}
  }, []);
  if (!show) return null;
  const dismiss = () => {
    setShow(false);
    document.documentElement.dataset.intro = "seen";
    try {
      localStorage.setItem(KEY, "1");
    } catch {}
  };
  return (
    <aside className="intro-banner card bracket flex flex-wrap items-center justify-between gap-4" aria-label="About this demo">
      <div className="flex min-w-0 items-start gap-3">
        <span className="mt-0.5" style={{ color: "var(--accent)" }}>
          <Icon name="info" size={20} />
        </span>
        <p className="text-sm" style={{ maxWidth: "70ch" }}>
          <strong>NexusPulse watches an online store&apos;s daily numbers</strong>, flags changes that fall outside what it expected, and explains where they
          came from. This demo runs on a generated store with known answers, so you can check it.
        </p>
      </div>
      <div className="flex gap-2">
        <Link href="/about" className="pill" style={{ color: "var(--foreground)" }}>
          How it works
        </Link>
        <button className="pill" onClick={dismiss}>
          Dismiss
        </button>
      </div>
    </aside>
  );
}
