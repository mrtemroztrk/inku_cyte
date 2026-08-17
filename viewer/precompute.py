#!/usr/bin/env python3
"""Warm the viewer's disk cache so first clicks are instant.

Two independent jobs:

  thumbs  plate-overview tiles (fast for --mode bf, slow for composite/MIP modes)
  series  per-well per-channel time courses (reads z-stacks; this is the slow one)

Both write under viewer/cache/ and are safe to interrupt — already-cached entries
are skipped, so re-running resumes.

  python viewer/precompute.py thumbs --mode bf
  python viewer/precompute.py thumbs --mode composite
  python viewer/precompute.py series --wells A01,A02,B01
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app as viewer  # noqa: E402  — sibling module, path set just above


def fmt_eta(done: int, total: int, t0: float) -> str:
    if not done:
        return "?"
    per = (time.time() - t0) / done
    left = per * (total - done)
    return f"{left / 60:.1f} dk" if left > 90 else f"{left:.0f} s"


def do_thumbs(args):
    idx = viewer.IDX
    wells = args.wells or idx.wells
    jobs = [(w, tp["index"]) for w in wells for tp in idx.tp]
    outdir = viewer.CACHE / "thumbs" / f"{args.mode}_{args.size}"
    outdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    made = skipped = 0
    for n, (w, t) in enumerate(jobs, 1):
        cf = outdir / f"{w}_t{t:02d}.jpg"
        if cf.is_file() and not args.force:
            skipped += 1
            continue
        im = viewer.render_thumb(w, t, args.mode, args.size)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82)
        cf.write_bytes(buf.getvalue())
        made += 1
        if made % 20 == 0:
            print(f"  {n}/{len(jobs)}  üretilen {made}  kalan ~{fmt_eta(n, len(jobs), t0)}",
                  flush=True)
    print(f"thumbs[{args.mode}]: {made} üretildi, {skipped} zaten vardı → {outdir}")


def do_series(args):
    idx = viewer.IDX
    wells = args.wells or idx.wells
    outdir = viewer.CACHE / "series"
    outdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    made = skipped = 0
    for n, w in enumerate(wells, 1):
        cf = outdir / f"{w}_s{args.stride}.json"
        if cf.is_file() and not args.force:
            skipped += 1
            continue
        res = viewer.wellseries(w, stride=args.stride)
        cf.write_bytes(json.dumps(json.loads(res.body)).encode())
        made += 1
        print(f"  {n}/{len(wells)}  {w}  kalan ~{fmt_eta(n, len(wells), t0)}", flush=True)
    print(f"series: {made} üretildi, {skipped} zaten vardı → {outdir}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="job", required=True)

    t = sub.add_parser("thumbs", help="plaka önizleme küçük resimleri")
    t.add_argument("--mode", default="bf",
                   choices=["bf", "green", "orange", "nir", "composite"])
    t.add_argument("--size", type=int, default=150)

    s = sub.add_parser("series", help="kuyu başına zaman serisi")
    s.add_argument("--stride", type=int, default=2, help="her N'inci z düzlemi")

    for p in (t, s):
        p.add_argument("--wells", type=lambda v: [x.strip() for x in v.split(",")],
                       default=None, help="virgülle: A01,B02 (varsayılan: hepsi)")
        p.add_argument("--force", action="store_true", help="var olanı da yeniden üret")

    args = ap.parse_args()

    # app.py builds its index in the FastAPI lifespan hook; do it by hand here.
    viewer.IDX = viewer.Index(viewer.DATA)
    viewer.CACHE.mkdir(parents=True, exist_ok=True)
    print(f"{viewer.DATA}: {len(viewer.IDX.wells)} kuyu, {len(viewer.IDX.tp)} zaman noktası")

    if args.wells:
        unknown = [w for w in args.wells if w not in viewer.IDX.wells]
        if unknown:
            sys.exit(f"bilinmeyen kuyu: {unknown}")

    (do_thumbs if args.job == "thumbs" else do_series)(args)


if __name__ == "__main__":
    main()
