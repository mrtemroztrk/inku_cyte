#!/usr/bin/env python3
"""The dome: where the tumour mass is, and what is inside it.

Defining "inside the dome" turned out to be the whole problem, so here is why this
definition and not another:

* Thresholding the brightfield dark disc looked obvious and failed — the aggregate
  is only 2-5σ darker than a background that itself varies, so across 11 test wells
  the fitted radius ranged 44-954 µm and the centre landed on the image edge in
  several of them. One well produced nothing at all.
* A convex hull around the segmented tumour cells is stable but is not a dome: it
  covered 23% of the field in one well and 72% in another, so "% of T cells inside"
  became a statement about hull size rather than about biology.
* What is stable is the **radial distribution of tumour signal about its own
  centroid**. R90 (the radius containing 90% of the green signal) came out
  760-1730 µm across the same test wells with a shape factor R90/R50 of 1.2-1.65 in
  every single one — a consistent, well-behaved measurement that tracks how spread
  the tumour actually is.

So the dome is a disc: centre = the tumour signal's centroid, radius = R90. Every
cell gets a normalised radius u = r / R90, which makes the read-out explicit and
drawable: u < 1 is inside the dome, and the radial profile shows how far in the T
cells actually got.

The z direction is deliberately not part of the boundary. At 2.798 µm/px the
objective is a 4x (NA ~0.13) whose depth of field is tens of microns, so objects
smear along z; a 3D containment test would mostly be measuring that smear. Depth is
reported separately, as a distribution.
"""
from __future__ import annotations

import numpy as np

# Normalised-radius bands. u = r / R90, so u<1 is inside the dome.
BANDS = ((0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.0), (1.0, 1.5), (1.5, np.inf))
BAND_LABELS = ["0–0.25 R", "0.25–0.5 R", "0.5–0.75 R", "0.75–1 R", "1–1.5 R", ">1.5 R"]


def fit_dome(signal_2d: np.ndarray, um_per_px: float) -> dict | None:
    """Centre and radial quantiles of a 2D signal map (use the tumour channel's MIP).

    Returns radii in µm. None when there is no signal to fit.
    """
    tot = float(signal_2d.sum())
    if tot <= 0:
        return None
    h, w = signal_2d.shape
    ys, xs = np.mgrid[0:h, 0:w]
    cy = float((ys * signal_2d).sum() / tot)
    cx = float((xs * signal_2d).sum() / tot)

    r = np.hypot(ys - cy, xs - cx).ravel() * um_per_px
    wts = signal_2d.ravel()
    order = np.argsort(r)
    r_sorted = r[order]
    cum = np.cumsum(wts[order]) / tot
    q = {p: float(r_sorted[np.searchsorted(cum, p / 100.0)]) for p in (50, 75, 90, 95)}

    return {
        "cy_px": cy, "cx_px": cx,
        "cy_um": cy * um_per_px, "cx_um": cx * um_per_px,
        "r50_um": q[50], "r75_um": q[75], "r90_um": q[90], "r95_um": q[95],
        "radius_um": q[90],                       # the dome boundary
        "shape_factor": round(q[90] / max(q[50], 1e-9), 3),
        "area_mm2": round(np.pi * q[90] ** 2 / 1e6, 4),
    }


def normalised_radius(points_yx: np.ndarray, dome: dict, um_per_px: float) -> np.ndarray:
    """u = r / R90 for object centroids given as (y, x) in pixels."""
    if not len(points_yx) or dome is None or dome["radius_um"] <= 0:
        return np.zeros(len(points_yx))
    dy = points_yx[:, 0] - dome["cy_px"]
    dx = points_yx[:, 1] - dome["cx_px"]
    return np.hypot(dy, dx) * um_per_px / dome["radius_um"]


def band_index(u: np.ndarray) -> np.ndarray:
    edges = np.array([b[1] for b in BANDS[:-1]])
    return np.searchsorted(edges, u, side="right")


def radial_profile(u: np.ndarray, dome: dict, field_px: tuple[int, int],
                   um_per_px: float) -> dict:
    """Counts and areal densities per radial band, plus the fraction inside the dome.

    Densities matter, not raw counts: the outer bands cover far more area, so counts
    alone would always look like "most cells are outside".
    """
    h, w = field_px
    R = dome["radius_um"] if dome else 0.0
    counts = np.bincount(band_index(u), minlength=len(BANDS)).tolist() if len(u) else [0] * len(BANDS)

    # Band areas, clipped to the imaged field: an annulus at u>1.5 mostly falls
    # outside the frame, and counting its full geometric area would deflate density.
    ys, xs = np.mgrid[0:h, 0:w]
    if R > 0:
        uu = np.hypot(ys - dome["cy_px"], xs - dome["cx_px"]) * um_per_px / R
        idx = band_index(uu.ravel())
        px_per_band = np.bincount(idx, minlength=len(BANDS))
    else:
        px_per_band = np.zeros(len(BANDS), dtype=int)
    areas_mm2 = px_per_band * (um_per_px ** 2) / 1e6

    dens = [round(c / a, 1) if a > 0 else None for c, a in zip(counts, areas_mm2)]
    inside = int(sum(counts[:4]))
    total = int(sum(counts))
    area_in = float(areas_mm2[:4].sum())
    area_out = float(areas_mm2[4:].sum())
    d_in = inside / area_in if area_in > 0 else None
    d_out = (total - inside) / area_out if area_out > 0 else None

    return {
        "counts": counts,
        "areas_mm2": [round(float(a), 4) for a in areas_mm2],
        "density_mm2": dens,
        "inside": inside,
        "total": total,
        "frac_inside": round(inside / total, 4) if total else None,
        "density_in_mm2": round(d_in, 1) if d_in is not None else None,
        "density_out_mm2": round(d_out, 1) if d_out is not None else None,
        # 1.0 = evenly spread, <1 = kept out of the dome, >1 = concentrated in it.
        # Zero is the most informative value here (total exclusion), so test for
        # None rather than truthiness — `if d_in` would drop it.
        "ratio": (round(d_in / d_out, 3)
                  if (d_in is not None and d_out is not None and d_out > 0) else None),
        "median_u": round(float(np.median(u)), 3) if len(u) else None,
    }
