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
import page as P            # noqa: E402
import theme as TH          # noqa: E402

CACHE = HERE / "cache" / "wells"
SITE = HERE / "site"

COCULTURE_ORDER = ["PDA", "PDA+CAF", "PDA+MAC", "PDA+CAF+MAC"]
COMPOUND_ORDER = ["control", "kras low", "kras high", "Src low", "Src high",
                  "low kras+Src", "high kras+Src"]


def load_wells() -> list[dict]:
    """Kuyu başına özet: son zaman noktası + zaman serisi."""
    import build

    cal = calib.load()
    out = []
    for fp in sorted(CACHE.glob("*.json")):
        pay = build.load_derived(fp.stem, cal)
        m, F = pay["meta"], pay["frames"]
        last = F[-1]
        out.append({
            **{k: m[k] for k in ("well", "coculture", "compound", "concentration",
                                 "has_tcells", "excluded")},
            "days": [t["hours"] / 24 for t in pay["times"]],
            "organoid": [f["derived"]["organoid_mm2"] for f in F],
            "tumour": [f["derived"]["tumour_mm2"] for f in F],
            "tcell_series": [f["derived"]["tcell_mm2"] for f in F],
            "dead_series": [f["derived"]["dead_mm2"] for f in F],
            "t_enrich": last["totals"]["orange"]["enrich_terr"],
            "tcells": last["derived"]["tcells"],
            "dead": last["derived"]["dead_mm2"],
            "organoid_last": last["derived"]["organoid_mm2"],
            "tumour_last": last["derived"]["tumour_mm2"],
            "growth": (last["derived"]["organoid_mm2"] / F[0]["derived"]["organoid_mm2"]
                       if F[0]["derived"]["organoid_mm2"] > 0 else None),
            # T hücrelerinin kenara göre medyan konumu: negatif = içeride
            "t_median_dist": last["bands"]["orange"]["median_signed_dist_um"],
            "terr_frac": last["bf"]["terr_frac"],
        })
    return out


# İşaretli uzaklık, teritoryanın kadrajda kapladığı alana duyarlı: teritorya
# görüşün tamamına yakınını kaplayınca her nokta zorunlu olarak "içeride" çıkar
# ve medyan uzaklık infiltrasyonu değil konfluensi ölçer. Ölçüldü: +T kuyularında
# teritorya oranı ile medyan uzaklık arasında Spearman ρ = −0,50 (p = 0,008,
# n = 27), ve PDA+MAC grubunun 6 kuyusundan 4'ünde teritorya alanın %95'ini
# kaplıyor. Bu yüzden uzaklık figürü yoğun kuyuları dışarıda bırakır.
CONFLUENT_MAX = 0.70


def confluence_confound(wells: list[dict]) -> dict:
    """Uzaklık ölçüsünün teritorya büyüklüğüne bağımlılığı — figürde raporlanır."""
    from scipy import stats

    sel = [w for w in wells if w["has_tcells"] and not w["excluded"]
           and w["t_median_dist"] is not None and w["terr_frac"] is not None]
    if len(sel) < 5:
        return {"n": len(sel)}
    rho, p = stats.spearmanr([w["terr_frac"] for w in sel],
                             [w["t_median_dist"] for w in sel])
    dropped = [w["well"] for w in sel if w["terr_frac"] > CONFLUENT_MAX]
    return {"n": len(sel), "rho": round(float(rho), 3), "p": round(float(p), 5),
            "cut": CONFLUENT_MAX, "dropped": sorted(dropped),
            "n_dropped": len(dropped)}


def strip_series(wells: list[dict], key: str, groupby: str, order: list[str],
                 only=None) -> dict:
    """Grup başına nokta bulutu + medyan + önyükleme GA'sı."""
    groups = []
    for g in order:
        sel = [w for w in wells
               if w[groupby] == g and not w["excluded"]
               and (only is None or only(w))
               and w[key] is not None and np.isfinite(w[key])]
        v = np.array([w[key] for w in sel], float)
        if not v.size:
            continue
        lo, hi = C.boot_ci(v) if v.size >= 3 else (float(v.min()), float(v.max()))
        groups.append({"label": g, "n": int(v.size),
                       "values": [round(float(x), 5) for x in v],
                       "wells": [w["well"] for w in sel],
                       "median": round(float(np.median(v)), 5),
                       "ci": [round(float(lo), 5), round(float(hi), 5)]})
    return {"groups": groups}


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


