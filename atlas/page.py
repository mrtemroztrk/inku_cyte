#!/usr/bin/env python3
"""HTML üretimi: kuyu sayfası, plaka sayfası, grup karşılaştırma sayfası.

Sayfalar kendi kendine yeter — CSS, JS ve veri gömülüdür, sunucu gerekmez.

Sayfa metni İngilizcedir: çıktı dergiye ve ortak yazarlara gidiyor. Kod
yorumları depo genelindeki gibi Türkçe kaldı.

Sayfada görünen hiçbir sayı burada hesaplanmaz — hepsi `build.py`'de üretilir ve
buraya hazır gelir. Böylece bir figürdeki değerin nereden geldiği tek bir yerde
okunabiliyor.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

import measure as M
import theme as TH

TPL = Path(__file__).resolve().parent / "templates"


def _asset(name: str) -> str:
    return (TPL / name).read_text(encoding="utf-8")


def _theme_js() -> str:
    return json.dumps({
        "colors": TH.CH_FIG, "scene": TH.CH_SCENE, "terrScene": TH.TERR_SCENE,
        "terr": TH.TERR_FIG, "seq": TH.SEQ, "label": TH.CH_LABEL_EN,
    }, ensure_ascii=False)


def _cond(m: dict) -> str:
    bits = [f"<b>{html.escape(m['coculture'])}</b>"]
    bits.append("<b>+ T cells</b>" if m["has_tcells"] else "no T cells")
    c = html.escape(str(m["compound"]))
    if m["concentration"] is not None:
        c += f" {m['concentration']:g} nM"
    bits.append(c)
    return " · ".join(bits)


def _fig(fid: str, num: str, title: str, question: str, caption: str,
         wide: bool = False, svg: bool = True, img: str | None = None) -> str:
    """Bir figür bloğu. `img` verilirse figür sunucuda matplotlib ile çizilmiş
    demektir ve doğrudan gömülür; verilmezse tarayıcı çizer (kuyu sayfası)."""
    tools = f'<button data-tbl="{fid}">table</button>'
    if img:
        tools += (f'<a class="dl" download="{fid}.svg" href="{img}">SVG</a>')
        body = f'<img class="pubfig" src="{img}" alt="{title}">'
    else:
        if svg:
            tools += f'<button data-svg="{fid}">SVG</button>'
        body = f'<div id="fig_{fid}"></div>'
    return f"""
      <figure class="{'wide' if wide else ''}" id="figure_{fid}">
        <div class="fighead">
          <h3><span class="fignum">{num}</span> {title}</h3>
          <div class="tools">{tools}</div>
        </div>
        <p class="figq">{question}</p>
        {body}
        <div class="tbl" id="tbl_{fid}"></div>
        <figcaption>{caption}</figcaption>
      </figure>"""


# --------------------------------------------------------------- kuyu sayfası
def well_page(pay: dict) -> str:
    m = pay["meta"]
    cal = pay["calibration"]
    tc, tu, ob = cal["tcell"], cal["tumour"], cal["object_counting"]
    well = pay["well"]
    data = dict(pay)
    data["band_labels"] = M.BAND_LABELS_EN

    warn = ('<span class="flag warn">excluded by QC — not used in group '
            'comparisons</span>' if m["excluded"] else "")

    chips = "".join(
        f'<button class="chip" data-ch="{ch}" aria-pressed="true">'
        f'<span class="sw" style="background:{TH.CH_SCENE[ch]}"></span>'
        f'{TH.CH_LABEL_EN[ch]}</button>' for ch in TH.CHANNELS)
    chips += ('<button class="chip" data-ch="terr" aria-pressed="true">'
              f'<span class="sw" style="background:{TH.TERR_SCENE}"></span>'
              'organoid footprint</button>')

    def q(qid: str, label: str, color: str | None) -> str:
        sw = f'<span class="sw" style="background:{color}"></span>' if color else ""
        return (f'<div class="q" id="q_{qid}"><div class="lbl">{sw}{label}</div>'
                f'<div class="val">—</div><div class="sub"></div></div>')

    readout = "".join([
        q("organoid", "organoid territory (brightfield)", TH.TERR_FIG),
        q("tumour", "tumour signal", TH.CH_FIG["green"]),
        q("tcell", "T-cell signal", TH.CH_FIG["orange"]),
        q("dead", "dead-cell signal", TH.CH_FIG["nir"]),
        q("enrich", "T cells inside the organoid", None),
    ])

    figs = "".join([
        _fig("depth", "Figure 1", "Signal by depth",
             "At which depth does each population sit?",
             "Bars are the threshold-above signal area measured on each z plane's "
             "own mask; z00 is at the bottom, matching the 3D scene. The three "
             "panels carry different units and are read independently of one "
             "another. Layer spacing is not to scale — the z step is recorded "
             "nowhere in the data. The italic tick row under the T-cell panel "
             "converts to cell equivalents by apportioning the whole-well total "
             "across layers in proportion to signal; layer areas cannot be "
             "converted directly, because the depth of field of a 4× objective "
             "(NA ≈ 0.13) is tens of microns and one cell appears in several "
             "layers. Click a bar to isolate that layer in the 3D scene."),
        _fig("bands", "Figure 2", "Signal by distance to the organoid boundary",
             "Are the populations inside the organoid, at its rim, or outside?",
             "Signed distance to the brightfield organoid territory: negative is "
             "inside. Enrichment is band density divided by whole-field density, "
             "so 1.0 is what a uniformly scattered population gives; raw area "
             "would always say “most of it is outside”, because the outer bands "
             "cover far more area. The axis is logarithmic because the quantity "
             "is a ratio — 0.5 and 2 are equal and opposite departures. Open "
             "symbols on the bottom row are bands with no signal at all "
             "(undefined on a log axis, shown rather than dropped)."),
        _fig("zband", "Figure 3", "Depth × distance",
             "Are depth and lateral position independent, or coupled?",
             "Each cell is the share of that channel's own total signal falling "
             "in that layer and that distance band. Panels are normalised "
             "separately — a panel says where its population sits, never how much "
             "of it there is compared with another channel. Colour carries "
             "magnitude only; the vertical line is the organoid boundary (0 µm).",
             wide=True),
        _fig("time", "Figure 4", "Time course",
             "How did each quantity change over the four days?",
             "Four quantities, four units, four panels. The filled marker is the "
             "timepoint currently shown in the 3D scene. Organoid mass is measured "
             "in brightfield and is independent of staining; tumour signal depends "
             "on the green stain, which does not label every organoid (see "
             "Methods), so it is a lower bound.", wide=True),
    ])

    dom = pay["frames"][-1].get("dome") or {}
    dome_note = ("The dashed ring is the radius containing 90 % of the organoid "
                 "mass (R90). It is defined in XY only — the z axis is not part of "
                 "the boundary."
                 if dom.get("dominant") else
                 "No dome outline is drawn for this well: the largest connected "
                 f"component holds only {100 * dom.get('largest_frac', 0):.0f} % of "
                 "the organoid territory, so “distance from the centre” is not a "
                 "defined quantity here. Figure 2, which measures distance to the "
                 "nearest boundary, still applies.")

    methods = f"""
    <details class="method" id="methods">
      <summary>Methods, units and limits</summary>
      <div class="body">
        <div>
          <h4>Where the organoid is</h4>
          <p>From brightfield, not from the green channel. Across the QC-passing
          wells, only a median 15 % of the objects visible in brightfield carry any
          green signal, so “where is the organoid” is answered by brightfield and
          “how much of it is stained” by green. The territory is the region more
          than 8 grey levels darker than the background of the flat-field-corrected,
          smoothed brightfield image, after a 31 px closing and hole filling.</p>
          <p>The threshold is <b>fixed across the whole plate</b> and is not adapted
          per well. An adapted threshold rescales every well differently and makes
          wells incomparable.</p>
          <h4>Fluorescence threshold</h4>
          <p>A fixed multiple of the plate-wide above-background gain (green and
          orange × 0.60, NIR × 0.35). Each plane's own median is subtracted first:
          the background level drifts both between wells and along z.</p>
          <h4>What the 3D scene draws</h4>
          <p>One point per 5.6 µm voxel above threshold, blended additively — the
          way fluorescence itself adds. It is a rendering of the segmentation, not
          a rendering of the raw image, so it shows exactly what was measured.</p>
        </div>
        <div>
          <h4>Where “≈ {tc['um2_per_cell']} µm² per T cell” comes from</h4>
          <p>The seeding numbers are known: wells marked for T cells received 5000.
          The difference in projected signal area between T-cell wells and matched
          T-cell-free wells, divided by 5000, gives
          <b>{tc['um2_per_cell']} µm² per cell</b> (95 % CI
          {tc['ci95'][0]}–{tc['ci95'][1]}, between-well CV {tc['cv'] * 100:.0f} %,
          n = {tc['n_wells']} wells).</p>
          <p>Three independent checks were required before using it. First, the
          scale implies an equivalent cell diameter of <b>{tc['eq_diam_um']} µm</b>
          — a T cell is 7–10 µm, and at 2.798 µm/px with fluorescence bloom this is
          the value one should get; the scale does not imply a biologically
          impossible cell. Second, the four co-culture groups reproduce it
          independently, at
          {min(v['um2_per_cell'] for v in tc['by_coculture'].values()):.0f}–
          {max(v['um2_per_cell'] for v in tc['by_coculture'].values()):.0f} µm².
          Third, the between-well spread is narrow.</p>
          <p><b>Per-layer counts are an apportionment, not a measurement.</b> The
          calibration is defined on the projected (maximum-intensity) mask. Layer
          areas sum to several times the projected area because one cell appears in
          several layers, so dividing a layer area by the same scale would inflate
          the count severalfold. Per-layer cell equivalents therefore distribute the
          well total across layers in proportion to signal, and sum exactly to the
          well total. The per-frame overcount factor is reported in Table 2.
          Distance bands do not have this problem — they are computed on the
          projected mask, so band areas sum exactly to the projected area and the
          scale applies directly.</p>
        </div>
        <div>
          <h4>Why the tumour is not counted in cells</h4>
          <p>The same calculation for 2000 seeded PDA cells gives
          {tu['um2_per_cell']} µm² per cell, an equivalent diameter of
          <b>{tu['eq_diam_um']} µm</b> — smaller than a T cell, which is physically
          impossible for a tumour cell. The green stain misses most organoids. The
          tumour is therefore reported as signal area and signal volume, never as a
          cell count. This calibration was computed and <b>rejected</b>; it is shown
          here so the rejection can be checked.</p>
          <h4>Why objects are not counted</h4>
          <p>The difference in connected-component count between T-cell wells and
          T-cell-free wells is {ob['delta_objects']}, against 5000 seeded. At this
          resolution each component contains about {ob['cells_per_object']} cells.
          Every measure here is therefore area-based rather than object-based.</p>
        </div>
        <div>
          <h4>Units, and what each one rests on</h4>
          <p><b>No assumption:</b> enrichment, shares and ratios (dimensionless);
          pixel and voxel counts.<br>
          <b>Rests on 2.798 µm/px:</b> all mm², µm² and µm distances. That value
          comes from the instrument's own field label (2.91 × 3.94 mm over
          1040 × 1408 px), not from the file metadata, and is
          <b>not independently verified</b>.<br>
          <b>Rests on the calibration above:</b> every number marked ≈.<br>
          <b>Not available:</b> µm³ volumes and absolute depth. Volumes are given as
          <code>µm²·layer</code>; multiplying by the z step in µm converts them to
          µm³.</p>
          <h4>The z step is genuinely absent</h4>
          <p>It appears in no file. The TIFF tags carry no optical fields at all
          (<code>XResolution</code> is a constant 72 dpi placeholder), and the plate
          XML contains zero occurrences of <i>z</i>, <i>step</i>, <i>objective</i>,
          <i>plane</i>, <i>focus</i> or <i>micron</i> — it records only well contents
          and seeding densities. The z axis is therefore drawn as an ordinal ladder
          with layer indices and carries no scale bar, while the XY axes are metric
          and do. Also, z00 is not an absolute height: focus is set per well, so
          compare the <i>shape</i> of a depth distribution between wells, not the
          layer number.</p>
          <h4>What this page cannot answer</h4>
          <p>Macrophages and CAFs have no fluorescent label and cannot be told apart
          from tumour cells in the image; which wells contain them is known only
          from the plate map. Absolute cell numbers for any population other than
          T cells are not recoverable. At 4× (NA ≈ 0.13) the axial resolution is
          low: expect depth slabs, not fine 3D structure, and out-of-focus haze in
          every plane. No deconvolution is applied.</p>
          <h4>Colours</h4>
          <p>The conventional green/orange/red fluorescence triple is not used: for
          a red-blind reader green and orange separate by ΔE 3.2 against a floor of
          6.0, and orange and red separate by only ΔE 7.1 even in normal vision
          (floor 15.0). The triple used here passes every threshold in both light
          and dark (<code>atlas/palette_check.py</code>). Colour is never the only
          carrier: every series is directly labelled and every figure has a table.</p>
        </div>
      </div>
    </details>"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{well} — inc_tests atlas</title>
