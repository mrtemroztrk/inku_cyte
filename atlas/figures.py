#!/usr/bin/env python3
"""Publication figures for the group page, drawn with matplotlib.

Why matplotlib and not the hand-built SVG used elsewhere: these are the figures
that go into a manuscript. Readers in this field have spent their careers looking
at matplotlib and R output, and a figure that looks like the ones they already
read is a figure they can interpret without first learning its conventions. The
interactive SVG figures on the well pages serve a different purpose — exploring
one well — and stay as they are.

Each figure answers one question and carries the statistics needed to judge it:
n per group, the median, its bootstrap confidence interval, an omnibus test, and
significance brackets only where a comparison actually survives correction. No
box plots — conditions hold 4 to 17 wells, and a box plot invents quartiles at
that size.

Figures are returned as standalone SVG (base64 data URI) so several can sit in
one HTML page without their internal ids colliding.
"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                     # noqa: E402
from matplotlib.lines import Line2D                 # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter   # noqa: E402
from scipy import stats                             # noqa: E402

import theme as TH                                  # noqa: E402

# Close to matplotlib's own defaults on purpose; only the things that make a
# figure hard to read in print are changed.
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white",
    "savefig.facecolor": "white", "savefig.bbox": "tight", "savefig.pad_inches": 0.08,
    "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9.5,
    "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.titlepad": 8,
    "xtick.labelsize": 8.5, "ytick.labelsize": 8.5, "legend.fontsize": 8.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": 0.9, "xtick.major.width": 0.9, "ytick.major.width": 0.9,
    "grid.color": "#d9d9d9", "grid.linewidth": 0.7, "axes.axisbelow": True,
    "legend.frameon": False, "figure.dpi": 110,
})

DOT = "#4a4a4a"
MED = "#111111"
CI = "#bfbfbf"
REF = "#666666"


def _svg(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="svg")
    plt.close(fig)
    return ("data:image/svg+xml;base64,"
            + base64.b64encode(buf.getvalue()).decode("ascii"))


def _jitter(n: int, width: float = 0.16) -> np.ndarray:
    """Deterministic spread so the same data always draws the same figure."""
    if n == 1:
        return np.zeros(1)
    return np.linspace(-width, width, n)


def _stars(q: float | None) -> str:
    if q is None or not np.isfinite(q):
        return ""
    return "***" if q < 0.001 else "**" if q < 0.01 else "*" if q < 0.05 else ""


def _plain_log_axis(ax, values):
    """Plain numbers on a log axis.

    Matplotlib's default renders 0.5 as "6 × 10⁻¹", which is correct and
    unreadable. Enrichment lives between roughly 0.1 and 10, so a fixed set of
    round ratios covers it and reads at a glance."""
    cand = [0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 1, 1.5, 2, 3, 5, 10, 20, 50]
    lo, hi = min(values), max(values)
    keep = [c for c in cand if lo / 1.6 <= c <= hi * 1.6]
    if len(keep) < 3:
        keep = cand
    ax.yaxis.set_major_locator(FixedLocator(keep))
    ax.yaxis.set_minor_locator(FixedLocator([]))
    ax.yaxis.set_major_formatter(FuncFormatter(
        lambda v, _: f"{v:g}" if v >= 1 else f"{v:.2f}".rstrip("0").rstrip(".")))


# Short axis labels. Rotating long names is the usual fix and the wrong one —
# rotated text is slower to read and the full name is in the caption anyway.
SHORT = {
    "PDA": "PDA", "PDA+CAF": "+CAF", "PDA+MAC": "+MAC", "PDA+CAF+MAC": "+CAF+MAC",
    "control": "control", "kras low": "KRAS\n10 nM", "kras high": "KRAS\n100 nM",
    "Src low": "SRC\n50 nM", "Src high": "SRC\n200 nM",
    "low kras+Src": "K+S\nlow", "high kras+Src": "K+S\nhigh",
}


def _xlabels(ax, labels, ns):
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels([f"{SHORT.get(l, l)}\nn = {n}" for l, n in zip(labels, ns)],
                       fontsize=8.5)


def _bracket(ax, x1, x2, y, label, log=False):
    """Significance bracket, drawn only for comparisons that survive correction."""
    h = y * 0.06 if log else y * 0.03
    ax.plot([x1, x1, x2, x2], [y, y + h, y + h, y], lw=0.9, c="#333333",
            clip_on=False)
    ax.text((x1 + x2) / 2, y + h * 1.15, label, ha="center", va="bottom",
            fontsize=8.5, clip_on=False)


def _omnibus(groups: list[dict]) -> str:
    """Kruskal-Wallis across the groups — one honest sentence for the whole panel."""
    arrs = [np.asarray(g["values"], float) for g in groups if len(g["values"]) > 1]
    if len(arrs) < 2:
        return ""
    try:
        h, p = stats.kruskal(*arrs)
    except ValueError:
        return ""
    return f"Kruskal–Wallis H = {h:.2f}, p = {p:.3f}"


# ------------------------------------------------------------------ strip plot
def strip(data: dict, ylabel: str, ref: float | None, log: bool,
          title: str, subtitle: str = "", width: float = 7.4,
          height: float = 3.5, fmt: str = "{:.2f}") -> str:
    """Every well a point, median with bootstrap CI, reference line, tests."""
    gs = data["groups"]
    fig, ax = plt.subplots(figsize=(width, height))
    if not gs:
        ax.text(0.5, 0.5, "no wells in this comparison", ha="center", va="center")
        ax.axis("off")
        return _svg(fig)

    for i, g in enumerate(gs):
        v = np.asarray(g["values"], float)
        lo, hi = g["ci"]
        # bootstrap CI of the median — the uncertainty of the summary, not the
        # spread of the wells, which the points themselves already show
        ax.add_patch(plt.Rectangle((i - 0.20, min(lo, hi)), 0.40, abs(hi - lo),
                                   facecolor=CI, edgecolor="none", alpha=0.55,
                                   zorder=1))
        ax.plot([i - 0.34, i + 0.34], [g["median"]] * 2, c=MED, lw=2.2, zorder=4,
                solid_capstyle="butt")
        ax.scatter(i + _jitter(len(v)), v, s=26, facecolor=DOT, edgecolor="white",
                   linewidth=0.7, zorder=3, alpha=0.85)

    if ref is not None:
        ax.axhline(ref, color=REF, lw=1.0, ls="--", zorder=2)
        ax.annotate(f"{ref:g} = expected if uniform", xy=(1.0, ref),
                    xycoords=("axes fraction", "data"), xytext=(4, 0),
                    textcoords="offset points", va="center", fontsize=8,
                    color=REF, annotation_clip=False)

    if log:
        ax.set_yscale("log")
        allv = [v for g in gs for v in g["values"] if v > 0] + [ref or 1]
        _plain_log_axis(ax, allv)
    _xlabels(ax, [g["label"] for g in gs], [g["n"] for g in gs])
    ax.set_ylabel(ylabel)
    ax.set_xlim(-0.6, len(gs) - 0.4)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)

    # significance brackets only where a pairwise test survives correction
    tests = [t for t in data.get("tests", [])
             if t.get("q") is not None and t["q"] < 0.05]
    if tests:
        idx = {g["label"]: i for i, g in enumerate(gs)}
        top = max(max(g["values"]) for g in gs)
        step = 1.35 if log else 1.12
        y = top * (1.18 if log else 1.06)
        for t in sorted(tests, key=lambda t: t["q"]):
            if t["a"] in idx and t["b"] in idx:
                _bracket(ax, idx[t["a"]], idx[t["b"]], y,
                         f"q = {t['q']:.3f} {_stars(t['q'])}".strip(), log)
                y *= step
    foot = _omnibus(gs)
    if not tests and foot:
        foot += " · no pairwise comparison survives BH correction"
    ax.set_title(title, pad=26)
    if subtitle:
        ax.annotate(subtitle, xy=(0, 1.015), xycoords="axes fraction", fontsize=8.5,
                    color="#555555", va="bottom", annotation_clip=False)
    if foot:
        ax.annotate(foot, xy=(0, -0.30), xycoords="axes fraction", fontsize=8,
                    color="#555555", annotation_clip=False)
    fig.tight_layout()
    return _svg(fig)


# ------------------------------------------------------------- paired design
def matched(data: dict, ylabel: str, title: str, subtitle: str = "",
            width: float = 7.4, height: float = 4.1) -> str:
    """Adding T cells or not, inside each co-culture. Medians joined by a line."""
    rows = data["rows"]
    fig, ax = plt.subplots(figsize=(width, height))
    if not rows:
        ax.text(0.5, 0.5, "not enough wells", ha="center", va="center")
        ax.axis("off")
        return _svg(fig)

    for i, r in enumerate(rows):
        for dx, vals, med in ((-0.17, r["values_ctrl"], r["med_ctrl"]),
                              (+0.17, r["values_t"], r["med_t"])):
            v = np.asarray(vals, float)
            ax.scatter(i + dx + _jitter(len(v), 0.055), v, s=24, facecolor=DOT,
                       edgecolor="white", linewidth=0.7, zorder=3, alpha=0.85)
            ax.plot([i + dx - 0.10, i + dx + 0.10], [med] * 2, c=MED, lw=2.0,
                    zorder=4, solid_capstyle="butt")
        ax.plot([i - 0.17, i + 0.17], [r["med_ctrl"], r["med_t"]], c=MED, lw=0.9,
                ls=":", zorder=2)
        q = r.get("q")
        lab = f"{r['ratio']:.2f}×\nδ = {r['delta']:+.2f}"
        if q is not None:
            lab += f"\nq = {q:.2f}" + (" " + _stars(q) if _stars(q) else " n.s.")
        ax.annotate(lab, xy=(i, -0.14), xycoords=("data", "axes fraction"),
                    ha="center", va="top", fontsize=8, color="#555555",
                    annotation_clip=False, linespacing=1.5)

    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels([SHORT.get(r["group"], r["group"]) for r in rows])
    ax.set_ylabel(ylabel)
    ax.set_xlim(-0.5, len(rows) - 0.5)
    ax.set_ylim(bottom=0)
    ax.yaxis.grid(True)
    # Legend inside the axes: above the frame it collides with the subtitle, and
    # the top-right corner of these panels is empty in every well.
    ax.legend(handles=[
        Line2D([], [], marker="o", ls="", color=DOT, markeredgecolor="white",
               label="left: no T cells · right: + T cells"),
        Line2D([], [], color=MED, lw=2.0, label="median"),
    ], loc="upper right", ncol=1, handletextpad=0.6, labelspacing=0.35,
        fontsize=8)
    sign = (f"direction agrees in {data['n_up']}/{data['n_groups']} co-cultures, "
            f"two-sided sign test p = {data['sign_p']}")
    ax.set_title(title, pad=30)
    if subtitle:
        ax.annotate(subtitle, xy=(0, 1.015), xycoords="axes fraction", fontsize=8.5,
                    color="#555555", va="bottom", annotation_clip=False)
    ax.annotate(sign, xy=(0, -0.50), xycoords="axes fraction", fontsize=8,
                color="#555555", va="top", annotation_clip=False)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    return _svg(fig)


# ------------------------------------------------------------------- curves
def curves(data: dict, ylabel: str, title: str, subtitle: str = "",
           width: float = 7.4, height: float = 2.9) -> str:
    """Growth: one panel per co-culture, shared y axis, wells behind the median."""
    gs = data["groups"]
    fig, axes = plt.subplots(1, max(len(gs), 1), figsize=(width, height),
                             sharey=True)
    axes = np.atleast_1d(axes)
    for ax, g in zip(axes, gs):
        days = np.asarray(g["days"], float)
        for w in g["wells"]:
            ax.plot(days, w["v"], color="#b6b6b6", lw=0.8, zorder=1)
        ax.plot(days, g["median"], color=MED, lw=2.0, zorder=3)
        ax.set_title(f"{SHORT.get(g['label'], g['label'])}\nn = {g['n']}", fontsize=9)
        ax.set_xlabel("days")
        ax.yaxis.grid(True)
        ax.set_ylim(bottom=0)
    axes[0].set_ylabel(ylabel)
    fig.suptitle(title + ("  —  " + subtitle if subtitle else ""), x=0.005,
                 ha="left", fontsize=10, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return _svg(fig)


# -------------------------------------------------------------- calibration
def calibration(cal: dict, width: float = 7.4, height: float = 3.6) -> str:
    """The evidence behind every ≈ in the atlas, and the rejected alternative."""
    t, tu = cal["tcell"], cal["tumour"]
    groups = list(t["by_coculture"].items())
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(width, height))

    # left — the scale, derived once per co-culture
    ax1.axhspan(t["ci95"][0], t["ci95"][1], color=CI, zorder=1)
    ax1.axhline(t["um2_per_cell"], color=MED, lw=2.0, zorder=3)
    xs = np.arange(len(groups))
    ax1.scatter(xs, [v["um2_per_cell"] for _, v in groups], s=34, facecolor=DOT,
                edgecolor="white", linewidth=0.8, zorder=4)
    ax1.set_xticks(xs)
    ax1.set_xticklabels([f"{SHORT.get(k, k)}\nn = {v['n_wells']}" for k, v in groups],
                        fontsize=8)
    ax1.set_ylabel("area per T cell (µm²)")
    ax1.set_title("Scale derived independently per co-culture")
    ax1.annotate(f"pooled median {t['um2_per_cell']:.1f} µm² · "
                 f"95 % CI {t['ci95'][0]:.1f}–{t['ci95'][1]:.1f} · "
                 f"CV {t['cv'] * 100:.0f} % · n = {t['n_wells']} wells",
                 xy=(0, -0.30), xycoords="axes fraction", fontsize=8,
                 color="#555555", va="top", annotation_clip=False)
    ax1.yaxis.grid(True)

    # right — the check that decides whether the scale may be used at all
    ax2.axhspan(7, 10, color="#dce9f9", zorder=1)
    ax2.annotate("a T cell is 7–10 µm", xy=(0.97, 10), xycoords=("axes fraction",
                 "data"), ha="right", va="bottom", fontsize=8, color="#2a6099")
    bars = ax2.bar([0, 1], [t["eq_diam_um"], tu["eq_diam_um"]], width=0.5,
                   color=[TH.CH_FIG["green"], "#c0392b"], zorder=3)
    for b, v in zip(bars, [t["eq_diam_um"], tu["eq_diam_um"]]):
        ax2.text(b.get_x() + b.get_width() / 2, v + 0.25, f"{v:.1f} µm",
                 ha="center", fontsize=9, fontweight="bold")
    ax2.set_xticks([0, 1])
    ax2.set_xticklabels(["T-cell scale\naccepted",
                         "tumour scale\nrejected: smaller\nthan a T cell"],
                        fontsize=8)
    ax2.set_ylabel("cell diameter the scale implies (µm)")
    ax2.set_ylim(0, max(t["eq_diam_um"], tu["eq_diam_um"], 12) * 1.32)
    ax2.set_title("The check each scale had to pass")
    ax2.yaxis.grid(True)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    return _svg(fig)


def build_all(d: dict) -> dict[str, str]:
    """Every group-page figure, keyed by the id the page uses."""
    return {
        "enrich_coc": strip(
            d["enrich_coculture"], "T-cell enrichment (× uniform)", 1.0, True,
            "T-cell enrichment inside the organoid, by co-culture",
            "day 4 · wells that received T cells"),
        "enrich_cmp": strip(
            d["enrich_compound"], "T-cell enrichment (× uniform)", 1.0, True,
            "T-cell enrichment inside the organoid, by compound",
            "day 4 · wells that received T cells"),
        "dist": strip(
            d["dist_coculture"], "median signed distance (µm)", 0.0, False,
            "How far the T-cell signal sits from the organoid boundary",
            "day 4 · negative = inside · confluent wells excluded"),
        "growth": curves(
            d["growth"], "organoid territory (mm²)",
            "Organoid growth", "brightfield, independent of staining"),
        "dead": matched(
            d["dead_matched"], "dead-cell signal (mm²)",
            "Effect of adding T cells on dead-cell signal",
            "day 4 · co-culture held constant"),
        "tumour": matched(
            d["tumour_matched"], "tumour signal (mm²)",
            "Effect of adding T cells on tumour signal",
            "day 4 · co-culture held constant"),
        "calib": calibration(d["calibration"]),
    }
