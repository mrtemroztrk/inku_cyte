#!/usr/bin/env python3
"""Ölçek ve birimler — tek kaynak.

Bu dosyanın var olma sebebi: **veride kalibrasyon yok.** Aşağıdaki denetim
sonucuna dayanıyor (`python3 analysis/scale.py` ile tekrarlanabilir):

* `XResolution` / `YResolution` = 1207959552/16777216 = **tam 72 dpi**, hem
  brightfield hem floresan tif'lerde, `ResolutionUnit` = inç. 72 dpi bir kütüphane
  varsayılanıdır (extras/ içindeki ekran çıktısı 96 dpi diyor — o da ekran
  varsayılanı). Bu alanlar mikroskop kalibrasyonu taşımıyor.
* Tif etiketlerinde `Software = Incucyte 2025C` dışında cihaz bilgisi yok;
  ImageDescription, OME-XML, ImageJ ya da MicroManager üstverisi yok.
* `plate_map.PlateMap` (ham Incucyte XML) yalnızca hücre tipi, ekim yoğunluğu ve
  bileşik taşıyor; objektif, büyütme ya da piksel boyutu geçmiyor.
* `extras/vid119_B2/` içindeki cihaz kompozitinde gömülü ölçek çubuğu ya da yazı
  yok (saf beyaz piksel oranı %0,18, kenarlarda yazı bloğu yok).

Sonuç: **piksel boyutu bu dosyalardan türetilemez.** Kullanılan değer dışarıdan
gelen bir iddiadır (cihaz arayüzünün alanı 2,91 × 3,94 mm olarak etiketlemesi;
1040 ve 1408 piksele bölününce ikisi de 2,798 veriyor). Doğrulanmadı.

Bunun analiz üzerindeki etkisi
------------------------------
Sonuçların çoğu **kalibrasyondan bağımsız**: alan oranları, zenginleşme oranları,
AUC'ler, korelasyonlar, profil şekilleri ve katman payları hepsi boyutsuz. Piksel
boyutu yalnızca **etiketleri** ölçekler: µm, µm², mm². Kalibrasyon yanlışsa bu
etiketler doğrusal olarak kayar, hiçbir karşılaştırma yön değiştirmez.

Bu yüzden bütün ölçümler **birincil olarak pikselde** saklanıyor; µm değerleri
türetilmiş kolonlar. Gerçek değer tarama protokolünden öğrenilirse:

    INC_UM_PER_PX=2.61 python3 analysis/a2_infiltration.py

tüm µm etiketleri yeniden ölçeklenir; yeniden çıkarım gerekmez (uzaklık bantları
piksel cinsinden sabittir, aşağıya bakın).

z ekseni
--------
**z adımı hiçbir yerde kayıtlı değil** ve veriden çıkarılamıyor. Bu yüzden bu
analizlerde hiçbir derinlik µm cinsinden verilmiyor; derinlik yalnızca **katman
indeksi** ve katman payları olarak raporlanıyor. Hacim (µm³) hiç hesaplanmadı.
(`viewer/analyze.py` varsayılan olarak 10 µm'lik bir z adımı varsayıp µm³ hacim
üretiyor — o kolonlar bu varsayıma bağlıdır, buradaki analizlerde kullanılmadı.)

Floresan yoğunlukları
---------------------
green/orange/nir kanalları float32 ve cihazın kendi kalibre birimlerinde; mutlak
bir fiziksel karşılığı (foton, molekül) yok ve kanallar arası ölçekleri farklı
(green ~0–6, orange ~4–1235, NIR ~0–3). Bu yüzden yoğunluk toplamları yalnızca
**aynı kanal içinde** ve keyfi birim (a.u.) olarak karşılaştırılıyor; kanallar
arası karşılaştırmalar alan/örtüşme üzerinden yapılıyor.
"""
from __future__ import annotations

import os

# Piksel boyutu — DOĞRULANMADI, dışarıdan gelen iddia. INC_UM_PER_PX ile ezilebilir.
UM_PER_PX = float(os.environ.get("INC_UM_PER_PX", "2.798"))
UM_PER_PX_VERIFIED = False
UM_PER_PX_SOURCE = ("cihaz arayüzünün alan etiketi 2,91 × 3,94 mm ÷ 1040 × 1408 px")

