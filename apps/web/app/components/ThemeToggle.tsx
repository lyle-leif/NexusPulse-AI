"use client";

import { useEffect, useState } from "react";
import Icon from "./Icons";

/** Dark by default; light on request. The choice is remembered on this device only. */
export default function ThemeToggle() {
  const [light, setLight] = useState(false);
  useEffect(() => setLight(document.documentElement.dataset.theme === "light"), []);
  const flip = () => {
    const next = !light;
    setLight(next);
    if (next) document.documentElement.dataset.theme = "light";
    else delete document.documentElement.dataset.theme;
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
