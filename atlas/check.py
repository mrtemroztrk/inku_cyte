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

CHS = ("green", "orange", "nir")


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


def render_gray(plane: np.ndarray, hi: float) -> Image.Image:
    """Tek kanalın ham düzlemi, gri tonlamalı.

    Kanallar ayrı ayrı saklanıyor ve renklendirme tarayıcıda yapılıyor: böylece
    hangi kanalın gösterileceği seçilebiliyor ve dosya, üç kanalın her
    kombinasyonunu ayrı ayrı saklamak zorunda kalmıyor. Ölçekleme plaka geneli
    sabit — kuyuya uyarlanmış bir ölçekleme görüntüyü güzelleştirir ama kuyular
    arası karşılaştırmayı bozar.
    """
    v = np.clip(_shrink(plane) / max(hi, 1e-9), 0, 1)
    return Image.fromarray((v * 255).astype(np.uint8), mode="L")


def render_outline(mask: np.ndarray) -> Image.Image:
    """Ölçülen maskenin sınırı, saydam zeminli tek renkli katman."""
    o = _outline(mask)
    a = np.zeros(o.shape + (2,), np.uint8)      # gri + alfa
    a[..., 0] = 255
    a[..., 1] = np.where(o, 255, 0)
    return Image.fromarray(a, mode="LA")


def render_bf(bf: np.ndarray) -> Image.Image:
    a = _shrink(bf.astype(np.float32))
    lo, hi = 57.5, 187.5                        # cihazın kendi penceresi
    g = np.clip((a - lo) / (hi - lo), 0, 1)
    return Image.fromarray((g * 255).astype(np.uint8), mode="L")


def _min_size(mask: np.ndarray, ch: str):
    """extract.py ile aynı asgari bileşen boyutu — maskeler birebir aynı olmalı."""
    return E._min_size(mask, ch)


def _pack_cube(masks: list[np.ndarray]) -> str:
    """Tam çözünürlüklü maske yığını → 3B sahnenin beklediği seyrek biçim.

    Kanıt sayfası fotoğrafı ile rekonstrüksiyonu üst üste koyuyor; binlenmiş bir
    voksel orada gerçek olmayan bir kalınlık gösterirdi, o yüzden burada ölçümün
    yapıldığı çözünürlük kullanılıyor. Biçim atlas'takiyle aynı: eleman sayısı,
    delta-kodlanmış indeksler, sonra değerler.
    """
    import gzip
    nz = len(masks)
    h, w = masks[0].shape
    idx = np.concatenate([np.flatnonzero(m).astype(np.uint64) + z * h * w
                          for z, m in enumerate(masks)]).astype(np.uint32)
    d = np.diff(np.concatenate([[0], idx.astype(np.int64)])).astype(np.uint32)
    val = np.ones(idx.size, np.uint8)
    blob = np.uint32(idx.size).tobytes() + d.tobytes() + val.tobytes()
    return base64.b64encode(gzip.compress(blob, 6)).decode("ascii")


