// Screenshots pages with local headless Chrome through the DevTools protocol (Node's built-in
// WebSocket; nothing downloaded). Driven by a JSON job file written by scripts/capture_media.py:
//   { "chrome": "...", "theme": "light" | "dark", "jobs": [
//       { "type": "shot", "url": "...", "width": 1280, "height": 800, "out": "a.png", "mobile": false, "ready": "<js expr>" },
//       { "type": "scroll", "url": "...", "width": 1280, "height": 800, "outDir": "dir", "stops": 5, "steps": 6, "ready": "<js expr>" } ] }
// A scroll job writes frame-000.png ... and frames.json ([{file, top, hold}]) into outDir.
// Usage: node scripts/capture.mjs <jobs.json>
import { spawn } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const spec = JSON.parse(readFileSync(process.argv[2], "utf-8"));
const port = 9300 + Math.floor(Math.random() * 500);
const profile = mkdtempSync(join(tmpdir(), "np-cap-"));
const proc = spawn(spec.chrome, ["--headless=new", "--hide-scrollbars", `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`, "--window-size=1280,800", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function pageSocket() {
  for (let i = 0; i < 50; i++) {
    try {
      const page = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((t) => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(200);
  }
  throw new Error("Chrome did not start");
}

const ws = new WebSocket(await pageSocket());
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

async function open(job) {
  await send("Emulation.setDeviceMetricsOverride", { width: job.width, height: job.height, deviceScaleFactor: 1, mobile: !!job.mobile });
  await send("Emulation.setTouchEmulationEnabled", { enabled: !!job.mobile });
  // Fresh first-visit state each time (intro banner shown), with the requested theme.
  await send("Storage.clearDataForOrigin", { origin: new URL(job.url).origin, storageTypes: "local_storage" }).catch(() => {});
  await send("Page.navigate", { url: job.url });
  const ready = job.ready || "true";
  for (let i = 0; i < 80; i++) {
    if (await evaluate(`document.readyState === 'complete' && !!(${ready})`).catch(() => false)) break;
    await sleep(250);
  }
  await evaluate("document.fonts.ready.then(() => true)");
  await sleep(1200); // let charts and transitions settle
}

const snap = async (file) => writeFileSync(file, Buffer.from((await send("Page.captureScreenshot", { format: "png" })).data, "base64"));

try {
  await send("Page.enable");
  await send("Runtime.enable");
  if (spec.theme === "light")
    await send("Page.addScriptToEvaluateOnNewDocument", { source: "try { localStorage.setItem('np-theme', 'light') } catch {}" });
  for (const job of spec.jobs) {
    await open(job);
    if (job.type === "shot") {
      await snap(job.out);
      console.log(`shot ${job.out}`);
      continue;
    }
    mkdirSync(job.outDir, { recursive: true });
    const total = await evaluate("document.documentElement.scrollHeight");
    const last = Math.max(0, total - job.height);
    const tops = Array.from({ length: job.stops }, (_, k) => Math.round((last * k) / (job.stops - 1)));
    const plan = [];
    tops.forEach((top, i) => {
      plan.push({ top, hold: true });
      if (i + 1 < tops.length)
        for (let s = 1; s < job.steps; s++) {
          const t = s / job.steps, ease = t * t * (3 - 2 * t);
          plan.push({ top: Math.round(top + (tops[i + 1] - top) * ease), hold: false });
        }
    });
    const frames = [];
    for (const [k, f] of plan.entries()) {
      await evaluate(`window.scrollTo(0, ${f.top}); new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))`);
      await sleep(f.hold ? 400 : 120);
      const file = `frame-${String(k).padStart(3, "0")}.png`;
      await snap(join(job.outDir, file));
      frames.push({ file, top: f.top, hold: f.hold });
    }
    writeFileSync(join(job.outDir, "frames.json"), JSON.stringify(frames));
    console.log(`scroll ${frames.length} frames, page height ${total}`);
  }
} finally {
  ws.close();
  proc.kill();
  await sleep(500);
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}
