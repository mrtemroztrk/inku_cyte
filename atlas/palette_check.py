#!/usr/bin/env python3
"""Kanal renklerinin denetimi — göz kararıyla değil, hesapla.

dataviz becerisindeki `scripts/validate_palette.js` doğrulayıcısının Python
karşılığı (bu makinede node yok). Aynı eşikler, aynı dönüşümler:

  parlaklık bandı  OKLCH L, moda göre
  kroma tabanı     OKLCH C ≥ 0,10 (altında renk griye düşer)
  CVD ayrımı       Machado-Oliveira-Fernandes (2009) protan/deutan, OKLab ΔE×100
  normal görüş     aynı ΔE, simülasyonsuz — tam renk görenler için taban
  kontrast         WCAG, zemine karşı

Kanal renkleri keyfi değil: green = tümör, orange = T hücresi, nir = ölü hücre
mikroskopi kuralı ve 3B sahnedeki renklerle aynı olmak zorunda — aynı şey her
yerde aynı renk. Bu yüzden slot seçimi serbest değil, doğrulanması zorunlu.

    python3 atlas/palette_check.py
"""
from __future__ import annotations

import itertools
import math

BAND = {"light": (0.43, 0.77), "dark": (0.48, 0.67)}
CHROMA_FLOOR = 0.10
CVD_TARGET, CVD_FLOOR = 8.0, 6.0
NORMAL_FLOOR = 15.0
CONTRAST_MIN = 3.0
SURFACE = {"light": "#fcfcfb", "dark": "#1a1a19"}

MACHADO = {
    "protan": ((0.152286, 1.052583, -0.204868),
               (0.114503, 0.786281, 0.099216),
               (-0.003882, -0.048116, 1.051998)),
    "deutan": ((0.367322, 0.860646, -0.227968),
               (0.280085, 0.672501, 0.047413),
               (-0.011820, 0.042940, 0.968881)),
    "tritan": ((1.255528, -0.076749, -0.178779),
               (-0.078411, 0.930809, 0.147602),
               (0.004733, 0.691367, 0.303900)),
}


def _lin(h: str) -> tuple[float, float, float]:
    h = h.strip().lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb)


def _oklab(rgb) -> tuple[float, float, float]:
    r, g, b = rgb
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def _sim(h: str, kind: str | None):
    rgb = _lin(h)
    if kind is None:
        return rgb
    M = MACHADO[kind]
    return tuple(min(1.0, max(0.0, sum(M[i][j] * rgb[j] for j in range(3)))) for i in range(3))


def delta_e(a: str, b: str, kind: str | None = None) -> float:
    x, y = _oklab(_sim(a, kind)), _oklab(_sim(b, kind))
    return 100 * math.dist(x, y)


def oklch(h: str) -> tuple[float, float]:
    L, a, b = _oklab(_lin(h))
    return L, math.hypot(a, b)


def contrast(a: str, b: str) -> float:
    def lum(h):
        r, g, bl = _lin(h)
        return 0.2126 * r + 0.7152 * g + 0.0722 * bl
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def validate(palette: list[str], mode: str = "light", surface: str | None = None,
             pairs: str = "all") -> dict:
    surface = surface or SURFACE[mode]
    lo_b, hi_b = BAND[mode]
    rows, fails, warns = [], [], []

    for i, c in enumerate(palette):
        L, C = oklch(c)
        cr = contrast(c, surface)
        ok_L = lo_b <= L <= hi_b
        ok_C = C >= CHROMA_FLOOR
        if not ok_L:
            fails.append(f"slot{i + 1} {c}: L={L:.3f} bandın dışında [{lo_b}, {hi_b}]")
        if not ok_C:
            fails.append(f"slot{i + 1} {c}: C={C:.3f} < {CHROMA_FLOOR}")
        if cr < CONTRAST_MIN:
            warns.append(f"slot{i + 1} {c}: kontrast {cr:.2f} < {CONTRAST_MIN} "
                         f"→ doğrudan etiket veya tablo zorunlu")
        rows.append({"slot": i + 1, "hex": c, "L": round(L, 3), "C": round(C, 3),
                     "contrast": round(cr, 2),
                     "L_ok": ok_L, "C_ok": ok_C})

    pl = (list(itertools.combinations(range(len(palette)), 2)) if pairs == "all"
          else [(i, i + 1) for i in range(len(palette) - 1)])
    prs = []
    for i, j in pl:
        a, b = palette[i], palette[j]
        p, d, tr = (delta_e(a, b, "protan"), delta_e(a, b, "deutan"), delta_e(a, b, "tritan"))
        n = delta_e(a, b)
        cvd = min(p, d)
        if cvd < CVD_FLOOR:
            fails.append(f"{a}↔{b}: CVD ΔE={cvd:.1f} < {CVD_FLOOR}")
        elif cvd < CVD_TARGET:
            warns.append(f"{a}↔{b}: CVD ΔE={cvd:.1f} (6–8 bandı) → ikincil kodlama zorunlu")
        if n < NORMAL_FLOOR:
            fails.append(f"{a}↔{b}: normal görüş ΔE={n:.1f} < {NORMAL_FLOOR}")
        prs.append({"pair": f"{a}↔{b}", "normal": round(n, 1), "protan": round(p, 1),
                    "deutan": round(d, 1), "tritan": round(tr, 1), "cvd": round(cvd, 1)})

    return {"mode": mode, "surface": surface, "slots": rows, "pairs": prs,
            "fails": fails, "warns": warns, "ok": not fails}


def report(name: str, palette: list[str], mode: str, surface: str | None = None) -> bool:
    r = validate(palette, mode, surface)
    print(f"\n{name}  [{mode}, zemin {r['surface']}]  →  "
          f"{'GEÇTİ' if r['ok'] else 'KALDI'}")
    print("  slot  hex       L      C      kontrast")
    for s in r["slots"]:
        print(f"  {s['slot']:>4d}  {s['hex']}  {s['L']:.3f}  {s['C']:.3f}   {s['contrast']:>5.2f}"
              f"  {'' if s['L_ok'] and s['C_ok'] else '  ← band/kroma'}")
    print("  çift                    normal  protan  deutan  tritan")
    for p in r["pairs"]:
        print(f"  {p['pair']:<22s}  {p['normal']:>6.1f}  {p['protan']:>6.1f}"
              f"  {p['deutan']:>6.1f}  {p['tritan']:>6.1f}")
    for f in r["fails"]:
        print(f"  ✗ {f}")
    for w in r["warns"]:
        print(f"  ! {w}")
    return r["ok"]


if __name__ == "__main__":
    # Figürlerde kullanılan kanal renkleri (açık zemin) ve 3B sahnedekiler (koyu).
    from theme import CH_FIG, CH_SCENE, SURFACE_FIG, SURFACE_SCENE

    order = ["green", "orange", "nir"]
    report("kanal renkleri — figür", [CH_FIG[c] for c in order], "light", SURFACE_FIG)
    report("kanal renkleri — 3B sahne", [CH_SCENE[c] for c in order], "dark", SURFACE_SCENE)