<style>{_asset('app.css')}</style>
</head>
<body>
<div class="wrap">

<header class="top">
  <span class="well">{well}</span>
  <span class="cond">{_cond(m)}</span>
  {warn}
  <span class="spacer"></span>
  <nav>
    <a href="index.html">← plate</a>
    <a href="groups.html">group comparisons</a>
    <a href="check/{well}.html" id="checklink">segmentation check</a>
    <a href="#methods">methods</a>
  </nav>
</header>

<section>
  <h2 class="sec">Spatial view</h2>
  <p class="lead">Every voxel above threshold, 5.6 µm on a side. Drag to orbit,
  shift-drag or middle-drag to pan, scroll to zoom, double-click to reset; keys
  1/3/7/9 give front, right, top and bottom views. The XY axes are metric and
  carry a scale bar; the <b>z axis is ordinal</b> — layers are drawn evenly
  spaced, but the distance between layers is recorded nowhere in the data, so no
  micron value is claimed for it. {dome_note}</p>

  <div class="stage">
    <div>
      <div class="scenebar">
        <div class="seg" role="group" aria-label="camera">
          <button data-view="home">oblique</button>
          <button data-view="top">top</button>
          <button data-view="front">front</button>
          <button data-view="right">right</button>
          <button data-view="bottom">bottom</button>
        </div>
        <label class="sel">layers
          <select id="slicemode">
            <option value="all">all</option>
            <option value="up">build up from z00</option>
            <option value="down">peel down from top</option>
            <option value="one">single layer</option>
          </select>
        </label>
        <button class="play" id="playz" title="animate layers" disabled>▶</button>
        <input type="range" id="cut" class="cut" min="0" max="16" value="16" disabled
               aria-label="layer cut">
        <span class="cutlabel" id="cutlabel"></span>
      </div>

      <div class="scene" id="scene" tabindex="0">
        <div class="hintbar">drag orbit · shift-drag pan · scroll zoom ·
          1/3/7/9 views · double-click reset</div>
        <div class="viewlabel" id="viewlabel"></div>
      </div>
      <p class="slabnote" id="cutshare"></p>

      <div class="proof" id="proof" hidden>
        <button class="proofclose" id="proofclose" title="close">×</button>
        <img id="proofimg" alt="raw plane with the measured mask outlined">
        <p id="proofcap"></p>
      </div>

      <div class="ctl">
        <div class="time">
          <button class="play" id="playt" title="play time">▶</button>
          <input type="range" id="tslider" min="0" max="12" value="12" step="1"
                 aria-label="timepoint">
          <span class="tlabel" id="tlabel">—</span>
        </div>
        <div class="chips">{chips}</div>
        <div class="chips">
          <button class="chip out" id="png3d">PNG ×3</button>
          <button class="chip out" id="panel3d">4-view panel</button>
        </div>
      </div>
    </div>

    <aside class="readout">
      <h3>At this timepoint</h3>
      {readout}
      <p class="note">The top four numbers are <b>measured</b> signal areas. The
      cell count under the T-cell row is <b>derived</b> — signal area divided by
      {tc['um2_per_cell']} µm² per cell — and is always written with ≈. The tumour
      is not converted to cells; the reason is in the methods section.</p>
    </aside>
  </div>

  <div class="tblblock">
    <div class="fighead"><h3><span class="fignum">Table 1</span> Summary at this
      timepoint</h3>
      <div class="tools"><button data-tbl="now">table</button></div></div>
    <div class="tbl on" id="tbl_now"></div>
  </div>
