#!/usr/bin/env python3
"""Kuyu başına 3B ölçüm: hangi hücre, nerede, ne kadar.

Aynı soruyu birbirinden bağımsız üç uzamsal eksende yanıtlar:

  derinlik     — z katmanı başına sinyal                        `by_z`
  yanal        — organoid kenarına işaretli uzaklık (içerisi −)  `bands`
  ikisi birden — z × uzaklık matrisi                            `zband`

`zband` ikisini birleştirir: "T hücreleri var" demek yetmez, hangi derinlikte ve
kenardan ne kadar içeride oldukları ayrı bilgidir. Kuyu sayfasında artık
çizilmiyor (ısı haritası okunmuyordu, kaldırıldı); ölçüm önbellekte duruyor.

Eşikler, arkaplan çıkarma, BF maskesi ve bant kenarları `analysis/extract.py`'den
birebir alınır — buradaki sayılar `analysis/out/` altındaki analizlerle aynı
tanımı kullanır, yeniden yorumlanmış bir ölçüm değildir.

Neden dome değil de işaretli uzaklık: kuyuların çoğunda tek bir kütle yok. BF
teritoryasının en büyük bileşeni B02'de %97 ama B01'de %16 — orada "merkezden
uzaklık" diye bir şey tanımlı değil. İşaretli uzaklık her iki durumda da çalışır.
Dome yalnızca tek kütle baskın olduğunda (`dome.dominant`) ayrıca uydurulur ve
3B sahnede sınır olarak çizilir.
"""
from __future__ import annotations

import base64
import gzip
import sys
from pathlib import Path

import numpy as np
import tifffile
from scipy import ndimage

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT / "viewer"))

import extract as E            # noqa: E402  eşikler, yollar, BF maskeleri, bant kenarları
import dome as D               # noqa: E402  radyal uyum

CH = ("green", "orange", "nir")

# Önbellek şeması. Ölçümün ürettiği alanlar değiştiğinde artırılır; build.py
# eski şemayla yazılmış bir kuyuyu `--force` beklemeden yeniden ölçer. Aksi
# hâlde yeni bir alan (ör. `vox_focus`) sayfada sessizce yok sayılır ve 3B sahne
# eski, sütunlu görünüme geri düşer.
SCHEMA = 3                     # 2: vox_focus / focus_by_z eklendi; 3: vox_focus tam çözünürlük

BIN_VOX = 2                    # 3B bulut için XY toplama → 5,6 µm/voksel
BIN_MAP = 4                    # BF ayak izi haritası → 11,2 µm/piksel

# extract.py ile aynı bant kenarları (µm; negatif = organoid teritoryası içi)
BANDS_UM = E.BANDS_UM
BAND_LABELS = ["<−150", "−150…−100", "−100…−50", "−50…−20", "−20…0",
               "0…20", "20…50", "50…100", "100…200", "200…400", ">400"]
# Sayfa metni İngilizce; eksi işareti tipografik minus (U+2212), kısa çizgi değil.
BAND_LABELS_EN = ["< −150", "−150 to −100", "−100 to −50", "−50 to −20", "−20 to 0",
                  "0 to 20", "20 to 50", "50 to 100", "100 to 200", "200 to 400",
                  "> 400"]

# Tek kütlenin "baskın" sayılması için teritoryanın en büyük bileşende olması
# gereken payı. Altındaysa kuyu çok-organoidlidir ve radyal çerçeve anlamsızdır.
DOMINANT_FRAC = 0.50


def _bin_sum(mask: np.ndarray, b: int) -> np.ndarray:
    """Maskeyi b×b bloklara toplar; değer = blokta kaç piksel sinyalli (0…b²)."""
    h, w = mask.shape[0] // b, mask.shape[1] // b
    return mask[: h * b, : w * b].reshape(h, b, w, b).sum((1, 3)).astype(np.uint8)


def _pack(acc: np.ndarray) -> str:
    """Seyrek voksel kübü → delta-kodlanmış indeks + değer, gzip, base64.

    Delta kodlama gzip'e ~7× kazandırıyor: indeksler artan ve kümelenmiş, farkları
    küçük ve tekrarlı. En yoğun kuyuda zaman noktası başına ~90 kB kalıyor, yani
    13 zaman noktası tek bir HTML dosyasına sığıyor — sunucu gerekmiyor.
    """
    idx = np.flatnonzero(acc).astype(np.uint32)
    val = acc.ravel()[idx]
    delta = np.diff(np.concatenate([[0], idx])).astype(np.uint32)
    blob = np.uint32(idx.size).tobytes() + delta.tobytes() + val.tobytes()
    return base64.b64encode(gzip.compress(blob, 6)).decode("ascii")


def _pack_map(m: np.ndarray) -> str:
    return base64.b64encode(gzip.compress(np.ascontiguousarray(m).tobytes(), 6)).decode("ascii")


