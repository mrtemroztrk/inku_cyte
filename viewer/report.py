#!/usr/bin/env python3
"""Turn analysis/summary.csv into the answers, grouped the way the plate was designed.

Reads what analyze.py produced and reports:

  infiltration  infiltration_ratio by co-culture and by compound, T-added wells only
                (the ratio is meaningless where no T cells were added)
  death         who the NIR objects sit on — tumour, T cell, both, neither
  time          how each read-out moves from t00 to t12
  wells         the extremes, so you know which wells to go and look at

Every table also carries the matched no-T-cell control column, because the orange
channel has a T-cell-free background population: wells that never received T cells
still yield 51-374 objects, so an absolute count is not a T-cell count.

Usage:
  python3 viewer/report.py                       # all of it
  python3 viewer/report.py --t 12                # one timepoint
  python3 viewer/report.py --csv out.csv         # write the grouped table
"""
from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("INC_CACHE", HERE / "cache"))
SUMMARY = CACHE / "analysis" / "summary.csv"


def load(path: Path) -> list[dict]:
    if not path.is_file():
        raise SystemExit(f"{path} yok — önce: python3 viewer/analyze.py --all")
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        if r.get("error"):
            continue
        rec = dict(r)
        for k, v in r.items():
            if k in ("well", "stamp", "condition", "coculture", "compound",
                     "has_tcells", "has_macrophages", "has_cafs", "error"):
                continue
            try:
                rec[k] = float(v) if v not in ("", None) else None
            except ValueError:
                rec[k] = None
        out.append(rec)
    return out


def agg(vals: list, fn=np.median) -> float | None:
    v = [x for x in vals if x is not None and np.isfinite(x)]
    return round(float(fn(v)), 3) if v else None