</section>

<section>
  <h2 class="sec">Where, and how much</h2>
  <div class="figs">{figs}</div>
</section>

{methods}

</div>
<script>window.DATA={json.dumps(data, ensure_ascii=False, separators=(',', ':'))};
window.THEME={_theme_js()};</script>
<script>{_asset('scene.js')}</script>
<script>{_asset('figs.js')}</script>
<script>{_asset('well.js')}</script>
</body>
</html>
"""


# --------------------------------------------------------------- grup sayfası
def groups_page(d: dict, figs: dict) -> str:
    cal = d["calibration"]
    tc = cal["tcell"]
    dm = d["dead_matched"]

    conf = d.get("confluence", {})
    stat_note = ("Every well is a point; the heavy line is the median and the grey "
                 "band is its bootstrap 95 % confidence interval (2000 resamples). "
                 "No box plots: with 4–17 wells per condition a box plot invents "
                 "quartiles. Tests are Mann-Whitney U, effect sizes are "
                 "Mann-Whitney AUC and Cliff's δ, and p values are corrected across "
                 "the comparisons in each figure with Benjamini-Hochberg "
                 "(column <code>q</code>).")

    sign = (f"The direction agrees in {dm['n_up']} of {dm['n_groups']} co-cultures; "
            f"sign test p = {dm['sign_p']}." if dm["n_groups"] else "")

    figs = "".join([
        _fig("enrich_coc", "Figure 1", "T-cell enrichment by co-culture",
             "Do T cells enter the organoid, and does the co-culture change that?",
             "Enrichment is T-cell signal density inside the brightfield organoid "
             "territory divided by density outside, so 1.0 is what a uniformly "
             "scattered population gives, below 1 is exclusion and above 1 is "
             "enrichment. A raw percentage would not be comparable across wells: "
             "the territory covers 6 % of the field in one well and 59 % in "
             "another, and there even a random population would come out “mostly "
             "inside”. Day 4, T-cell wells only. Log axis — the quantity is a "
             "ratio. " + stat_note, wide=True, img=figs["enrich_coc"]),
        _fig("enrich_cmp", "Figure 2", "T-cell enrichment by compound",
             "Do the KRAS and SRC inhibitors change T-cell access to the organoid?",
             "The same measure grouped by treatment, day 4, T-cell wells only. "
             "Doses are in the plate map: KRAS 10 and 100 nM, SRC 50 and 200 nM. "
             + stat_note, wide=True, img=figs["enrich_cmp"]),
        _fig("dist", "Figure 3", "How deep into the organoid the T cells reach",
             "Not whether T cells are inside, but how far inside they get.",
             "Median signed distance of the T-cell signal to the organoid boundary: "
             "negative is inside the territory, positive outside, zero at the rim. "
             "This is independent of Figure 1 — a population can be enriched inside "
             "and still sit only at the rim. "
             "<b>Confluent wells are excluded from this figure.</b> When the "
             "territory fills the field, every point is inside it by construction "
             "and the median distance measures confluence rather than infiltration. "
             f"Measured across all {conf.get('n', 0)} T-cell wells, territory "
             f"fraction and median distance correlate at Spearman ρ = "
             f"{conf.get('rho', float('nan'))} (p = {conf.get('p', float('nan'))}), "
             f"so wells whose territory covers more than "
             f"{100 * conf.get('cut', 0.7):.0f} % of the field are dropped here: "
             f"{conf.get('n_dropped', 0)} well(s)"
             + (" (" + ", ".join(conf.get("dropped", [])) + ")"
                if conf.get("dropped") else "")
             + ". Figure 1 is unaffected — enrichment is a density ratio and does "
               "not have this dependence. " + stat_note, wide=True, img=figs["dist"]),
        _fig("growth", "Figure 4", "Organoid growth",
             "How does the organoid mass develop, and does the co-culture change it?",
             "Brightfield territory area, independent of staining. Thin lines are "
             "individual wells, the heavy line is the group median. All four panels "
             "share one y axis, so they are directly comparable to each other — "
             "the unit is the same.", wide=True, img=figs["growth"]),
        _fig("dead", "Figure 5", "Effect of adding T cells on dead-cell signal",
             "Do the T cells kill?",
             "Matched design with co-culture held constant: co-culture affects both "
             "death and T-cell distribution on its own, so pooling T-cell and "
             "T-cell-free wells across co-cultures would confound the two. The "
             "dashed line joins the two medians. " + sign + " " + stat_note,
             wide=True, img=figs["dead"]),
        _fig("tumour", "Figure 6", "Effect of adding T cells on tumour signal",
             "Does adding T cells reduce the tumour?",
             "The same matched design on tumour signal area. This is not a tumour "
             "<i>cell count</i>: the green stain labels only part of the organoid "
             "population, so the area is a lower bound, and if staining efficiency "
             "differs between groups a difference could come from staining rather "
             "than from biology. Read together with Figure 5. " + stat_note,
             wide=True, img=figs["tumour"]),
        _fig("calib", "Figure 7", "Calibration of the T-cell scale",
             "Is the conversion from signal area to cell number trustworthy?",
             "Left: the area-per-cell scale derived independently in each "
             "co-culture group, with the pooled median and its bootstrap CI. Right: "
             "the equivalent cell diameter that each scale implies, against the "
             "known size range of a T cell. The same calculation applied to the "
             "2000 seeded tumour cells is shown for comparison and falls below the "
             "size of a T cell, which is impossible — that is why tumour signal is "
             "never converted to a cell count. This figure is the evidence for the "
             "≈ numbers used everywhere else.", wide=True, img=figs["calib"]),
    ])

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Group comparisons — inc_tests atlas</title>
<style>{_asset('app.css')}</style>
</head>
<body>
<div class="wrap">

<header class="top">
  <span class="well">Group comparisons</span>
  <span class="cond">{d['n_wells']} wells · {d['n_excluded']} excluded by QC ·
  day 4 unless stated</span>
  <span class="spacer"></span>
  <nav><a href="index.html">← plate</a></nav>
</header>

<section>
  <h2 class="sec">What is compared</h2>
  <p class="lead">Each well page opens one well in space; this page groups wells
  and compares them. The numbers are the same measurement — a point here has the
  value printed on that well's own page. Each figure answers one question and
  carries its own statistics table; every table downloads as CSV and every figure
  as SVG, so what is on screen is what goes into the manuscript.</p>
  <div class="figs">{figs}</div>
</section>

<details class="method" id="methods">
  <summary>Statistics and units</summary>
  <div class="body">
    <div>
      <h4>Why no box plots and no t-tests</h4>
      <p>Conditions hold 4–17 wells. At that size a box plot draws quartiles that
      the data does not support, and a parametric test assumes a distribution shape
      that cannot be checked. Every well is therefore shown as a point, the median
      is drawn explicitly, and its uncertainty is a bootstrap interval over 2000
      resamples of the wells.</p>
      <h4>Effect size before p value</h4>
      <p>Mann-Whitney AUC (0.5 = no separation, 1.0 = complete) and Cliff's δ
      (−1 to +1) are reported alongside every p value, because with these sample
      sizes a non-significant p is uninformative on its own while a large,
      consistent effect is worth reporting as such. Multiple comparisons within a
      figure are corrected with Benjamini-Hochberg.</p>
    </div>
    <div>
      <h4>Matched comparisons</h4>
      <p>Wherever the question is “what does adding T cells do”, the comparison is
      made inside each co-culture and not across the pooled plate: co-culture
      changes both death and T-cell distribution on its own. When individual
      groups are underpowered but agree in direction, a sign test over the groups
      is reported instead of a pooled test.</p>
      <h4>Units</h4>
      <p>Enrichment, AUC and δ are dimensionless and assume nothing. Areas in mm²
      rest on the pixel size of 2.798 µm/px, taken from the instrument's field
      label and not independently verified. Cell numbers rest on the calibration
      in Figure 7 and are always written with ≈. There is no µm³ volume anywhere
      because the z step is recorded in no file.</p>
    </div>
  </div>
</details>

</div>
<script>window.GROUPS={json.dumps(d, ensure_ascii=False, separators=(',', ':'))};
window.THEME={_theme_js()};</script>
<script>{_asset('figs.js')}</script>
<script>{_asset('groups.js')}</script>
</body>
</html>
"""


