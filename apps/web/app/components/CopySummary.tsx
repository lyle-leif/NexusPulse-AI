"use client";

import { useState } from "react";
import Icon from "./Icons";

/** Copies a plain-text summary of an issue (for Slack or email). Falls back to a hidden textarea. */
export default function CopySummary({ text }: { text: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      setState(ok ? "copied" : "failed");
    }
    setTimeout(() => setState("idle"), 2500);
  };
  return (
    <span className="inline-flex items-center gap-2">
      <button className="pill" onClick={copy} data-copy-text={text}>
        <Icon name="copy" size={14} />
        Copy summary
      </button>
      <span role="status" aria-live="polite" className="faint text-xs">
        {state === "copied" ? "Copied" : state === "failed" ? "Could not copy" : ""}
      </span>
    </span>
  );
}
