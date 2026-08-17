#!/usr/bin/env python3
"""Measure per-channel display statistics by sampling the plate.

Why this is not a one-liner:

1. The fluorescence channels are float32 on wildly different scales (green ~0-6,
   orange ~4-1200, NIR ~0-3 in an early well) — each needs its own range.
2. The orange background is a *per-well* offset (B04 sits at ~43, A04 at ~15) and
   the T-cell signal is the tail above it. A single absolute black point therefore
   leaves half the plate glowing. So we also measure the range *relative to each
   frame's median*, which is the background level; the viewer's default mode puts
   the black point at the frame median and takes the gain from here, so background
   drops out while brightness stays comparable between wells.
3. A MIP over 17 planes lifts the background well above a single plane's, so plane
   and MIP get separate statistics.
4. NIR is >99.9% background: any percentile over all pixels collapses onto the
   background value. Percentiles of above-background pixels are used as fallback.

Writes viewer/cache/channel_stats.json.

Usage: python viewer/scan_stats.py [--samples 300] [--mip-samples 40]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import tifffile

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("INC_DATA", HERE.parent / "data" / "inc_tests")).resolve()
CACHE = Path(os.environ.get("INC_CACHE", HERE / "cache"))
CHANNELS = ["bf", "green", "orange", "nir"]
STAMP_RE = re.compile(r"_(\d{4})y(\d{2})m(\d{2})d_(\d{2})h(\d{2})m")
PLANE_RE = re.compile(r"_plane(\d+)_\.tif$")
SUB = 40_000  # pixels kept per frame


SPARSE_FRAC = 0.05   # above-background share below which a channel counts as sparse


def robust_hi(pool: np.ndarray, lo: float, phi: float, hard_max: float) -> tuple[float, str]:
    """Upper display bound.

    For a dense channel (green, orange, brightfield) a high percentile over all
    pixels is right. For a sparse one it is not: only 0.36% of NIR's MIP pixels are
    above zero, so p99.5 of everything lands *inside* the background and the channel
    renders as a binary blob. There we scale to the above-background population
    instead — its p95 (~6.6 for NIR MIP) is the value that actually shows structure.
    """
    above = pool[pool > lo + 1e-9]
    frac = above.size / pool.size if pool.size else 0.0

    cands: list[tuple[str, float | None]] = []
    if 0 < frac < SPARSE_FRAC:
        cands.append((f"p_above95 (seyrek %{frac * 100:.2f})", float(np.percentile(above, 95.0))))
    cands.append(("p_all", float(np.percentile(pool, phi))))
    if above.size:
        cands.append(("p_above99", float(np.percentile(above, 99.0))))
        cands.append(("p_above99.9", float(np.percentile(above, 99.9))))
    cands.append(("max/5", hard_max / 5.0))

    for name, v in cands:
        if v is not None and v > lo + 1e-6:
            return v, name
    return lo + 1.0, "fallback"


def summarize(abs_pool: np.ndarray, rel_pool: np.ndarray, plo: float, phi: float,
              gmin: float, gmax: float) -> dict:
    lo = float(np.percentile(abs_pool, plo))
    hi, hi_src = robust_hi(abs_pool, lo, phi, gmax)

    off_lo = float(np.percentile(rel_pool, plo))
    off_hi, off_src = robust_hi(rel_pool, off_lo, phi, gmax)

    p9999 = float(np.percentile(abs_pool, 99.99))
    return {
        "lo": lo, "hi": hi, "hi_from": hi_src,
        "off_lo": off_lo, "off_hi": off_hi, "off_from": off_src,
        "slider_max": min(gmax, max(p9999, hi * 4.0)),
        "signal_frac": round(float((abs_pool > lo + 1e-9).sum()) / abs_pool.size, 5),
    }


def collect(files: list[Path]) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Pool subsampled pixels, and the same pixels minus each frame's median."""
    absv, relv = [], []
    gmin, gmax = np.inf, -np.inf
    for f in files:
        a = tifffile.imread(f).astype(np.float32, copy=False).reshape(-1)
        gmin = min(gmin, float(a.min()))
        gmax = max(gmax, float(a.max()))
        s = a[:: max(1, a.size // SUB)]
        absv.append(s)
        relv.append(s - float(np.median(s)))
    return np.concatenate(absv), np.concatenate(relv), gmin, gmax


def collect_mips(groups: list[list[Path]]) -> tuple[np.ndarray, np.ndarray, float, float]:
    absv, relv = [], []
    gmin, gmax = np.inf, -np.inf
    for planes in groups:
        mip = None
        for f in planes:
            a = tifffile.imread(f).astype(np.float32, copy=False)
            mip = a.copy() if mip is None else np.maximum(mip, a)
        m = mip.reshape(-1)
        gmin = min(gmin, float(m.min()))
        gmax = max(gmax, float(m.max()))
        s = m[:: max(1, m.size // SUB)]
        absv.append(s)
        relv.append(s - float(np.median(s)))
    return np.concatenate(absv), np.concatenate(relv), gmin, gmax


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=300, help="planes per channel")
    ap.add_argument("--mip-samples", type=int, default=40, help="z-stacks per channel")
    ap.add_argument("--plo", type=float, default=0.5)
    # MIP: 99.5, matched against Incucyte's own VID119 composite — a p99.9 white point
    # leaves the signal in the bottom of the range and looks washed out.
    # Single plane: 99.9, because a plane through a thick spheroid carries a lot of
    # out-of-focus haze, which drags the lower percentiles up and would otherwise
    # light up the whole field.
    ap.add_argument("--phi-mip", type=float, default=99.5, dest="phi_mip")
    ap.add_argument("--phi-plane", type=float, default=99.9, dest="phi_plane")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    wells_dir = DATA / "wells"
    wells = sorted(p.name for p in wells_dir.iterdir() if p.is_dir())
    out: dict[str, dict] = {}

    for ch in CHANNELS:
        files: list[Path] = []
        for w in wells:
            d = wells_dir / w / ch
            if d.is_dir():
                files.extend(f for f in d.iterdir() if f.suffix.lower() in (".tif", ".tiff"))
        if not files:
            continue

        # stratify by timepoint so late-appearing signal (NIR) is represented
        by_t: dict[str, list[Path]] = defaultdict(list)
        for f in files:
            mo = STAMP_RE.search(f.name)
            by_t[mo.group(0) if mo else "?"].append(f)
        per_t = max(1, args.samples // len(by_t))
        picked: list[Path] = []
        for _, group in sorted(by_t.items()):
            picked.extend(rng.sample(group, min(per_t, len(group))))

        t0 = time.time()
        a_pool, r_pool, gmin, gmax = collect(picked)
        entry = {"min": gmin, "max": gmax, "n_files": len(files),
                 "plo": args.plo, "phi_plane": args.phi_plane, "phi_mip": args.phi_mip,
                 "plane": {**summarize(a_pool, r_pool, args.plo, args.phi_plane, gmin, gmax),
                           "samples": len(picked)}}
        p = entry["plane"]
        print(f"{ch:7s} düzlem  n={len(picked):4d}  mutlak [{p['lo']:.4g}, {p['hi']:.4g}]"
              f" ({p['hi_from']})  medyana göre [{p['off_lo']:+.4g}, {p['off_hi']:+.4g}]"
              f" ({p['off_from']})  ({time.time() - t0:.1f}s)", flush=True)

        # --- MIP statistics, for channels that actually have a stack -------------
        stacks: dict[tuple[str, str], list[Path]] = defaultdict(list)
        for f in files:
            if PLANE_RE.search(f.name):
                mo = STAMP_RE.search(f.name)
                stacks[(f.parent.parent.name, mo.group(0) if mo else "?")].append(f)
        if stacks:
            groups = [sorted(stacks[k]) for k in
                      rng.sample(sorted(stacks), min(args.mip_samples, len(stacks)))]
            t0 = time.time()
            a2, r2, mn2, mx2 = collect_mips(groups)
            entry["mip"] = {**summarize(a2, r2, args.plo, args.phi_mip, mn2, mx2),
                            "samples": len(groups), "min": mn2, "max": mx2}
            m = entry["mip"]
            print(f"{ch:7s} MIP     n={len(groups):4d}  mutlak [{m['lo']:.4g}, {m['hi']:.4g}]"
                  f" ({m['hi_from']})  medyana göre [{m['off_lo']:+.4g}, {m['off_hi']:+.4g}]"
                  f" ({m['off_from']})  ({time.time() - t0:.1f}s)", flush=True)
        out[ch] = entry

    CACHE.mkdir(parents=True, exist_ok=True)
    dst = CACHE / "channel_stats.json"
    dst.write_text(json.dumps(out, indent=2))
    print(f"\nyazıldı: {dst}")


if __name__ == "__main__":
    main()
