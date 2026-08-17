#!/usr/bin/env python3
"""Tek geçişte özellik çıkarımı — 88 kuyu × 13 zaman noktası.

Buradaki ölçümlerin neredeyse tamamı **piksel/voksel tabanlı**: kanal başına eşik
üstü alan, alan oranı, uzaklık dağılımı. Nesne sayıları da çıkarılıyor ama ikincil.
Bunun nedeni 4× objektifte tek hücrelerin güvenilir biçimde ayrıştırılamaması;
alan oranları eşik seçimine nesne sayımından çok daha az duyarlı.

Organoid maskesi neden brightfield'dan
--------------------------------------
Green kanalı organoidlerin **hepsini boyamıyor**: brightfield'da net görünen çok
sayıda organoidin green sinyali yok (A03, B01, A01 gözle doğrulandı). O yüzden
"organoid nerede" sorusu BF'den, "ne kadarı boyanmış" sorusu green'den yanıtlanır.
BF ile floresan z-yığınları uzamsal olarak hizalı (faz korelasyonu kayması ≤ 1 px,
4 kuyuda ölçüldü), yani BF maskesi floresan kanallara doğrudan uygulanabilir.

İki BF maskesi üretiliyor:
  fine  — zeminden BF_THR gri seviye koyu bölgeler; ayrık organoidleri ayrı tutar
  terr  — fine'ın 31 px kapaması + delik doldurma; bir agregatın *teritoryası*
Konum ölçümleri (içeride/dışarıda, uzaklık bantları) terr üzerinden yapılır,
organoid başına tablo da terr bileşenlerinden çıkar.

Çıktı
-----
cache/features/{well}_t{nn}.json   örnek başına tüm ölçümler
cache/features/features.csv        skaler kolonlar, tek tablo
cache/features/organoids.csv       organoid başına satır
cache/features/bf_flat.npy         plaka geneli aydınlatma (vinyet) referansı

Kullanım
--------
  python3 analysis/extract.py --flat            # bir kez: aydınlatma referansı
  python3 analysis/extract.py --check           # 8 kuyu, son zaman — hızlı bakış
  python3 analysis/extract.py --all --jobs 6    # tüm plaka (~20-30 dk)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import tifffile
from scipy import ndimage

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = Path(os.environ.get("INC_DATA", ROOT / "data" / "inc_tests")).resolve()
CACHE = Path(os.environ.get("INC_CACHE", ROOT / "viewer" / "cache"))
OUT = CACHE / "features"
FLAT_PATH = OUT / "bf_flat.npy"

UM_PER_PX = 2.798            # Incucyte 4×; extras/ ölçek yazısından geri hesaplandı
CH = ("green", "orange", "nir")
PREFIX = {"green": "Green_Zstacks", "orange": "Orange_Tcells", "nir": "NIR_deadCells",
          "bf": "BF_Tcell_Infil_dye"}

# Floresan eşiği = plaka geneli arkaplan üstü kazanç (channel_stats.json off_hi) × kat.
# Ana eşik THR_MAIN; alt/üst eşikler yalnızca duyarlılık kontrolü için hesaplanır.
#
# green neden 0,36: 0,60'ta eşik düzlemin p99,5'ine düşüyor ve arkaplan üstü
# ışığın yalnızca %16'sını alıyordu; gözle net görünen hücreler maskeye
# girmiyordu. Ölçüldü (B04 z09, hücreli bölge vs boş köşe, asgari 4 px ile):
#     0,60 → 41 nesne, boş köşede 6  (gürültü oranı 0,15)
#     0,36 → 99 nesne, boş köşede 5  (gürültü oranı 0,05)
#     0,24 → 324 nesne, boş köşede 26 (gürültü oranı 0,08)
# Yani eşiği düşürmek gürültüyü artırmıyor, azaltıyor — asgari boyut filtresiyle
# birlikte. 0,24'te arkaplan beneklenmesi geri geliyor.
#
# orange neden 0,60'ta bırakıldı: orada bağımsız bir kısıt var. Ekim sayısından
# türetilen kalibrasyon, eşik düştükçe hücre başına daha büyük alan veriyor ve
# öngörülen hücre çapı büyüyor: ×0,80 → 9,5 µm, ×0,60 → 10,8 µm, ×0,40 → 12,9 µm.
# Bir T hücresi 7–10 µm; ×0,40 fiziksel olarak imkânsız bir hücre öngörüyor, yani
# oradaki fazlalık hücre değil taşma. 0,60 bu kısıtın içinde kalıyor.
THR_MAIN = {"green": 0.36, "orange": 0.60, "nir": 0.35}
THR_ALT = (0.24, 0.60)

# Asgari bağlı bileşen boyutu (piksel). Düşük eşikte kalan tek piksellik benek
# gürültüsünü atar; bir T hücresi bu ölçekte ~5 piksel olduğu için gerçek nesneye
# dokunmaz.
MIN_OBJ_PX = {"green": 4, "orange": 1, "nir": 1}

# BF organoid maskesi — eşik plaka geneli sabit, kuyuya göre uyarlanmıyor.
# (Kuyuya uyarlanan eşik her kuyuyu farklı ölçekler, kuyular karşılaştırılamaz olur.)
BF_SIGMA = 6.0               # px
BF_THR = 8.0                 # gri seviye; zemin ~128, vinyet ~4,6 seviye (flat ile düzeltilir)
BF_MIN_PX = 30
BF_CLOSE_TERR = 31
BF_MIN_TERR = 200
MIN_ORG_PX = 300             # organoid tablosuna girme eşiği (~55 µm eşdeğer çap)
SMALL_LO, SMALL_HI = 4, 60   # "tek hücre boyutlu" BF nesnesi aralığı (px)
NORMAL_FLOOR = 128.0         # beklenen zemin gri seviyesi; sapma QC bayrağı

# İşaretli uzaklık bantları (µm; negatif = organoid teritoryası içi)
BANDS_UM = (-np.inf, -150, -100, -50, -20, 0, 20, 50, 100, 200, 400, np.inf)


# ------------------------------------------------------------------------ io
def _code(well: str) -> str:
    return well[0] + str(int(well[1:]))


def bf_path(well: str, stamp: str) -> Path:
    return DATA / "wells" / well / "bf" / f"{PREFIX['bf']}_{_code(well)}_1_{stamp}.tif"


def plane_paths(well: str, ch: str, stamp: str) -> list[Path]:
    d = DATA / "wells" / well / ch
    if not d.is_dir():
        return []
    fs = [f for f in d.iterdir() if stamp in f.name and "_plane" in f.name]
    return sorted(fs, key=lambda p: int(p.name.split("_plane")[1].split("_")[0]))


_THR: dict[str, dict[str, float]] | None = None
_FLAT: np.ndarray | None = None


def thresholds() -> dict[str, dict[str, float]]:
    global _THR
    if _THR is None:
        f = CACHE / "channel_stats.json"
        if not f.is_file():
            raise SystemExit("channel_stats.json yok — önce: python3 viewer/scan_stats.py")
        st = json.loads(f.read_text())
        _THR = {ch: {"main": float(st[ch]["plane"]["off_hi"]) * frac,
                     "lo": float(st[ch]["plane"]["off_hi"]) * THR_ALT[0],
                     "hi": float(st[ch]["plane"]["off_hi"]) * THR_ALT[1]}
                for ch, frac in THR_MAIN.items()}
    return _THR


def flat() -> np.ndarray:
    """Plaka geneli aydınlatma sapması (medyanı sıfırlanmış). Vinyet ~4,6 gri
    seviye — BF eşiği 8 seviye olduğu için düzeltilmezse kenarlar maskeye girer."""
    global _FLAT
    if _FLAT is None:
        if not FLAT_PATH.is_file():
            raise SystemExit("bf_flat.npy yok — önce: python3 analysis/extract.py --flat")
        a = np.load(FLAT_PATH)
        _FLAT = a - np.median(a)
    return _FLAT


def build_flat(stamp: str) -> np.ndarray:
    """t00'da tüm kuyuların kaba yumuşatılmış BF'sinin piksel bazlı medyanı.
    Hücreler kuyudan kuyuya farklı yerlerde olduğu için medyan onları eler,
    geriye optik aydınlatma profili kalır."""
    acc = []
    for w in all_wells():
        bf = tifffile.imread(bf_path(w, stamp)).astype(np.float32)
        acc.append(ndimage.gaussian_filter(bf, 30.0))
    a = np.median(np.stack(acc), 0)
    OUT.mkdir(parents=True, exist_ok=True)
    np.save(FLAT_PATH, a)
    print(f"→ {FLAT_PATH}  (aralık {a.min():.1f}–{a.max():.1f} gri seviye)")
    return a


# --------------------------------------------------------------- bf segmentation
def bf_masks(bf: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    f = bf.astype(np.float32) - flat()
    sm = ndimage.gaussian_filter(f, BF_SIGMA)
    # zemin = yumuşatılmış görüntünün histogram tepesi. Yumuşatma zemin tepesini
    # daraltır; ham görüntüde gürültülü zemin yayılıp tepe koyu bir sferoide kayabiliyor.
    h, e = np.histogram(sm, bins=512, range=(0, 256))
    floor = float(e[int(np.argmax(h))] + 0.25)
    d = floor - sm

    fine = ndimage.binary_opening(d > BF_THR, np.ones((3, 3)))
    lab, _ = ndimage.label(ndimage.binary_closing(fine, np.ones((7, 7))))
    sz = np.bincount(lab.ravel())
    sz[0] = 0
    fine = np.isin(lab, np.where(sz >= BF_MIN_PX)[0])

    terr = ndimage.binary_fill_holes(
        ndimage.binary_closing(fine, np.ones((BF_CLOSE_TERR, BF_CLOSE_TERR))))
    lab2, _ = ndimage.label(terr)
    sz2 = np.bincount(lab2.ravel())
    sz2[0] = 0
    terr = np.isin(lab2, np.where(sz2 >= BF_MIN_TERR)[0])

    info = {"bf_floor": round(floor, 1),
            "bf_floor_offset": round(floor - NORMAL_FLOOR, 1),
            "bf_depth_p99": round(float(np.percentile(d, 99)), 2),
            "bf_depth_mean": round(float(d[d > 0].mean()) if (d > 0).any() else 0.0, 2)}
    return fine, terr, info


def bf_particles(bf: np.ndarray, floor: float) -> dict:
    """Tek hücre boyutlu koyu nesneler — kapama *yapmadan* (kapama komşu hücreleri
    birleştirir). Etiketsiz bağışıklık hücresi yoğunluğu için vekil."""
    f = ndimage.gaussian_filter(bf.astype(np.float32) - flat(), 1.0)
    m = (floor - f) > BF_THR
    lab, n = ndimage.label(m)
    if n == 0:
        return {"bf_particles": 0, "bf_particle_area_frac": 0.0,
                "bf_particle_med_px": 0.0, "bf_obj_total": 0}
    sz = np.bincount(lab.ravel())[1:]
    sel = sz[(sz >= SMALL_LO) & (sz <= SMALL_HI)]
    return {"bf_particles": int(sel.size),
            "bf_particle_area_frac": round(float(sel.sum()) / m.size, 6),
            "bf_particle_med_px": round(float(np.median(sel)), 1) if sel.size else 0.0,
            "bf_obj_total": int(n)}


def focus_score(bf: np.ndarray) -> float:
    return round(float(np.var(ndimage.laplace(bf.astype(np.float32)))), 2)


# ------------------------------------------------------------ fluorescence pass
def _min_size(mask: np.ndarray, ch: str) -> np.ndarray:
    """Asgari boyuttan küçük bağlı bileşenleri atar (bkz. MIN_OBJ_PX)."""
    n_min = MIN_OBJ_PX.get(ch, 1)
    if n_min <= 1 or not mask.any():
        return mask
    lab, n = ndimage.label(mask)
    if not n:
        return mask
    sz = np.bincount(lab.ravel())
    sz[0] = 0
    return np.isin(lab, np.where(sz >= n_min)[0])


def channel_pass(well: str, ch: str, stamp: str, thr: dict[str, float],
                 terr: np.ndarray) -> dict | None:
    paths = plane_paths(well, ch, stamp)
    if not paths:
        return None
    H, W = terr.shape
    nz = len(paths)
    mip = np.zeros((H, W), np.float32)
    area_z, area_z_in, sum_z, bg_z = [], [], [], []
    binned = np.zeros((nz, H // 2, W // 2), bool)

    for zi, p in enumerate(paths):
        a = tifffile.imread(p).astype(np.float32)
        bgv = float(np.median(a))
        a -= bgv                                   # düzlem başına arkaplan
        m = _min_size(a > thr["main"], ch)
        area_z.append(int(m.sum()))
        area_z_in.append(int((m & terr).sum()))
        sum_z.append(round(float(a[m].sum()), 1))
        bg_z.append(round(bgv, 3))
        np.maximum(mip, a, out=mip)
        binned[zi] = m[: H // 2 * 2, : W // 2 * 2].reshape(H // 2, 2, W // 2, 2).any((1, 3))

    mask = _min_size(mip > thr["main"], ch)
    out = {
        f"{ch}_bg_med": round(float(np.median(bg_z)), 3),
        f"{ch}_bg_drift": round(float(np.max(bg_z) - np.min(bg_z)), 3),
        f"{ch}_area_frac": round(float(mask.mean()), 6),
        f"{ch}_area_frac_lo": round(float((mip > thr["lo"]).mean()), 6),
        f"{ch}_area_frac_hi": round(float((mip > thr["hi"]).mean()), 6),
        f"{ch}_int_mean": round(float(mip[mask].mean()), 3) if mask.any() else 0.0,
        f"{ch}_int_sum": round(float(mip[mask].sum()), 1),
        f"{ch}_p99": round(float(np.percentile(mip, 99)), 3),
        f"{ch}_p999": round(float(np.percentile(mip, 99.9)), 3),
        f"{ch}_vox_frac": round(float(np.sum(area_z)) / (nz * H * W), 7),
        f"{ch}_area_by_z": area_z,
        f"{ch}_area_by_z_in": area_z_in,
        f"{ch}_sum_by_z": sum_z,
        f"{ch}_bg_by_z": bg_z,
    }
    az = np.asarray(area_z, float)
    if az.sum() > 0:
        w = az / az.sum()
        zc = float((np.arange(nz) * w).sum())
        out[f"{ch}_mean_z"] = round(zc, 2)
        out[f"{ch}_sd_z"] = round(float(np.sqrt(((np.arange(nz) - zc) ** 2 * w).sum())), 2)
        out[f"{ch}_top_z"] = int(np.argmax(az))
        out[f"{ch}_z_conc3"] = round(float(np.sort(w)[::-1][:3].sum()), 3)
    else:
        out.update({f"{ch}_mean_z": None, f"{ch}_sd_z": None,
                    f"{ch}_top_z": None, f"{ch}_z_conc3": None})

    lab, n = ndimage.label(mask)
    if n:
        sz = np.bincount(lab.ravel())[1:]
        idx = np.where(sz >= 3)[0] + 1
        if idx.size:
            mi = np.asarray(ndimage.mean(mip, lab, idx))
            s = sz[idx - 1]
            out[f"{ch}_nobj"] = int(idx.size)
            out[f"{ch}_obj_med_px"] = round(float(np.median(s)), 1)
            out[f"{ch}_obj_p90_px"] = round(float(np.percentile(s, 90)), 1)
            out[f"{ch}_obj_med_int"] = round(float(np.median(mi)), 3)
            out[f"{ch}_obj_p90_int"] = round(float(np.percentile(mi, 90)), 3)
            # boy sınıflarına göre alan payı: küçük parlak (T hücresi tipi) vs iri
            tot = float(s.sum())
            out[f"{ch}_objfrac_lt10"] = round(float(s[s < 10].sum() / tot), 4)
            out[f"{ch}_objfrac_10_50"] = round(float(s[(s >= 10) & (s < 50)].sum() / tot), 4)
            out[f"{ch}_objfrac_ge50"] = round(float(s[s >= 50].sum() / tot), 4)
        else:
            n = 0
    if not n:
        for k, v in (("nobj", 0), ("obj_med_px", 0.0), ("obj_p90_px", 0.0),
                     ("obj_med_int", 0.0), ("obj_p90_int", 0.0), ("objfrac_lt10", None),
                     ("objfrac_10_50", None), ("objfrac_ge50", None)):
            out[f"{ch}_{k}"] = v
    return {"scalars": out, "mask": mask, "mip": mip, "binned": binned}


# ------------------------------------------------------------------ one sample
def analyze(well: str, stamp: str, t_index: int) -> dict:
    thr = thresholds()
    bf = tifffile.imread(bf_path(well, stamp))
    H, W = bf.shape
    px_um2 = UM_PER_PX ** 2

    fine, terr, bfinfo = bf_masks(bf)
    rec: dict = {"well": well, "t": t_index, "stamp": stamp, "H": H, "W": W,
                 "um_per_px": UM_PER_PX, "field_mm2": round(H * W * px_um2 / 1e6, 3),
                 **bfinfo, "bf_focus": focus_score(bf)}
    rec.update(bf_particles(bf, bfinfo["bf_floor"]))

    lab_org, n_org = ndimage.label(terr)
    sizes = np.bincount(lab_org.ravel())
    sizes[0] = 0
    lab_f, n_fine = ndimage.label(fine)
    sz_f = np.bincount(lab_f.ravel())[1:] if n_fine else np.zeros(0)
    rec.update({
        "bf_fine_frac": round(float(fine.mean()), 5),
        "bf_fine_nobj": int(n_fine),
        "bf_fine_med_px": round(float(np.median(sz_f)), 1) if n_fine else 0.0,
        "bf_terr_frac": round(float(terr.mean()), 5),
        "bf_terr_mm2": round(float(terr.sum()) * px_um2 / 1e6, 4),
        "bf_terr_nobj": int(n_org),
        "bf_largest_px": int(sizes.max()) if n_org else 0,
        "bf_largest_frac": round(float(sizes.max()) / max(sizes.sum(), 1), 3) if n_org else 0.0,
        # doluluk: teritoryanın ne kadarı gerçekten koyu madde — kompakt sferoid ~1
        "bf_solidity": round(float(fine.sum()) / max(float(terr.sum()), 1), 3),
        "confluent": bool(terr.mean() > 0.90),
    })
    for lo, hi, name in ((200, 1000, "tiny"), (1000, 10000, "small"),
                         (10000, 100000, "mid"), (100000, 10 ** 12, "big")):
        rec[f"bf_n_{name}"] = int(((sizes >= lo) & (sizes < hi)).sum())

    # işaretli uzaklık: organoid teritoryası sınırından µm (negatif = içeride)
    if terr.any() and not terr.all():
        sd_um = (ndimage.distance_transform_edt(~terr)
                 - ndimage.distance_transform_edt(terr)) * UM_PER_PX
    else:
        sd_um = np.full(terr.shape, np.inf if not terr.any() else -np.inf, np.float32)
    band_idx = np.digitize(sd_um, BANDS_UM[1:-1])
    band_area = np.bincount(band_idx.ravel(), minlength=len(BANDS_UM) - 1)
    rec["band_area_px"] = band_area.tolist()

    chans: dict[str, dict] = {}
    for ch in CH:
        r = channel_pass(well, ch, stamp, thr[ch], terr)
        if r is None:
            return {"well": well, "t": t_index, "error": f"{ch} kanalı eksik"}
        chans[ch] = r
        rec.update(r["scalars"])

    # --- organoide göre konum -------------------------------------------------
    org_frac = float(terr.mean())
    for ch in CH:
        m = chans[ch]["mask"]
        tot = int(m.sum())
        inside = int((m & terr).sum())
        rec[f"{ch}_frac_in_organoid"] = round(inside / tot, 4) if tot else None
        if tot and 0 < org_frac < 1:
            d_out = (tot - inside) / (1 - org_frac)
            rec[f"{ch}_enrich_organoid"] = round((inside / org_frac) / d_out, 3) if d_out > 0 else None
        else:
            rec[f"{ch}_enrich_organoid"] = None
        cnt = np.bincount(band_idx[m].ravel(), minlength=len(BANDS_UM) - 1)
        rec[f"{ch}_band_px"] = cnt.tolist()
        overall = tot / m.size if tot else np.nan
        with np.errstate(divide="ignore", invalid="ignore"):
            dens = np.where(band_area > 0, cnt / np.maximum(band_area, 1), np.nan)
        rec[f"{ch}_band_enrich"] = ([None if not np.isfinite(v) else round(float(v / overall), 3)
                                     for v in dens] if tot else [None] * len(dens))
        sdv = sd_um[m]
        rec[f"{ch}_median_signed_dist_um"] = round(float(np.median(sdv)), 1) if sdv.size else None

    # --- kanallar arası örtüşme: ölüm kime ait -------------------------------
    st = np.ones((3, 3), bool)
    dil = {ch: ndimage.binary_dilation(chans[ch]["mask"], st, 2) for ch in CH}
    nm = chans["nir"]["mask"]
    n_tot = int(nm.sum())
    on_g = int((nm & dil["green"]).sum())
    on_o = int((nm & dil["orange"]).sum())
    rec.update({
        "nir_px": n_tot,
        "nir_on_green_frac": round(on_g / n_tot, 4) if n_tot else None,
        "nir_on_orange_frac": round(on_o / n_tot, 4) if n_tot else None,
        "nir_on_both_frac": round(int((nm & dil["green"] & dil["orange"]).sum()) / n_tot, 4)
        if n_tot else None,
        "nir_on_neither_frac": round(int((nm & ~dil["green"] & ~dil["orange"]).sum()) / n_tot, 4)
        if n_tot else None,
        "nir_in_organoid_frac": round(int((nm & terr).sum()) / n_tot, 4) if n_tot else None,
        "orange_on_green_frac": round(int((chans["orange"]["mask"] & dil["green"]).sum())
                                      / max(int(chans["orange"]["mask"].sum()), 1), 4),
    })
    rec["death_index_tumour"] = round(on_g / max(int(chans["green"]["mask"].sum()), 1), 5)
    rec["death_index_tcell"] = round(on_o / max(int(chans["orange"]["mask"].sum()), 1), 5)

    # --- 3B: derinlikte organoid içi/dışı ------------------------------------
    tb = terr[: H // 2 * 2, : W // 2 * 2].reshape(H // 2, 2, W // 2, 2).any((1, 3))
    for ch in CH:
        b = chans[ch]["binned"]
        tot_v = int(b.sum())
        v_in = b & tb
        rec[f"{ch}_vox_in_organoid_frac"] = round(int(v_in.sum()) / tot_v, 4) if tot_v else None
        zin = v_in.sum((1, 2)).astype(float)
        rec[f"{ch}_mean_z_in"] = (round(float((np.arange(len(zin)) * zin).sum() / zin.sum()), 2)
                                  if zin.sum() else None)
        zout = (b & ~tb).sum((1, 2)).astype(float)
        rec[f"{ch}_mean_z_out"] = (round(float((np.arange(len(zout)) * zout).sum() / zout.sum()), 2)
                                   if zout.sum() else None)

    # --- organoid başına satır ------------------------------------------------
    big = np.where(sizes >= MIN_ORG_PX)[0]
    orgs = []
    if big.size:
        gm, om, nmk = chans["green"]["mask"], chans["orange"]["mask"], chans["nir"]["mask"]
        finef = ndimage.sum(fine.astype(np.float32), lab_org, big)
        gsum = ndimage.sum(gm.astype(np.float32), lab_org, big)
        osum = ndimage.sum(om.astype(np.float32), lab_org, big)
        nsum = ndimage.sum(nmk.astype(np.float32), lab_org, big)
        gint = ndimage.sum(chans["green"]["mip"] * gm, lab_org, big)
        oint = ndimage.sum(chans["orange"]["mip"] * om, lab_org, big)
        coms = ndimage.center_of_mass(terr, lab_org, big)
        for k, li in enumerate(big):
            a = int(sizes[li])
            orgs.append({
                "id": int(li), "area_px": a, "area_um2": round(a * px_um2, 1),
                "eq_diam_um": round(2 * np.sqrt(a / np.pi) * UM_PER_PX, 1),
                "solidity": round(float(finef[k]) / a, 3),
                "cy": round(float(coms[k][0]), 1), "cx": round(float(coms[k][1]), 1),
                "green_px": int(gsum[k]), "green_cov": round(float(gsum[k]) / a, 4),
                "green_int": round(float(gint[k]), 1),
                "orange_px": int(osum[k]), "orange_cov": round(float(osum[k]) / a, 4),
                "orange_int": round(float(oint[k]), 1),
                "nir_px": int(nsum[k]), "nir_cov": round(float(nsum[k]) / a, 5)})
    rec["organoids"] = orgs
    rec["n_organoids_scored"] = len(orgs)
    if orgs:
        cov = np.array([o["green_cov"] for o in orgs])
        ar = np.array([o["area_px"] for o in orgs], float)
        for tag, lim in (("001", 0.01), ("005", 0.05)):
            rec[f"green_pos_organoid_frac_{tag}"] = round(float((cov > lim).mean()), 4)
            rec[f"green_pos_area_frac_{tag}"] = round(float(ar[cov > lim].sum() / ar.sum()), 4)
        rec["organoid_med_area_um2"] = round(float(np.median([o["area_um2"] for o in orgs])), 1)
        rec["organoid_med_diam_um"] = round(float(np.median([o["eq_diam_um"] for o in orgs])), 1)
        rec["organoid_p90_diam_um"] = round(
            float(np.percentile([o["eq_diam_um"] for o in orgs], 90)), 1)
        rec["organoid_med_green_cov"] = round(float(np.median(cov)), 4)
        rec["organoid_med_orange_cov"] = round(
            float(np.median([o["orange_cov"] for o in orgs])), 4)
    else:
        for k in ("green_pos_organoid_frac_001", "green_pos_area_frac_001",
                  "green_pos_organoid_frac_005", "green_pos_area_frac_005",
                  "organoid_med_area_um2", "organoid_med_diam_um", "organoid_p90_diam_um",
                  "organoid_med_green_cov", "organoid_med_orange_cov"):
            rec[k] = None
    return rec


# ------------------------------------------------------------------------ run
def _job(a):
    well, stamp, ti, force = a
    f = OUT / f"{well}_t{ti:02d}.json"
    if f.is_file() and not force:
        try:
            return json.loads(f.read_text())
        except Exception:
            pass
    try:
        rec = analyze(well, stamp, ti)
    except Exception as e:
        rec = {"well": well, "t": ti, "error": repr(e)}
    OUT.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rec))
    return rec


def timepoints() -> list[str]:
    d = next(p for p in sorted((DATA / "wells").iterdir()) if p.is_dir())
    return sorted({f.name.split("_1_")[1].split("_plane")[0]
                   for f in (d / "green").iterdir() if "_plane" in f.name})


def all_wells() -> list[str]:
    return sorted(p.name for p in (DATA / "wells").iterdir() if p.is_dir())


def plate_map() -> dict[str, dict]:
    with open(DATA / "plate_map.csv", newline="") as fh:
        return {r["well"]: r for r in csv.DictReader(fh)}


def hours() -> dict[int, float]:
    f = DATA / "timepoints.csv"
    if not f.is_file():
        return {}
    with open(f, newline="") as fh:
        return {int(r["t"][1:]): float(r["hours_from_start"]) for r in csv.DictReader(fh)}


META_COLS = ["well", "t", "hours", "row", "col", "condition", "coculture", "compound",
             "concentration", "has_tcells", "has_macrophages", "has_cafs"]


def meta_for(well: str, ti: int, pm: dict, hrs: dict) -> dict:
    m = pm.get(well, {})
    return {"well": well, "t": ti, "hours": hrs.get(ti, ""),
            "row": m.get("row", ""), "col": m.get("col", ""),
            "condition": m.get("condition", ""), "coculture": m.get("coculture", ""),
            "compound": m.get("compound", ""), "concentration": m.get("concentration", ""),
            "has_tcells": "yes" if m.get("t_cells") else "no",
            "has_macrophages": "yes" if m.get("macrophages") else "no",
            "has_cafs": "yes" if m.get("cafs") else "no"}


def write_tables(recs: list[dict]):
    pm, hrs = plate_map(), hours()
    recs = sorted(recs, key=lambda r: (r["well"], r["t"]))
    skip = {"organoids"}
    cols: list[str] = []
    for r in recs:
        for k, v in r.items():
            if k in skip or k in META_COLS:
                continue
            if isinstance(v, list):
                for i in range(len(v)):
                    c = f"{k}_{i}"
                    if c not in cols:
                        cols.append(c)
            elif k not in cols:
                cols.append(k)
    fields = META_COLS + cols
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "features.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in recs:
            row = meta_for(r["well"], r["t"], pm, hrs)
            for k, v in r.items():
                if k in skip or k in META_COLS:
                    continue
                if isinstance(v, list):
                    for i, x in enumerate(v):
                        row[f"{k}_{i}"] = x
                else:
                    row[k] = v
            w.writerow(row)
    ocols = ["well", "t", "hours", "condition", "coculture", "compound", "has_tcells",
             "has_macrophages", "has_cafs", "id", "area_px", "area_um2", "eq_diam_um",
             "solidity", "cy", "cx", "green_px", "green_cov", "green_int", "orange_px",
             "orange_cov", "orange_int", "nir_px", "nir_cov"]
    with open(OUT / "organoids.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=ocols, extrasaction="ignore")
        w.writeheader()
        for r in recs:
            base = meta_for(r["well"], r["t"], pm, hrs)
            for o in r.get("organoids", []):
                w.writerow({**base, **o})
    print(f"→ {OUT/'features.csv'}  ({len(recs)} satır, {len(fields)} kolon)")
    print(f"→ {OUT/'organoids.csv'}")


def run_check(jobs: int):
    pm, stamps = plate_map(), timepoints()
    ws = ["A01", "A02", "A03", "A04", "B01", "B02", "B03", "B04"]
    tasks = [(w, stamps[-1], len(stamps) - 1, True) for w in ws]
    recs = {}
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for r in ex.map(_job, tasks):
            recs[r["well"]] = r
    print(f'\n{"kuyu":5s} {"koşul":16s} {"BF ter%":>7s} {"organoid":>8s} {"med çap":>8s} '
          f'{"green+%":>8s} {"orange%":>8s} {"T org.içi":>10s} {"T zeng.":>8s} {"NIR%":>7s}')
    for w in ws:
        r = recs[w]
        if r.get("error"):
            print(f"{w:5s} HATA {r['error']}")
            continue
        c = pm[w]["coculture"] + ("+T" if pm[w]["t_cells"] else "")
        print(f'{w:5s} {c:16s} {100*r["bf_terr_frac"]:7.1f} {r["n_organoids_scored"]:8d} '
              f'{(r["organoid_med_diam_um"] or 0):8.0f} '
              f'{100*(r["green_pos_organoid_frac_001"] or 0):8.1f} '
              f'{100*r["orange_area_frac"]:8.2f} '
              f'{100*(r["orange_frac_in_organoid"] or 0):10.1f} '
              f'{(r["orange_enrich_organoid"] or 0):8.2f} {100*r["nir_area_frac"]:7.3f}')
    print("\ngreen+% = BF'de görülen organoidlerin yüzde kaçında green sinyali var (kapsama >%1)")
    print("T zeng. = organoid içi orange yoğunluğu / dışı. 1 = rastgele, >1 zenginleşme")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wells", type=lambda v: [x.strip() for x in v.split(",")])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--t", default="all")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--flat", action="store_true", help="aydınlatma referansını üret")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--tables-only", action="store_true")
    a = ap.parse_args()

    stamps = timepoints()
    if a.flat:
        build_flat(stamps[0])
        return
    if a.check:
        run_check(a.jobs)
        return
    if a.tables_only:
        recs = [json.loads(f.read_text()) for f in sorted(OUT.glob("*_t*.json"))]
        write_tables([r for r in recs if not r.get("error")])
        return

    wells = all_wells() if a.all else (a.wells or [])
    if not wells:
        ap.error("--all, --wells, --check veya --flat gerekli")
    if a.t == "all":
        ts = list(range(len(stamps)))
    elif "-" in a.t:
        lo, hi = a.t.split("-")
        ts = list(range(int(lo), int(hi) + 1))
    else:
        ts = [int(x) for x in a.t.split(",")]

    tasks = [(w, stamps[t], t, a.force) for w in wells for t in ts]
    print(f"{len(wells)} kuyu × {len(ts)} zaman = {len(tasks)} örnek, {a.jobs} işlem")
    t0, recs, done = time.time(), [], 0
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        futs = [ex.submit(_job, t) for t in tasks]
        for f in as_completed(futs):
            recs.append(f.result())
            done += 1
            if done % 25 == 0 or done == len(tasks):
                el = time.time() - t0
                print(f"  {done}/{len(tasks)}  {el/60:.1f} dk  "
                      f"kalan ~{el/done*(len(tasks)-done)/60:.1f} dk", flush=True)
    errs = [r for r in recs if r.get("error")]
    if errs:
        print(f"\n{len(errs)} örnek başarısız, ilk 5:")
        for r in errs[:5]:
            print(f"  {r['well']} t{r['t']:02d}: {r['error']}")
    write_tables([r for r in recs if not r.get("error")])


if __name__ == "__main__":
    main()