# Uzaklık bantlarının **birincil tanımı piksel cinsinden**; µm etiketleri türetilmiş.
# Negatif = organoid teritoryası içi. Bu kenarlar çıkarım sırasında sabitlendi ve
# kalibrasyon değişse de aynı kalır (yalnızca etiketleri değişir).
BAND_EDGES_UM_AT_2798 = (-150.0, -100.0, -50.0, -20.0, 0.0, 20.0, 50.0, 100.0,
                         200.0, 400.0)
BAND_EDGES_PX = tuple(round(e / 2.798, 2) for e in BAND_EDGES_UM_AT_2798)

NZ = 17
Z_STEP_UM = None            # bilinmiyor — kasten None; µm derinlik üretilmiyor


def um(px: float) -> float:
    return px * UM_PER_PX


def um2(px2: float) -> float:
    return px2 * UM_PER_PX ** 2


def band_edges_um() -> tuple[float, ...]:
    """Geçerli kalibrasyona göre bant kenarları."""
    return tuple(round(e * UM_PER_PX, 1) for e in BAND_EDGES_PX)


def band_labels(unit: str = "um") -> list[str]:
    e = band_edges_um() if unit == "um" else BAND_EDGES_PX
    f = "{:.0f}" if unit == "um" else "{:.0f}"
    out = [f"<{f.format(e[0])}"]
    out += [f"{f.format(e[i])}…{f.format(e[i+1])}" for i in range(len(e) - 1)]
    out += [f">{f.format(e[-1])}"]
    return out


def note() -> str:
    """Her özet dosyasının altına konan tek satırlık ölçek beyanı."""
    return (f"Ölçek: **{UM_PER_PX:g} µm/px**. Tif üstverisinde kalibrasyon yok "
            f"(XResolution = tam 72 dpi yer tutucu, plaka XML'inde optik bilgi yok); "
            f"kullanılan değerin kaynağı {UM_PER_PX_SOURCE} ve **doğrulanmadı**. "
            f"Piksel cinsinden "
            "verilen her sayı bu varsayımdan bağımsızdır; µm/µm²/mm² etiketleri "
            "kalibrasyonla doğrusal ölçeklenir ve hiçbir oran, AUC ya da "
            "korelasyonu etkilemez. Farklı bir değer için `INC_UM_PER_PX=...`. "
            "**z adımı bilinmiyor**; derinlik yalnızca katman indeksi olarak verildi.")


def audit():
    """Kalibrasyon iddiasını dosyalara karşı yeniden denetler."""
    from pathlib import Path
    import tifffile

    root = Path(os.environ.get("INC_DATA", Path(__file__).resolve().parent.parent
                               / "data" / "inc_tests"))
    print("ÖLÇEK DENETİMİ\n" + "=" * 60)
    seen = []
    for p in sorted(root.glob("wells/*/*/*.tif"))[:3] + sorted(
            root.glob("extras/*/*.tif"))[:1]:
        with tifffile.TiffFile(p) as tf:
            t = tf.pages[0].tags
            xr = t["XResolution"].value if "XResolution" in t else None
            ru = t["ResolutionUnit"].value if "ResolutionUnit" in t else None
            dpi = xr[0] / xr[1] if xr else None
            desc = "ImageDescription" in t
            seen.append((p.name[:44], dpi, ru, desc))
    print(f'{"dosya":46s} {"dpi":>8s} {"birim":>6s} {"açıklama":>9s}')
    for n, d, r, de in seen:
        print(f"{n:46s} {d if d else '—':>8} {r if r else '—':>6} {str(de):>9s}")
    print("\n72 dpi = kütüphane varsayılanı, 96 dpi = ekran varsayılanı — ikisi de "
          "mikroskop kalibrasyonu değil.")
    pm = root / "plate_map.PlateMap"
    if pm.is_file():
        txt = pm.read_text(errors="ignore").lower()
        hits = [k for k in ("micron", "pixel", "objective", "magnif", "calib", "µm", "scale")
                if k in txt]
        print(f"plate_map.PlateMap içinde optik anahtar kelime: {hits or 'yok'}")
    print(f"\nKullanılan değer: {UM_PER_PX:g} µm/px (doğrulanmadı: "
          f"{not UM_PER_PX_VERIFIED})")
    print(f"Kaynak: {UM_PER_PX_SOURCE}")
    print(f"Bant kenarları (px, sabit): {BAND_EDGES_PX}")
    print(f"Bant kenarları (µm, türetilmiş): {band_edges_um()}")
    print(f"z adımı: {Z_STEP_UM if Z_STEP_UM else 'BİLİNMİYOR — µm derinlik üretilmiyor'}")


if __name__ == "__main__":
    audit()
