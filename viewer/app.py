#!/usr/bin/env python3
"""inc_tests viewer — FastAPI backend.

Serves single-channel 8-bit PNG frames out of the reorganized inc_tests tree so the
browser can composite them additively. Channels stay separate on the wire: colour,
opacity and contrast are client-side, so changing them never costs a round trip.

Run:  python viewer/app.py            (or: uvicorn viewer.app:app --port 8000)
"""
from __future__ import annotations

import io
import json
import os
import re
import csv
import sys
import time
import threading
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import dome
import volume

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("INC_DATA", HERE.parent / "data" / "inc_tests")).resolve()
CACHE = Path(os.environ.get("INC_CACHE", HERE / "cache"))
STATIC = HERE / "static"

# Byte budget for decoded planes held in RAM. A float32 plane is ~5.9 MB.
PLANE_CACHE_BYTES = int(os.environ.get("INC_PLANE_CACHE_MB", "1500")) * 1024 * 1024
MIP_CACHE_BYTES = int(os.environ.get("INC_MIP_CACHE_MB", "600")) * 1024 * 1024

CHANNELS = [
    {"id": "bf", "label": "Brightfield", "detail": "BF_Tcell_Infil_dye · tek düzlem",
     "color": "#ffffff", "base": True},
    {"id": "green", "label": "Green", "detail": "Green_Zstacks · z-stack",
     "color": "#3ddc50", "base": False},
    {"id": "orange", "label": "Orange", "detail": "Orange_Tcells · T hücreleri",
     "color": "#ff8a2b", "base": False},
    {"id": "nir", "label": "NIR", "detail": "NIR_deadCells · ölü hücreler",
     "color": "#ff3b6b", "base": False},
]
CHANNEL_IDS = [c["id"] for c in CHANNELS]

# Incucyte writes a dummy 72 dpi into the TIFFs, but its own composite export
# (extras/vid119_B2) is annotated "2.91 x 3.94 mm" for a 1040 x 1408 px field —
# 2.91/1040 == 3.94/1408 == 2.798 µm/px. That is the real plate scale.
DEFAULT_UM_PER_PX = float(os.environ.get("INC_UM_PER_PX", "2.798"))

# Brightfield display window used by the instrument itself. Recovered by fitting
# the grey component of VID119 against the BF TIFFs: grey ≈ 1.95·BF − 112, stable
# across all 13 timepoints (R² ≈ 0.98). Using it makes the viewer look like the
# original software instead of a washed-out version of it.
INCUCYTE_BF_WINDOW = (57.5, 187.5)

STAMP_RE = re.compile(r"_(\d{4})y(\d{2})m(\d{2})d_(\d{2})h(\d{2})m")
PLANE_RE = re.compile(r"_plane(\d+)_\.tif$")


# --------------------------------------------------------------------------- cache
class ByteLRU:
    """Thread-safe LRU keyed by hashables, bounded by total nbytes of the values."""

    def __init__(self, max_bytes: int):
        self.max_bytes = max_bytes
        self._d: OrderedDict = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()
        self.hits = self.misses = 0

    def get(self, key):
        with self._lock:
            if key in self._d:
                self._d.move_to_end(key)
                self.hits += 1
                return self._d[key]
            self.misses += 1
            return None

    def put(self, key, val):
        n = getattr(val, "nbytes", None) or len(val)
        with self._lock:
            if key in self._d:
                self._bytes -= getattr(self._d[key], "nbytes", 0) or len(self._d[key])
                del self._d[key]
            self._d[key] = val
            self._bytes += n
            while self._bytes > self.max_bytes and len(self._d) > 1:
                _, old = self._d.popitem(last=False)
                self._bytes -= getattr(old, "nbytes", 0) or len(old)

    def stats(self):
        return {"items": len(self._d), "mb": round(self._bytes / 1e6, 1),
                "hits": self.hits, "misses": self.misses}


PLANES = ByteLRU(PLANE_CACHE_BYTES)
MIPS = ByteLRU(MIP_CACHE_BYTES)


