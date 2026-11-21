"""Capture the README screenshots, the Overview scroll GIF and the Time Machine GIF from the live demo (or any base URL).

Uses the locally installed Chrome in headless mode for screenshots and Pillow to build the GIF.
Nothing is downloaded. Output: docs/media/*.png, docs/media/overview.gif and docs/media/time-machine.gif.

Run: python scripts/capture_media.py [base_url] [chrome_path]
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
OUT = Path("docs/media")

# Time Machine GIF: the demo store's holiday revenue drop (Dec 23 - Jan 8), from just before it
# starts until it is flagged and explained, two days per frame.
GIF_START, GIF_FRAMES, GIF_STEP = date(2025, 12, 21), 10, 2


def shot(url: str, path: Path, width: int, height: int, wait_ms: int = 6000) -> None:
    args = [CHROME, "--headless=new", "--hide-scrollbars", f"--window-size={width},{height}",
            f"--virtual-time-budget={wait_ms}", f"--screenshot={path.resolve()}"]
    with tempfile.TemporaryDirectory() as profile:  # fresh profile: first-visit state, default (dark) theme
        subprocess.run(args + [f"--user-data-dir={profile}", url], check=True, capture_output=True, timeout=120)


def phone_shot(url: str, path: Path, width: int = 390, height: int = 844) -> None:
    """Headless Chrome will not make a window narrower than about 500px, so the page is loaded
    in a phone-sized iframe inside a wider window and the iframe area is cropped out."""
    with tempfile.TemporaryDirectory() as tmp:
        frame = Path(tmp) / "phone.html"
        frame.write_text(f'<html><body style="margin:0;background:#080b07"><iframe src="{url}" '
                         f'style="border:0;width:{width}px;height:{height}px"></iframe></body></html>', encoding="utf-8")
        raw = Path(tmp) / "raw.png"
        shot(frame.as_uri(), raw, width + 200, height)
        Image.open(raw).crop((0, 0, width, height)).save(path)


def scroll_gif(url: str, path: Path, out_w: int = 880) -> None:
    """A screen-sized window scrolling down the whole page: a pause at each stop, eased steps between.
    The frames come from scripts/capture_scroll.mjs, which really scrolls the page in headless Chrome."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["node", str(Path(__file__).with_name("capture_scroll.mjs")), url, tmp, CHROME, "1280", "800", "5", "6"],
                       check=True, timeout=300)
        plan = json.loads((Path(tmp) / "frames.json").read_text())
        frames, durations = [], []
        for i, f in enumerate(plan):
            im = Image.open(Path(tmp) / f["file"]).convert("RGB")
            frames.append(im.resize((out_w, round(im.height * out_w / im.width)), Image.LANCZOS))
            durations.append((2800 if i == 0 else 2200) if f["hold"] else 60)
    # One shared palette keeps colours steady between frames and the file smaller.
    pal = frames[0].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    # Whole frames (no frame differencing): the delta encoding mixed up content between scroll positions.
    q[0].save(path, save_all=True, append_images=q[1:], duration=durations, loop=0, optimize=False, disposal=1)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    scroll_gif(f"{BASE}/", OUT / "overview.gif")
    phone_shot(f"{BASE}/", OUT / "overview-phone.png")
    shot(f"{BASE}/evaluation/", OUT / "evaluation.png", 1280, 1500)
    shot(f"{BASE}/about/", OUT / "how-it-works.png", 1280, 1000)

    frames = []
    with tempfile.TemporaryDirectory() as tmp:
        for k in range(GIF_FRAMES):
            day = (GIF_START + timedelta(days=k * GIF_STEP)).isoformat()
            p = Path(tmp) / f"{day}.png"
            shot(f"{BASE}/time-machine/?day={day}", p, 1280, 1300, wait_ms=8000)
            im = Image.open(p).convert("RGB")
            im = im.crop((0, 0, im.width, 1150)).resize((960, int(1150 * 960 / im.width)), Image.LANCZOS)
            frames.append(im.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    frames[0].save(OUT / "time-machine.gif", save_all=True, append_images=frames[1:], duration=900, loop=0, optimize=True)
    for f in sorted(OUT.iterdir()):
        print(f, f"{f.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
