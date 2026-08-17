#!/usr/bin/env python3
"""Grup karşılaştırma sayfası — makaleye giren figürler.

Kuyu sayfaları tek bir kuyuyu uzamsal olarak açar; bu sayfa kuyuları gruplar ve
karşılaştırır. Ölçüler `atlas/cache/wells/` içindeki aynı ölçümden gelir, yani
kuyu sayfasında görülen sayı ile buradaki nokta aynı sayıdır.

İstatistik `analysis/common.py`'den alınır ve `analysis/README.md`'deki kurallara
uyar; o kurallar koşul başına 2–17 kuyuluk örneklem için seçilmişti:

  * Kutu grafiği yok — her kuyu bir nokta, medyan çizgiyle, önyükleme GA'sıyla.
    n=4 iken bir kutu grafiği çeyrekleri uydurur.
  * Parametrik test yok — Mann-Whitney U p-değeri, etki büyüklüğü olarak
    Mann-Whitney AUC ve Cliff δ.
  * Çoklu karşılaştırma Benjamini-Hochberg ile düzeltilir (`q`).
  * Eşleşmiş karşılaştırma tercih edilir: ko-kültür hem ölümü hem T dağılımını
    bağımsız olarak etkilediği için sabit tutulur.
  * Konum yalnızca katman olarak raporlanır (katman başına sinyal); organoide
    göre içeride/dışarıda ya da kenara uzaklık hesaplanmaz — yüzey bilinmiyor.

    python3 atlas/groups.py
"""
from __future__ import annotations

import json
import math
import sys
from itertools import combinations
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "analysis"))

import common as C          # noqa: E402  auc, mwu_p, bh_fdr, boot_ci, cliffs_delta
import calib                # noqa: E402
import figures as FG        # noqa: E402
import page as P            # noqa: E402
import theme as TH          # noqa: E402

CACHE = HERE / "cache" / "wells"
SITE = HERE / "site"

COCULTURE_ORDER = ["PDA", "PDA+CAF", "PDA+MAC", "PDA+CAF+MAC"]
COMPOUND_ORDER = ["control", "Dye", "kras low", "kras high", "Src low", "Src high",
                  "low kras+Src", "high kras+Src"]
# Plaka haritasındaki adların okunur karşılığı ve dozu (nM). "Dye" = bileşiksiz,
# yalnız boya; T hücresi almayan kuyularda ek bir kontrol grubudur.
COMPOUND_LABEL = {
    "control": "control (vehicle)", "Dye": "dye only, no compound",
    "kras low": "KRAS inhibitor 10 nM", "kras high": "KRAS inhibitor 100 nM",
    "Src low": "SRC inhibitor 50 nM", "Src high": "SRC inhibitor 200 nM",
    "low kras+Src": "KRAS 10 nM + SRC 50 nM", "high kras+Src": "KRAS 100 nM + SRC 200 nM",
}
COCULTURE_LABEL = {
    "PDA": "PDA organoids alone (2000 tumour cells)",
    "PDA+CAF": "PDA + cancer-associated fibroblasts (4000 CAFs)",
    "PDA+MAC": "PDA + macrophages (8000)",
    "PDA+CAF+MAC": "PDA + CAFs (4000) + macrophages (8000)",
}


def load_wells() -> list[dict]:
    """Kuyu başına: plaka haritası + her büyüklüğün 13 noktalık zaman serisi.

    Grup sayfası herhangi bir zaman noktasında kurulabilsin diye her şey seri
    olarak tutulur; `build(ti)` istenen indeksten okur."""
    import build

    cal = calib.load()
    out = []
    for fp in sorted(CACHE.glob("*.json")):
        pay = build.load_derived(fp.stem, cal)
        m, F = pay["meta"], pay["frames"]
        D = [f["derived"] for f in F]
        out.append({
            **{k: m[k] for k in ("well", "coculture", "compound", "concentration",
                                 "has_tcells", "has_cafs", "has_macrophages",
                                 "excluded")},
            "days": [t["hours"] / 24 for t in pay["times"]],
            "organoid": [d["organoid_mm2"] for d in D],
            "tumour": [d["tumour_mm2"] for d in D],
            "tcell_mm2": [d["tcell_mm2"] for d in D],
            "tcells": [d["tcells"] for d in D],
            "dead": [d["dead_mm2"] for d in D],
            # katman başına T hücresi sinyali (mm², düzlem maskeleri) — "hangi
            # katmanda ne kadar" sorusunun kuyu başına cevabı
            "tcell_by_z": [d["tcell_area_by_z_mm2"] for d in D],
            "tcell_peak_z": [d["tcell_peak_z"] for d in D],
            # ayak izi büyümesi: t / t0 (boyutsuz)
            "growth": [(d["organoid_mm2"] / D[0]["organoid_mm2"]
                        if D[0]["organoid_mm2"] > 0 else None) for d in D],
        })
    return out


