#!/usr/bin/env python3
"""Every animation the README shows, produced from the real pages.

A README that describes an interface persuades nobody; a README that shows it
working is the interface's own evidence. Each recipe here drives the actual page
through `atlas/shoot.py` and records what happens, so an animation cannot drift
away from what the code does — if a feature breaks, its animation breaks with it.

    python3 atlas/gifs.py            # all of them, ~15 min
    python3 atlas/gifs.py overlay-rotate stack
    python3 atlas/gifs.py --list
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import shoot                                              # noqa: E402

SITE = HERE / "site"
DOCS = HERE.parent / "docs"
WELL = "B04.html"
CHECK = "check/B04.html"


def _run(page, states, crop, size=(1320, 1200), duration=240, max_w=720):
    return lambda out: shoot.frames_gif(SITE / page, out, states, size[0], size[1],
                                        duration=duration, crop=crop, max_w=max_w)


# Every entry: (page, description, builder). The description is what the README
# says next to the animation, so the two cannot disagree.
def build_recipes() -> dict:
    R = {}

    # ---- plate ------------------------------------------------------------
    R["plate"] = ("index.html",
                  "The plate, recoloured by each available measure.",
                  _run("index.html",
                       [f"SHOOT.metric('{m}')" for m in
                        ["tcells", "tcell_peak_z", "organoid_mm2", "growth",
                         "dead_mm2", "tcells"]],
                       crop=(120, 250, 1200, 900), size=(1320, 1000), duration=900))

    # ---- well page: 3D --------------------------------------------------
    R["slice"] = (WELL,
                  "Building the stack one z layer at a time. The line under the "
                  "scene reports how much of each channel the visible slab holds.",
                  _run(WELL, [f"SHOOT.slice('up',{z})" for z in range(17)],
                       crop=(20, 353, 1160, 885), size=(1180, 1000), duration=260))

    R["peel"] = (WELL,
                 "The same stack peeled from the top down.",
                 _run(WELL, [f"SHOOT.slice('down',{z})" for z in range(16, -1, -1)],
                      crop=(20, 353, 1160, 885), size=(1180, 1000), duration=260))

    R["single-layer"] = (WELL,
                         "Stepping through the stack one layer at a time.",
                         _run(WELL, [f"SHOOT.slice('one',{z})" for z in range(17)],
                              crop=(20, 353, 1160, 885), size=(1180, 1000),
                              duration=300))

    R["orbit"] = (WELL,
                  "One full turn of the reconstruction. Parallel projection, so "
                  "equal sizes stay equal wherever they sit on screen.",
                  _run(WELL, [f"SHOOT.view({a},22)" for a in range(-180, 180, 18)],
                       crop=(20, 395, 1160, 885), size=(1180, 1000), duration=170))

    R["views"] = (WELL,
                  "The camera presets: oblique, top, front, right, bottom — the "
                  "same keys Blender puts on the numpad.",
                  _run(WELL, [f"SHOOT.view('{v}')" for v in
                              ["home", "top", "front", "right", "bottom", "home"]],
                       crop=(20, 353, 1160, 885), size=(1180, 1000), duration=850))

    R["channels"] = (WELL,
                     "Channels switched on one at a time: organoid footprint, "
                     "tumour, T cells, dead cells.",
                     _run(WELL,
                          ["SHOOT.channel('green',false);SHOOT.channel('orange',false);"
                           "SHOOT.channel('nir',false);SHOOT.channel('terr',true)",
                           "SHOOT.channel('green',true)",
                           "SHOOT.channel('orange',true)",
                           "SHOOT.channel('nir',true)",
                           "SHOOT.channel('terr',false)",
                           "SHOOT.channel('terr',true)"],
                          crop=(20, 353, 1160, 925), size=(1180, 1000), duration=900))

    R["time"] = (WELL,
                 "Four days in one well. The numbers on the right and the figures "
                 "below follow the slider.",
                 _run(WELL, [f"SHOOT.time({t})" for t in range(13)],
                      crop=(20, 353, 1320, 925), size=(1400, 1000), duration=420))

    R["proof"] = (WELL,
                  "Clicking a bar in the depth figure isolates that layer in 3D "
                  "and puts the photograph of it on the page.",
                  _run(WELL, [f"SHOOT.clickLayer({z})" for z in
                              [12, 10, 8, 6, 4, 3, 4, 6, 8, 10]],
                       crop=(20, 353, 1160, 995), size=(1180, 1100), duration=650))

    # ---- check page ------------------------------------------------------
    R["zscan"] = (CHECK,
                  "The raw plane on the left with the measured mask outlined, the "
                  "same layer in 3D on the right, moving together through z.",
                  _run(CHECK, [f"SHOOT.z({z})" for z in range(17)],
                       crop=(100, 250, 1250, 1135), size=(1340, 1150), duration=300))

    R["overlay-sweep"] = (CHECK,
                          "The registration check: the photograph fades over the "
                          "reconstruction. The voxels fade in place rather than "
                          "sliding across the stain.",
                          _run(CHECK,
                               [f"SHOOT.stack('one');SHOOT.z(9);SHOOT.view('top');"
                                f"SHOOT.overlay(true,{m})" for m in range(0, 101, 10)],
                               crop=(280, 394, 1060, 1425), size=(1320, 1460),
                               duration=260, max_w=560))

    R["overlay-rotate"] = (CHECK,
                           "The photograph is a plane inside the scene at the z "
                           "height of its own layer, so the camera is free: the "
                           "voxels stand on the stain from every angle.",
                           _run(CHECK,
                                ["SHOOT.stack('one');SHOOT.z(9);SHOOT.overlay(true,70)"]
                                + [f"SHOOT.view({a},{max(6, 60 - abs(a) // 4)})"
                                   for a in range(-150, 151, 20)],
                                crop=(280, 394, 1060, 1425), size=(1320, 1460),
                                duration=220, max_w=620))

    R["stack"] = (CHECK,
                  "Single layer, z00 → layer, layer → z16 — the photograph "
                  "switches to a maximum projection of the same planes, so both "
                  "sides always show the same accumulation.",
                  _run(CHECK,
                       [f"SHOOT.stack('{m}');SHOOT.z({z});SHOOT.overlay(false)"
                        for m in ("one", "up", "down") for z in (3, 6, 9, 12)],
                       crop=(100, 250, 1250, 1135), size=(1340, 1150), duration=650))

    # ---- group page ------------------------------------------------------
    R["figures"] = ("groups.html",
                    "The manuscript figures: every well a point, medians with "
                    "bootstrap intervals, tests corrected across each figure.",
                    _run("groups.html", [f"SHOOT.scroll({y})" for y in
                                         (300, 1100, 1900, 2700, 3500, 4300)],
                         crop=(100, 0, 1250, 1000), size=(1360, 1000), duration=1100))

    return R


def main() -> None:
    R = build_recipes()
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="which animations (default: all)")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for k, (page, desc, _) in R.items():
            print(f"  {k:16s} {page:16s} {desc}")
        return

    names = args.names or list(R)
    DOCS.mkdir(exist_ok=True)
    t0 = time.time()
    for i, n in enumerate(names, 1):
        if n not in R:
            print(f"  ✗ {n}: unknown; try --list")
            continue
        page, desc, build = R[n]
        out = DOCS / f"{n}.gif"
        print(f"[{i}/{len(names)}] {n} ← {page}", flush=True)
        try:
            build(out)
            print(f"      {out.name}  {out.stat().st_size / 1e6:.2f} MB", flush=True)
        except SystemExit as exc:
            print(f"      ✗ {exc}", flush=True)
    print(f"\n{(time.time() - t0) / 60:.1f} dk  ·  {DOCS}")


if __name__ == "__main__":
    main()