def _dome(terr: np.ndarray, um: float) -> dict | None:
    """Tek kütle baskınsa onun merkezi ve R90'ı; değilse baskın olmadığını söyler.

    Uyum **en büyük bileşene** yapılır, tüm teritoryaya değil: dağınık döküntü ve
    ayrı organoidler ağırlık merkezini kadrajın ortasına çeker ve R90 kuyunun
    değil kadrajın ölçüsü olur (B04'te tüm teritorya R90=1689 µm, en büyük bileşen
    1053 µm).
    """
    lab, n = ndimage.label(terr)
    if not n:
        return None
    sz = np.bincount(lab.ravel())
    sz[0] = 0
    big_id = int(sz.argmax())
    frac = float(sz.max() / sz.sum())
    big = lab == big_id
    d = D.fit_dome(big.astype(np.float32), um)
    if d is None:
        return None
    d = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in d.items()}
    d["largest_frac"] = round(frac, 3)
    d["dominant"] = bool(frac >= DOMINANT_FRAC)
    d["area_mm2_mask"] = round(float(big.sum()) * um ** 2 / 1e6, 4)
    d["n_components"] = int(n)
    return d


def measure_frame(well: str, stamp: str, t_index: int) -> dict:
    """Bir kuyu-zaman noktası: voksel bulutu + üç eksende dağılım."""
    thr = E.thresholds()
    um = E.UM_PER_PX

    bf = tifffile.imread(E.bf_path(well, stamp))
    fine, terr, bfinfo = E.bf_masks(bf)
    H, W = bf.shape
    px_mm2 = um ** 2 / 1e6

    # --- işaretli uzaklık: organoid kenarına, içerisi negatif ---------------
    if terr.any() and not terr.all():
        sd_um = (ndimage.distance_transform_edt(~terr)
                 - ndimage.distance_transform_edt(terr)) * um
    else:
        sd_um = np.full((H, W), np.inf if not terr.any() else -np.inf, np.float32)
    band_idx = np.digitize(sd_um, BANDS_UM[1:-1]).astype(np.int16)
    nb = len(BANDS_UM) - 1
    band_area_px = np.bincount(band_idx.ravel(), minlength=nb)[:nb]

    vox, vox_focus, by_z, by_z_in, zband, bands, totals = {}, {}, {}, {}, {}, {}, {}
    focus_by_z = {}
    nz = 0
    for ch in CH:
        paths = E.plane_paths(well, ch, stamp)
        nz = len(paths)
        acc = None
        mip = np.zeros((H, W), np.float32)
        best_v = np.full((H, W), -np.inf, np.float32)   # en parlak düzlem
        best_z = np.zeros((H, W), np.int16)             # ve hangi düzlem olduğu
        az, az_in = [], []
        zb = np.zeros((nz, nb), np.int64)
        for zi, p in enumerate(paths):
            a = tifffile.imread(p).astype(np.float32)
            a -= float(np.median(a))          # düzlem başına arkaplan (z boyunca kayıyor)
            up = a > best_v
            best_v = np.where(up, a, best_v)
            best_z = np.where(up, zi, best_z).astype(np.int16)
            m = E._min_size(a > thr[ch]["main"], ch)
            az.append(int(m.sum()))
            az_in.append(int((m & terr).sum()))
            zb[zi] = np.bincount(band_idx[m], minlength=nb)[:nb]
            np.maximum(mip, a, out=mip)
            c = _bin_sum(m, BIN_VOX)
            if acc is None:
                acc = np.zeros((nz,) + c.shape, np.uint8)
            acc[zi] = c

        mask = E._min_size(mip > thr[ch]["main"], ch)
        tot = int(mask.sum())

        # --- odak düzlemine indirgenmiş bulut ------------------------------
        # 4× objektifin odak derinliği onlarca mikron: tek bir nesne birkaç
        # düzlemde birden eşiği geçiyor ve 3B'de dikey bir sütuna dönüşüyor.
        # Ölçülen yayılma bu kuyularda 2,6–3,0×. Her XY konumu en parlak
        # olduğu tek düzleme yerleştirilince sütunlar kayboluyor ve geriye
        # nesnenin gerçekten bulunduğu yüzey kalıyor.
        # Odak bulutu **tam çözünürlükte** (piksel = voksel, 2,8 µm): her XY
        # konumu tek bir düzlemde olduğundan voksel sayısı MIP maskesinin piksel
        # sayısı kadar ve delta kodlama bunu küçük tutuyor. 2×2 toplama, tek
        # piksellik zayıf hücreleri çeyrek ağırlığa düşürüp görünmez kılıyordu;
        # burada her hücre olduğu şekilde, olduğu piksellerle çizilir.
        fc = np.zeros((nz, H, W), np.uint8)
        ys, xs = np.nonzero(mask)
        if ys.size:
            fc[best_z[ys, xs], ys, xs] = 1
        vox_focus[ch] = _pack(fc)
        focus_by_z[ch] = np.bincount(best_z[mask], minlength=nz).tolist() if tot else [0] * nz
        cnt = np.bincount(band_idx[mask], minlength=nb)[:nb]

        vox[ch] = _pack(acc)
        by_z[ch] = az
        by_z_in[ch] = az_in
        zband[ch] = zb.tolist()
        # Bant başına yoğunluk: bantlar çok farklı alanlar kaplıyor, ham piksel
        # sayısı her zaman "çoğu dışarıda" derdi. Zenginleşme = bant yoğunluğu /
        # kuyu geneli yoğunluk; 1,0 = rastgele dağılım.
        overall = tot / mask.size if tot else np.nan
        bands[ch] = {
            "px": cnt.tolist(),
            "area_mm2": [round(float(c * px_mm2), 5) for c in cnt],
            "enrich": [None if not (a_ > 0 and tot) else round(float((c / a_) / overall), 3)
                       for c, a_ in zip(cnt, band_area_px)],
            "median_signed_dist_um": round(float(np.median(sd_um[mask])), 1) if tot else None,
        }
        n_in = int((mask & terr).sum())
        frac_in = n_in / tot if tot else None
        # Zenginleşme **yuvarlanmamış** sayımlardan hesaplanır. Önce oranı
        # yuvarlayıp sonra bölmek küçük oranlarda (frac_in ≈ 1e-4) bağıl hatayı
        # %60'ın üstüne çıkarıyordu — extract.py ile aynı tanım, aynı sonuç.
        f_terr = float(terr.mean())
        enrich = None
        if tot and 0 < f_terr < 1 and n_in < tot:
            enrich = ((n_in / f_terr) / ((tot - n_in) / (1 - f_terr)))
        totals[ch] = {
            "area_mm2": round(float(tot) * px_mm2, 5),
            "area_frac": round(float(mask.mean()), 6),
            "vox": int(np.sum(az)),
            "px_in_terr": n_in,
            "px_total": tot,
            "frac_in_terr": round(frac_in, 6) if frac_in is not None else None,
            "enrich_terr": None if enrich is None else round(enrich, 3),
        }

    f_terr = float(terr.mean())

    return {
        "t": t_index,
        "stamp": stamp,
        "grid": {"nz": nz, "h": acc.shape[1], "w": acc.shape[2], "bin": BIN_VOX},
        "vox": vox,
        "grid_focus": {"nz": nz, "h": H, "w": W, "bin": 1},
        "vox_focus": vox_focus,
        "focus_by_z": focus_by_z,
        "terr_map": _pack_map(_bin_sum(terr, BIN_MAP)),
        "terr_shape": [terr.shape[0] // BIN_MAP, terr.shape[1] // BIN_MAP],
        "bf": {"terr_frac": round(f_terr, 5),
               "terr_mm2": round(f_terr * H * W * px_mm2, 4),
               "fine_frac": round(float(fine.mean()), 5),
               "floor": bfinfo.get("bf_floor"),
               "floor_offset": bfinfo.get("bf_floor_offset"),
               "focus": round(E.focus_score(bf), 1)},
        "dome": _dome(terr, um),
        "band_area_mm2": [round(float(a * px_mm2), 4) for a in band_area_px],
        "by_z": by_z,
        "by_z_in": by_z_in,
        "zband": zband,
        "bands": bands,
        "totals": totals,
    }


if __name__ == "__main__":
    import json
    import time

    w = sys.argv[1] if len(sys.argv) > 1 else "B04"
    ti = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    t0 = time.time()
    r = measure_frame(w, E.timepoints()[ti], ti)
    d = r["dome"]
    print(f"{w} t{ti}  {time.time() - t0:.1f}s   yük {len(json.dumps(r)) / 1024:.0f} kB")
    print(f"BF teritorya {r['bf']['terr_mm2']} mm² ({d['n_components']} bileşen)")
    print(f"dome: baskın={d['dominant']} en büyük bileşen %{100 * d['largest_frac']:.0f}"
          f"  R50={d['r50_um']:.0f} R90={d['r90_um']:.0f} µm  biçim={d['shape_factor']}")
    for ch in CH:
        t = r["totals"][ch]
        print(f"  {ch:7s} {t['area_mm2']:.4f} mm²  vox={t['vox']:7d}  "
              f"teritoryada %{100 * (t['frac_in_terr'] or 0):.0f}  "
              f"zenginleşme {t['enrich_terr']}  paket {len(r['vox'][ch]) / 1024:.0f} kB")
    print("\nbant zenginleşmesi (organoid içi ← → dışı):")
    print("  " + "  ".join(f"{l:>10s}" for l in BAND_LABELS))
    for ch in CH:
        print(f"  " + "  ".join(f"{('—' if v is None else f'{v:.2f}'):>10s}"
                                for v in r["bands"][ch]["enrich"]) + f"   {ch}")