def times() -> list[dict]:
    """Zaman noktaları: indeks, saat, çekim zamanı (timepoints.csv'den, aynen)."""
    import build
    return build.plate_meta()["times"]


def catalogue(wells: list[dict]) -> list[dict]:
    """Deney düzeni, satır satır: hangi kuyuya ne uygulandı.

    Sayfada tablo olarak basılır; her figürün altındaki kuyu listeleri buraya
    işaret eder. "n = 7" bir figürde yedi kuyu demektir, ve hangi yedi kuyu olduğu
    her zaman yazılıdır."""
    rows = {}
    for w in wells:
        key = (w["coculture"], w["compound"], w["concentration"], w["has_tcells"])
        r = rows.setdefault(key, {"coculture": w["coculture"], "compound": w["compound"],
                                  "concentration": w["concentration"],
                                  "has_tcells": w["has_tcells"], "wells": [],
                                  "excluded": []})
        (r["excluded"] if w["excluded"] else r["wells"]).append(w["well"])
    order = {c: i for i, c in enumerate(COCULTURE_ORDER)}
    corder = {c: i for i, c in enumerate(COMPOUND_ORDER)}
    return sorted(rows.values(), key=lambda r: (order.get(r["coculture"], 99),
                                                corder.get(r["compound"], 99),
                                                r["has_tcells"]))


def at(w: dict, key: str, ti: int):
    v = w[key][ti]
    return None if v is None else v


# Uzaklık bantları ve teritorya içi zenginleşme bu sayfada artık yok. Organoidin
# yüzeyi z'de bilinmiyor; "içeride / dışarıda" ve "kenara uzaklık" 2B ayak izine
# göre tanımlıydı ve savunulamaz bulundu. Yerine, savunulabilir olan: katman
# başına ne kadar sinyal var ve gruplar arasında bu profil nasıl değişiyor.


def layer_profile(wells: list[dict], key: str, ti: int, groupby: str,
                  order: list[str], only=None) -> dict:
    """Grup başına katman profili: kuyu eğrileri + katman başına medyan."""
    groups = []
    for g in order:
        sel = [w for w in wells
               if w[groupby] == g and not w["excluded"]
               and (only is None or only(w)) and at(w, key, ti) is not None]
        if not sel:
            continue
        M = np.array([at(w, key, ti) for w in sel], float)
        pk = int(np.argmax(np.median(M, axis=0)))
        groups.append({"label": g, "n": len(sel), "nz": int(M.shape[1]), "peak": pk,
                       "median": [round(float(v), 6) for v in np.median(M, axis=0)],
                       "q1": [round(float(v), 6) for v in np.percentile(M, 25, axis=0)],
                       "q3": [round(float(v), 6) for v in np.percentile(M, 75, axis=0)],
                       "wells": [{"well": w["well"],
                                  "v": [round(float(x), 6) for x in at(w, key, ti)]}
                                 for w in sel]})
    return {"groups": groups}


def strip_series(wells: list[dict], key: str, ti: int, groupby: str,
                 order: list[str], only=None) -> dict:
    """Grup başına nokta bulutu + medyan + önyükleme GA'sı (+ ortalama ± SS)."""
    groups = []
    for g in order:
        sel = [w for w in wells
               if w[groupby] == g and not w["excluded"]
               and (only is None or only(w))
               and at(w, key, ti) is not None and np.isfinite(at(w, key, ti))]
        v = np.array([at(w, key, ti) for w in sel], float)
        if not v.size:
            continue
        lo, hi = C.boot_ci(v) if v.size >= 3 else (float(v.min()), float(v.max()))
        groups.append({"label": g, "n": int(v.size),
                       "values": [round(float(x), 5) for x in v],
                       "wells": [w["well"] for w in sel],
                       "median": round(float(np.median(v)), 5),
                       "ci": [round(float(lo), 5), round(float(hi), 5)],
                       "mean": round(float(v.mean()), 5),
                       "sd": round(float(v.std(ddof=1)), 5) if v.size > 1 else None})
    return {**{"groups": groups}, "tests": []}


def strip_tested(wells, key, ti, groupby, order, only=None) -> dict:
    d = strip_series(wells, key, ti, groupby, order, only)
    d["tests"] = pairwise(d)
    return d


