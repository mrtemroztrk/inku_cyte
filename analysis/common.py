#!/usr/bin/env python3
"""Analiz betiklerinin ortak parçaları: veri yükleme, gruplama, istatistik, çizim.

Her analiz betiği (a1…a6) bunu içe aktarır; kendi CSV'sini, figürlerini ve
metin özetini `analysis/out/<ad>/` altına yazar.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                    # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402

from scale import (BAND_EDGES_PX, UM_PER_PX, UM_PER_PX_SOURCE,      # noqa: E402
                   UM_PER_PX_VERIFIED, Z_STEP_UM, band_edges_um)
from scale import band_labels as _band_labels                       # noqa: E402
from scale import note as scale_note                                # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = Path(os.environ.get("INC_DATA", ROOT / "data" / "inc_tests")).resolve()
FEAT = Path(os.environ.get("INC_CACHE", ROOT / "viewer" / "cache")) / "features"
OUTROOT = HERE / "out"

# --- palet (dataviz referans paleti, açık mod) -------------------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#8a8983"
GRID = "#e6e5e1"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
          "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
STATUS = {"good": "#1baf7a", "warning": "#eda100", "serious": "#eb6834", "critical": "#e34948"}
SEQ = LinearSegmentedColormap.from_list(
    "seq_blue", ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"])
DIV = LinearSegmentedColormap.from_list(
    "div_br", ["#184f95", "#3987e5", "#9ec5f4", "#f0efec", "#f0a6a5", "#e34948", "#9c1f1e"])

# Ko-kültür → sabit renk yuvası. Renk varlığı takip eder, sırasını değil.
COCULTURE_ORDER = ["PDA", "PDA+CAF", "PDA+MAC", "PDA+CAF+MAC"]
COCULTURE_COLOR = dict(zip(COCULTURE_ORDER, SERIES[:4]))
COMPOUND_ORDER = ["control", "kras low", "kras high", "Src low", "Src high",
                  "low kras+Src", "high kras+Src", "Dye"]

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "text.color": INK,
    "xtick.color": INK2, "ytick.color": INK2, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.grid": True, "axes.axisbelow": True, "axes.spines.top": False,
    "axes.spines.right": False, "font.size": 9, "axes.titlesize": 10,
    "axes.titleweight": "bold", "axes.titlelocation": "left", "legend.frameon": False,
    "legend.fontsize": 8, "lines.linewidth": 2.0, "figure.dpi": 130,
})


# ------------------------------------------------------------------- veri
EXTRACT_UM_PER_PX = 2.798        # extract.py çalışırken geçerli olan değer


def _rescale(df: pd.DataFrame, cols: dict[str, int]) -> pd.DataFrame:
    """µm türevli kolonları geçerli kalibrasyona çevirir.

    CSV'ler çıkarım anındaki kalibrasyonla yazıldı. INC_UM_PER_PX ile başka bir
    değer verilirse, µm kolonları yeniden çıkarım yapmadan burada ölçeklenir —
    hepsi piksel ölçümlerinin doğrusal (alan için karesel) fonksiyonu."""
    if abs(UM_PER_PX - EXTRACT_UM_PER_PX) < 1e-9:
        return df
    k = UM_PER_PX / EXTRACT_UM_PER_PX
    for c, power in cols.items():
        if c in df:
            df[c] = df[c] * (k ** power)
    return df


def load(min_t: int | None = None) -> pd.DataFrame:
    f = FEAT / "features.csv"
    if not f.is_file():
        raise SystemExit(f"{f} yok — önce: python3 analysis/extract.py --all")
    df = pd.read_csv(f)
    df = pd.concat([df, pd.DataFrame({
        "t_added": df.has_tcells.eq("yes"), "mac": df.has_macrophages.eq("yes"),
        "caf": df.has_cafs.eq("yes"), "is_dye": df.compound.eq("Dye"),
        "day": df.hours / 24.0})], axis=1)
    df = _rescale(df, {"bf_terr_mm2": 2, "field_mm2": 2, "organoid_med_area_um2": 2,
                       "organoid_med_diam_um": 1, "organoid_p90_diam_um": 1,
                       "green_median_signed_dist_um": 1,
                       "orange_median_signed_dist_um": 1,
                       "nir_median_signed_dist_um": 1})
    if min_t is not None:
        df = df[df.t >= min_t]
    return df


def load_organoids() -> pd.DataFrame:
    f = FEAT / "organoids.csv"
    if not f.is_file():
        raise SystemExit(f"{f} yok — önce: python3 analysis/extract.py --all")
    d = pd.read_csv(f)
    d = pd.concat([d, pd.DataFrame({
        "t_added": d.has_tcells.eq("yes"), "mac": d.has_macrophages.eq("yes"),
        # varsayımsız birincil ölçü: piksel
        "eq_diam_px": 2 * np.sqrt(d.area_px / np.pi)})], axis=1)
    return _rescale(d, {"area_um2": 2, "eq_diam_um": 1})


def qc_wells(df: pd.DataFrame) -> set[str]:
    """QC'den geçemeyen kuyular — a1 bunu hesaplayıp diske yazar, diğerleri okur."""
    f = OUTROOT / "a1_qc" / "excluded_wells.csv"
    if f.is_file():
        return set(pd.read_csv(f).well)
    return set()


