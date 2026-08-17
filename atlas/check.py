#!/usr/bin/env python3
"""Segmentasyon kanıt sayfası: ölçüm gerçekten görüntüdeki şeyi mi ölçtü.

Atlas'ın bütün sayıları bir eşiğin arkasında duruyor. Bu sayfa o eşiği görünür
kılar: solda ham düzlem — mikroskobun gördüğü —, üstünde ölçülen maskenin sınırı;
sağda aynı düzlemin 3B karşılığı. z kaydırıcısı ikisini birlikte gezdirir, yani
"bu katmanda ne var" sorusunun görüntüdeki ve ölçümdeki karşılığı yan yana durur.

Neden gerekli: eşik plaka geneli sabit ve kuyuya uyarlanmıyor (uyarlansaydı
kuyular karşılaştırılamazdı). Bunun bedeli, bazı kuyularda eşiğin cömert, bazı
kuyularda cimri kalmasıdır. Sayının yanında görüntü olmadan bu görülmez.

    python3 atlas/check.py --wells B04,B01        # seçili kuyular, son zaman noktası
    python3 atlas/check.py --all --jobs 7         # tüm plaka
    python3 atlas/check.py --wells B04 --t 6      # başka bir zaman noktası

Çıktı: atlas/site/check/<kuyu>.html — kendi kendine yeten, gömülü görüntülerle.
"""
from __future__ import annotations

import argparse
import base64
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
from scipy import ndimage

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "analysis"))

import extract as E            # noqa: E402
import calib                   # noqa: E402
import theme as TH             # noqa: E402

SITE = HERE / "site" / "check"
BIN = 2                        # görüntü küçültme; 520×704, gömülü olarak makul
JPEG_Q = 82

CH_RGB = {ch: tuple(int(TH.CH_SCENE[ch][1 + 2 * i:3 + 2 * i], 16) for i in range(3))
          for ch in ("green", "orange", "nir")}


def _b64(img: Image.Image, fmt: str = "JPEG") -> str:
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.convert("RGB").save(buf, "JPEG", quality=JPEG_Q, optimize=True)
        mime = "image/jpeg"
    else:
        img.save(buf, "PNG", optimize=True)
        mime = "image/png"
    return f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _shrink(a: np.ndarray, b: int = BIN) -> np.ndarray:
    h, w = a.shape[0] // b, a.shape[1] // b
    return a[: h * b, : w * b].reshape(h, b, w, b).mean((1, 3))


def _outline(mask: np.ndarray, b: int = BIN) -> np.ndarray:
    """Maskenin sınırı, küçültülmüş ızgarada. İçini doldurmuyoruz: dolgu altındaki
    ham sinyali gizler ve tam da görülmek istenen şey odur."""
    h, w = mask.shape[0] // b, mask.shape[1] // b
    m = mask[: h * b, : w * b].reshape(h, b, w, b).any((1, 3))
    return m & ~ndimage.binary_erosion(m, np.ones((3, 3)))


def render_plane(planes: dict[str, np.ndarray], masks: dict[str, np.ndarray],
                 hi: dict[str, float], outline: bool) -> Image.Image:
    """Üç kanalı toplamalı bindirir; istenirse maske sınırlarını üstüne çizer.

    Ölçekleme viewer'daki ile aynı mantıkta: düzlemin kendi medyanı arkaplan
    olarak çıkarılır, beyaz nokta plaka geneli ölçülen kazançtır. Kuyuya
    uyarlanmış bir ölçekleme görüntüyü güzelleştirir ama kuyular arasında
    karşılaştırmayı bozar.
    """
    h, w = _shrink(planes["green"]).shape
    rgb = np.zeros((h, w, 3), np.float32)
    for ch in ("green", "orange", "nir"):
        a = _shrink(planes[ch])
        v = np.clip(a / max(hi[ch], 1e-9), 0, 1)[:, :, None]
        rgb += v * np.array(CH_RGB[ch], np.float32)[None, None, :] / 255.0
    if outline:
        for ch in ("green", "orange", "nir"):
            o = _outline(masks[ch])
            col = np.array(CH_RGB[ch], np.float32) / 255.0
            rgb[o] = np.minimum(1.0, col * 1.35 + 0.25)
    return Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))


