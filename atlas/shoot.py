#!/usr/bin/env python3
"""Headless screenshots of the generated pages, and animated GIFs of the viewer.

Written because a figure that has never been looked at is not finished. Chrome
renders WebGL in software here (SwiftShader), so the 3D scene comes out of a
headless run exactly as it does on screen.

    python3 atlas/shoot.py B04.html                    # one screenshot
    python3 atlas/shoot.py B04.html --scroll 1200      # further down the page
    python3 atlas/shoot.py B04.html --gif slice        # layer-by-layer animation
    python3 atlas/shoot.py B04.html --gif orbit        # rotation animation
    python3 atlas/shoot.py check/B04.html --gif zscan  # photo + 3D side by side

GIFs land in docs/ and are what the README shows.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE / "site"
DOCS = HERE.parent / "docs"

CHROME = shutil.which("google-chrome") or shutil.which("google-chrome-stable") \
    or shutil.which("chromium")

BASE = ["--headless=new", "--disable-gpu", "--enable-unsafe-swiftshader",
        "--no-sandbox", "--hide-scrollbars", "--force-device-scale-factor=1",
        "--disable-lcd-text", "--allow-file-access-from-files"]


def shot(page: Path, out: Path, width: int = 1400, height: int = 1400,
         wait_ms: int = 12000, script: str | None = None) -> Path:
    """One screenshot. `script` is JavaScript run before the shot is taken."""
    out.parent.mkdir(parents=True, exist_ok=True)
    url = page.resolve().as_uri()
    if script:
        # Chrome has no --evaluate flag, so the instruction travels in the URL
        # fragment and a small hook inside the page runs it.
        from urllib.parse import quote
        url += "#shoot=" + quote(script, safe="")
    cmd = [CHROME, *BASE, f"--window-size={width},{height}",
           f"--virtual-time-budget={wait_ms}", f"--screenshot={out}", url]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not out.is_file():
        raise SystemExit(f"screenshot failed:\n{r.stderr[-1500:]}")
    return out


def frames_gif(page: Path, out: Path, states: list[str], width: int, height: int,
               duration: int = 320, wait_ms: int = 9000,
               crop: tuple[int, int, int, int] | None = None) -> Path:
    """Render one screenshot per state and write them out as an animated GIF.

    `crop` keeps only the part of the page worth animating — a README animation
    of a whole page is mostly unchanging text, which both wastes bytes and hides
    the thing that actually moves."""
    from PIL import Image

    tmp = Path(tempfile.mkdtemp())
    imgs = []
    for i, st in enumerate(states):
        p = shot(page, tmp / f"f{i:03d}.png", width, height, wait_ms, st)
        im = Image.open(p).convert("RGB")
        imgs.append(im.crop(crop) if crop else im)
        print(f"  frame {i + 1}/{len(states)}", flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    # A 256-colour adaptive palette keeps the dark scene from banding.
    pal = [im.convert("P", palette=Image.ADAPTIVE, colors=200) for im in imgs]
    pal[0].save(out, save_all=True, append_images=pal[1:], duration=duration,
                loop=0, optimize=True, disposal=2)
    for im in imgs:
        im.close()
    shutil.rmtree(tmp, ignore_errors=True)
    return out


# ------------------------------------------------------------------ recipes
def gif_slice(page: Path, out: Path) -> Path:
    """Build the stack layer by layer, then hold on the full stack."""
    states = []
    for z in range(17):
        states.append(f"SHOOT.slice('up',{z})")
    states += ["SHOOT.slice('up',16)"] * 3
    return frames_gif(page, out, states, 1180, 900, duration=260,
                      crop=(20, 258, 1160, 770))


def gif_orbit(page: Path, out: Path) -> Path:
    """One full turn of the reconstruction."""
    states = [f"SHOOT.view({a},22)" for a in range(-180, 180, 18)]
    return frames_gif(page, out, states, 1180, 900, duration=170,
                      crop=(20, 300, 1160, 760))


def gif_zscan(page: Path, out: Path) -> Path:
    """The check page: photograph and reconstruction stepping through z together."""
    states = [f"SHOOT.z({z})" for z in range(17)] + ["SHOOT.z(16)"] * 2
    return frames_gif(page, out, states, 1340, 1150, duration=300,
                      crop=(110, 330, 1270, 1092))


def gif_overlay(page: Path, out: Path) -> Path:
    """Sweep the photograph over the reconstruction and back.

    This is the registration proof: if the voxels were displaced relative to the
    stain, the sweep would show two offset copies of the same pattern instead of
    one that fades in place."""
    up = list(range(0, 101, 10))
    states = [f"SHOOT.z(9);SHOOT.overlay(true,{m})" for m in up + up[::-1][1:]]
    return frames_gif(page, out, states, 1100, 1300, duration=200,
                      crop=(300, 380, 860, 940))


RECIPES = {"slice": gif_slice, "orbit": gif_orbit, "zscan": gif_zscan,
           "overlay": gif_overlay}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("page", help="path under atlas/site, e.g. B04.html")
    ap.add_argument("-o", "--out")
    ap.add_argument("--width", type=int, default=1400)
    ap.add_argument("--height", type=int, default=1400)
    ap.add_argument("--scroll", type=int, default=0, help="scroll down before shooting")
    ap.add_argument("--gif", choices=sorted(RECIPES))
    ap.add_argument("--wait", type=int, default=12000)
    args = ap.parse_args()

    if CHROME is None:
        raise SystemExit("no Chrome/Chromium on PATH")
    page = SITE / args.page
    if not page.is_file():
        raise SystemExit(f"{page} does not exist")

    if args.gif:
        out = Path(args.out) if args.out else DOCS / f"{args.gif}.gif"
        RECIPES[args.gif](page, out)
        print(f"{out}  {out.stat().st_size / 1e6:.2f} MB")
        return

    out = Path(args.out) if args.out else Path(tempfile.gettempdir()) / "shot.png"
    js = f"window.scrollTo(0,{args.scroll})" if args.scroll else None
    shot(page, out, args.width, args.height, args.wait, js)
    print(out)


if __name__ == "__main__":
    main()