def outdir(name: str) -> Path:
    d = OUTROOT / name
    d.mkdir(parents=True, exist_ok=True)
    return d


# -------------------------------------------------------------- istatistik
def auc(a: np.ndarray, b: np.ndarray) -> float:
    """Mann-Whitney AUC: rastgele bir `a` elemanının rastgele bir `b`
    elemanından büyük olma olasılığı. 0,5 = ayırt edilemez, 1 = tam ayrım."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    if a.size == 0 or b.size == 0:
        return np.nan
    r = pd.Series(np.concatenate([a, b])).rank().to_numpy()
    return float((r[:a.size].sum() - a.size * (a.size + 1) / 2) / (a.size * b.size))


def mwu_p(a, b) -> float:
    from scipy.stats import mannwhitneyu
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    if a.size < 3 or b.size < 3:
        return np.nan
    try:
        return float(mannwhitneyu(a, b, alternative="two-sided").pvalue)
    except ValueError:
        return np.nan


def bh_fdr(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg düzeltilmiş p — çok sayıda karşılaştırma yapılıyor."""
    p = np.asarray(p, float)
    ok = np.isfinite(p)
    out = np.full(p.shape, np.nan)
    q = p[ok]
    if q.size == 0:
        return out
    o = np.argsort(q)
    adj = q[o] * q.size / (np.arange(q.size) + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    r = np.empty_like(adj)
    r[o] = np.clip(adj, 0, 1)
    out[ok] = r
    return out


def boot_ci(x, n=2000, stat=np.median, seed=0) -> tuple[float, float]:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if x.size < 3:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    s = np.array([stat(rng.choice(x, x.size, replace=True)) for _ in range(n)])
    return tuple(np.percentile(s, [2.5, 97.5]))


def cliffs_delta(a, b) -> float:
    """AUC'nin −1…1 ölçeğine taşınmış hâli; etki büyüklüğü olarak okunur."""
    u = auc(a, b)
    return np.nan if not np.isfinite(u) else 2 * u - 1


def stars(p: float) -> str:
    if not np.isfinite(p):
        return ""
    return "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"


# ------------------------------------------------------------------ çizim
def _wrap(s: str, width: int) -> str:
    import textwrap
    return "\n".join(textwrap.wrap(s, width)) if len(s) > width else s


def finish(fig, path: Path, note: str | None = None, title_width: int = 34):
    """Yerleşimi kapatır: uzun başlıklar sarılır, dipnot eksen alanının altına
    konur. Sola hizalı başlıklar eksenin dışına taşıp komşu panele giriyordu."""
    # Başlıklar sola hizalı (rcParams), o yüzden loc="center" boş döner — üç konumu
    # da dolaşmak gerekiyor.
    for ax in fig.axes:
        for loc in ("left", "center", "right"):
            t = ax.get_title(loc=loc)
            if t and "\n" not in t:
                ax.set_title(_wrap(t, title_width), loc=loc)
    fig.tight_layout(pad=0.9, w_pad=1.6)
    if note:
        n = len(fig.axes) or 1
        fig.text(0.0, -0.015, _wrap(note, max(80, 42 * min(n, 4))),
                 fontsize=6.5, color=MUTED, va="top", ha="left")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  → {path.name}")


def plate_grid(ax, values: dict[str, float], title: str, cmap=SEQ,
               vmin=None, vmax=None, center=None, fmt="{:.0f}", label=""):
    """96 kuyuluk plaka haritası. Kolon 9 görüntülenmedi → boş bırakılır."""
    rows = "ABCDEFGH"
    grid = np.full((8, 12), np.nan)
    for w, v in values.items():
        if isinstance(w, str) and len(w) == 3 and w[0] in rows:
            grid[rows.index(w[0]), int(w[1:]) - 1] = v
    norm = None
    if center is not None:
        lo = np.nanmin(grid) if vmin is None else vmin
        hi = np.nanmax(grid) if vmax is None else vmax
        lo, hi = min(lo, center - 1e-6), max(hi, center + 1e-6)
        norm = TwoSlopeNorm(vcenter=center, vmin=lo, vmax=hi)
    im = ax.imshow(np.ma.masked_invalid(grid), cmap=cmap, norm=norm,
                   vmin=None if norm else vmin, vmax=None if norm else vmax,
                   aspect="equal")
    ax.set_xticks(range(12), [str(i + 1) for i in range(12)])
    ax.set_yticks(range(8), list(rows))
    ax.set_title(title)
    ax.grid(False)
    ax.set_xticks(np.arange(-.5, 12, 1), minor=True)
    ax.set_yticks(np.arange(-.5, 8, 1), minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=2)
    ax.tick_params(which="minor", length=0)
    for r in range(8):
        for c in range(12):
            if np.isfinite(grid[r, c]):
                v = grid[r, c]
                rgba = im.cmap(im.norm(v))
                lum = 0.299 * rgba[0] + 0.587 * rgba[1] + 0.114 * rgba[2]
                ax.text(c, r, fmt.format(v), ha="center", va="center", fontsize=5.5,
                        color="#ffffff" if lum < 0.5 else INK)
    cb = ax.figure.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cb.outline.set_visible(False)
    if label:
        cb.set_label(label, fontsize=8)
    return im


def strip(ax, groups: list[tuple[str, np.ndarray]], colors=None, log=False,
          hline=None, hlabel=None, seed=1):
    """Nokta + medyan çizgisi. Kuyu sayıları küçük; kutu grafiği yanıltıcı olur."""
    rng = np.random.default_rng(seed)
    colors = colors or SERIES
    for i, (name, vals) in enumerate(groups):
        v = np.asarray(vals, float)
        v = v[np.isfinite(v)]
        if log:
            v = np.clip(v, 1e-4, None)
        x = i + rng.uniform(-0.16, 0.16, v.size)
        ax.scatter(x, v, s=16, color=colors[i % len(colors)], alpha=0.75,
                   linewidths=0.6, edgecolors=SURFACE, zorder=3)
        if v.size:
            m = np.median(v)
            ax.plot([i - 0.3, i + 0.3], [m, m], color=INK, lw=2, zorder=4)
    ax.set_xticks(range(len(groups)), [g[0] for g in groups])
    if log:
        ax.set_yscale("log")
    if hline is not None:
        ax.axhline(hline, color=MUTED, ls="--", lw=1, zorder=1)
        if hlabel:
            ax.text(0.99, hline, hlabel, transform=ax.get_yaxis_transform(),
                    ha="right", va="bottom", fontsize=7, color=MUTED)


def timeseries(ax, df: pd.DataFrame, ycol: str, groupcol: str, order=None,
               colors=None, agg="median", band=True):
    """Grup başına zaman eğrisi; bant = kuyular arası IQR."""
    order = order or [g for g in df[groupcol].dropna().unique()]
    colors = colors or SERIES
    for i, g in enumerate(order):
        d = df[df[groupcol] == g]
        if d.empty:
            continue
        gr = d.groupby("day")[ycol]
        med = gr.median() if agg == "median" else gr.mean()
        c = colors[i % len(colors)] if isinstance(colors, list) else colors.get(g, SERIES[i % 8])
        ax.plot(med.index, med.values, color=c, label=str(g), zorder=3)
        if band and d.well.nunique() > 2:
            lo, hi = gr.quantile(0.25), gr.quantile(0.75)
            ax.fill_between(med.index, lo.values, hi.values, color=c, alpha=0.13,
                            linewidth=0, zorder=2)
    ax.set_xlabel("gün")


def band_labels(unit: str = "um") -> list[str]:
    """Uzaklık bantlarının etiketleri. Bantların birincil tanımı piksel;
    µm etiketleri geçerli kalibrasyondan türetilir (bkz. analysis/scale.py)."""
    return _band_labels(unit)


def write_summary(path: Path, title: str, lines: list[str]):
    """Her özetin sonuna ölçek beyanı eklenir — hangi sayının varsayıma dayandığı
    özetin kendisinden okunabilsin diye."""
    txt = (f"# {title}\n\n" + "\n".join(lines)
           + "\n\n---\n\n### Birimler ve ölçek\n\n" + scale_note() + "\n")
    path.write_text(txt)
    print(f"  → {path.name}")
    return txt