def render_bf(bf: np.ndarray, terr: np.ndarray, outline: bool) -> Image.Image:
    a = _shrink(bf.astype(np.float32))
    lo, hi = 57.5, 187.5                        # cihazın kendi penceresi
    g = np.clip((a - lo) / (hi - lo), 0, 1)
    rgb = np.repeat(g[:, :, None], 3, axis=2)
    if outline:
        o = _outline(terr)
        rgb[o] = np.array([0.42, 0.78, 1.0])    # teritorya sınırı
    return Image.fromarray((rgb * 255).astype(np.uint8))


def build_well(well: str, ti: int) -> dict:
    """Bir kuyu-zaman noktası için tüm düzlemlerin görüntüleri ve düzlem sayıları."""
    thr = E.thresholds()
    stamp = E.timepoints()[ti]
    um = E.UM_PER_PX
    px_mm2 = um ** 2 / 1e6

    bf = tifffile.imread(E.bf_path(well, stamp))
    fine, terr, bfinfo = E.bf_masks(bf)

    # Plaka geneli beyaz nokta: eşiğin 3,2 katı. Eşik nerede duruyor görünsün diye
    # sabit ve kuyudan bağımsız.
    hi = {ch: thr[ch]["main"] * 3.2 for ch in ("green", "orange", "nir")}

    planes_all = {ch: E.plane_paths(well, ch, stamp) for ch in ("green", "orange", "nir")}
    nz = len(planes_all["green"])

    raw, over, cum, stats = [], [], [], []
    # Birikimli görüntü: 0..z arası maksimum projeksiyon. "Alt katmanlar açık
    # kalsın" seçildiğinde 3B'de görünen dilim ile fotoğrafın gösterdiği şey aynı
    # olmalı — tek düzlemlik bir fotoğrafı çok katmanlı bir dilimle karşılaştırmak
    # hizalama kanıtını bozardı.
    run = {ch: None for ch in ("green", "orange", "nir")}
    for z in range(nz):
        pl, mk = {}, {}
        for ch in ("green", "orange", "nir"):
            a = tifffile.imread(planes_all[ch][z]).astype(np.float32)
            a -= float(np.median(a))
            pl[ch] = a
            mk[ch] = a > thr[ch]["main"]
            run[ch] = a.copy() if run[ch] is None else np.maximum(run[ch], a)
        raw.append(_b64(render_plane(pl, mk, hi, False)))
        over.append(_b64(render_plane(pl, mk, hi, True)))
        cum.append(_b64(render_plane(run, mk, hi, False)))
        stats.append({ch: {"px": int(mk[ch].sum()),
                           "mm2": round(float(mk[ch].sum()) * px_mm2, 6),
                           "in_terr": int((mk[ch] & terr).sum())}
                      for ch in ("green", "orange", "nir")})

    return {
        "well": well, "t": ti, "stamp": stamp, "nz": nz,
        "shape": [bf.shape[0] // BIN, bf.shape[1] // BIN],
        "um_per_px": um * BIN,
        "raw": raw, "over": over, "cum": cum, "stats": stats,
        "bf": {"raw": _b64(render_bf(bf, terr, False)),
               "over": _b64(render_bf(bf, terr, True)),
               "terr_mm2": round(float(terr.mean()) * bf.size * px_mm2, 4),
               "terr_frac": round(float(terr.mean()), 5)},
        "thresholds": {ch: round(thr[ch]["main"], 4) for ch in ("green", "orange", "nir")},
        "white_point": {ch: round(hi[ch], 4) for ch in ("green", "orange", "nir")},
        "bf_thr": E.BF_THR,
    }


def page(d: dict, meta: dict) -> str:
    import page as P            # şablon varlıkları için

    cond = P._cond(meta)
    day = d["t"]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{d['well']} segmentation check — inc_tests atlas</title>
<style>{P._asset('app.css')}</style>
</head>
<body>
<div class="wrap">

<header class="top">
  <span class="well">{d['well']}</span>
  <span class="cond">{cond} · segmentation check · t{day:02d}</span>
  <span class="spacer"></span>
  <nav>
    <a href="../{d['well']}.html">← well page</a>
    <a href="../index.html">plate</a>
  </nav>
</header>

<section>
  <h2 class="sec">Does the measurement match the image?</h2>
  <p class="lead">Left is the raw plane as the microscope recorded it, with the
  three fluorescence channels blended additively and the plate-wide scaling
  applied — no per-well adjustment, so what looks dim here <i>is</i> dim relative
  to the rest of the plate. Toggle the outline to draw the boundary of the mask
  that every number in this atlas is computed from. Right is the same layer in
  3D. Move the z slider and both follow; what you see on the left is exactly what
  was counted on the right.</p>

  <div class="checkbar">
    <button class="play" id="playz" title="step through layers">▶</button>
    <input type="range" id="z" class="cut" min="0" max="{d['nz'] - 1}" value="0"
           aria-label="z layer">
    <span class="cutlabel" id="zlabel"></span>
    <label class="chk"><input type="checkbox" id="outline" checked>
      show measured mask outline</label>
    <label class="chk"><input type="checkbox" id="showbf">
      brightfield instead of fluorescence</label>
    <label class="sel">layers
      <select id="stack">
        <option value="one">this layer only</option>
        <option value="cum">this layer and everything below</option>
      </select>
    </label>
    <label class="chk"><input type="checkbox" id="overlay">
      <b>overlay photo on the reconstruction</b></label>
    <label class="chk" id="mixwrap" hidden>photo
      <input type="range" id="mix" class="cut" min="0" max="100" value="55"
             aria-label="photo opacity">
      <span class="cutlabel" id="mixlabel">55 %</span></label>
  </div>

  <div class="checkgrid" id="grid">
    <figure id="leftfig">
      <div class="imgbox"><img id="shot" alt="raw plane"></div>
      <figcaption id="shotcap"></figcaption>
    </figure>
    <figure id="rightfig">
      <div class="scene" id="scene" tabindex="0">
        <img id="ovl" alt="" hidden>
        <div class="hintbar" id="scenehint">drag orbit · scroll zoom ·
          double-click reset</div>
      </div>
      <figcaption id="scenecap">The same layer isolated in the voxel
      reconstruction. Every dot is one 5.6 µm voxel above threshold — one dot here
      for a patch that crossed the threshold on the left.</figcaption>
    </figure>
  </div>

  <div class="tblblock">
    <div class="fighead"><h3><span class="fignum">Table</span> What the threshold
      selected in this layer</h3>
      <div class="tools"><button data-tbl="plane">table</button></div></div>
    <div class="tbl on" id="tbl_plane"></div>
  </div>
</section>

<details class="method" open>
  <summary>How to read this page</summary>
  <div class="body">
    <div>
      <h4>What the outline is</h4>
      <p>The boundary of the pixels above threshold in <i>this plane</i>, for each
      channel in its own colour. Thresholds are fixed for the whole plate at a
      constant multiple of the measured above-background gain: green
      {d['thresholds']['green']}, orange {d['thresholds']['orange']}, NIR
      {d['thresholds']['nir']} (in the calibrated units of each channel, after the
      plane's own median has been subtracted). The brightfield outline is the
      organoid territory: more than {d['bf_thr']:.0f} grey levels darker than the
      background, closed and hole-filled.</p>
      <h4>Checking that the reconstruction is in the right place</h4>
      <p>Tick <b>overlay photo on the reconstruction</b>. The camera locks to a
      straight top-down view and the projection is scaled so that one voxel lands
      exactly on the pixels it was measured from; the photograph is then blended
      on top. If the reconstruction were shifted, rotated or flipped relative to
      the image, every dot would sit beside its blob instead of on it, and the
      slider would show two offset copies of the same pattern. Sweeping the
      slider from 0 to 100 % is the check: the dots should disappear <i>into</i>
      the stain, not slide across it.</p>
      <h4>What to look for</h4>
      <p>Signal inside no outline means the threshold missed it. Outline around
      nothing visible means the threshold fired on noise. Both are real failure
      modes and both are visible here. The out-of-focus haze that surrounds every
      in-focus object is expected at 4× (NA ≈ 0.13) and is the reason layer areas
      sum to more than the projected area.</p>
    </div>
    <div>
      <h4>Why the display is not adjusted per well</h4>
      <p>The white point is fixed at {d['white_point']['green']} /
      {d['white_point']['orange']} / {d['white_point']['nir']} for green / orange /
      NIR — 3.2× the threshold in each channel. A per-well autoscale would make
      every well look equally bright and would hide exactly the difference the
      measurements are about.</p>
      <h4>What this page cannot show</h4>
      <p>Whether an object is a tumour cell, a CAF or a macrophage. Macrophages
      and CAFs carry no fluorescent label; in brightfield they are dark like
      everything else. The organoid territory is therefore an upper bound on
      tumour extent, and the green channel a lower bound — it does not stain every
      organoid.</p>
    </div>
  </div>
</details>

</div>
<script>window.CHECK={json.dumps(d, ensure_ascii=False, separators=(',', ':'))};
window.VOX={json.dumps(meta.get('vox_payload', {}), ensure_ascii=False,
                       separators=(',', ':'))};
window.THEME={P._theme_js()};</script>
<script>{P._asset('scene.js')}</script>
<script>{P._asset('figs.js')}</script>
<script>{P._asset('check.js')}</script>
</body>
</html>
"""


def _job(a):
    well, ti = a
    t0 = time.time()
    try:
        return well, build_well(well, ti), time.time() - t0, None
    except Exception as exc:                                       # noqa: BLE001
        return well, None, time.time() - t0, f"{type(exc).__name__}: {exc}"


def main() -> None:
    import build as B

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", help="virgülle ayrılmış kuyu listesi")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--t", type=int, default=12, help="zaman noktası (varsayılan son)")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 1))
    args = ap.parse_args()

    meta = B.plate_meta()
    cal = calib.load()
    wells = ([w.strip() for w in args.wells.split(",")] if args.wells
             else sorted(meta["wells"]) if args.all else ["B04"])

    SITE.mkdir(parents=True, exist_ok=True)
    t0, done = time.time(), 0
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        for well, d, dt, err in ex.map(_job, [(w, args.t) for w in wells]):
            done += 1
            if err:
                print(f"  ✗ {well}: {err}")
                continue
            wm = dict(meta["wells"][well])
            pay = B.load_derived(well, cal)
            if pay:                      # 3B sahne aynı ölçümü kullansın
                fr = pay["frames"][args.t]
                wm["vox_payload"] = {"vox": fr["vox"], "grid": fr["grid"],
                                     "dome": fr["dome"], "terr_map": fr["terr_map"],
                                     "terr_shape": fr["terr_shape"],
                                     "voxel_um": pay["voxel_um"]}
            out = SITE / f"{well}.html"
            out.write_text(page(d, wm), encoding="utf-8")
            eta = (time.time() - t0) / done * (len(wells) - done)
            print(f"  {well}  {out.stat().st_size / 1e6:.2f} MB  {dt:.0f}s"
                  f"   [{done}/{len(wells)}  ~{eta / 60:.0f} dk]", flush=True)
    print(f"[check] {done} sayfa  ·  {(time.time() - t0) / 60:.1f} dk  ·  {SITE}")


if __name__ == "__main__":
    main()