# --------------------------------------------------------------------------- index
class Index:
    """well -> channel -> t-index -> {z: path}, built by walking the tree."""

    def __init__(self, root: Path):
        self.root = root
        self.stamps: list[str] = []
        self.tp: list[dict] = []
        self.map: dict[str, dict[str, dict[int, dict[int, Path]]]] = {}
        self.nz: dict[str, int] = {}
        self.plate: dict[str, dict] = {}
        self.extras: dict[int, Path] = {}
        self.extras_well: str | None = None
        self._build()

    def _build(self):
        wells_dir = self.root / "wells"
        if not wells_dir.is_dir():
            raise SystemExit(
                f"{wells_dir} yok. Beklenen yapı: <veri>/wells/<A01>/<bf|green|orange|nir>/*.tif\n"
                f"INC_DATA ile veri kökünü belirtin."
            )
        stamps: set[str] = set()
        raw: dict = {}
        for well_dir in sorted(p for p in wells_dir.iterdir() if p.is_dir()):
            well = well_dir.name
            per_ch = {}
            for ch in CHANNEL_IDS:
                cdir = well_dir / ch
                if not cdir.is_dir():
                    continue
                by_stamp: dict[str, dict[int, Path]] = {}
                for f in cdir.iterdir():
                    if f.suffix.lower() not in (".tif", ".tiff"):
                        continue
                    mo = STAMP_RE.search(f.name)
                    if not mo:
                        continue
                    stamp = "{}-{}-{}T{}:{}".format(*mo.groups())
                    zmo = PLANE_RE.search(f.name)
                    z = int(zmo.group(1)) if zmo else 0
                    by_stamp.setdefault(stamp, {})[z] = f
                    stamps.add(stamp)
                if by_stamp:
                    per_ch[ch] = by_stamp
                    self.nz[ch] = max(self.nz.get(ch, 0), max(len(v) for v in by_stamp.values()))
            if per_ch:
                raw[well] = per_ch

        self.stamps = sorted(stamps)
        idx = {s: i for i, s in enumerate(self.stamps)}
        for well, per_ch in raw.items():
            self.map[well] = {
                ch: {idx[s]: zs for s, zs in by_stamp.items()} for ch, by_stamp in per_ch.items()
            }

        # real datetimes + elapsed hours
        t0 = time.mktime(time.strptime(self.stamps[0], "%Y-%m-%dT%H:%M")) if self.stamps else 0
        for i, s in enumerate(self.stamps):
            ts = time.mktime(time.strptime(s, "%Y-%m-%dT%H:%M"))
            self.tp.append({"t": f"t{i:02d}", "index": i, "datetime": s,
                            "hours": round((ts - t0) / 3600, 1)})

        self._read_plate_map()
        self._find_extras()

    def _read_plate_map(self):
        csv_path = self.root / "plate_map.csv"
        if not csv_path.is_file():
            return
        with open(csv_path, newline="") as fh:
            for row in csv.DictReader(fh):
                self.plate[row["well"]] = row

    def _find_extras(self):
        base = self.root / "extras"
        if not base.is_dir():
            return
        for d in sorted(base.iterdir()):
            if not d.is_dir():
                continue
            idx = {s: i for i, s in enumerate(self.stamps)}
            for f in d.iterdir():
                mo = STAMP_RE.search(f.name)
                if mo and f.suffix.lower() in (".tif", ".tiff"):
                    stamp = "{}-{}-{}T{}:{}".format(*mo.groups())
                    if stamp in idx:
                        self.extras[idx[stamp]] = f
            if self.extras:
                wmo = re.search(r"_([A-H])(\d{1,2})_1_", next(iter(self.extras.values())).name)
                if wmo:
                    self.extras_well = f"{wmo.group(1)}{int(wmo.group(2)):02d}"
                break

    @property
    def wells(self):
        return sorted(self.map)

    def path(self, well: str, ch: str, t: int, z: int) -> Path:
        try:
            zs = self.map[well][ch][t]
        except KeyError:
            raise HTTPException(404, f"yok: {well}/{ch}/t{t:02d}")
        if z in zs:
            return zs[z]
        if len(zs) == 1:  # brightfield: single plane, z is ignored
            return next(iter(zs.values()))
        raise HTTPException(404, f"yok: {well}/{ch}/t{t:02d}/z{z:02d}")

    def zcount(self, well: str, ch: str, t: int) -> int:
        try:
            return len(self.map[well][ch][t])
        except KeyError:
            return 0


IDX: Index


# ------------------------------------------------------------------------ imaging
def load_plane(path: Path) -> np.ndarray:
    key = str(path)
    a = PLANES.get(key)
    if a is None:
        a = tifffile.imread(path)
        if a.ndim == 3:  # RGB extras
            a = a.astype(np.float32).mean(axis=2)
        a = np.ascontiguousarray(a)
        PLANES.put(key, a)
    return a