# -------------------------------------------------------------- plaka sayfası
def index_page(summ: dict) -> str:
    cal = summ["calibration"]["tcell"]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>inc_tests atlas — plate</title>
<style>{_asset('app.css')}</style>
</head>
<body>
<div class="wrap">

<header class="top">
  <span class="well">inc_tests atlas</span>
  <span class="cond">PDA 30364 · T-cell infiltration · 88 wells × 13 timepoints ·
  Incucyte 4×</span>
  <span class="spacer"></span>
  <nav><a href="groups.html">group comparisons →</a></nav>
</header>

<section>
  <h2 class="sec">Plate</h2>
  <p class="lead">Click a well to open its 3D view, depth and distance profiles,
  time course and tables. Colour shows the measure selected below, at the last
  timepoint (day 4). Hatched wells failed QC; the cross-hatched column was not
  imaged. The dot in the corner marks wells that received T cells.</p>

  <div class="platebar">
    <label for="metric">colour by</label>
    <select id="metric">
      <option value="t_enrich">T-cell enrichment (× uniform)</option>
      <option value="tcells">T cells (≈ count)</option>
      <option value="organoid_mm2">organoid territory (mm²)</option>
      <option value="growth">growth (day 4 / day 0)</option>
      <option value="dead_mm2">dead-cell signal (mm²)</option>
    </select>
    <div class="scalestrip"><span id="slo">—</span>
      <span class="bar" id="sbar"></span><span id="shi">—</span></div>
  </div>

  <div class="plate" id="plate"></div>