def pairwise(strip: dict) -> list[dict]:
    """Gruplar arası ikili testler; p-değerleri BH ile düzeltilir."""
    gs = strip["groups"]
    rows, ps = [], []
    for a, b in combinations(range(len(gs)), 2):
        x = np.array(gs[a]["values"], float)
        y = np.array(gs[b]["values"], float)
        p = C.mwu_p(x, y)
        rows.append({"a": gs[a]["label"], "b": gs[b]["label"],
                     "n_a": len(x), "n_b": len(y),
                     "auc": round(float(C.auc(x, y)), 3),
                     "delta": round(float(C.cliffs_delta(x, y)), 3),
                     "p": None if not np.isfinite(p) else round(float(p), 5)})
        ps.append(p)
    if rows:
        q = C.bh_fdr(np.array(ps, float))
        for r, qq in zip(rows, q):
            r["q"] = None if not np.isfinite(qq) else round(float(qq), 5)
    return rows


def matched_tcell_effect(wells: list[dict], key: str, ti: int) -> dict:
    """±T hücresi etkisi, ko-kültür sabit tutularak.

    Ko-kültür hem ölümü hem T dağılımını bağımsız olarak etkiliyor; T'li ve
    T'siz kuyuları doğrudan havuzlamak bu iki etkiyi karıştırır. Her ko-kültür
    içinde ayrı karşılaştırılır, sonra yön tutarlılığı işaret testiyle bakılır.
    """
    rows, ps = [], []
    for g in COCULTURE_ORDER:
        sel = [w for w in wells if w["coculture"] == g and not w["excluded"]
               and at(w, key, ti) is not None and np.isfinite(at(w, key, ti))]
        a = np.array([at(w, key, ti) for w in sel if w["has_tcells"]], float)
        b = np.array([at(w, key, ti) for w in sel if not w["has_tcells"]], float)
        if a.size < 2 or b.size < 2:
            continue
        p = C.mwu_p(a, b)
        rows.append({"group": g, "n_t": int(a.size), "n_ctrl": int(b.size),
                     "med_t": round(float(np.median(a)), 5),
                     "med_ctrl": round(float(np.median(b)), 5),
                     "ratio": round(float(np.median(a) / max(np.median(b), 1e-12)), 3),
                     "delta": round(float(C.cliffs_delta(a, b)), 3),
                     "p": None if not np.isfinite(p) else round(float(p), 5),
                     "values_t": [round(float(x), 5) for x in a],
                     "values_ctrl": [round(float(x), 5) for x in b],
                     "wells_t": [w["well"] for w in sel if w["has_tcells"]],
                     "wells_ctrl": [w["well"] for w in sel if not w["has_tcells"]]})
        ps.append(p)
    if rows:
        for r, qq in zip(rows, C.bh_fdr(np.array(ps, float))):
            r["q"] = None if not np.isfinite(qq) else round(float(qq), 5)
    # İşaret testi: gruplar tek tek anlamlı olmasa da yön tutarlı mı.
    # İki yönlü binom, H₀: yön rastgele (p=0,5).
    up = sum(1 for r in rows if r["ratio"] > 1)
    n = len(rows)
    m = max(up, n - up)
    sign_p = (min(1.0, 2 * sum(math.comb(n, k) for k in range(m, n + 1)) / 2 ** n)
              if n else None)
    return {"rows": rows, "n_groups": n, "n_up": up,
            "sign_p": None if sign_p is None else round(float(sign_p), 4)}


def timecourse(wells: list[dict], key: str, groupby: str, order: list[str],
               only=None) -> dict:
    """Grup başına medyan eğri + kuyu eğrileri."""
    out = []
    for g in order:
        sel = [w for w in wells if w[groupby] == g and not w["excluded"]
               and (only is None or only(w))]
        if not sel:
            continue
        M = np.array([w[key] for w in sel], float)
        out.append({"label": g, "n": len(sel), "days": sel[0]["days"],
                    "median": [round(float(v), 5) for v in np.median(M, axis=0)],
                    "wells": [{"well": w["well"],
                               "v": [round(float(x), 5) for x in w[key]]} for w in sel]})
    return {"groups": out}