def matched_tcell_effect(wells: list[dict], key: str) -> dict:
    """±T hücresi etkisi, ko-kültür sabit tutularak.

    Ko-kültür hem ölümü hem T dağılımını bağımsız olarak etkiliyor; T'li ve
    T'siz kuyuları doğrudan havuzlamak bu iki etkiyi karıştırır. Her ko-kültür
    içinde ayrı karşılaştırılır, sonra yön tutarlılığı işaret testiyle bakılır.
    """
    rows, ps = [], []
    for g in COCULTURE_ORDER:
        sel = [w for w in wells if w["coculture"] == g and not w["excluded"]
               and w[key] is not None and np.isfinite(w[key])]
        a = np.array([w[key] for w in sel if w["has_tcells"]], float)
        b = np.array([w[key] for w in sel if not w["has_tcells"]], float)
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
                     "values_ctrl": [round(float(x), 5) for x in b]})
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


def timecourse(wells: list[dict], key: str, groupby: str, order: list[str]) -> dict:
    """Grup başına medyan eğri + kuyu eğrileri."""
    out = []
    for g in order:
        sel = [w for w in wells if w[groupby] == g and not w["excluded"]]
        if not sel:
            continue
        M = np.array([w[key] for w in sel], float)
        out.append({"label": g, "n": len(sel), "days": sel[0]["days"],
                    "median": [round(float(v), 5) for v in np.median(M, axis=0)],
                    "wells": [{"well": w["well"],
                               "v": [round(float(x), 5) for x in w[key]]} for w in sel]})
    return {"groups": out}


def build() -> dict:
    wells = load_wells()
    t_only = lambda w: w["has_tcells"]                              # noqa: E731

    # Uzaklık ölçüsü yoğun kuyularda anlamını yitiriyor (yukarıdaki gerekçe),
    # o yüzden bu figürde ek bir koşul var. Zenginleşme yoğunluk oranı olduğu
    # için aynı sorundan etkilenmiyor ve tüm kuyularda kalıyor.
    dist_ok = lambda w: w["has_tcells"] and w["terr_frac"] is not None \
        and w["terr_frac"] <= CONFLUENT_MAX                            # noqa: E731

    enrich_coc = strip_series(wells, "t_enrich", "coculture", COCULTURE_ORDER, t_only)
    enrich_cmp = strip_series(wells, "t_enrich", "compound", COMPOUND_ORDER, t_only)
    dist_coc = strip_series(wells, "t_median_dist", "coculture", COCULTURE_ORDER, dist_ok)
    growth = timecourse(wells, "organoid", "coculture", COCULTURE_ORDER)

    return {
        "calibration": calib.load(),
        "n_wells": len([w for w in wells if not w["excluded"]]),
        "n_excluded": len([w for w in wells if w["excluded"]]),
        "confluence": confluence_confound(wells),
        "enrich_coculture": {**enrich_coc, "tests": pairwise(enrich_coc)},
        "enrich_compound": {**enrich_cmp, "tests": pairwise(enrich_cmp)},
        "dist_coculture": {**dist_coc, "tests": pairwise(dist_coc)},
        "growth": growth,
        "dead_matched": matched_tcell_effect(wells, "dead"),
        "tumour_matched": matched_tcell_effect(wells, "tumour_last"),
    }


def main() -> None:
    if not any(CACHE.glob("*.json")):
        raise SystemExit("ölçüm yok — önce: python3 atlas/build.py --all")
    d = build()
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "groups.html").write_text(P.groups_page(d), encoding="utf-8")
    print(f"[gruplar] {d['n_wells']} kuyu ({d['n_excluded']} QC dışı)  →  "
          f"{SITE / 'groups.html'}")
    e = d["enrich_coculture"]
    print("\nT hücresi zenginleşmesi, ko-kültüre göre (gün 4, yalnız +T kuyular):")
    for g in e["groups"]:
        print(f"  {g['label']:<12s} n={g['n']:2d}  medyan {g['median']:.2f}×  "
              f"GA [{g['ci'][0]:.2f}–{g['ci'][1]:.2f}]")
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
