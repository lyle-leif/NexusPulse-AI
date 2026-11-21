"""Capture the README screenshots, the Overview scroll GIF and the Time Machine GIF from the live demo (or any base URL).

Pages are captured in the light theme by local headless Chrome through scripts/capture.mjs (Node's built-in
DevTools client); Pillow builds the GIFs. Nothing is downloaded.
Output: docs/media/overview.gif, time-machine.gif, evaluation.png, how-it-works.png, overview-phone.png.

Run: python scripts/capture_media.py [base_url] [chrome_path] [theme]
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from PIL import Image

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://lyle-leif.github.io/NexusPulse-AI").rstrip("/")
CHROME = sys.argv[2] if len(sys.argv) > 2 else r"C:\Program Files\Google\Chrome\Application\chrome.exe"
THEME = sys.argv[3] if len(sys.argv) > 3 else "light"
OUT = Path("docs/media")

# Time Machine GIF: the demo store's holiday revenue drop (Dec 23 - Jan 8), from just before it
# starts until it is flagged and explained, two days per frame.
GIF_START, GIF_FRAMES, GIF_STEP = date(2025, 12, 21), 10, 2

# Ready when the page's data has rendered (not just the loading skeleton).
OVERVIEW_READY = "document.body.innerText.includes('NET REVENUE') || document.body.innerText.includes('Net revenue')"
TM_READY = "!document.querySelector('[aria-busy=\"true\"]') && document.body.innerText.toLowerCase().includes('viewing the store as of')"


def run_jobs(jobs: list[dict]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        spec = Path(tmp) / "jobs.json"
        spec.write_text(json.dumps({"chrome": CHROME, "theme": THEME, "jobs": jobs}), encoding="utf-8")
        subprocess.run(["node", str(Path(__file__).with_name("capture.mjs")), str(spec)], check=True, timeout=900)


def save_gif(frames: list[Image.Image], durations: list[int] | int, path: Path) -> None:
    # One shared palette keeps colours steady between frames. Whole frames are stored (no frame
    # differencing), which avoids content from one frame leaking into the next.
    pal = frames[0].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    q[0].save(path, save_all=True, append_images=q[1:], duration=durations, loop=0, optimize=False, disposal=1)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        days = [(GIF_START + timedelta(days=k * GIF_STEP)).isoformat() for k in range(GIF_FRAMES)]
        run_jobs(
            [{"type": "scroll", "url": f"{BASE}/", "width": 1280, "height": 800, "outDir": str(t / "scroll"), "stops": 5, "steps": 6,
              "ready": OVERVIEW_READY},
             {"type": "shot", "url": f"{BASE}/", "width": 390, "height": 844, "mobile": True, "out": str(OUT / "overview-phone.png"),
              "ready": OVERVIEW_READY},
             {"type": "shot", "url": f"{BASE}/evaluation/", "width": 1280, "height": 1500, "out": str(OUT / "evaluation.png")},
             {"type": "shot", "url": f"{BASE}/about/", "width": 1280, "height": 1000, "out": str(OUT / "how-it-works.png")}]
            + [{"type": "shot", "url": f"{BASE}/time-machine/?day={d}", "width": 1280, "height": 1150, "out": str(t / f"tm-{d}.png"),
                "ready": TM_READY} for d in days])

        plan = json.loads((t / "scroll" / "frames.json").read_text())
        frames = [Image.open(t / "scroll" / f["file"]).convert("RGB").resize((880, 550), Image.LANCZOS) for f in plan]
        save_gif(frames, [(2800 if i == 0 else 2200) if f["hold"] else 60 for i, f in enumerate(plan)], OUT / "overview.gif")

        tm = [Image.open(t / f"tm-{d}.png").convert("RGB").resize((960, 862), Image.LANCZOS) for d in days]
        save_gif(tm, 900, OUT / "time-machine.gif")
    for f in sorted(OUT.iterdir()):
        print(f, f"{f.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
