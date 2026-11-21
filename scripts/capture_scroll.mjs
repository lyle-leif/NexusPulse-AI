// Screenshots a page at a series of scroll positions in a normal-sized window, using local
// headless Chrome through the DevTools protocol (Node's built-in WebSocket; nothing downloaded).
// Usage: node scripts/capture_scroll.mjs <url> <out_dir> <chrome_path> [width] [height] [stops] [steps]
// Writes frame-000.png ... and frames.json ([{file, top, hold}]).
import { spawn } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [url, outDir, chrome, W = "1280", H = "800", STOPS = "5", STEPS = "6"] = process.argv.slice(2);
const width = +W, height = +H, stops = +STOPS, steps = +STEPS;
const port = 9300 + Math.floor(Math.random() * 500);
const profile = mkdtempSync(join(tmpdir(), "np-cap-"));
mkdirSync(outDir, { recursive: true });

const proc = spawn(chrome, [
  "--headless=new", "--hide-scrollbars", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  `--window-size=${width},${height}`, "about:blank",
], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function target() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(200);
  }
  throw new Error("Chrome did not start");
}

const ws = new WebSocket(await target());
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let id = 0;
const pending = new Map();
ws.addEventListener("message", (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
});
const send = (method, params = {}) => new Promise((res, rej) => {
  const n = ++id;
  pending.set(n, (m) => (m.error ? rej(new Error(`${method}: ${m.error.message}`)) : res(m.result)));
  ws.send(JSON.stringify({ id: n, method, params }));
});
const evaluate = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result.value;

try {
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
  await send("Page.navigate", { url });
  // Wait for the page's data to render: the Overview shows its numbers once loaded.
  for (let i = 0; i < 60 && !(await evaluate("document.readyState === 'complete' && document.body.innerText.includes('$')")); i++) await sleep(500);
  await sleep(2500);
  const total = await evaluate("document.documentElement.scrollHeight");
  const last = Math.max(0, total - height);
  const tops = Array.from({ length: stops }, (_, k) => Math.round((last * k) / (stops - 1)));
  const plan = [];
  tops.forEach((top, i) => {
    plan.push({ top, hold: true });
    if (i + 1 < tops.length)
      for (let s = 1; s < steps; s++) {
        const t = s / steps, ease = t * t * (3 - 2 * t);
        plan.push({ top: Math.round(top + (tops[i + 1] - top) * ease), hold: false });
      }
  });
  const frames = [];
  for (const [k, f] of plan.entries()) {
    await evaluate(`window.scrollTo(0, ${f.top}); new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))`);
    await sleep(f.hold ? 400 : 120);
    const { data } = await send("Page.captureScreenshot", { format: "png" });
    const file = `frame-${String(k).padStart(3, "0")}.png`;
    writeFileSync(join(outDir, file), Buffer.from(data, "base64"));
    frames.push({ file, top: f.top, hold: f.hold });
  }
  writeFileSync(join(outDir, "frames.json"), JSON.stringify(frames));
  console.log(`${frames.length} frames, page height ${total}`);
} finally {
  ws.close();
  proc.kill();
  await sleep(500);
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}
