#!/usr/bin/env python3
"""3D segmentation and per-well quantification of T-cell infiltration and cell death.

What it measures, per well and timepoint
----------------------------------------
tumour   green channel segmented as 3D objects (tumour cells), plus the convex hull
         of their positions — the aggregate's territory, with no smoothing or
         threshold-on-a-blur parameter to tune.
T cells  orange channel as 3D objects: count, how many fall inside the tumour hull,
         and the distance from each to the nearest tumour cell.
death    NIR channel as 3D objects, classified by what they overlap — tumour signal,
         T-cell signal, both, or neither. NIR is a generic dead-cell dye, so this
         co-localisation is the only thing that says *whose* death it marks.

Why infiltration is reported as a ratio, not a percentage
--------------------------------------------------------
"% of T cells inside the tumour" is not comparable between wells, because the hull
covers 23% of the field in one well and 72% in another — in the second one, T cells
scattered at random would already score 70% "inside". So the headline number is

    infiltration_ratio = (T density inside hull) / (T density outside hull)

which is 1.0 for a random distribution, <1 for exclusion, >1 for enrichment. The
distance-based metrics carry the same normalisation: the observed fraction of T
cells within 50 µm of a tumour cell is divided by the fraction that uniformly
scattered points would achieve in the same well.

Measured examples at day 4: B04 (PDA+CAF+MAC, +T) gives ratio 0.0 — every T cell is
outside the spheroid, median distance 857 µm. B01 (PDA only, +T) gives ~1.0 with a
median distance of 123 µm: the tumour there is not a compact sphere, so T cells sit
among the tumour cells without that counting as active infiltration.

Other design decisions worth knowing
------------------------------------
* **Containment is scored in XY, not XYZ.** 2.798 µm/px means a 4x objective
  (NA ~0.13) whose depth of field is tens of microns, so objects smear along z.
  Depth numbers are reported as descriptive, not used for containment tests.
* **Thresholds are plate-wide.** They come from the pooled statistics in
  cache/channel_stats.json (`off_hi`, the above-background gain), applied after
  per-plane background subtraction, so counts stay comparable between wells.
  A per-frame threshold would silently rescale every well.
* **A built-in control.** The plate map records which wells got 5000 extra T cells;
  `--check` splits the T-cell counts by that column. Run it first — if those wells
  do not come out clearly higher, nothing downstream is trustworthy.
* µm³ volumes depend on the z step, which is not recorded in the files (--z-step).

Usage
-----
  python3 viewer/analyze.py --check                 # control against the plate map
  python3 viewer/analyze.py --wells B04,B01 --t all
  python3 viewer/analyze.py --all --jobs 6          # whole plate -> summary.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import tifffile
from scipy import ndimage
from scipy.spatial import ConvexHull, Delaunay

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

DATA = Path(os.environ.get("INC_DATA", HERE.parent / "data" / "inc_tests")).resolve()
CACHE = Path(os.environ.get("INC_CACHE", HERE / "cache"))
OUT = CACHE / "analysis"

BIN = 2                     # XY binning; 1040x1408 -> 520x704
UM_PER_PX = 2.798 * BIN     # binned pixel size, µm
MIN_OBJ_VOX = 4             # discard specks
DIST_BANDS_UM = (25.0, 50.0, 100.0)
RANDOM_POINTS = 4000        # for the uniform-distribution baseline
RNG_SEED = 7

# Fraction of each channel's plate-wide above-background gain used as the threshold.
# NIR is lower because it is near-binary — >99.9% of its pixels are exactly background.
THR_FRAC = {"green": 0.60, "orange": 0.60, "nir": 0.35}


# --------------------------------------------------------------------------- io
def stack_paths(well: str, ch: str, stamp: str) -> list[Path]:
    d = DATA / "wells" / well / ch
    if not d.is_dir():
        return []
    files = [f for f in d.iterdir() if stamp in f.name and "_plane" in f.name]
    return sorted(files, key=lambda p: int(p.name.split("_plane")[1].split("_")[0]))


def load_volume(well: str, ch: str, stamp: str) -> np.ndarray | None:
    paths = stack_paths(well, ch, stamp)
    if not paths:
        return None
    planes = []
    for p in paths:
        a = tifffile.imread(p).astype(np.float32)
        a = np.clip(a - float(np.median(a)), 0, None)      # per-plane background
        h, w = a.shape
        a = a[: h // BIN * BIN, : w // BIN * BIN]
        planes.append(a.reshape(h // BIN, BIN, w // BIN, BIN).mean((1, 3)))
    return np.stack(planes)


_THR: dict[str, float] | None = None


def channel_thresholds() -> dict[str, float]:
    global _THR
    if _THR is None:
        stats = json.loads((CACHE / "channel_stats.json").read_text())
        _THR = {}
        for ch, frac in THR_FRAC.items():
            e = stats.get(ch, {}).get("plane")
            if not e:
                raise SystemExit(f"{ch} istatistiği yok — önce: python3 viewer/scan_stats.py")
            _THR[ch] = float(e["off_hi"]) * frac
    return _THR


# ------------------------------------------------------------------ segmentation
def objects_3d(vol: np.ndarray, thr: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """3D connected components above threshold.

    Returns (label volume, centroids as (z,y,x), voxel counts) with specks removed.
    """
    mask = vol > thr
    if not mask.any():
        return np.zeros_like(vol, dtype=np.int32), np.zeros((0, 3)), np.zeros(0, dtype=int)
    lab, n = ndimage.label(mask)
    idx = np.arange(1, n + 1)
    sizes = np.asarray(ndimage.sum(np.ones_like(lab), lab, idx))
    keep = sizes >= MIN_OBJ_VOX
    if not keep.any():
        return lab, np.zeros((0, 3)), np.zeros(0, dtype=int)
    coms = np.asarray(ndimage.center_of_mass(vol, lab, idx[keep]))
    return lab, coms.reshape(-1, 3), sizes[keep].astype(int)


def hull_of(points_xy: np.ndarray):
    """Convex hull of tumour-cell positions, or None if there are too few."""
    if len(points_xy) < 4:
        return None, None
    try:
        h = ConvexHull(points_xy)
        return h, Delaunay(points_xy[h.vertices])
    except Exception:
        return None, None


def inside_hull(tri, points_xy: np.ndarray) -> np.ndarray:
    if tri is None or len(points_xy) == 0:
        return np.zeros(len(points_xy), dtype=bool)
    return tri.find_simplex(points_xy) >= 0


def classify_deaths(lab_dead: np.ndarray, labels_kept: np.ndarray,
                    green_mask: np.ndarray, orange_mask: np.ndarray) -> dict:
    """What each NIR object overlaps: dilated by one binned pixel (~5.6 µm) so a
    dead cell whose dye and lineage marker are not pixel-aligned still counts."""
    st = np.ones((1, 3, 3), dtype=bool)
    g = ndimage.binary_dilation(green_mask, st)
    o = ndimage.binary_dilation(orange_mask, st)
    counts = {"tumour": 0, "tcell": 0, "both": 0, "neither": 0}
    if not labels_kept.size:
        return counts
    on_g = ndimage.maximum(g.astype(np.uint8), lab_dead, labels_kept) > 0
    on_o = ndimage.maximum(o.astype(np.uint8), lab_dead, labels_kept) > 0
    for ig, io in zip(np.atleast_1d(on_g), np.atleast_1d(on_o)):
        key = "both" if (ig and io) else "tumour" if ig else "tcell" if io else "neither"
        counts[key] += 1
    return counts


# -------------------------------------------------------------------- one sample
def analyze_one(well: str, stamp: str, t_index: int, z_step_um: float) -> dict:
    thr = channel_thresholds()
    vols = {ch: load_volume(well, ch, stamp) for ch in ("green", "orange", "nir")}
    if any(v is None for v in vols.values()):
        return {"well": well, "t": t_index, "error": "eksik kanal"}

    nz, h, w = vols["green"].shape
    px_area = UM_PER_PX ** 2
    field_mm2 = h * w * px_area / 1e6

    lab_g, com_g, sz_g = objects_3d(vols["green"], thr["green"])
    lab_o, com_o, sz_o = objects_3d(vols["orange"], thr["orange"])
    lab_d, com_d, sz_d = objects_3d(vols["nir"], thr["nir"])

    gmask = vols["green"] > thr["green"]
    omask = vols["orange"] > thr["orange"]

    # --- tumour territory: convex hull of tumour-cell positions -----------------
    g_xy = com_g[:, 1:][:, ::-1] if len(com_g) else np.zeros((0, 2))    # (x, y)
    hull, tri = hull_of(g_xy)
    hull_mm2 = float(hull.volume) * px_area / 1e6 if hull is not None else 0.0
    hull_frac = hull_mm2 / field_mm2 if field_mm2 else 0.0

    o_xy = com_o[:, 1:][:, ::-1] if len(com_o) else np.zeros((0, 2))
    d_xy = com_d[:, 1:][:, ::-1] if len(com_d) else np.zeros((0, 2))
    o_in = inside_hull(tri, o_xy)
    d_in = inside_hull(tri, d_xy)

    def density_ratio(n_in: int, n_tot: int) -> float | None:
        """Inside-hull density over outside-hull density. 1.0 = random scatter."""
        if not n_tot or hull_frac <= 0 or hull_frac >= 1:
            return None
        f_in = n_in / n_tot
        out = (1 - f_in) / (1 - hull_frac)
        return round((f_in / hull_frac) / out, 3) if out > 0 else None

    # --- distance from each cell to the nearest tumour cell ---------------------
    gfoot = gmask.any(0)
    if gfoot.any():
        edt = ndimage.distance_transform_edt(~gfoot) * UM_PER_PX
    else:
        edt = np.full(gfoot.shape, np.inf, dtype=np.float32)

    def dists_of(xy: np.ndarray) -> np.ndarray:
        if not len(xy):
            return np.zeros(0)
        xi = np.clip(xy[:, 0].astype(int), 0, w - 1)
        yi = np.clip(xy[:, 1].astype(int), 0, h - 1)
        return edt[yi, xi]

    d_o = dists_of(o_xy)
    d_dd = dists_of(d_xy)

    rng = np.random.default_rng(RNG_SEED)
    rnd = np.stack([rng.integers(0, w, RANDOM_POINTS), rng.integers(0, h, RANDOM_POINTS)], 1)
    d_rnd = dists_of(rnd.astype(float))

    def band_stats(dd: np.ndarray, prefix: str) -> dict:
        out = {}
        for b in DIST_BANDS_UM:
            key = f"{prefix}_frac_within_{int(b)}um"
            obs = float((dd <= b).mean()) if dd.size else None
            exp = float((d_rnd <= b).mean()) if d_rnd.size else None
            out[key] = round(obs, 4) if obs is not None else None
            if obs is not None and exp:
                out[f"{prefix}_enrich_{int(b)}um"] = round(obs / exp, 3)
            else:
                out[f"{prefix}_enrich_{int(b)}um"] = None
        return out

    rec = {
        "well": well, "t": t_index, "stamp": stamp, "nz": nz,
        "z_step_um": z_step_um, "um_per_px": UM_PER_PX, "field_mm2": round(field_mm2, 3),

        "tumour_count": int(len(sz_g)),
        "tumour_vox": int(sz_g.sum()),
        "tumour_volume_um3": round(float(sz_g.sum()) * px_area * z_step_um, 1),
        "tumour_hull_mm2": round(hull_mm2, 4),
        "tumour_hull_frac": round(hull_frac, 4),
        "tumour_mean_z": round(float(com_g[:, 0].mean()), 2) if len(com_g) else None,

        "t_count": int(len(sz_o)),
        "t_inside_hull": int(o_in.sum()),
        "t_frac_inside_hull": round(float(o_in.mean()), 4) if len(o_in) else None,
        "infiltration_ratio": density_ratio(int(o_in.sum()), len(o_in)),
        "t_median_dist_um": round(float(np.median(d_o)), 1) if d_o.size else None,
        "t_vox_total": int(sz_o.sum()),
        "t_mean_z": round(float(com_o[:, 0].mean()), 2) if len(com_o) else None,
        **band_stats(d_o, "t"),

        "dead_count": int(len(sz_d)),
        "dead_inside_hull": int(d_in.sum()),
        "dead_frac_inside_hull": round(float(d_in.mean()), 4) if len(d_in) else None,
        "dead_density_ratio": density_ratio(int(d_in.sum()), len(d_in)),
        "dead_median_dist_um": round(float(np.median(d_dd)), 1) if d_dd.size else None,
        "dead_mean_z": round(float(com_d[:, 0].mean()), 2) if len(com_d) else None,
        **band_stats(d_dd, "dead"),

        "random_frac_within_50um": round(float((d_rnd <= 50).mean()), 4) if d_rnd.size else None,
    }

    idx_d = np.arange(1, int(lab_d.max()) + 1) if lab_d.max() > 0 else np.zeros(0, dtype=int)
    if idx_d.size:
        sizes_d = np.asarray(ndimage.sum(np.ones_like(lab_d), lab_d, idx_d))
        kept = idx_d[sizes_d >= MIN_OBJ_VOX]
    else:
        kept = np.zeros(0, dtype=int)
    deaths = classify_deaths(lab_d, kept, gmask, omask)
    rec.update({f"dead_on_{k}": v for k, v in deaths.items()})

    # per-layer object counts, for the depth question
    rec["tumour_by_z"] = np.bincount(com_g[:, 0].round().astype(int), minlength=nz).tolist() \
        if len(com_g) else [0] * nz
    rec["t_by_z"] = np.bincount(com_o[:, 0].round().astype(int), minlength=nz).tolist() \
        if len(com_o) else [0] * nz
    rec["dead_by_z"] = np.bincount(com_d[:, 0].round().astype(int), minlength=nz).tolist() \
        if len(com_d) else [0] * nz
    return rec


def _job(args):
    well, stamp, t_index, z_step = args
    cf = OUT / f"{well}_t{t_index:02d}.json"
    if cf.is_file():
        try:
            return json.loads(cf.read_text())
        except Exception:
            pass
    try:
        rec = analyze_one(well, stamp, t_index, z_step)
    except Exception as e:              # keep the sweep going, record the failure
        rec = {"well": well, "t": t_index, "error": repr(e)}
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps(rec))
    return rec


# -------------------------------------------------------------------------- main
def timepoints() -> list[str]:
    d = DATA / "wells"
    first = next(p for p in sorted(d.iterdir()) if p.is_dir())
    stamps = set()
    for f in (first / "green").iterdir():
        if "_plane" in f.name:
            stamps.add(f.name.split("_1_")[1].split("_plane")[0])
    return sorted(stamps)


def all_wells() -> list[str]:
    return sorted(p.name for p in (DATA / "wells").iterdir() if p.is_dir())


def plate_map() -> dict[str, dict]:
    f = DATA / "plate_map.csv"
    if not f.is_file():
        return {}
    with open(f, newline="") as fh:
        return {r["well"]: r for r in csv.DictReader(fh)}


CSV_FIELDS = [
    "well", "t", "stamp", "hours", "condition", "coculture", "compound", "concentration",
    "has_tcells", "has_macrophages", "has_cafs",
    "tumour_count", "tumour_hull_mm2", "tumour_hull_frac", "tumour_volume_um3",
    "tumour_vox", "tumour_mean_z",
    "t_count", "t_inside_hull", "t_frac_inside_hull", "infiltration_ratio",
    "t_median_dist_um", "t_frac_within_25um", "t_enrich_25um",
    "t_frac_within_50um", "t_enrich_50um", "t_frac_within_100um", "t_enrich_100um",
    "t_vox_total", "t_mean_z",
    "dead_count", "dead_inside_hull", "dead_frac_inside_hull", "dead_density_ratio",
    "dead_median_dist_um", "dead_frac_within_50um", "dead_enrich_50um",
    "dead_on_tumour", "dead_on_tcell", "dead_on_both", "dead_on_neither", "dead_mean_z",
    "random_frac_within_50um", "field_mm2", "error",
]


def write_csv(records: list[dict], pm: dict, stamps: list[str], dst: Path):
    hours = {}
    if stamps:
        import time as _t
        base = None
        for i, s in enumerate(stamps):
            ts = _t.mktime(_t.strptime(s, "%Yy%mm%dd_%Hh%Mm"))
            base = ts if base is None else base
            hours[i] = round((ts - base) / 3600, 1)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(records, key=lambda x: (x["well"], x["t"])):
            meta = pm.get(r["well"], {})
            w.writerow({**r,
                        "hours": hours.get(r["t"], ""),
                        "condition": meta.get("condition", ""),
                        "coculture": meta.get("coculture", ""),
                        "compound": meta.get("compound", ""),
                        "concentration": meta.get("concentration", ""),
                        "has_tcells": "yes" if meta.get("t_cells") else "no",
                        "has_macrophages": "yes" if meta.get("macrophages") else "no",
                        "has_cafs": "yes" if meta.get("cafs") else "no"})
    print(f"→ {dst}")


def run_check(z_step: float, jobs: int):
    pm = plate_map()
    stamps = timepoints()
    wells = all_wells()
    with_t = [w for w in wells if pm.get(w, {}).get("t_cells")][:6]
    without_t = [w for w in wells if not pm.get(w, {}).get("t_cells")][:6]
    tasks = [(w, stamps[-1], len(stamps) - 1, z_step) for w in with_t + without_t]
    recs = {}
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for r in ex.map(_job, tasks):
            recs[r["well"]] = r

    print("\nKONTROL — son zaman noktası")
    print(f'{"kuyu":6s} {"T ekli":7s} {"T nesne":>8s} {"tümör":>7s} {"kabuk%":>7s} '
          f'{"içeride%":>9s} {"infilt.":>8s} {"medyan µm":>10s} {"ölü":>5s}')
    for grp, ws in (("evet", with_t), ("hayır", without_t)):
        for w in ws:
            r = recs.get(w, {})
            if r.get("error"):
                print(f'{w:6s} {grp:7s} HATA {r["error"][:50]}')
                continue
            ir = r["infiltration_ratio"]
            print(f'{w:6s} {grp:7s} {r["t_count"]:>8d} {r["tumour_count"]:>7d} '
                  f'{100 * r["tumour_hull_frac"]:>7.0f} '
                  f'{100 * (r["t_frac_inside_hull"] or 0):>9.0f} '
                  f'{("%.2f" % ir) if ir is not None else "—":>8s} '
                  f'{(r["t_median_dist_um"] if r["t_median_dist_um"] is not None else -1):>10.0f} '
                  f'{r["dead_count"]:>5d}')
    a = [recs[w]["t_count"] for w in with_t if not recs[w].get("error")]
    b = [recs[w]["t_count"] for w in without_t if not recs[w].get("error")]
    if a and b:
        print(f'\nortalama T nesne: T ekli {np.mean(a):.0f} · eklenmemiş {np.mean(b):.0f} '
              f'· kat {np.mean(a) / max(np.mean(b), 1e-9):.1f}×')
        print("Bu kat 1'den belirgin büyük olmalı; değilse segmentasyon güvenilmez.")
    print("infilt. = kabuk içi T yoğunluğu / kabuk dışı. 1 = rastgele, <1 dışlanma, >1 zenginleşme.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wells", type=lambda v: [x.strip() for x in v.split(",")])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--t", default="all", help="12, 0-4, 0,6,12 veya all")
    ap.add_argument("--z-step", type=float, default=10.0, dest="z_step",
                    help="µm — dosyalarda kayıtlı değil, yalnızca hacim birimlerini etkiler")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--out", default=str(OUT / "summary.csv"))
    args = ap.parse_args()

    if args.force and OUT.is_dir():
        for f in OUT.glob("*.json"):
            f.unlink()

    if args.check:
        run_check(args.z_step, args.jobs)
        return

    wells = all_wells() if args.all else (args.wells or [])
    if not wells:
        ap.error("--all veya --wells gerekli (ya da --check)")
    known = set(all_wells())
    bad = [w for w in wells if w not in known]
    if bad:
        ap.error(f"bilinmeyen kuyu: {bad}")

    stamps = timepoints()
    if args.t == "all":
        ts = list(range(len(stamps)))
    elif "-" in args.t:
        a, b = args.t.split("-")
        ts = list(range(int(a), int(b) + 1))
    else:
        ts = [int(x) for x in args.t.split(",")]
    bad = [t for t in ts if not 0 <= t < len(stamps)]
    if bad:
        ap.error(f"zaman noktası aralık dışı: {bad} (0–{len(stamps) - 1})")

    tasks = [(w, stamps[t], t, args.z_step) for w in wells for t in ts]
    print(f"{len(wells)} kuyu × {len(ts)} zaman = {len(tasks)} örnek, {args.jobs} işlem")
    t0 = time.time()
    recs, done = [], 0
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futs = [ex.submit(_job, task) for task in tasks]
        for f in as_completed(futs):
            recs.append(f.result())
            done += 1
            if done % 25 == 0 or done == len(tasks):
                el = time.time() - t0
                print(f"  {done}/{len(tasks)}  geçen {el / 60:.1f} dk  "
                      f"kalan ~{el / done * (len(tasks) - done) / 60:.1f} dk", flush=True)

    errs = [r for r in recs if r.get("error")]
    if errs:
        print(f"\n{len(errs)} örnek başarısız, ilk 5:")
        for r in errs[:5]:
            print(f'  {r["well"]} t{r["t"]:02d}: {r["error"]}')
    write_csv(recs, plate_map(), stamps, Path(args.out))


if __name__ == "__main__":
    main()