def load_mip(well: str, ch: str, t: int) -> np.ndarray:
    key = (well, ch, t)
    a = MIPS.get(key)
    if a is None:
        zs = IDX.map[well][ch][t]
        acc = None
        for z in sorted(zs):
            p = load_plane(zs[z]).astype(np.float32, copy=False)
            acc = p.copy() if acc is None else np.maximum(acc, p)
        a = acc
        MIPS.put(key, a)
    return a


def get_frame(well: str, ch: str, t: int, z: int, mip: bool) -> np.ndarray:
    if mip and IDX.zcount(well, ch, t) > 1:
        return load_mip(well, ch, t)
    return load_plane(IDX.path(well, ch, t, z))


def percentiles(a: np.ndarray, plo: float, phi: float) -> tuple[float, float]:
    """Robust display range for one frame.

    NIR is >99.9% background, so a plain p99.8 lands on the background value and
    lo == hi — which would render the frame as a hard binary mask. When that
    happens, fall back to the distribution of above-background pixels.
    """
    flat = a.reshape(-1)
    if flat.size > 400_000:  # subsample: percentiles are stable well before this
        flat = flat[:: max(1, flat.size // 400_000)]
    lo, hi = (float(v) for v in np.percentile(flat, [plo, phi]))
    if hi > lo:
        return lo, hi
    above = flat[flat > lo]
    if above.size:
        hi = float(np.percentile(above, 99.0))
    if hi <= lo:
        hi = float(flat.max())
    if hi <= lo:
        hi = lo + 1.0
    return lo, hi


def frame_median(a: np.ndarray) -> float:
    """Background level of a frame. Most of the field is background, so the median
    is it — and it drifts per well (media autofluorescence) and per z-projection."""
    flat = a.reshape(-1)
    if flat.size > 200_000:
        flat = flat[:: max(1, flat.size // 200_000)]
    return float(np.median(flat))


def resolve_range(a: np.ndarray, lo, hi, off_lo, off_hi, plo, phi) -> tuple[float, float]:
    if off_lo is not None and off_hi is not None:
        m = frame_median(a)
        return m + off_lo, m + off_hi
    if lo is not None and hi is not None:
        return lo, hi
    alo, ahi = percentiles(a, plo, phi)
    return (alo if lo is None else lo), (ahi if hi is None else hi)


def to_u8(a: np.ndarray, lo: float, hi: float, gamma: float) -> np.ndarray:
    if hi <= lo:
        hi = lo + 1e-6
    x = (a.astype(np.float32, copy=False) - lo) / (hi - lo)
    np.clip(x, 0.0, 1.0, out=x)
    if abs(gamma - 1.0) > 1e-3:
        x **= 1.0 / max(gamma, 1e-3)
    return (x * 255.0 + 0.5).astype(np.uint8)


def encode(u8: np.ndarray, fmt: str, max_w: int | None) -> tuple[bytes, str]:
    im = Image.fromarray(u8, mode="L")
    if max_w and im.width > max_w:
        h = max(1, round(im.height * max_w / im.width))
        im = im.resize((max_w, h), Image.BILINEAR)
    buf = io.BytesIO()
    if fmt == "jpeg":
        im.save(buf, "JPEG", quality=88)
        return buf.getvalue(), "image/jpeg"
    im.save(buf, "PNG", compress_level=1)
    return buf.getvalue(), "image/png"


# ----------------------------------------------------------------- display ranges
_ranges_memo: dict | None = None


def default_ranges() -> dict:
    """Global per-channel display statistics, from scan_stats.py if it has been run."""
    global _ranges_memo
    if _ranges_memo is None:
        f = CACHE / "channel_stats.json"
        _ranges_memo = {}
        if f.is_file():
            try:
                _ranges_memo = json.loads(f.read_text())
            except Exception:
                pass
    return _ranges_memo


def display_defaults() -> dict:
    """What each channel should look like out of the box, per channel id.

    Brightfield gets the instrument's own absolute window; the fluorescence
    channels get a black point that follows each frame's background (it drifts
    per well) with a gain measured across the plate.
    """
    out = {}
    for ch in CHANNEL_IDS:
        s = stat_for(ch, False)
        if ch == "bf":
            out[ch] = {"mode": "abs", "lo": INCUCYTE_BF_WINDOW[0],
                       "hi": INCUCYTE_BF_WINDOW[1], "opacity": 1.0}
        elif s:
            out[ch] = {"mode": "rel", "off_lo": s["off_lo"], "off_hi": s["off_hi"],
                       "opacity": 1.0}
        else:
            out[ch] = {"mode": "auto", "opacity": 1.0}
    return out


def stat_for(ch: str, mip: bool) -> dict | None:
    """Plane or MIP statistics block for a channel, whichever applies."""
    e = default_ranges().get(ch)
    if not e:
        return None
    return (e.get("mip") if mip else None) or e.get("plane")


def display_range(a: np.ndarray, ch: str, mip: bool, bright: float = 1.0) -> tuple[float, float]:
    """The default display window for a frame. `bright` > 1 narrows it (brighter)."""
    d = display_defaults().get(ch, {"mode": "auto"})
    if d["mode"] == "abs":
        lo = d["lo"]
        return lo, lo + (d["hi"] - lo) / max(bright, 1e-3)
    if d["mode"] == "rel":
        s = stat_for(ch, mip) or {}
        off_lo = s.get("off_lo", d["off_lo"])
        off_hi = s.get("off_hi", d["off_hi"])
        m = frame_median(a)
        return m + off_lo, m + off_hi / max(bright, 1e-3)
    return percentiles(a, 1.0, 99.8)


# --------------------------------------------------------------------------- app
@asynccontextmanager
async def lifespan(_app: FastAPI):
    global IDX
    t = time.time()
    IDX = Index(DATA)
    CACHE.mkdir(parents=True, exist_ok=True)
    print(f"[viewer] {DATA}: {len(IDX.wells)} kuyu, {len(IDX.tp)} zaman noktası, "
          f"z={IDX.nz} ({time.time() - t:.1f}s)", flush=True)
    yield


app = FastAPI(title="inc_tests viewer", lifespan=lifespan)


@app.get("/api/meta")
def meta():
    chans = []
    for c in CHANNELS:
        nz = IDX.nz.get(c["id"], 0)
        if nz:
            chans.append({**c, "nz": nz})
    return {
        "data_root": str(DATA),
        "wells": IDX.wells,
        "timepoints": IDX.tp,
        "channels": chans,
        "nz": max(IDX.nz.values()) if IDX.nz else 1,
        "plate": IDX.plate,
        "rows": sorted({w[0] for w in IDX.wells}),
        "cols": sorted({int(w[1:]) for w in IDX.wells}),
        "ranges": default_ranges(),
        "defaults": display_defaults(),
        "um_per_px": DEFAULT_UM_PER_PX,
        "z_step_um": DEFAULT_Z_STEP_UM,
        "z_step_known": False,
        "extras": {"well": IDX.extras_well, "timepoints": sorted(IDX.extras)}
                  if IDX.extras else None,
    }


@app.get("/api/frame/{well}/{ch}")
def frame(
    well: str, ch: str,
    t: int = 0, z: int = 0, mip: int = 0,
    lo: float | None = None, hi: float | None = None,
    off_lo: float | None = Query(None, description="black point relative to frame median"),
    off_hi: float | None = Query(None, description="white point relative to frame median"),
    plo: float = 1.0, phi: float = 99.8,
    gamma: float = 1.0,
    w: int | None = Query(None, description="downsample to this width"),
    fmt: str = "png",
):
    a = get_frame(well, ch, t, z, bool(mip))
    lo, hi = resolve_range(a, lo, hi, off_lo, off_hi, plo, phi)
    body, mtype = encode(to_u8(a, lo, hi, gamma), fmt, w)
    return Response(body, media_type=mtype, headers={
        "Cache-Control": "public, max-age=3600",
        "X-Range": f"{lo:.6g},{hi:.6g}",
    })


@app.get("/api/autorange/{well}/{ch}")
def autorange(well: str, ch: str, t: int = 0, z: int = 0, mip: int = 0,
              plo: float = 1.0, phi: float = 99.8):
    a = get_frame(well, ch, t, z, bool(mip))
    lo, hi = percentiles(a, plo, phi)
    return {"lo": lo, "hi": hi, "median": frame_median(a),
            "min": float(a.min()), "max": float(a.max())}


@app.get("/api/extra/{t}")
def extra(t: int, w: int | None = None):
    """VID119 RGB composite for the one well that has it."""
    p = IDX.extras.get(t)
    if p is None:
        raise HTTPException(404, "extra yok")
    im = Image.open(p).convert("RGB")
    if w and im.width > w:
        im = im.resize((w, round(im.height * w / im.width)), Image.BILINEAR)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return Response(buf.getvalue(), media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/thumb/{well}")
def thumb(well: str, t: int = 0, mode: str = "bf", size: int = 150):
    """Small plate-overview tile. Disk-cached; composite mode needs the whole stack."""
    cf = CACHE / "thumbs" / f"{mode}_{size}" / f"{well}_t{t:02d}.jpg"
    if cf.is_file():
        return FileResponse(cf, media_type="image/jpeg",
                            headers={"Cache-Control": "public, max-age=86400"})
    cf.parent.mkdir(parents=True, exist_ok=True)
    im = render_thumb(well, t, mode, size)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    cf.write_bytes(buf.getvalue())
    return Response(buf.getvalue(), media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})


def render_thumb(well: str, t: int, mode: str, size: int) -> Image.Image:
    def gray(ch, use_mip):
        a = get_frame(well, ch, t, 0, use_mip)
        lo, hi = display_range(a, ch, use_mip)
        im = Image.fromarray(to_u8(a, lo, hi, 1.0), "L")
        return im.resize((size, round(im.height * size / im.width)), Image.BILINEAR)

    if mode == "composite":
        base = None
        for ch, col in (("green", (61, 220, 80)), ("orange", (255, 138, 43)),
                        ("nir", (255, 59, 107))):
            if ch not in IDX.map.get(well, {}):
                continue
            g = np.asarray(gray(ch, True), dtype=np.float32) / 255.0
            tint = np.stack([g * c for c in col], axis=-1)
            base = tint if base is None else np.maximum(base, tint)
        if base is None:
            return gray("bf", False).convert("RGB")
        return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")

    if mode in ("green", "orange", "nir"):
        return gray(mode, True).convert("RGB")
    return gray("bf", False).convert("RGB")


@app.get("/api/wellseries/{well}")
def wellseries(well: str, stride: int = 2, plo: float = 99.0):
    """Per-timepoint signal summary for one well. Slow on first call, then cached."""
    cf = CACHE / "series" / f"{well}_s{stride}.json"
    if cf.is_file():
        return JSONResponse(json.loads(cf.read_text()))
    cf.parent.mkdir(parents=True, exist_ok=True)
    out: dict = {"well": well, "stride": stride, "channels": {}}
    for ch in CHANNEL_IDS:
        if ch not in IDX.map.get(well, {}):
            continue
        mean, high, frac = [], [], []
        multi = IDX.nz.get(ch, 1) > 1
        s = stat_for(ch, multi)
        for tp in IDX.tp:
            zs = IDX.map[well][ch].get(tp["index"])
            if not zs:
                mean.append(None); high.append(None); frac.append(None); continue
            keys = sorted(zs)
            keys = keys[:: max(1, stride)] if len(keys) > 1 else keys
            acc = None
            for z in keys:
                p = load_plane(zs[z]).astype(np.float32, copy=False)
                acc = p.copy() if acc is None else np.maximum(acc, p)
            # Report signal above this frame's own background, since the background
            # level differs per well and drifts over the run.
            bg = frame_median(acc)
            mean.append(round(float(acc.mean()) - bg, 4))
            high.append(round(float(np.percentile(acc.reshape(-1)[::4], plo)) - bg, 4))
            frac.append(round(float((acc > bg + s["off_hi"] * 0.5).mean()), 6) if s else None)
        out["channels"][ch] = {"mean": mean, "p_high": high, "area_frac": frac,
                               "note": "arkaplan (kare medyanı) çıkarılmış"}
    cf.write_text(json.dumps(out))
    return JSONResponse(out)


# --------------------------------------------------------------------------- 3D
# The z step is not in the files and cannot be recovered from them; it comes from
# the scan protocol. Everything geometric below is correct once this is right.
DEFAULT_Z_STEP_UM = float(os.environ.get("INC_Z_STEP_UM", "10"))

VOLS = ByteLRU(int(os.environ.get("INC_VOL_CACHE_MB", "500")) * 1024 * 1024)


def get_volume(well: str, ch: str, t: int, bin_xy: int) -> np.ndarray:
    key = (well, ch, t, bin_xy)
    v = VOLS.get(key)
    if v is None:
        zs = IDX.map.get(well, {}).get(ch, {}).get(t)
        if not zs:
            raise HTTPException(404, f"yok: {well}/{ch}/t{t:02d}")
        v = volume.build_volume([load_plane(zs[z]) for z in sorted(zs)], bin_xy)
        VOLS.put(key, v)
    return v


def channel_hi(ch: str, mip: bool = True) -> float:
    """Signal scale for a channel, above background — from the plate-wide stats."""
    s = stat_for(ch, mip)
    return float(s["off_hi"]) if s else 1.0


def stack_channels(well: str, t: int, chans: list[str]) -> list[str]:
    have = IDX.map.get(well)
    if have is None:
        raise HTTPException(404, f"bilinmeyen kuyu: {well}")
    if not 0 <= t < len(IDX.tp):
        raise HTTPException(404, f"zaman noktası aralık dışı: {t} (0–{len(IDX.tp) - 1})")
    return [c for c in chans if c in have and IDX.nz.get(c, 1) > 1 and t in have[c]]


def png(arr_rgb: np.ndarray, max_w: int | None = None) -> Response:
    im = Image.fromarray(arr_rgb, "RGB")
    if max_w and im.width > max_w:
        im = im.resize((max_w, max(1, round(im.height * max_w / im.width))), Image.BILINEAR)
    buf = io.BytesIO()
    im.save(buf, "PNG", compress_level=1)
    return Response(buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=1800"})


@app.get("/api/zprofile/{well}")
def zprofile(well: str, t: int = 0, bin_xy: int = Query(4, alias="bin")):
    """How much of each channel's signal sits in each z layer."""
    out = {"well": well, "t": t, "nz": IDX.nz, "channels": {}}
    for ch in stack_channels(well, t, CHANNEL_IDS):
        vol = get_volume(well, ch, t, bin_xy)
        out["channels"][ch] = volume.z_profile(vol, channel_hi(ch))
    return out


_BBOX: dict[tuple, tuple[int, int, int, int]] = {}


def object_bbox(well: str, t: int, bin_xy: int) -> tuple[int, int, int, int]:
    """Crop window around the spheroid, from the tumour channel (or whatever exists)."""
    key = (well, t, bin_xy)
    if key not in _BBOX:
        ref = next((c for c in ("green", "orange", "nir") if stack_channels(well, t, [c])), None)
        if ref is None:
            _BBOX[key] = (0, 0, 10 ** 6, 10 ** 6)
        else:
            vol = get_volume(well, ref, t, bin_xy)
            _BBOX[key] = volume.find_object_bbox(vol.max(0))
    return _BBOX[key]


def upscale(rgb: np.ndarray, target_w: int) -> np.ndarray:
    """Nearest-neighbour blow-up: the volume is coarse, do not pretend otherwise."""
    h, w = rgb.shape[:2]
    if w >= target_w or w == 0:
        return rgb
    k = max(1, int(round(target_w / w)))
    return np.repeat(np.repeat(rgb, k, axis=0), k, axis=1)


@app.get("/api/render3d/{well}")
def render3d(well: str, t: int = 0, az: float = 0.0, el: float = 60.0,
             channels: str = "green,orange,nir",
             z_step_um: float = DEFAULT_Z_STEP_UM,
             z_exag: float = 1.0,
             crop: int = 0,
             scale: str = "global",
             bin_xy: int = Query(2, alias="bin"),
             bright: float = 1.0, w: int | None = 760):
    chans = [c.strip() for c in channels.split(",") if c.strip()]
    use = stack_channels(well, t, chans)
    if not use:
        raise HTTPException(404, "bu kuyu/zaman için z-stack kanalı yok")

    # z step in binned pixels — this is what makes the projection to scale
    z_px = z_step_um * max(z_exag, 0.05) / (DEFAULT_UM_PER_PX * bin_xy)
    box = object_bbox(well, t, bin_xy) if crop else None

    layers = []
    for ch in use:
        vol = get_volume(well, ch, t, bin_xy)
        if box:
            y0, x0, y1, x1 = box
            vol = vol[:, y0:min(y1, vol.shape[1]), x0:min(x1, vol.shape[2])]
        proj = volume.project(vol, z_px, az, el)
        # The plate-wide scale is set on the whole field; inside a crop it can leave
        # a channel black (T cells are largely outside the spheroid). Default here is
        # a per-view scale, since this view is for *where* things are — the numbers
        # for *how much* come from /api/zprofile, which does use the shared scale.
        ref = channel_hi(ch)
        if scale == "auto":
            ref = max(float(np.percentile(proj, 99.7)), 0.15 * ref)
        g = np.clip(proj / max(ref / max(bright, 1e-3), 1e-9), 0, 1)
        layers.append(volume.colorize(g, volume.CHANNEL_RGB[ch]))
    rgb = volume.combine(layers)
    return png(upscale(rgb, w or 0), w)


@app.get("/api/ortho/{well}")
def ortho(well: str, t: int = 0, x: int = -1, y: int = -1,
          channels: str = "green,orange,nir",
          z_step_um: float = DEFAULT_Z_STEP_UM,
          bin_xy: int = Query(4, alias="bin"),
          bright: float = 1.0, plane: str = "xz", thickness: int = 5):
    chans = [c.strip() for c in channels.split(",") if c.strip()]
    use = stack_channels(well, t, chans)
    if not use:
        raise HTTPException(404, "z-stack yok")
    z_px = z_step_um / (DEFAULT_UM_PER_PX * bin_xy)
    layers = []
    for ch in use:
        vol = get_volume(well, ch, t, bin_xy)
        nz, h, wd = vol.shape
        if plane == "yz":
            cut = volume.ortho_yz(vol, x if x >= 0 else wd // 2, z_px, thickness)
        else:
            cut = volume.ortho_xz(vol, y if y >= 0 else h // 2, z_px, thickness)
        g = np.clip(cut / max(channel_hi(ch) / max(bright, 1e-3), 1e-9), 0, 1)
        layers.append(volume.colorize(g, volume.CHANNEL_RGB[ch]))
    # A cut is only ~16 planes tall against ~500 px wide, so blow it up without
    # smoothing — the aspect stays true, the pixels stay honest.
    return png(upscale(volume.combine(layers), 1000))


@app.get("/api/depth/{well}/{ch}")
def depth(well: str, ch: str, t: int = 0, bin_xy: int = Query(2, alias="bin"),
          w: int | None = 900):
    """Depth-coded view: colour says which layer the signal came from."""
    if not stack_channels(well, t, [ch]):
        raise HTTPException(404, f"{ch} için z-stack yok")
    vol = get_volume(well, ch, t, bin_xy)
    return png(volume.depth_coded_rgb(vol, channel_hi(ch)), w)


# ------------------------------------------------------------------------- dome
DOME_BIN = 2
DOME_THR_FRAC = {"green": 0.60, "orange": 0.60, "nir": 0.35}
BAND_COLORS = [(90, 255, 255), (60, 220, 255), (90, 200, 255), (140, 170, 255),
               (255, 170, 90), (255, 90, 90)]


def _dome_thr(ch: str) -> float:
    s = stat_for(ch, False)
    return float(s["off_hi"]) * DOME_THR_FRAC[ch] if s else 1.0


def _centroids(vol: np.ndarray, thr: float) -> np.ndarray:
    """3D object centroids as (y, x) in binned pixels."""
    from scipy import ndimage as ndi
    mask = vol > thr
    if not mask.any():
        return np.zeros((0, 2))
    lab, n = ndi.label(mask)
    if n == 0:
        return np.zeros((0, 2))
    idx = np.arange(1, n + 1)
    sizes = np.asarray(ndi.sum(np.ones_like(lab), lab, idx))
    keep = idx[sizes >= 4]
    if not keep.size:
        return np.zeros((0, 2))
    coms = np.asarray(ndi.center_of_mass(vol, lab, keep)).reshape(-1, 3)
    return coms[:, 1:]


def dome_data(well: str, t: int) -> dict:
    use = stack_channels(well, t, ["green", "orange", "nir"])
    if "green" not in use:
        raise HTTPException(404, "green z-stack yok")
    um = DEFAULT_UM_PER_PX * DOME_BIN
    gvol = get_volume(well, "green", t, DOME_BIN)
    gmip = gvol.max(0)
    gsig = np.where(gmip > _dome_thr("green"), gmip, 0.0)
    d = dome.fit_dome(gsig, um)
    if d is None:
        raise HTTPException(404, "tümör sinyali yok")

    out = {"well": well, "t": t, "um_per_px": um, "bin": DOME_BIN,
           "field_px": list(gmip.shape), "dome": d,
           "bands": dome.BAND_LABELS, "channels": {}}
    for ch in ("green", "orange", "nir"):
        if ch not in use:
            continue
        vol = gvol if ch == "green" else get_volume(well, ch, t, DOME_BIN)
        pts = _centroids(vol, _dome_thr(ch))
        u = dome.normalised_radius(pts, d, um)
        prof = dome.radial_profile(u, d, gmip.shape, um)
        prof["count"] = int(len(pts))
        out["channels"][ch] = prof
    return out


@app.get("/api/dome/{well}")
def dome_api(well: str, t: int = 0):
    return dome_data(well, t)


@app.get("/api/domeview/{well}")
def domeview(well: str, t: int = 0, channels: str = "orange,nir",
             show_green: int = 1, w: int | None = 900):
    """The dome drawn on the image, with each cell coloured by its radial band."""
    from PIL import ImageDraw
    d = dome_data(well, t)
    dm = d["dome"]
    um = d["um_per_px"]
    gvol = get_volume(well, "green", t, DOME_BIN)
    gmip = gvol.max(0)
    h, wd = gmip.shape

    bfa = None
    try:
        bfa = volume.bin_xy(load_plane(IDX.path(well, "bf", t, 0)).astype(np.float32), DOME_BIN)
    except HTTPException:
        pass

    base = np.zeros((h, wd, 3), dtype=np.float32)
    if bfa is not None:
        lo, hi = INCUCYTE_BF_WINDOW
        g = np.clip((bfa[:h, :wd] - lo) / (hi - lo), 0, 1)
        base += g[..., None] * np.array([255.0, 255.0, 255.0]) * 0.55
    if show_green:
        gg = np.clip(gmip / max(_dome_thr("green") * 2.5, 1e-9), 0, 1)
        base[..., 1] += gg * 210

    im = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")
    dr = ImageDraw.Draw(im)
    cy, cx = dm["cy_px"], dm["cx_px"]
    for key, col, wdt in (("r50_um", (255, 235, 120), 1), ("r90_um", (255, 210, 0), 2)):
        rr = dm[key] / um
        dr.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=col, width=wdt)
    dr.line([cx - 6, cy, cx + 6, cy], fill=(255, 210, 0))
    dr.line([cx, cy - 6, cx, cy + 6], fill=(255, 210, 0))

    for ch in [c.strip() for c in channels.split(",") if c.strip()]:
        if ch not in d["channels"]:
            continue
        vol = get_volume(well, ch, t, DOME_BIN)
        pts = _centroids(vol, _dome_thr(ch))
        u = dome.normalised_radius(pts, dm, um)
        bi = dome.band_index(u)
        rad = 3 if ch == "orange" else 4
        for (py, px), b in zip(pts, bi):
            col = BAND_COLORS[min(int(b), len(BAND_COLORS) - 1)]
            if ch == "nir":
                dr.rectangle([px - rad, py - rad, px + rad, py + rad], outline=col)
            else:
                dr.ellipse([px - rad, py - rad, px + rad, py + rad], outline=col)

    return png(np.asarray(im), w)


@app.get("/api/pixel/{well}")
def pixel(well: str, x: int, y: int, t: int = 0, z: int = 0, mip: int = 0):
    """Raw values of every channel at one pixel — the honest way to set contrast."""
    out: dict[str, float | None] = {}
    for ch in CHANNEL_IDS:
        if ch not in IDX.map.get(well, {}):
            continue
        try:
            a = get_frame(well, ch, t, z, bool(mip))
        except HTTPException:
            out[ch] = None
            continue
        out[ch] = float(a[y, x]) if 0 <= y < a.shape[0] and 0 <= x < a.shape[1] else None
    return {"well": well, "x": x, "y": y, "t": t, "z": z, "mip": bool(mip), "values": out}


@app.get("/api/stats")
def stats():
    return {"planes": PLANES.stats(), "mips": MIPS.stats(),
            "plane_cache_mb": PLANE_CACHE_BYTES // 1024 // 1024}


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")


def pick_port(preferred: int, tries: int = 40) -> int:
    """First free port at or above `preferred` — 8000 is commonly already taken."""
    import socket
    for p in range(preferred, preferred + tries):
        with socket.socket() as s:
            # SO_REUSEADDR, same as uvicorn will use: without it a port left in
            # TIME_WAIT by the previous run probes as busy and every restart drifts
            # to a new port.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise SystemExit(f"{preferred}–{preferred + tries} arasında boş port yok")


if __name__ == "__main__":
    import uvicorn
    if not STATIC.is_dir():
        sys.exit(f"{STATIC} yok")
    want = int(os.environ.get("INC_PORT", "8791"))
    port = pick_port(want)
    if port != want:
        print(f"[viewer] {want} meşgul → {port}", flush=True)
    print(f"[viewer] → http://127.0.0.1:{port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
