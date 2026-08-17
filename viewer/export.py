#!/usr/bin/env python3
"""Export display-ready images from the float32 originals.

Why this exists: green/orange/NIR are float32 with tiny numeric ranges (green sits
at 0–5 with a thin tail to ~300). A generic image viewer treats float TIFF as
0–255 grey, so 99% of the picture lands on grey level 0-2 and the file looks
black — the data is fine, the scaling isn't. This writes 8-bit PNG/TIFF using the
same scaling the viewer uses, so the files open anywhere.

Examples
--------
  # one well, last timepoint, MIP, RGB composite of all channels
  python3 viewer/export.py B04 --t 12 --mip --composite

  # every timepoint of two wells, channels as separate 8-bit greyscale PNGs
  python3 viewer/export.py A04 B04 --t all --mip --separate

  # a single z-plane as 8-bit TIFF for ImageJ/QuPath
  python3 viewer/export.py B04 --t 12 --z 8 --separate --format tif

  # whole plate, one composite per well at the last timepoint
  python3 viewer/export.py --all --t 12 --mip --composite -o export/plate_t12
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app as viewer  # noqa: E402  — sibling module, path set just above

# Same colours as the viewer's defaults.
COLORS = {"bf": (255, 255, 255), "green": (61, 220, 80),
          "orange": (255, 138, 43), "nir": (255, 59, 107)}


def scaled_u8(well: str, ch: str, t: int, z: int, mip: bool,
              mode: str, bright: float, gamma: float) -> np.ndarray:
    """Same window the viewer would use. `bright` > 1 narrows it, as in the UI."""
    a = viewer.get_frame(well, ch, t, z, mip)
    s = viewer.stat_for(ch, mip)
    if mode == "default":
        lo, hi = viewer.display_range(a, ch, mip, bright)
    elif mode == "rel" and s:
        m = viewer.frame_median(a)
        lo, hi = m + s["off_lo"], m + s["off_hi"] / max(bright, 1e-3)
    elif mode == "abs" and s:
        lo, hi = s["lo"], s["lo"] + (s["hi"] - s["lo"]) / max(bright, 1e-3)
    else:
        lo, hi = viewer.percentiles(a, 1.0, 99.8)
    return viewer.to_u8(a, lo, hi, gamma)


def composite_rgb(well: str, t: int, z: int, mip: bool, chans: list[str],
                  mode: str, bright: float, gamma: float, bf_opacity: float) -> Image.Image:
    """Brightfield as the base, fluorescence added on top — as the viewer draws it."""
    out = None
    for ch in chans:
        u8 = scaled_u8(well, ch, t, z, mip and viewer.IDX.nz.get(ch, 1) > 1,
                       mode, 1.0 if ch == "bf" else bright, gamma)
        g = u8.astype(np.float32) / 255.0
        tint = np.stack([g * c for c in COLORS.get(ch, (255, 255, 255))], axis=-1)
        if ch == "bf":
            out = tint * bf_opacity
        else:
            out = tint if out is None else out + tint
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def save(im: Image.Image, path: Path, scale: float):
    if scale != 1.0:
        im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))),
                       Image.LANCZOS)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)


def main():
    ap = argparse.ArgumentParser(
        description="float32 orijinallerden her yerde açılabilir 8-bit görüntü üretir",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("wells", nargs="*", help="A04 B04 … (boşsa --all gerekir)")
    ap.add_argument("--all", action="store_true", help="tüm kuyular")
    ap.add_argument("--t", default="all", help="zaman noktası: 12, 0-4, 0,6,12 veya all")
    ap.add_argument("--z", type=int, default=8, help="z düzlemi (--mip yoksa)")
    ap.add_argument("--mip", action="store_true", help="z boyunca maksimum projeksiyon")
    ap.add_argument("--channels", default="bf,green,orange,nir")
    ap.add_argument("--composite", action="store_true", help="tek RGB overlay yaz")
    ap.add_argument("--separate", action="store_true", help="kanal başına gri görüntü yaz")
    ap.add_argument("--format", default="png", choices=["png", "tif"])
    ap.add_argument("--mode", default="default", choices=["default", "rel", "abs", "auto"],
                    help="default: uygulamadaki varsayılan pencere (BF için Incucyte aralığı)")
    ap.add_argument("--bright", type=float, default=1.0,
                    help=">1 daha parlak (pencereyi daraltır), uygulamadaki kaydırıcı gibi")
    ap.add_argument("--gamma", type=float, default=1.0)
    ap.add_argument("--bf-opacity", type=float, default=1.0,
                    help="kompozitte brightfield tabanının ağırlığı")
    ap.add_argument("--scale", type=float, default=1.0, help="0.5 = yarı boyut")
    ap.add_argument("-o", "--out", default="export", help="çıktı dizini")
    args = ap.parse_args()

    if not args.composite and not args.separate:
        args.composite = True

    viewer.IDX = viewer.Index(viewer.DATA)
    if not viewer.default_ranges() and args.mode not in ("auto",):
        print("uyarı: channel_stats.json yok → --mode auto kullanılıyor "
              "(önce: python3 viewer/scan_stats.py)", file=sys.stderr)
        args.mode = "auto"

    wells = viewer.IDX.wells if args.all else args.wells
    if not wells:
        ap.error("kuyu belirtin veya --all kullanın")
    unknown = [w for w in wells if w not in viewer.IDX.wells]
    if unknown:
        ap.error(f"bilinmeyen kuyu: {unknown} (örn. A04, dolgulu iki hane)")

    n_t = len(viewer.IDX.tp)
    if args.t == "all":
        ts = list(range(n_t))
    elif "-" in args.t:
        a, b = args.t.split("-")
        ts = list(range(int(a), int(b) + 1))
    else:
        ts = [int(x) for x in args.t.split(",")]
    bad = [t for t in ts if not 0 <= t < n_t]
    if bad:
        ap.error(f"zaman noktası aralık dışı: {bad} (0–{n_t - 1})")

    chans = [c.strip() for c in args.channels.split(",") if c.strip()]
    unknown = [c for c in chans if c not in viewer.CHANNEL_IDS]
    if unknown:
        ap.error(f"bilinmeyen kanal: {unknown} (bf, green, orange, nir)")

    out = Path(args.out)
    ext = "png" if args.format == "png" else "tif"
    made = 0
    for w in wells:
        avail = [c for c in chans if c in viewer.IDX.map.get(w, {})]
        for t in ts:
            zt = "MIP" if args.mip else f"z{args.z:02d}"
            stamp = viewer.IDX.tp[t]["datetime"].replace(":", "").replace("-", "")
            base = f"{w}_t{t:02d}_{stamp}_{zt}"
            if args.composite:
                im = composite_rgb(w, t, args.z, args.mip, avail,
                                   args.mode, args.bright, args.gamma, args.bf_opacity)
                save(im, out / w / f"{base}_composite.{ext}", args.scale)
                made += 1
            if args.separate:
                for ch in avail:
                    u8 = scaled_u8(w, ch, t, args.z,
                                   args.mip and viewer.IDX.nz.get(ch, 1) > 1,
                                   args.mode, 1.0 if ch == "bf" else args.bright, args.gamma)
                    save(Image.fromarray(u8, "L"), out / w / f"{base}_{ch}.{ext}", args.scale)
                    made += 1
        print(f"  {w} bitti", flush=True)
    print(f"{made} görüntü → {out.resolve()}")


if __name__ == "__main__":
    main()