def build_well(well: str, ti: int) -> dict:
    """Bir kuyu-zaman noktası: kanal başına ham düzlemler, maske sınırları,
    tam çözünürlüklü voksel yığını ve düzlem başına sayılar."""
    thr = E.thresholds()
    stamp = E.timepoints()[ti]
    um = E.UM_PER_PX
    px_mm2 = um ** 2 / 1e6

    bf = tifffile.imread(E.bf_path(well, stamp))
    fine, terr, bfinfo = E.bf_masks(bf)
    H, W = bf.shape

    # Beyaz nokta eşiğin sabit katı: eşiğin görüntüde nerede durduğu görünsün
    # diye kuyuya uyarlanmıyor.
    hi = {ch: thr[ch]["main"] * 3.2 for ch in CHS}
    paths = {ch: E.plane_paths(well, ch, stamp) for ch in CHS}
    nz = len(paths["green"])

    raw = {c: [] for c in CHS}
    out = {c: [] for c in CHS}
    out_lo = {c: [] for c in CHS}
    masks = {c: [] for c in CHS}
    run = {c: None for c in CHS}
    best_v = {c: None for c in CHS}     # en parlak düzlemin değeri
    best_z = {c: None for c in CHS}     # ve hangi düzlem olduğu
    stats = []

    for z in range(nz):
        st = {}
        for ch in CHS:
            a = tifffile.imread(paths[ch][z]).astype(np.float32)
            a -= float(np.median(a))
            m = _min_size(a > thr[ch]["main"], ch)
            if best_v[ch] is None:
                best_v[ch] = a.copy()
                best_z[ch] = np.zeros(a.shape, np.int16)
            else:
                up = a > best_v[ch]
                best_v[ch] = np.where(up, a, best_v[ch])
                best_z[ch] = np.where(up, z, best_z[ch]).astype(np.int16)
            run[ch] = a.copy() if run[ch] is None else np.maximum(run[ch], a)
            # Yalnızca ham düzlemler gömülür; "z00'dan buraya" / "buradan
            # z16'ya" / "hepsi" izdüşümleri tarayıcıda, düzlemlerin piksel
            # başına maksimumu ("lighten") alınarak kurulur — bir MIP'in tanımı
            # tam olarak bu, ve sayfa üçte bir küçülüyor.
            raw[ch].append(_b64(render_gray(a, hi[ch])))
            out[ch].append(_b64(render_outline(m), "PNG"))
            # Duyarlı eşik (×0,24 kazanç, ölçümde kullanılmaz): ana eşiğin
            # kaçırdığı zayıf sinyal ne kadar, gözle ve sayıyla görülsün diye.
            m_lo = _min_size(a > thr[ch]["lo"], ch)
            out_lo[ch].append(_b64(render_outline(m_lo & ~m), "PNG"))
            masks[ch].append(m)
            st[ch] = {"px": int(m.sum()), "px_lo": int(m_lo.sum()),
                      "mm2": round(float(m.sum()) * px_mm2, 6),
                      "in_terr": int((m & terr).sum())}
        stats.append(st)

    # --- odak düzlemine indirgenmiş bulut --------------------------------
    # Tek bir nesne, 4× objektifin odak derinliği yüzünden birkaç düzlemde birden
    # eşiği geçiyor ve 3B'de dikey bir sütuna dönüşüyor. Her XY konumunu en
    # parlak olduğu düzleme yerleştirmek o sütunları kaldırıyor; ölçülen yayılma
    # bu kuyularda 2,6–3,0×.
    focus, focus_by_z, smear = {}, {}, {}
    for ch in CHS:
        mip_mask = _min_size(np.maximum.reduce([m for m in masks[ch]]) if False
                             else (run[ch] > thr[ch]["main"]), ch)
        cube = [np.zeros((H, W), bool) for _ in range(nz)]
        ys, xs = np.nonzero(mip_mask)
        if ys.size:
            zz = best_z[ch][ys, xs]
            for z in range(nz):
                sel = zz == z
                if sel.any():
                    cube[z][ys[sel], xs[sel]] = True
        focus[ch] = _pack_cube(cube)
        focus_by_z[ch] = (np.bincount(best_z[ch][mip_mask], minlength=nz).tolist()
                          if ys.size else [0] * nz)
        n_all = int(sum(int(m.sum()) for m in masks[ch]))
        n_foc = int(mip_mask.sum())
        smear[ch] = round(n_all / n_foc, 2) if n_foc else None

    return {
        "well": well, "t": ti, "stamp": stamp, "nz": nz,
        "vox_focus": focus, "focus_by_z": focus_by_z, "smear": smear,
        "shape": [H // BIN, W // BIN],
        "um_per_px": um * BIN,
        "raw": raw, "outline": out, "outline_lo": out_lo, "stats": stats,
        "vox": {ch: _pack_cube(masks[ch]) for ch in CHS},
        "grid": {"nz": nz, "h": H, "w": W, "bin": 1},
        "voxel_um": um,
        "colors": {c: TH.CH_SCENE[c] for c in CHS},
        "labels": {c: TH.CH_LABEL_EN[c] for c in CHS},
        "bf": {"raw": _b64(render_bf(bf)),
               "outline": _b64(render_outline(terr), "PNG"),
               "terr_mm2": round(float(terr.mean()) * bf.size * px_mm2, 4),
               "terr_frac": round(float(terr.mean()), 5)},
        "thresholds": {ch: round(thr[ch]["main"], 4) for ch in CHS},
        "thresholds_lo": {ch: round(thr[ch]["lo"], 4) for ch in CHS},
        "white_point": {ch: round(hi[ch], 4) for ch in CHS},
        "min_obj_px": {ch: E.MIN_OBJ_PX.get(ch, 1) for ch in CHS},
        "bf_thr": E.BF_THR,
    }


def page(d: dict, meta: dict) -> str:
    import page as P            # şablon varlıkları için

    cond = P._cond(meta)
    day = d["t"]
    smear_txt = " · ".join(
        f"{d['labels'][c]} {d['smear'][c]}×" for c in ("green", "orange", "nir")
        if d["smear"].get(c))
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

  <div class="zrow">
    <button class="play" id="playz" title="step through layers">▶</button>
    <div class="zbar" id="zbar">
      <input type="range" id="z" min="0" max="{d['nz'] - 1}" value="0" step="1"
             list="zticks" aria-label="z layer">
      <datalist id="zticks">{''.join(f'<option value="{i}"></option>' for i in range(d['nz']))}</datalist>
      <div class="zticklabels" aria-hidden="true">{''.join(f'<span>{("z%02d" % i) if (i % 4 == 0 or i == d['nz'] - 1) else ""}</span>' for i in range(d['nz']))}</div>
    </div>
    <span class="zlabel" id="zlabel"></span>
    <label class="sel">layers
      <select id="stack">
        <option value="one">this layer only</option>
        <option value="up">z00 → this layer</option>
        <option value="down">this layer → z{d['nz'] - 1:02d}</option>
        <option value="all">all layers</option>
      </select>
    </label>
  </div>

  <div class="checkbar">
    <span class="barlbl">show</span>
    <div class="chips" id="chchips"></div>
    <label class="chk"><input type="checkbox" id="outline" checked>
      measured mask outline</label>
    <label class="chk"><input type="checkbox" id="outlo">
      + what a more sensitive threshold would add</label>
    <label class="chk"><input type="checkbox" id="showbf">
      brightfield</label>
    <label class="sel">3D shows
      <select id="cloud">
        <option value="all">the thresholded pixels of each plane (matches the photograph)</option>
        <option value="focus">best-focus plane only (one z per pixel, for 3D shape)</option>
      </select>
    </label>
    <label class="chk"><input type="checkbox" id="zup">
      z00 on top</label>
  </div>

  <div class="checkbar">
    <label class="chk"><input type="checkbox" id="overlay">
      <b>overlay photo on the reconstruction</b></label>
    <label class="chk" id="mixwrap" hidden>photo
      <input type="range" id="mix" class="cut" min="0" max="100" value="60"
             aria-label="photo opacity">
      <span class="cutlabel" id="mixlabel">60 %</span></label>
    <label class="chk"><input type="checkbox" id="link" checked>
      link panels — zoom and pan together</label>
    <span class="cutlabel" id="zoomlab"></span>
    <button class="chip out" id="zoomreset">reset view</button>
    <div class="seg" id="camseg" role="group" aria-label="camera">
      <button data-view="top">top</button>
      <button data-view="home">oblique</button>
      <button data-view="front">front</button>
      <button data-view="right">right</button>
      <button data-view="bottom">bottom</button>
    </div>
  </div>

  <div class="checkgrid" id="grid">
    <figure id="leftfig">
      <canvas id="shot" hidden></canvas>
      <div class="scene" id="photo3d" tabindex="0">
        <div class="hintbar">drag orbit · shift-drag pan · scroll zoom ·
          double-click reset</div>
      </div>
      <figcaption id="shotcap"></figcaption>
    </figure>
    <figure id="rightfig">
      <div class="scene" id="scene" tabindex="0">
        <div class="hintbar" id="scenehint">drag orbit · shift-drag pan ·
          scroll zoom · double-click reset</div>
        <div class="viewlabel" id="viewlabel"></div>
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
      <h4>What "3D shows" means</h4>
      <p>The default, <i>the thresholded pixels of each plane</i>, draws in every
      layer exactly the pixels above threshold in that plane — the same pixels the
      outline on the photograph encloses, so a stain in the photograph and its
      dots in the reconstruction match pixel for pixel. This is what every area
      and volume number is computed from.</p>
      <p>The depth of field of a 4× objective (NA ≈ 0.13) is tens of microns, so
      one object crosses the threshold in several neighbouring planes: measured
      here, thresholded voxels outnumber distinct XY positions by
      <b>{smear_txt}</b>. Seen from the side, that stretches each object into a
      column of out-of-focus light. <i>Best-focus plane only</i> places each XY
      position once, in the plane where it is brightest — the columns disappear and
      the 3D shape reads — but a single layer then shows only the pixels whose
      brightest plane it is, and a stain can look hollow. Use it for shape, not for
      checking a plane against its photograph.</p>
      <h4>The two panels are twins</h4>
      <p>The photograph is not a flat picture beside a 3D view: it hangs inside a
      second copy of the same scene — same box, same ladder, same scale bar — as a
      plane at the z height of its own layer. With <b>link panels</b> on, the two
      scenes share one camera: orbit, pan or zoom either side and the other
      follows exactly, so a tilted photograph and the tilted reconstruction are
      compared from the same viewpoint at the same size, which is the only
      comparison that means anything. Turn linking off to move one side alone.</p>
      <h4>Layers</h4>
      <p><i>This layer only</i> shows one raw plane and lights one layer.
      <i>z00 → this layer</i> and <i>this layer → z{d['nz'] - 1:02d}</i> show the
      maximum projection of the planes on either side of the slider and light the
      same layers in 3D — the stack building up from one end or being peeled from
      the other. <i>All layers</i> is the full projection against the full stack.
      Both sides always show the same accumulation. The outline is always the mask
      of the slider's own layer, so it is hidden in <i>all layers</i>, where no
      layer is current. <b>z00 on top</b> flips the ordinal z axis so z00 is drawn
      uppermost, for stacks whose first plane is the apex of the dome; XY is
      untouched, so the top view still matches the photograph.</p>
      <h4>Checking that the reconstruction is in the right place</h4>
      <p>Tick <b>overlay photo on the reconstruction</b>. The photograph is placed
      <i>inside</i> the 3D scene, as a textured plane at the z height of the layer
      it came from — not pasted flat over the screen. That means the camera stays
      free: rotate to an oblique angle and the photograph rotates with the scene,
      so you can see the voxels standing on the stain from any direction. From
      directly above (the <b>top</b> button) the projection is exact and any shift,
      rotation, flip or scale error would show as dots beside their blobs rather
      than on them; from an oblique angle you can additionally see that the
      objects sit at the right height and are not floating.</p>
      <h4>Is the threshold missing dim cells?</h4>
      <p>Tick <b>+ what a more sensitive threshold would add</b>. A second,
      thinner outline in a paler tint then marks the pixels that a threshold at
      0.24× the plate gain would select and the measured threshold ({d['thresholds']['green']} /
      {d['thresholds']['orange']} / {d['thresholds']['nir']}, i.e. 0.36 / 0.60 / 0.35× the gain) does not; the
      table gives both pixel counts. That sensitive threshold is not used for any
      number in the atlas — it brings back background speckle in empty corners —
      but the outline shows exactly what is being left out and lets a dim cell be
      judged on its pixels rather than argued about.</p>
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
<dialog id="explain"><div class="exbody"></div>
  <form method="dialog"><button class="wide">close</button></form></dialog>
<script>window.CHECK={json.dumps(d, ensure_ascii=False, separators=(',', ':'))};
window.VOX={json.dumps(meta.get('vox_payload', {}), ensure_ascii=False,
                       separators=(',', ':'))};
window.THEME={P._theme_js()};
window.DEFS={json.dumps(__import__("defs").build(__import__("calib").load()),
                        ensure_ascii=False, separators=(",", ":"))};</script>
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
