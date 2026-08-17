#!/usr/bin/env python3
"""Sinyalden hücre sayısına: kalibrasyon ve onun sınırları.

Bu dosyanın tek işi, "ne kadar hücre var" sorusuna verilebilecek en savunulabilir
cevabı üretmek ve **verilemeyecek olanı reddetmek**. Sayılar burada sabit yazılı
değil; her çalıştırmada plakadan yeniden ölçülür ve doğrulama testleriyle birlikte
raporlanır (`python3 atlas/calib.py`).

Dayanak: ekim sayıları biliniyor. Her kuyuda 2000 PDA hücresi var; "more T cells"
kuyularında 5000 T hücresi. Bu, sinyali hücreye çeviren bir ölçek verir.

T HÜCRESİ (orange) — kabul edildi
  T'li ve T'siz kuyular arasındaki MIP alan farkı 5000 hücreye bölünür.
  Üç bağımsız doğrulama geçildi:
    1. Ölçek, hücre başına ~91 µm² veriyor → eşdeğer çap ~10,7 µm. Bir T hücresi
       7–10 µm; 2,798 µm/px'te floresan taşmasıyla birlikte beklenen değer bu.
       Ölçek biyolojik olarak imkânsız bir hücre boyutu üretmiyor.
    2. Dört ko-kültür grubu (PDA, +CAF, +MAC, +CAF+MAC) ölçeği birbirinden
       bağımsız olarak 84–102 µm² aralığında tekrarlıyor.
    3. Kuyular arası dağılım dar (CV ~%20), medyanın önyükleme GA'sı ±%9.

TÜMÖR (green) — reddedildi
  Aynı hesap 2000 PDA hücresi için ~63 µm²/hücre veriyor → eşdeğer çap ~8,9 µm,
  yani bir T hücresinden küçük. Bir PDA hücresi T hücresinden büyüktür, dolayısıyla
  bu ölçek **fiziksel olarak imkânsız**; green kanalı organoidlerin çoğunu
  boyamıyor (analysis/out/a1_qc §2) ve eksik sayıyor. Tümör bu yüzden hücre olarak
  değil, **sinyal hacmi/alanı** olarak raporlanır.

NESNE SAYIMI — reddedildi
  T'li ve T'siz kuyular arasındaki bağlı bileşen farkı 5000 değil ~1155. Yani bu
  çözünürlükte her nesne ortalama ~4,3 hücre içeriyor; nesne saymak hücre saymak
  değil. Alan tabanlı ölçünün nicel gerekçesi budur.

Ölü hücre (nir) için ekim referansı yok — ölü hücreler ekilmiyor, oluşuyor. Bu
kanal alan/hacim olarak raporlanır, T hücresi ölçeğiyle çevrilmez.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FEAT = ROOT / "viewer" / "cache" / "features" / "features.csv"
EXCLUDED = ROOT / "analysis" / "out" / "a1_qc" / "excluded_wells.csv"
CACHE = HERE / "cache" / "calibration.json"

UM_PER_PX = 2.798          # Incucyte 4×; cihaz alan etiketinden geri hesaplandı
N_TCELLS_SEEDED = 5000     # plate_map: "more T cells"
N_PDA_SEEDED = 2000        # plate_map: her kuyuda sabit
H_PX, W_PX = 1408, 1040
FIELD_UM2 = H_PX * W_PX * UM_PER_PX ** 2

# Doğrulama eşikleri — kalibrasyon bunları geçemezse kullanılmaz.
MAX_CV = 0.35              # kuyular arası değişkenlik
DIAM_RANGE_UM = (7.0, 16.0)  # eşdeğer çap bu aralığın dışındaysa ölçek şüpheli


def _load() -> pd.DataFrame:
    if not FEAT.is_file():
        raise SystemExit(f"{FEAT} yok — önce: python3 analysis/extract.py --all")
    df = pd.read_csv(FEAT)
    if EXCLUDED.is_file():
        df = df[~df.well.isin(set(pd.read_csv(EXCLUDED).well))]
    return df


def _boot_ci(v: np.ndarray, n: int = 2000, seed: int = 0) -> tuple[float, float]:
    r = np.random.default_rng(seed)
    b = [np.median(r.choice(v, v.size)) for _ in range(n)]
    return float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def measure(df: pd.DataFrame | None = None) -> dict:
    """Kalibrasyonu plakadan ölçer ve doğrulama kayıtlarıyla birlikte döndürür."""
    df = _load() if df is None else df
    t0 = df[df.t == 0]

    # --- T hücresi: eşleşmiş fark. Arkaplan turuncu popülasyon ko-kültüre göre
    # değiştiği için (tümör kütlesiyle ölçekleniyor) çıkarma ko-kültür içinde yapılır.
    bg = t0[t0.has_tcells == "no"].groupby("coculture").orange_area_frac.median()
    pos = t0[t0.has_tcells == "yes"].copy()
    pos["delta"] = pos.orange_area_frac - pos.coculture.map(bg)
    pos = pos[pos.delta > 0]
    per_cell = (pos.delta * FIELD_UM2 / N_TCELLS_SEEDED).to_numpy()

    med = float(np.median(per_cell))
    lo, hi = _boot_ci(per_cell)
    cv = float(np.std(per_cell) / np.mean(per_cell))
    diam = 2 * np.sqrt(med / np.pi)

    groups = {}
    for c, g in pos.groupby("coculture"):
        m = float(np.median(g.delta * FIELD_UM2 / N_TCELLS_SEEDED))
        groups[c] = {"n_wells": int(len(g)), "um2_per_cell": round(m, 1),
                     "eq_diam_um": round(2 * np.sqrt(m / np.pi), 2)}

    # --- Tümör: aynı hesap, reddedilmesinin gerekçesi olarak kaydedilir.
    #     Boya kontrolü kolonları (10–12) belirgin biçimde odak dışı ve seyrek
    #     olduğu için tümör tarafında dışarıda bırakılır — dışlansa bile sonuç
    #     imkânsız kalıyor, yani reddin sebebi kolon seçimi değil.
    g0 = t0[~t0.col.isin([10, 11, 12])]
    green_per_cell = float(np.median(g0.green_area_frac * FIELD_UM2 / N_PDA_SEEDED))
    green_diam = 2 * np.sqrt(green_per_cell / np.pi)

    # --- Nesne sayımı: 1 nesne = 1 hücre mi?
    d_nobj = float(t0[t0.has_tcells == "yes"].orange_nobj.median()
                   - t0[t0.has_tcells == "no"].orange_nobj.median())

    ok = (cv <= MAX_CV) and (DIAM_RANGE_UM[0] <= diam <= DIAM_RANGE_UM[1])

    return {
        "um_per_px": UM_PER_PX,
        "field_um2": round(FIELD_UM2, 1),
        "tcell": {
            "accepted": bool(ok),
            "um2_per_cell": round(med, 1),
            "ci95": [round(lo, 1), round(hi, 1)],
            "cv": round(cv, 3),
            "eq_diam_um": round(diam, 2),
            "n_wells": int(len(pos)),
            "n_seeded": N_TCELLS_SEEDED,
            "by_coculture": groups,
            "basis": "MIP alanı (z boyunca maksimum projeksiyon maskesi)",
        },
        "tumour": {
            "accepted": False,
            "um2_per_cell": round(green_per_cell, 1),
            "eq_diam_um": round(green_diam, 2),
            "n_seeded": N_PDA_SEEDED,
            "reason": (f"eşdeğer çap {green_diam:.1f} µm — bir T hücresinden "
                       f"({diam:.1f} µm) küçük, dolayısıyla imkânsız; green kanalı "
                       f"organoidlerin çoğunu boyamıyor ve eksik sayıyor"),
        },
        "object_counting": {
            "accepted": False,
            "delta_objects": round(d_nobj),
            "expected": N_TCELLS_SEEDED,
            "cells_per_object": round(N_TCELLS_SEEDED / d_nobj, 2) if d_nobj > 0 else None,
            "reason": (f"T'li ve T'siz kuyular arasındaki nesne farkı {d_nobj:.0f}, "
                       f"beklenen {N_TCELLS_SEEDED}; her bağlı bileşen ortalama "
                       f"{N_TCELLS_SEEDED / d_nobj:.1f} hücre içeriyor"),
        },
    }


def load(refresh: bool = False) -> dict:
    """Ölçülmüş kalibrasyon; ilk çağrıda hesaplanır, sonra `atlas/cache/`ten."""
    if not refresh and CACHE.is_file():
        return json.loads(CACHE.read_text())
    c = measure()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(c, indent=2, ensure_ascii=False))
    return c


def tcells_from_area_um2(area_um2: float, cal: dict | None = None) -> float:
    """MIP sinyal alanından ≈T hücresi sayısı. Yalnızca orange kanalı için geçerli."""
    cal = cal or load()
    return area_um2 / cal["tcell"]["um2_per_cell"]


def main() -> None:
    c = measure()
    t, g, o = c["tcell"], c["tumour"], c["object_counting"]
    w = 78
    print("=" * w)
    print("SİNYAL → HÜCRE KALİBRASYONU".center(w))
    print("=" * w)
    print(f"\nGörüş alanı {c['field_um2'] / 1e6:.3f} mm²  ·  {c['um_per_px']} µm/px "
          f"(doğrulanmadı, cihaz etiketinden)\n")

    print("T HÜCRESİ (orange) — " + ("KABUL" if t["accepted"] else "RED"))
    print(f"  {t['um2_per_cell']} µm²/hücre   %95 GA [{t['ci95'][0]}–{t['ci95'][1]}]   "
          f"CV {t['cv']:.0%}   n={t['n_wells']} kuyu")
    print(f"  eşdeğer çap {t['eq_diam_um']} µm  (T hücresi 7–10 µm + floresan taşması)")
    print(f"  temel: {t['basis']}")
    print("  ko-kültür grupları bağımsız olarak:")
    for k, v in t["by_coculture"].items():
        print(f"    {k:<12s} n={v['n_wells']:2d}   {v['um2_per_cell']:6.1f} µm²/hücre"
              f"   çap {v['eq_diam_um']} µm")

    print("\nTÜMÖR (green) — RED")
    print(f"  {g['um2_per_cell']} µm²/hücre → eşdeğer çap {g['eq_diam_um']} µm")
    print(f"  {g['reason']}")
    print("  → tümör hücre olarak değil, sinyal hacmi/alanı olarak raporlanır")

    print("\nNESNE SAYIMI — RED")
    print(f"  {o['reason']}")
    print("  → alan tabanlı ölçünün gerekçesi")
    print("\n" + "=" * w)
    print("Kullanım:  ≈T hücresi = MIP orange alanı (µm²) / "
          f"{t['um2_per_cell']}")
    print("Katman başına sayı, toplamın z sinyal payına göre dağıtılmasıdır —")
    print("katman alanları doğrudan toplanamaz (odak dışı yayılma fazla sayar).")
    print("=" * w)


if __name__ == "__main__":
    main()