def build(ti: int | None = None, wells: list[dict] | None = None,
          T: list[dict] | None = None) -> dict:
    """Bir zaman noktasındaki grup karşılaştırmaları (varsayılan: son nokta)."""
    wells = wells if wells is not None else load_wells()
    T = T if T is not None else times()
    ti = len(T) - 1 if ti is None else ti
    t_only = lambda w: w["has_tcells"]                              # noqa: E731
    no_t = lambda w: not w["has_tcells"]                            # noqa: E731

    # "Dye" kolonundaki kuyulara ölü-hücre boyası verilmemiş: NIR sinyalleri
    # 21 kuyuda da tam sıfır (gün 4 medyan 0,0, en yüksek 2e-5 mm²), oysa green
    # ve orange arkaplanı öbür kuyular kadar. Ölü hücre karşılaştırmalarına
    # girmeleri "T'siz kuyularda ölüm yok" gibi bir yanılsama üretir; dışarıda
    # tutulur ve sayfada söylenir.
    no_dye = [w for w in wells if w["compound"] != "Dye"]

    def split(key, pool=None):
        # aynı büyüklük, T hücresi alan ve almayan kuyularda ayrı ayrı
        pool = wells if pool is None else pool
        return {"t": strip_tested(pool, key, ti, "compound", COMPOUND_ORDER, t_only),
                "no_t": strip_tested(pool, key, ti, "compound", COMPOUND_ORDER, no_t)}

    return {
        "calibration": calib.load(),
        "t": {**T[ti], "index": ti, "day": round(T[ti]["hours"] / 24, 2)},
        "times": T,
        "n_wells": len([w for w in wells if not w["excluded"]]),
        "n_excluded": len([w for w in wells if w["excluded"]]),
        "catalogue": catalogue(wells),
        # T hücreleri: nerede (katman) ve ne kadar
        "tz_coculture": layer_profile(wells, "tcell_by_z", ti, "coculture",
                                      COCULTURE_ORDER, t_only),
        "tz_compound": layer_profile(wells, "tcell_by_z", ti, "compound",
                                     COMPOUND_ORDER, t_only),
        "tcells_coculture": strip_tested(wells, "tcells", ti, "coculture",
                                         COCULTURE_ORDER, t_only),
        "tcells_compound": strip_tested(wells, "tcells", ti, "compound",
                                        COMPOUND_ORDER, t_only),
        "tcell_time": timecourse(wells, "tcells", "coculture", COCULTURE_ORDER, t_only),
        # tedavi rejimleri: bileşiğe göre, T'li ve T'siz kuyular yan yana
        "dead_compound": split("dead", no_dye),
        "tumour_compound": split("tumour"),
        "growth_compound": split("growth"),
        # organoid ayak izi zamanla
        "growth": timecourse(wells, "organoid", "coculture", COCULTURE_ORDER),
        # ±T etkisi, ko-kültür sabit
        "dead_matched": matched_tcell_effect(no_dye, "dead", ti),
        "tumour_matched": matched_tcell_effect(wells, "tumour", ti),
    }


def build_all() -> list[dict]:
    """Her zaman noktası için bir sayfa verisi (kuyular bir kez okunur)."""
    wells, T = load_wells(), times()
    return [build(ti, wells, T) for ti in range(len(T))]


def write_pages(all_d: list[dict] | None = None) -> dict:
    """Her zaman noktası için bir sayfa; son nokta ayrıca groups.html."""
    all_d = all_d if all_d is not None else build_all()
    SITE.mkdir(parents=True, exist_ok=True)
    for d in all_d:
        html = P.groups_page(d, FG.build_all(d))
        (SITE / f"groups_t{d['t']['index']:02d}.html").write_text(html, encoding="utf-8")
        if d["t"]["index"] == len(all_d) - 1:
            (SITE / "groups.html").write_text(html, encoding="utf-8")
    return all_d[-1]


def main() -> None:
    if not any(CACHE.glob("*.json")):
        raise SystemExit("ölçüm yok — önce: python3 atlas/build.py --all")
    d = write_pages()
    print(f"[gruplar] {d['n_wells']} kuyu ({d['n_excluded']} QC dışı) · "
          f"{len(d['times'])} zaman noktası  →  {SITE / 'groups.html'}")
    e = d["tcells_coculture"]
    print("\nT hücresi sinyali (≈ hücre), ko-kültüre göre (gün 4, yalnız +T kuyular):")
    for g in e["groups"]:
        print(f"  {g['label']:<12s} n={g['n']:2d}  medyan {g['median']:.0f}  "
              f"GA [{g['ci'][0]:.0f}–{g['ci'][1]:.0f}]")
    print("\nT hücresi katman profili (medyan mm², ko-kültüre göre):")
    for g in d["tz_coculture"]["groups"]:
        print(f"  {g['label']:<12s} n={g['n']:2d}  tepe z{g['peak']:02d}")
    print("\nikili testler (BH düzeltmeli):")
    for t in e["tests"]:
        print(f"  {t['a']:<12s} vs {t['b']:<12s}  AUC {t['auc']:.2f}  "
              f"δ {t['delta']:+.2f}  p {t['p']}  q {t['q']}")
    dm = d["dead_matched"]
    print(f"\nölü hücre sinyali, ±T eşleşmiş: {dm['n_up']}/{dm['n_groups']} grupta "
          f"T ile artıyor, işaret testi p={dm['sign_p']}")
    for r in dm["rows"]:
        print(f"  {r['group']:<12s} T'li {r['med_t']:.4f} vs T'siz {r['med_ctrl']:.4f} mm² "
              f"({r['ratio']:.2f}×)  δ {r['delta']:+.2f}  q {r['q']}")


if __name__ == "__main__":
    main()
