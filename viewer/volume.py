#!/usr/bin/env python3
"""Depth analysis and 3D projection of the z-stacks.

What the data supports, measured before building this:

* There is genuine depth content — a plane's correlation with the middle plane
  falls from 1.00 to ~0.35 at the ends of the stack, so the 17 planes are not one
  image blurred 17 times.
* Orange (T cells) has a sharp focus peak: gradient energy 4.7 at z3-z4 versus 1.1
  at z16, and its signal peaks there too. Green (tumour) is flat across z.
* Axial resolution is nonetheless poor: the 2.798 µm/px scale means a 4x
  objective (NA ~0.13), whose depth of field is tens of microns. Expect
  depth *slabs*, not fine 3D structure, and expect out-of-focus haze.
* The z step is not recorded anywhere in the files and cannot be recovered from
  them, so it is a parameter (`z_step_um`). Everything below is geometrically
  correct once that number is right.

Rendering uses shear-warp parallel projection: a parallel view of a stack of
planes is each plane translated proportionally to its depth, so a rotation costs
17 image shifts rather than a full volume resample.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

# Colours match the viewer's channel defaults.
CHANNEL_RGB = {
    "bf": (255, 255, 255),
    "green": (61, 220, 80),
    "orange": (255, 138, 43),
    "nir": (255, 59, 107),
}


def subtract_background(plane: np.ndarray) -> np.ndarray:
    """Per-plane background removal. The level drifts with z (defocus) and per well."""
    return np.clip(plane - float(np.median(plane)), 0, None)


def bin_xy(a: np.ndarray, k: int) -> np.ndarray:
    if k <= 1:
        return a
    h, w = a.shape
    a = a[: h // k * k, : w // k * k]
    return a.reshape(h // k, k, w // k, k).mean((1, 3))


def build_volume(planes: list[np.ndarray], k: int) -> np.ndarray:
    """(nz, h, w) float32, background-subtracted and XY-binned."""
    return np.stack([bin_xy(subtract_background(p.astype(np.float32)), k) for p in planes])


def find_object_bbox(mip: np.ndarray, margin: float = 0.25) -> tuple[int, int, int, int]:
    """Bounding box of the main structure, so the 3D view can crop to it.

    The field is ~2.9 mm wide while the stack is only 17 planes deep, so a
    full-field 3D view is a sliver no matter how it is rendered. Cropping to the
    spheroid puts the depth and the width on comparable scales, which is the only
    way the projection reads as a shape rather than a smear.
    """
    h, w = mip.shape
    sm = ndimage.gaussian_filter(mip, max(2.0, min(h, w) / 120))
    thr = np.percentile(sm, 97.0)
    mask = sm > thr
    if mask.sum() < 25:
        return 0, 0, h, w
    mask = ndimage.binary_closing(mask, np.ones((7, 7)))
    lab, n = ndimage.label(mask)
    if n == 0:
        return 0, 0, h, w
    sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))
    ys, xs = np.where(lab == int(np.argmax(sizes)) + 1)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    my, mx = int((y1 - y0) * margin), int((x1 - x0) * margin)
    return (max(0, y0 - my), max(0, x0 - mx), min(h, y1 + my), min(w, x1 + mx))


# ------------------------------------------------------------------ measurements
def z_profile(vol: np.ndarray, hi: float) -> dict:
    """Per-plane summary: how much signal sits in each layer, and where focus is."""
    sig, area, sharp = [], [], []
    thr = hi * 0.5
    for z in range(vol.shape[0]):
        p = vol[z]
        sig.append(float(p.mean()))
        area.append(float((p > thr).mean()))
        sharp.append(float(np.abs(np.diff(p, axis=0)).mean() + np.abs(np.diff(p, axis=1)).mean()))
    total = sum(sig) or 1.0
    return {
        "signal": [round(v, 5) for v in sig],
        "share": [round(v / total, 5) for v in sig],       # fraction of the channel's signal
        "area_frac": [round(v, 6) for v in area],
        "sharpness": [round(v, 5) for v in sharp],
        "focus_z": int(np.argmax(sharp)),
        "peak_z": int(np.argmax(sig)),
        "centroid_z": round(float((np.arange(len(sig)) * np.array(sig)).sum() / total), 2),
    }


def depth_map(vol: np.ndarray, hi: float) -> tuple[np.ndarray, np.ndarray]:
    """Intensity-weighted mean depth per pixel (0..nz-1) and the MIP weight."""
    w = np.clip(vol - hi * 0.15, 0, None)
    tot = w.sum(0)
    zs = np.arange(vol.shape[0], dtype=np.float32)[:, None, None]
    mean_z = np.where(tot > 0, (w * zs).sum(0) / np.maximum(tot, 1e-9), np.nan)
    return mean_z, vol.max(0)


TURBO = np.array([  # perceptually ordered depth ramp, dark blue → red
    (48, 18, 59), (61, 84, 179), (39, 150, 235), (30, 200, 190),
    (94, 227, 105), (188, 234, 55), (247, 190, 45), (246, 116, 32),
    (207, 48, 18), (122, 4, 3),
], dtype=np.float32)


def depth_coded_rgb(vol: np.ndarray, hi: float) -> np.ndarray:
    """One image where hue says *which layer* the signal came from."""
    mean_z, weight = depth_map(vol, hi)
    nz = vol.shape[0]
    f = np.clip(np.nan_to_num(mean_z, nan=0.0) / max(nz - 1, 1), 0, 1) * (len(TURBO) - 1)
    i0 = np.floor(f).astype(int)
    i1 = np.minimum(i0 + 1, len(TURBO) - 1)
    frac = (f - i0)[..., None]
    col = TURBO[i0] * (1 - frac) + TURBO[i1] * frac
    v = np.clip(weight / max(hi, 1e-9), 0, 1)[..., None]
    rgb = col * v
    rgb[np.isnan(mean_z)] = 0
    return np.clip(rgb, 0, 255).astype(np.uint8)


# -------------------------------------------------------------------- projection
def project(vol: np.ndarray, z_px: float, az: float, el: float) -> np.ndarray:
    """Shear-warp parallel projection (max along the view ray).

    az rotates within the plate plane, el tilts the stack towards the viewer.
    z_px is the z step expressed in binned pixels, so geometry is to scale.
    """
    # Resample to (near-)isotropic voxels first. Without this each plane lands on
    # its own row band and the projection comes out striped, because the per-plane
    # shift is several pixels while the planes are one voxel thick.
    nz0 = vol.shape[0]
    if z_px > 1.2 and nz0 > 1:
        nz_iso = int(round((nz0 - 1) * z_px)) + 1
        vol = ndimage.zoom(vol, (nz_iso / nz0, 1.0, 1.0), order=1)
        z_px = (nz0 - 1) * z_px / max(vol.shape[0] - 1, 1)

    nz, h, w = vol.shape
    e = np.deg2rad(el)

    planes = vol
    if abs(az) > 0.5:
        planes = ndimage.rotate(vol, az, axes=(2, 1), reshape=False, order=1,
                                mode="constant", cval=0.0)

    ce, se = np.cos(e), np.sin(e)
    span = int(round(abs((nz - 1) * z_px * se)))
    out_h = max(2, int(round(h * ce)) + span)
    out = np.zeros((out_h, w), dtype=np.float32)

    squeezed_h = max(1, int(round(h * ce)))
    for k in range(nz):
        p = planes[k]
        if squeezed_h != h:
            p = ndimage.zoom(p, (squeezed_h / h, 1.0), order=1)
        off = int(round((k - (nz - 1) / 2) * z_px * se)) + span // 2
        y0 = max(0, off)
        y1 = min(out_h, off + p.shape[0])
        if y1 <= y0:
            continue
        np.maximum(out[y0:y1], p[y0 - off: y1 - off], out=out[y0:y1])
    return out


def ortho_xz(vol: np.ndarray, y: int, z_px: float, thickness: int = 5) -> np.ndarray:
    """Vertical cut at row y, z stretched to scale — the infiltration-depth view."""
    nz, h, w = vol.shape
    y0, y1 = max(0, y - thickness // 2), min(h, y + thickness // 2 + 1)
    slab = vol[:, y0:y1, :].max(1)              # (nz, w)
    out_h = max(2, int(round((nz - 1) * z_px)) + 1)
    return ndimage.zoom(slab, (out_h / nz, 1.0), order=1)


def ortho_yz(vol: np.ndarray, x: int, z_px: float, thickness: int = 5) -> np.ndarray:
    nz, h, w = vol.shape
    x0, x1 = max(0, x - thickness // 2), min(w, x + thickness // 2 + 1)
    slab = vol[:, :, x0:x1].max(2)              # (nz, h)
    out_w = max(2, int(round((nz - 1) * z_px)) + 1)
    return ndimage.zoom(slab, (out_w / nz, 1.0), order=1).T   # (h, out_w)


def colorize(gray01: np.ndarray, rgb: tuple[int, int, int]) -> np.ndarray:
    return gray01[..., None] * np.array(rgb, dtype=np.float32)


def combine(layers: list[np.ndarray]) -> np.ndarray:
    """Additive compositing, as in the 2D viewer."""
    out = None
    for l in layers:
        out = l if out is None else out + l
    return np.clip(out if out is not None else np.zeros((2, 2, 3)), 0, 255).astype(np.uint8)