def table(title: str, header: list[str], rows: list[list]):
    widths = [max(len(str(header[i])), *(len(str(r[i])) for r in rows)) if rows
              else len(str(header[i])) for i in range(len(header))]
    print(f"\n{title}")
    print("  " + "  ".join(str(h).ljust(widths[i]) for i, h in enumerate(header)))
    print("  " + "  ".join("-" * widths[i] for i in range(len(header))))
    for r in rows:
        print("  " + "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(r)))


def fmt(v, nd=2):
    return "—" if v is None else f"{v:.{nd}f}"


def report_infiltration(rows: list[dict], t: int | None):
    sel = [r for r in rows if t is None or int(r["t"]) == t]
    groups = defaultdict(lambda: defaultdict(list))
    for r in sel:
        key = r["coculture"] or "?"
        groups[key][r["has_tcells"]].append(r)

    out = []
    for key in sorted(groups):
        g = groups[key]
        yes, no = g.get("yes", []), g.get("no", [])
        out.append([
            key, len(yes), len(no),
            fmt(agg([r["infiltration_ratio"] for r in yes])),
            fmt(agg([r["infiltration_ratio"] for r in no])),
            fmt(agg([r["t_median_dist_um"] for r in yes]), 0),
            fmt(agg([r["t_median_dist_um"] for r in no]), 0),
            fmt(agg([r["t_enrich_50um"] for r in yes])),
            fmt(agg([r["tumour_hull_frac"] for r in yes])),
        ])
    table(f"İNFİLTRASYON — ko-kültüre göre{'' if t is None else f' (t{t:02d})'}"
          "  ·  medyan değerler",
          ["ko-kültür", "n(+T)", "n(-T)", "infilt.+T", "infilt.-T",
           "uzaklık+T µm", "uzaklık-T µm", "zeng.50µm", "kabuk payı"], out)
    print("  infilt. = kabuk içi T yoğunluğu / kabuk dışı · 1=rastgele <1=dışlanma >1=zenginleşme")
    print("  -T kolonu kontroldür: turuncu kanalın T'siz arkaplanı bu değerleri üretir")

    # compound, T-added wells only
    groups2 = defaultdict(list)
    for r in sel:
        if r["has_tcells"] == "yes":
            groups2[r["compound"] or "?"].append(r)
    out2 = []
    for key in sorted(groups2, key=lambda k: -(agg([r["infiltration_ratio"]
                                                    for r in groups2[k]]) or -9)):
        g = groups2[key]
        out2.append([key, len(g),
                     fmt(agg([r["infiltration_ratio"] for r in g])),
                     fmt(agg([r["t_median_dist_um"] for r in g]), 0),
                     fmt(agg([r["t_count"] for r in g]), 0),
                     fmt(agg([r["tumour_count"] for r in g]), 0)])
    table("İNFİLTRASYON — bileşiğe göre (yalnız T eklenen kuyular)",
          ["bileşik", "n", "infilt.", "uzaklık µm", "T nesne", "tümör nesne"], out2)


def report_death(rows: list[dict], t: int | None):
    sel = [r for r in rows if t is None or int(r["t"]) == t]
    groups = defaultdict(list)
    for r in sel:
        groups[(r["coculture"] or "?", r["has_tcells"])].append(r)
    out = []
    for key in sorted(groups):
        g = groups[key]
        tot = agg([r["dead_count"] for r in g], np.median)
        on_t = agg([r["dead_on_tumour"] for r in g], np.median)
        on_c = agg([r["dead_on_tcell"] for r in g], np.median)
        on_b = agg([r["dead_on_both"] for r in g], np.median)
        on_n = agg([r["dead_on_neither"] for r in g], np.median)
        out.append([key[0], key[1], len(g), fmt(tot, 0), fmt(on_t, 0), fmt(on_c, 0),
                    fmt(on_b, 0), fmt(on_n, 0),
                    fmt(agg([r["dead_frac_inside_hull"] for r in g]))])
    table(f"ÖLÜM — kim, nerede{'' if t is None else f' (t{t:02d})'}  ·  medyan nesne sayısı",
          ["ko-kültür", "T ekli", "n", "ölü", "tümör üstü", "T üstü",
           "ikisi", "hiçbiri", "kabuk içi pay"], out)
    print("  sınıflama: NIR nesnesinin green/orange maskesiyle örtüşmesi (±5,6 µm)")


def report_time(rows: list[dict]):
    ts = sorted({int(r["t"]) for r in rows})
    for group_val, label in (("yes", "T eklenen"), ("no", "T eklenmeyen")):
        out = []
        for t in ts:
            g = [r for r in rows if int(r["t"]) == t and r["has_tcells"] == group_val]
            if not g:
                continue
            out.append([f"t{t:02d}",
                        fmt(agg([r["hours"] for r in g]), 0),
                        fmt(agg([r["tumour_count"] for r in g]), 0),
                        fmt(agg([r["tumour_hull_frac"] for r in g])),
                        fmt(agg([r["t_count"] for r in g]), 0),
                        fmt(agg([r["infiltration_ratio"] for r in g])),
                        fmt(agg([r["t_median_dist_um"] for r in g]), 0),
                        fmt(agg([r["dead_count"] for r in g]), 0)])
        table(f"ZAMAN — {label} kuyular (medyan)",
              ["t", "saat", "tümör nesne", "kabuk payı", "T nesne",
               "infilt.", "uzaklık µm", "ölü"], out)


def report_extremes(rows: list[dict], t: int | None, n: int = 6):
    sel = [r for r in rows if (t is None or int(r["t"]) == t) and r["has_tcells"] == "yes"
           and r["infiltration_ratio"] is not None]
    if not sel:
        return
    sel.sort(key=lambda r: r["infiltration_ratio"])
    def line(r):
        return [r["well"], f't{int(r["t"]):02d}', r["condition"][:38],
                fmt(r["infiltration_ratio"]), fmt(r["t_median_dist_um"], 0),
                fmt(r["t_count"], 0), fmt(r["dead_count"], 0)]
    hdr = ["kuyu", "t", "koşul", "infilt.", "uzaklık µm", "T nesne", "ölü"]
    table("EN ÇOK DIŞLANMA (T eklenen kuyular)", hdr, [line(r) for r in sel[:n]])
    table("EN ÇOK ZENGİNLEŞME", hdr, [line(r) for r in sel[-n:][::-1]])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", default=str(SUMMARY))
    ap.add_argument("--t", type=int, default=None, help="tek zaman noktası")
    ap.add_argument("--csv", help="gruplanmış tabloyu CSV olarak yaz")
    args = ap.parse_args()

    rows = load(Path(args.summary))
    wells = {r["well"] for r in rows}
    ts = {int(r["t"]) for r in rows}
    print(f"{len(rows)} satır · {len(wells)} kuyu · {len(ts)} zaman noktası")

    report_infiltration(rows, args.t)
    report_death(rows, args.t)
    if args.t is None:
        report_time(rows)
    report_extremes(rows, args.t if args.t is not None else max(ts))

    if args.csv:
        keys = ["well", "t", "hours", "condition", "coculture", "has_tcells",
                "has_macrophages", "has_cafs", "compound", "concentration",
                "tumour_count", "tumour_hull_frac", "t_count", "infiltration_ratio",
                "t_median_dist_um", "t_enrich_50um", "dead_count", "dead_on_tumour",
                "dead_on_tcell", "dead_on_both", "dead_on_neither"]
        with open(args.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            w.writerows(sorted(rows, key=lambda r: (r["well"], r["t"])))
        print(f"\n→ {args.csv}")

    print("\nUYARI: turuncu kanalda T hücresi olmayan bir arkaplan popülasyonu var "
          "(T'siz kuyularda da 51–374 nesne). t_count mutlak T sayısı değil; "
          "karşılaştırmayı eşleşmiş koşullar arasında yapın.")


if __name__ == "__main__":
    main()
