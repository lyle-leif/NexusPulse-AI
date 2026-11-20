"use client";

import { useEffect, useState } from "react";

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
  return (
    <button className="nav-link" onClick={flip} aria-pressed={light} title="Switch light or dark theme">
      {light ? "Dark" : "Light"}
    </button>
  );
}
