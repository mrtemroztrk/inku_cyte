#!/usr/bin/env python3
"""Sayfadaki her büyüklüğün tanımı, formülü ve dayanağı — tek kaynak.

Bir tabloda sayı gösterip nasıl hesaplandığını söylememek, okuyucudan güvenmesini
istemek demektir. Bilimsel bir çalışmada bu yeterli değil: her değerin yanındaki
"?" bu sözlükten beslenir ve formülü, hangi maskeden geldiğini, hangi varsayıma
dayandığını ve neyi ölçmediğini gösterir.

Metin İngilizce (çıktı dergiye gidiyor). `formula` tek satırlık, okunabilir bir
ifade; `steps` o ifadeye nasıl varıldığı; `caveat` yorumlamadan önce bilinmesi
gereken şey.
"""
from __future__ import annotations

UM = 2.798


def build(cal: dict) -> dict:
    per_cell = cal["tcell"]["um2_per_cell"]
    ci = cal["tcell"]["ci95"]
    return {

        # ---------------------------------------------------------- masks
        "organoid": {
            "title": "Organoid territory (brightfield)",
            "formula": "area of the brightfield mask, in mm²",
            "steps": [
                "The brightfield image is flat-field corrected with a plate-wide "
                "illumination reference and smoothed (Gaussian, σ = 6 px).",
                "Background is the histogram peak of the smoothed image — not the "
                "mean, because a dark spheroid drags the mean.",
                "A pixel belongs to the organoid if it is more than 8 grey levels "
                "darker than that background.",
                "The mask is opened, closed with a 31 px element and hole-filled, "
                "then components smaller than 200 px are dropped.",
                "Area = pixel count × (2.798 µm)² ÷ 10⁶.",
            ],
            "caveat": "This is where cellular material is, not where tumour is. "
                      "CAF and macrophage clusters, debris and dead material are "
                      "also dark in brightfield, so it is an upper bound on tumour "
                      "extent. It is used because the green stain misses most "
                      "organoids, so brightfield answers “where” and green answers "
                      "“how much of it is stained”.",
        },

        "signal_area": {
            "title": "Signal area (per channel)",
            "formula": "area of the pixels above threshold in the projection, in mm²",
            "steps": [
                "Each z plane has its own median subtracted; the background level "
                "drifts both between wells and along z.",
                "The 17 planes are combined by maximum projection.",
                "A pixel counts as signal if it exceeds a threshold fixed for the "
                "whole plate — a constant multiple of the plate-wide "
                "above-background gain, never adapted per well.",
                "Connected components below the channel's minimum size are dropped "
                "(green: 4 px) to remove single-pixel noise.",
                "Area = pixel count × (2.798 µm)² ÷ 10⁶.",
            ],
            "caveat": "The only assumption is the pixel size (2.798 µm/px, "
                      "back-calculated from the instrument's field label and not "
                      "independently verified). The threshold is deliberately not "
                      "per-well: an adapted threshold rescales every well "
                      "differently and makes wells incomparable.",
        },

        "volume": {
            "title": "Signal volume",
            "formula": "voxel count × (2.798 µm)²  →  µm²·layer",
            "steps": [
                "Every z plane is thresholded on its own, so a voxel is one pixel "
                "in one plane above threshold.",
                "The count is multiplied by the pixel area to give µm²·layer.",
            ],
            "caveat": "This is not µm³. Converting to a volume needs the distance "
                      "between layers, and the z step is recorded in no file — not "
                      "in the TIFF tags, which carry no optical fields at all, and "
                      "not in the plate XML, which contains no optical entry. "
                      "Multiply by the z step in µm to obtain µm³. Note also that "
                      "layer areas sum to several times the projected area, because "
                      "the depth of field of a 4× objective is tens of microns and "
                      "one object appears in several planes.",
        },

        # -------------------------------------------------------- derived cells
        "tcells": {
            "title": "T-cell number — a derived estimate",
            "formula": f"signal area (µm²) ÷ {per_cell} µm² per cell",
            "steps": [
                "The seeding numbers are known: wells marked for T cells received "
                "5000, matched wells received none.",
                "For each T-cell well, the projected orange signal area is taken and "
                "the median area of the matched T-cell-free wells of the same "
                "co-culture is subtracted — orange carries a background population "
                "that is present with or without T cells.",
                f"That difference divided by 5000 gives {per_cell} µm² per cell "
                f"(95 % CI {ci[0]}–{ci[1]}, between-well CV "
                f"{cal['tcell']['cv'] * 100:.0f} %, n = {cal['tcell']['n_wells']}).",
                f"The scale implies an equivalent cell diameter of "
                f"{cal['tcell']['eq_diam_um']} µm. A T cell is 7–10 µm, and with "
                "fluorescence bloom at this pixel size that is the value one should "
                "get — this is the check that decides whether the scale may be used "
                "at all.",
                "The four co-culture groups reproduce the scale independently, at "
                + "–".join(str(int(v["um2_per_cell"]))
                           for v in (min(cal["tcell"]["by_coculture"].values(),
                                         key=lambda v: v["um2_per_cell"]),
                                     max(cal["tcell"]["by_coculture"].values(),
                                         key=lambda v: v["um2_per_cell"])))
                + " µm².",
            ],
            "caveat": "Always written with ≈. It is an estimate, not a count: no "
                      "cell is individually identified. Object counting was tested "
                      "and rejected — the difference in connected-component count "
                      f"between wells with and without T cells is "
                      f"{cal['object_counting']['delta_objects']} against 5000 "
                      f"seeded, so each component holds about "
                      f"{cal['object_counting']['cells_per_object']} cells at this "
                      "resolution.",
        },

        "tumour_no_cells": {
            "title": "Why the tumour is not converted to cells",
            "formula": "rejected",
            "steps": [
                "The same calculation was run for the 2000 seeded PDA cells.",
                f"It gives {cal['tumour']['um2_per_cell']} µm² per cell, an "
                f"equivalent diameter of {cal['tumour']['eq_diam_um']} µm.",
                "That is smaller than a T cell, which is impossible for a tumour "
                "cell — so the scale is wrong, and it is wrong in a knowable way: "
                "the green stain labels only part of the organoid population.",
            ],
            "caveat": "The calibration was computed and <b>rejected</b>; it is shown "
                      "on the group page so the rejection can be checked rather than "
                      "taken on trust. Tumour is reported as signal area and signal "
                      "volume only.",
        },

        "layer_cells": {
            "title": "Cells per layer — an apportionment, not a measurement",
            "formula": "N_total × area(z) ÷ Σ area(z)",
            "steps": [
                "The calibration is defined on the projected mask.",
                "Layer areas are a different quantity: they sum to several times the "
                "projected area, because one cell appears in several planes.",
                "Dividing a layer area by the same scale would therefore inflate the "
                "count severalfold.",
                "Instead the well total is distributed across layers in proportion to "
                "signal, so the layers sum exactly to the well total.",
            ],
            "caveat": "This is the shape of the depth distribution, not an "
                      "independent count per layer. The overcount factor for the "
                      "current frame is printed in the depth table.",
        },

        "overcount": {
            "title": "Layer areas ÷ projected area",
            "formula": "Σ(area in each plane) ÷ (area in the projection)",
            "steps": [
                "Both are measured, with the same threshold.",
                "A value of 1 would mean each object appears in exactly one plane.",
            ],
            "caveat": "Values of 2–5 are expected and are not an error: the depth of "
                      "field of a 4× objective (NA ≈ 0.13) is tens of microns, so a "
                      "single object is in focus enough to cross the threshold in "
                      "several planes. This is why per-layer areas are never summed "
                      "and never converted to cell numbers directly.",
        },

        "zorder": {
            "title": "Which end of the stack is which",
            "formula": "not recorded — the z axis is ordinal, z00 is simply the "
                       "first plane",
            "steps": [
                "Nothing in the files records the scan direction, so only the "
                "signal itself can be read.",
                "Across all QC-passing wells at day 4, signal is essentially absent "
                "at z00–z01 (0.1–1.3 % of each channel).",
                "T cells peak sharply at z03 (20 % of their signal) and dead cells "
                "at z04; tumour signal rises from z02, is widest at z05–z06 and "
                "thins out towards z16.",
                "Two readings fit this. If z00 is the plate side, the T cells and "
                "debris have settled onto the plate under the tumour. If z00 is the "
                "apex of the dome, they rest on the dome's upper surface and the "
                "tumour thins downwards. The atlas does not choose: the "
                "<i>z00 on top</i> switch draws the second reading, and every "
                "number is a layer index that means the same thing either way.",
            ],
            "caveat": "z00 is not an absolute height — focus is set per well, so "
                      "compare the <i>shape</i> of a depth distribution between "
                      "wells, not the layer number. The spacing between layers is "
                      "unknown, so the z axis is ordinal and carries no scale bar.",
        },

        "growth": {
            "title": "Growth",
            "formula": "organoid territory at day 4 ÷ territory at day 0",
            "steps": [
                "Both are brightfield territory areas, measured identically.",
                "The ratio is dimensionless, so it does not depend on the pixel size.",
            ],
            "caveat": "Brightfield includes every dark object, so growth here means "
                      "growth of cellular mass, not of tumour specifically.",
        },
    }
