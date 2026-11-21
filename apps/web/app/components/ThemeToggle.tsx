"use client";

import { setRootData, useRootData } from "@/lib/rootData";
import Icon from "./Icons";

/** Dark by default; light on request. The choice is remembered on this device only. */
export default function ThemeToggle() {
  const light = useRootData(() => document.documentElement.dataset.theme === "light", false);
  const flip = () => {
    const next = !light;
    setRootData("theme", next ? "light" : undefined);
    try {
      localStorage.setItem("np-theme", next ? "light" : "dark");
    } catch {}
  };
  const label = light ? "Switch to dark theme" : "Switch to light theme";
  return (
    <button className="icon-btn" onClick={flip} aria-label={label} title={label}>
      <Icon name={light ? "moon" : "sun"} size={18} />
    </button>
  );
}