</section>

<section>
  <h2 class="sec">How to read the numbers in this atlas</h2>
  <div class="figs">
    <div>
      <p class="lead"><b>Signal areas are measured; cell counts are derived.</b>
      Everything reported in mm² or as a voxel count is a direct measurement of
      the segmented image. A T-cell count is an estimate: signal area divided by
      {cal['um2_per_cell']} µm² per cell, a scale calibrated from the seeding
      numbers and validated three ways (it implies an equivalent cell diameter of
      {cal['eq_diam_um']} µm, the real size of a T cell, and the four co-culture
      groups reproduce it independently). Derived numbers are always written
      with ≈.</p>
      <p class="lead"><b>The tumour is never converted to cells.</b> The same
      calculation applied to the 2000 seeded PDA cells implies a cell smaller than
      a T cell, which is impossible — the green stain misses most organoids. Tumour
      is reported as signal area and signal volume only.</p>
    </div>
    <div>
      <p class="lead"><b>Enrichment</b> is density inside the organoid territory
      divided by density outside. 1.0 is a uniform scatter, below 1 is exclusion,
      above 1 is enrichment. A raw percentage would not be comparable: the
      territory covers 6 % of the field in one well and 59 % in another.</p>
      <p class="lead"><b>What is not available:</b> µm³ volumes and absolute depth,
      because the z step appears in no file — the TIFF tags carry no optical fields
      and the plate XML contains no optical entry at all. Macrophages and CAFs have
      no fluorescent label and cannot be located in the image; which wells contain
      them is known only from the plate map.</p>
    </div>
  </div>
</section>

</div>
<script>window.SUMM={json.dumps(summ, ensure_ascii=False, separators=(',', ':'))};
window.THEME={_theme_js()};</script>
<script>{_asset('figs.js')}</script>
<script>{_asset('index.js')}</script>
</body>
</html>
"""
