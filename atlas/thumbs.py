#!/usr/bin/env python3
"""Kuyu sayfasına gömülen kanıt küçük resimleri.

Kuyu sayfasında bir katmana tıklandığında o katmanın **gerçek fotoğrafı** açılır:
ölçülen sayının arkasındaki görüntü, aynı sayfada, tıklama anında. Böylece
"bu katmanda şu kadar var" iddiası sayfadan ayrılmadan denetlenebilir.

Küçük resimler kasıtlı olarak küçük (uzun kenar 176 px): amaç ayrıntı incelemek
değil, "eşik doğru şeyi mi yakaladı" sorusuna bakışta cevap vermek. Tam
çözünürlüklü inceleme `atlas/check.py` sayfasında.

Boyut: kuyu başına 13 zaman × 17 katman = 221 kare, JPEG olarak toplam ~0,5 MB —
kuyu sayfasını iki katına çıkarmadan sığıyor.

    python3 atlas/thumbs.py --all --jobs 7      # tüm plaka, ~8 dk
    python3 atlas/thumbs.py --wells B04
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "analysis"))

import extract as E            # noqa: E402
import check as CK             # noqa: E402  aynı çizim mantığı, tek yerde

CACHE = HERE / "cache" / "thumbs"
LONG_EDGE = 176
QUALITY = 72


def _thumb(img: Image.Image) -> str:
    im = img.copy()
    im.thumbnail((LONG_EDGE, LONG_EDGE), Image.LANCZOS)
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=QUALITY, optimize=True)
    import base64
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def build_well(well: str) -> dict:
    """Her zaman noktası × katman için bir küçük resim, artı BF karesi."""
    thr = E.thresholds()
    hi = {ch: thr[ch]["main"] * 3.2 for ch in ("green", "orange", "nir")}
    stamps = E.timepoints()

    frames, bf_thumbs = [], []
    for stamp in stamps:
        bf = tifffile.imread(E.bf_path(well, stamp))
        _, terr, _ = E.bf_masks(bf)
        bf_thumbs.append(_thumb(CK.render_bf(bf, terr, True)))

        paths = {ch: E.plane_paths(well, ch, stamp) for ch in ("green", "orange", "nir")}
        nz = len(paths["green"])
        per_z = []
        for z in range(nz):
            pl, mk = {}, {}
            for ch in ("green", "orange", "nir"):
                a = tifffile.imread(paths[ch][z]).astype(np.float32)
                a -= float(np.median(a))
                pl[ch] = a
                mk[ch] = a > thr[ch]["main"]
            per_z.append(_thumb(CK.render_plane(pl, mk, hi, True)))
        frames.append(per_z)
    return {"well": well, "z": frames, "bf": bf_thumbs,
            "long_edge": LONG_EDGE, "outlined": True}


def load(well: str) -> dict | None:
    fp = CACHE / f"{well}.json"
    return json.loads(fp.read_text()) if fp.is_file() else None


def _job(well):
    t0 = time.time()
    try:
        d = build_well(well)
        CACHE.mkdir(parents=True, exist_ok=True)
        fp = CACHE / f"{well}.json"
        fp.write_text(json.dumps(d, separators=(",", ":")))
        return well, fp.stat().st_size, time.time() - t0, None
    except Exception as exc:                                       # noqa: BLE001
        return well, 0, time.time() - t0, f"{type(exc).__name__}: {exc}"


def main() -> None:
    import build as B

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 1))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    meta = B.plate_meta()
    wells = ([w.strip() for w in args.wells.split(",")] if args.wells
             else sorted(meta["wells"]) if args.all else ["B04"])
    todo = [w for w in wells if args.force or not (CACHE / f"{w}.json").is_file()]
    print(f"[thumbs] {len(todo)}/{len(wells)} kuyu · {args.jobs} iş")

    t0, done = time.time(), 0
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        for well, size, dt, err in ex.map(_job, todo):
            done += 1
            if err:
                print(f"  ✗ {well}: {err}")
            else:
                eta = (time.time() - t0) / done * (len(todo) - done)
                print(f"  {well}  {size / 1e6:.2f} MB  {dt:.0f}s"
                      f"   [{done}/{len(todo)}  ~{eta / 60:.0f} dk]", flush=True)
    print(f"[thumbs] bitti, {(time.time() - t0) / 60:.1f} dk")


if __name__ == "__main__":
    main()
