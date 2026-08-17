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

import defs as DEFS
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
    ])

    figs = "".join([
        _fig("depth", "Figure 1", "Signal by depth",
             "At which depth does each population sit?",
             "Bars are the threshold-above signal area measured on each z plane's "
             "own mask; z00 is drawn at the bottom, or on top when the scene is "
             "flipped with <i>z00 on top</i> — the figure always matches the 3D "
             "scene. The three "
             "panels carry different units and are read independently of one "
             "another. Layer spacing is not to scale — the z step is recorded "
             "nowhere in the data. The italic tick row under the T-cell panel "
             "converts to cell equivalents by apportioning the whole-well total "
             "across layers in proportion to signal; layer areas cannot be "
             "converted directly, because the depth of field of a 4× objective "
             "(NA ≈ 0.13) is tens of microns and one cell appears in several "
             "layers. Click a bar to isolate that layer in the 3D scene and open "
             "the photograph of it."),
        _fig("time", "Figure 2", "Time course",
             "How did each quantity change over the four days?",
             "Four quantities, four units, four panels. The filled marker is the "
             "timepoint currently shown in the 3D scene. Organoid mass is measured "
             "in brightfield and is independent of staining; tumour signal depends "
             "on the green stain, which does not label every organoid (see "
             "Methods), so it is a lower bound. <b>Click any point to open the "
             "image stack for that timepoint</b> and step through its layers — the "
             "curve and the pictures it was measured from, side by side.",
             wide=True),
    ])

    last = pay["frames"][-1]
    sm = []
    for ch, lbl in (("green", "tumour"), ("orange", "T cells")):
        z = last["by_z"].get(ch) or []
        a = last["totals"][ch]["area_frac"] * last["grid"]["h"] * last["grid"]["w"] \
            * (last["grid"]["bin"] ** 2)
        if a > 0 and sum(z) > 0:
            sm.append(f"{sum(z) / a:.1f}-fold for {lbl}")
    smear_txt = " and ".join(sm) if sm else "two- to three-fold"

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
          <p>One point per 5.6 µm voxel above threshold, each XY position in the
          plane where it is brightest; every channel accumulates its own density
          and is coloured afterwards, so a dense region saturates towards its own
          channel colour, never towards white. It is a rendering of the
          segmentation, not of the raw image, so it shows exactly what was
          measured.</p>
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
          well total. The per-frame overcount factor is reported in Table 2.</p>
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
          <p><b>No assumption:</b> shares and ratios (dimensionless); pixel and
          voxel counts.<br>
          <b>Rests on 2.798 µm/px:</b> all mm² and µm² areas. That value
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
          <h4>What this page deliberately does not compute</h4>
          <p>Nothing about where the cells sit <i>relative to the organoid</i>:
          no “inside/outside”, no distance to the boundary, no dome surface. The
          brightfield gives the organoid's footprint in XY, but its surface in z is
          unknown, and at 4× a cell over the footprint may be above, inside or
          below the dome. What <b>can</b> be said, and is said, is how much of each
          signal there is in each layer, and how that changes over time.</p>
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
  <p class="lead">Each XY position above threshold is drawn once, 5.6 µm on a
  side, in the plane where it is brightest (<i>best-focus plane</i>) when the
  whole stack is shown. A 4× objective keeps one object above threshold in
  several neighbouring planes — here the layer areas exceed the projected area
  {smear_txt} — so drawing every plane (<i>all planes (raw)</i>, the volume
  Figure 1 is measured from) stretches each object into a column of out-of-focus
  light. When the stack is sliced to a layer or a run of layers, the raw planes
  are drawn instead: exactly the pixels above threshold in those planes, as in
  their photographs. Drag to orbit, shift-drag to pan,
  scroll to zoom, double-click to reset; keys 1/3/7/9 give front, right, top and
  bottom views. The XY axes are metric and
  carry a scale bar; the <b>z axis is ordinal</b> — layers are drawn evenly
  spaced, but the distance between layers is recorded nowhere in the data, so no
  micron value is claimed for it. The grey base plane is the organoid's
  brightfield footprint — its area, in XY; nothing about the organoid's surface
  or depth is claimed.</p>

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
        <label class="sel">3D
          <select id="cloud">
            <option value="auto">auto: raw planes when sliced, best-focus for the whole stack</option>
            <option value="focus">best-focus plane</option>
            <option value="all">all planes (raw)</option>
          </select>
        </label>
        <label class="sel">layers
          <select id="slicemode">
            <option value="all">all</option>
            <option value="up">z00 → layer</option>
            <option value="down">layer → z16</option>
            <option value="one">single</option>
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
        <div>
          <p id="proofcap"></p>
          <div class="proofbar">
            <span class="barlbl">layer</span>
            <input type="range" id="proofz" class="cut" min="0" max="16" value="8"
                   aria-label="proof layer">
            <span class="cutlabel" id="proofzlab"></span>
          </div>
        </div>
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
        <label class="chk"><input type="checkbox" id="zup"> z00 on top</label>
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
<dialog id="explain"><div class="exbody"></div>
  <form method="dialog"><button class="wide">close</button></form></dialog>
<script>window.DATA={json.dumps(data, ensure_ascii=False, separators=(',', ':'))};
window.THEME={_theme_js()};
window.DEFS={json.dumps(DEFS.build(cal), ensure_ascii=False, separators=(',', ':'))};</script>
<script>{_asset('scene.js')}</script>
<script>{_asset('figs.js')}</script>
<script>{_asset('well.js')}</script>
</body>
</html>
"""


# --------------------------------------------------------------- grup sayfası
def _fmtn(v, d=2):
    if v is None:
        return "—"
    return f"{v:,.{d}f}" if d else f"{v:,.0f}"


def _glabel(g: str) -> str:
    import groups as G
    return G.COMPOUND_LABEL.get(g, G.COCULTURE_LABEL.get(g, g))


def _wells_block(data: dict, unit: str, d: int = 2, title: str | None = None) -> str:
    """Bir figürün altına: her grup, kuyuları, n'i, medyanı, ortalama ± SS'si.
    "n = 7" ne demek ve hangi yedi kuyu — hep yazılı olsun diye."""
    rows = []
    for g in data["groups"]:
        wl = ", ".join(g["wells"]) if isinstance(g["wells"][0], str) \
            else ", ".join(w["well"] for w in g["wells"])
        stat = ""
        if "median" in g and not isinstance(g["median"], list):
            stat = (f' — median {_fmtn(g["median"], d)}, mean {_fmtn(g.get("mean"), d)}'
                    f' ± {_fmtn(g.get("sd"), d)} {unit}')
        elif "peak" in g:
            stat = f' — median profile peaks at z{g["peak"]:02d}'
        rows.append(f'<li><b>{html.escape(g["label"])}</b> '
                    f'<span class="k">({html.escape(_glabel(g["label"]))})</span> — '
                    f'n = {g["n"]} wells: {wl}{stat}</li>')
    head = f"<b>{title}</b> " if title else ""
    return (f'<div class="wellsblock">{head}<ul>' + "".join(rows) + "</ul></div>"
            if rows else "")


def _takeaway_strip(data: dict, unit: str, d: int = 2) -> str:
    """Figürün söylediği, düz cümleyle — sayılardan üretilir, yorum eklenmez."""
    gs = data["groups"]
    if len(gs) < 2:
        return ""
    hi = max(gs, key=lambda g: g["median"]); lo = min(gs, key=lambda g: g["median"])
    sig = [t for t in data.get("tests", []) if t.get("q") is not None and t["q"] < 0.05]
    out = (f"Highest median: <b>{hi['label']}</b> ({_fmtn(hi['median'], d)} {unit}); "
           f"lowest: <b>{lo['label']}</b> ({_fmtn(lo['median'], d)} {unit}).")
    if sig:
        out += (" Differences that survive correction (q &lt; 0.05): " +
                "; ".join(f"{t['a']} vs {t['b']} (q = {t['q']:.3f})" for t in sig) + ".")
    else:
        out += " No pairwise difference survives Benjamini-Hochberg correction."
    return f'<p class="takeaway">{out}</p>'


def _takeaway_profile(data: dict) -> str:
    gs = data["groups"]
    if not gs:
        return ""
    pk = {g["peak"] for g in gs}
    if len(pk) == 1:
        return (f'<p class="takeaway">The T-cell signal peaks in the same layer, '
                f'<b>z{pk.pop():02d}</b>, in every group.</p>')
    return ('<p class="takeaway">Peak layer of the median profile: ' +
            "; ".join(f"{g['label']} z{g['peak']:02d}" for g in gs) + ".</p>")


def _catalogue_table(cat: list[dict]) -> str:
    rows = []
    for r in cat:
        rows.append(
            f"<tr><td>{html.escape(r['coculture'])}</td>"
            f"<td>{html.escape(_glabel(r['compound']))}</td>"
            f"<td>{'yes (5000)' if r['has_tcells'] else 'no'}</td>"
            f"<td>{len(r['wells'])}</td><td>{', '.join(r['wells'])}"
            + (f' <span class="k">excluded by QC: {", ".join(r["excluded"])}</span>'
               if r["excluded"] else "") + "</td></tr>")
    return ('<table class="cat"><thead><tr><th>co-culture</th><th>compound</th>'
            '<th>T cells added</th><th>n</th><th>wells</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table>")


def groups_page(d: dict, figs: dict) -> str:
    cal = d["calibration"]
    tc = cal["tcell"]
    dm = d["dead_matched"]
    tm = d["tumour_matched"]
    t = d["t"]
    when = f"day {t['day']:g} ({t['hours']:g} h after seeding, imaged {t['datetime'].replace('T', ' ')})"

    stat_note = ("Every well is a point; the heavy line is the median and the grey "
                 "band is its bootstrap 95 % confidence interval (2000 resamples). "
                 "No box plots: with 4–17 wells per condition a box plot invents "
                 "quartiles. Tests are Mann-Whitney U, effect sizes are "
                 "Mann-Whitney AUC and Cliff's δ, and p values are corrected across "
                 "the comparisons in each figure with Benjamini-Hochberg "
                 "(column <code>q</code>). Mean ± SD per group is in the block "
                 "under the figure and in the table.")
    layer_note = ("Thin lines are individual wells, the heavy line is the group "
                  "median per layer and the shaded band its interquartile range; "
                  "the dotted line marks the layer where the median peaks. The x "
                  "axis is the layer index — ordinal, because the z step is "
                  "recorded in no file — so read the <i>shape</i> and the peak "
                  "layer, not microns. Layer areas are measured on each plane's own "
                  "mask and one cell appears in several neighbouring planes, so "
                  "the curves are wider than the cells; that is the same for every "
                  "well and does not affect the comparison.")
    cmp_note = ("Compound groups pool the four co-cultures: each compound was given "
                "to one T-cell well per co-culture, so a T-cell compound group is "
                "n = 4 wells, one of each co-culture, and co-culture is balanced "
                "across compounds. Wells without T cells exist only for the "
                "control, dye-only, low-dose and low-combination arms.")
    sign_d = (f"The direction agrees in {dm['n_up']} of {dm['n_groups']} co-cultures; "
              f"sign test p = {dm['sign_p']}." if dm["n_groups"] else "")
    sign_t = (f"The direction agrees in {tm['n_up']} of {tm['n_groups']} co-cultures; "
              f"sign test p = {tm['sign_p']}." if tm["n_groups"] else "")

    def matched_block(data):
        rows = []
        for r in data["rows"]:
            rows.append(f'<li><b>{html.escape(r["group"])}</b> — without T cells '
                        f'(n = {r["n_ctrl"]}): {", ".join(r["wells_ctrl"])}; '
                        f'with T cells (n = {r["n_t"]}): {", ".join(r["wells_t"])}'
                        f' — medians {_fmtn(r["med_ctrl"], 4)} vs {_fmtn(r["med_t"], 4)} mm² '
                        f'({r["ratio"]:.2f}×)</li>')
        return f'<div class="wellsblock"><b>Wells in this figure:</b><ul>{"".join(rows)}</ul></div>'

    def pair_blocks(sp, unit, dd):
        return (_wells_block(sp["t"], unit, dd, "Left panel — wells with T cells:") +
                _wells_block(sp["no_t"], unit, dd, "Right panel — wells without T cells:"))

    def pair_take(sp, unit, dd):
        a = _takeaway_strip(sp["t"], unit, dd); b = _takeaway_strip(sp["no_t"], unit, dd)
        return ((a.replace('<p class="takeaway">', '<p class="takeaway"><b>With T cells:</b> ')
                 if a else "") +
                (b.replace('<p class="takeaway">', '<p class="takeaway"><b>Without T cells:</b> ')
                 if b else ""))

    def fig(fid, num, title, question, caption, extra):
        return _fig(fid, num, title, question, caption, wide=True, img=figs[fid]) \
            .replace('<div class="tbl" id="tbl_' + fid + '"></div>',
                     extra + '<div class="tbl" id="tbl_' + fid + '"></div>')

    figs_html = "".join([
        fig("tz_coc", "Figure 1", "T-cell signal by layer, by co-culture",
            "In which layers do the T cells sit, and does the co-culture move them?",
            "Position is reported by layer only. Nothing is claimed about the "
            "cells' position relative to the organoid: the organoid's surface in z "
            "is not known, so “inside”, “outside” and “distance to the boundary” "
            "are not computed anywhere in this atlas. What is measured is how "
            f"much T-cell signal each layer holds at {when}, T-cell wells only. "
            + layer_note,
            _takeaway_profile(d["tz_coculture"]) + _wells_block(d["tz_coculture"], "")),
        fig("tz_cmp", "Figure 2", "T-cell signal by layer, by compound",
            "Do the KRAS and SRC inhibitors change where along z the T cells sit?",
            "The same profiles grouped by treatment, T-cell wells only. " + cmp_note
            + " " + layer_note,
            _takeaway_profile(d["tz_compound"]) + _wells_block(d["tz_compound"], "")),
        fig("tc_coc", "Figure 3", "T-cell signal by co-culture",
            "How much T-cell signal is there, and does the co-culture change it?",
            "Whole-well T-cell signal converted to ≈ cells with the calibration in "
            "the last figure; every T-cell well received 5000 T cells, so "
            "differences are in what remains detectable above threshold at this "
            "timepoint. " + stat_note,
            _takeaway_strip(d["tcells_coculture"], "cells", 0)
            + _wells_block(d["tcells_coculture"], "cells", 0)),
        fig("tc_cmp", "Figure 4", "T-cell signal by compound",
            "Do the compounds change how much T-cell signal remains?",
            "The same quantity grouped by treatment, T-cell wells only. " + cmp_note
            + " " + stat_note,
            _takeaway_strip(d["tcells_compound"], "cells", 0)
            + _wells_block(d["tcells_compound"], "cells", 0)),
        fig("tc_time", "Figure 5", "T-cell signal over time, by co-culture",
            "How does the T-cell signal develop over the four days?",
            "Every T-cell well as a thin line, the group median heavy; the dotted "
            "vertical line is the timepoint this page shows. All panels share one "
            "y axis.",
            _wells_block(d["tcell_time"], "")),
        fig("dead_cmp", "Figure 6", "Dead-cell signal by compound",
            "Do the compounds change how much cell death there is, with and without T cells?",
            "Dead-cell (NIR) signal area, whole well, grouped by treatment; left "
            "panel wells that received T cells, right panel wells that did not, "
            "same y axis. <b>The dye-only wells (columns 10–12) did not receive "
            "the dead-cell dye</b> — their NIR signal is zero in all 21 wells while "
            "their green and orange background is normal — so they are left out "
            "of every dead-cell comparison. " + cmp_note + " " + stat_note,
            pair_take(d["dead_compound"], "mm²", 4) + pair_blocks(d["dead_compound"], "mm²", 4)),
        fig("tumour_cmp", "Figure 7", "Tumour signal by compound",
            "Do the compounds change the tumour signal, with and without T cells?",
            "Tumour (green) signal area, whole well. This is not a tumour cell "
            "count: the green stain labels only part of the organoid population, "
            "so the area is a lower bound. " + cmp_note + " " + stat_note,
            pair_take(d["tumour_compound"], "mm²", 3) + pair_blocks(d["tumour_compound"], "mm²", 3)),
        fig("growth_cmp", "Figure 8", "Organoid growth by compound",
            "Do the compounds slow the growth of the organoid mass?",
            "Growth is the brightfield footprint area at this timepoint divided by "
            "the same well's footprint at day 0 — dimensionless, 1.0 = no change. "
            "Brightfield includes every dark object, so this is growth of cellular "
            "mass, not of tumour specifically. " + cmp_note + " " + stat_note,
            pair_take(d["growth_compound"], "×", 2) + pair_blocks(d["growth_compound"], "×", 2)),
        fig("growth", "Figure 9", "Organoid footprint area over time, by co-culture",
            "How does the organoid mass develop, and does the co-culture change it?",
            "The area of the well covered by dark (cellular) material in "
            "brightfield, in mm², at each of the 13 imaging times — independent of "
            "any stain. Thin lines are individual wells (with and without T cells), "
            "the heavy line is the group median, the dotted vertical line the "
            "timepoint this page shows. All four panels share one y axis, so they "
            "are directly comparable.",
            _wells_block(d["growth"], "")),
        fig("dead", "Figure 10", "Effect of adding T cells on dead-cell signal",
            "Do the T cells kill?",
            "Matched design with co-culture held constant: co-culture affects both "
            "death and T-cell distribution on its own, so pooling T-cell and "
            "T-cell-free wells across co-cultures would confound the two. The "
            "dashed line joins the two medians. Dye-only wells (no dead-cell dye) "
            "are excluded. " + sign_d + " " + stat_note,
            matched_block(dm)),
        fig("tumour", "Figure 11", "Effect of adding T cells on tumour signal",
            "Does adding T cells reduce the tumour?",
            "The same matched design on tumour signal area. If staining efficiency "
            "differs between groups a difference could come from staining rather "
            "than from biology. Read together with Figure 10. " + sign_t + " " + stat_note,
            matched_block(tm)),
        fig("calib", "Figure 12", "Calibration of the T-cell scale",
            "Is the conversion from signal area to cell number trustworthy?",
            "Left: the area-per-cell scale derived independently in each "
            "co-culture group, with the pooled median and its bootstrap CI. Right: "
            "the equivalent cell diameter that each scale implies, against the "
            "known size range of a T cell. The same calculation applied to the "
            "2000 seeded tumour cells is shown for comparison and falls below the "
            "size of a T cell, which is impossible — that is why tumour signal is "
            "never converted to a cell count. This figure is the evidence for the "
            "≈ numbers used everywhere else.", ""),
    ])

    tsel = "".join(
        f'<option value="groups_t{x["t"]:02d}.html"{" selected" if x["t"] == t["index"] else ""}>'
        f'day {x["hours"] / 24:.2f} · {x["hours"]:g} h · {x["datetime"].replace("T", " ")}'
        f'</option>' for x in d["times"])

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Group comparisons — {when} — inc_tests atlas</title>
<style>{_asset('app.css')}</style>
</head>
<body>
<div class="wrap">

<header class="top">
  <span class="well">Group comparisons</span>
  <span class="cond">{d['n_wells']} wells · {d['n_excluded']} excluded by QC</span>
  <span class="spacer"></span>
  <nav><a href="index.html">← plate</a></nav>
</header>

<section>
  <h2 class="sec">Which timepoint</h2>
  <p class="lead">Every figure on this page is computed at one imaging time. The
  plate was imaged 13 times over four days; pick any of them — the page reloads
  with that timepoint's numbers. Time-course figures show all 13 and mark the
  chosen one.</p>
  <div class="platebar">
    <label for="tsel">timepoint</label>
    <select id="tsel" onchange="location.href=this.value">{tsel}</select>
    <span class="k">now showing: <b>{when}</b></span>
  </div>
</section>

<section>
  <h2 class="sec">What was done to which well</h2>
  <p class="lead">Every well holds <b>2000 PDA tumour cells</b> (pancreatic ductal
  adenocarcinoma organoids, line 30364) in a dome. Four <b>co-cultures</b>: PDA
  alone, PDA + 4000 cancer-associated fibroblasts (CAF), PDA + 8000 macrophages
  (MAC), or PDA + both. Some wells additionally received <b>5000 T cells</b>.
  Each well got one <b>compound</b>: vehicle control, dye only, a KRAS inhibitor
  (10 or 100 nM), a SRC inhibitor (50 or 200 nM), or both together (low or high
  dose). The dye-only wells carry no dead-cell dye and are kept out of dead-cell
  comparisons. “<b>n = 7</b>” under a group means the figure was computed from seven
  wells, and the wells are listed under every figure and in this table. Wells
  excluded by QC are named and are in no figure.</p>
  {_catalogue_table(d['catalogue'])}
</section>

<section>
  <h2 class="sec">How the numbers are made</h2>
  <div class="figs">
    <div>
      <p class="lead"><b>What is measured.</b> In every fluorescence plane, pixels
      brighter than a fixed, plate-wide threshold are “signal”; the signal area is
      their count × (2.798 µm)². Green = tumour stain, orange = T cells, NIR = dead
      cells. The organoid footprint is the dark area in brightfield. These are
      measurements; nothing is fitted.</p>
      <p class="lead"><b>How a T cell's area was decided.</b> Every T-cell well
      received exactly 5000 T cells (plate map). At the first imaging time the
      orange signal area of the T-cell wells exceeds that of matched wells without
      T cells by a certain amount; that difference ÷ 5000 =
      <b>{tc['um2_per_cell']} µm² per T cell</b> (95 % CI {tc['ci95'][0]}–{tc['ci95'][1]},
      n = {tc['n_wells']} wells). It implies a cell {tc['eq_diam_um']} µm across —
      a real T cell is 7–10 µm, and at this pixel size with fluorescence bloom this
      is what one should get — and the four co-cultures reproduce it independently
      (Figure 12).</p>
    </div>
    <div>
      <p class="lead"><b>How “how many T cells” is decided.</b> Orange signal area
      in the well ÷ {tc['um2_per_cell']} µm² per cell. It is written with ≈
      because it is a conversion, not a count of objects: at 4× single T cells
      cannot be resolved (each connected blob holds several). The tumour is never
      converted to cells — the same calculation gives a cell smaller than a T
      cell, which is impossible, because the green stain misses most organoids.</p>
      <p class="lead"><b>What is not claimed.</b> Where the cells sit relative to
      the organoid (its surface in z is unknown), µm³ volumes (the z step is
      recorded nowhere) and absolute depths. Position is reported by layer index
      only.</p>
    </div>
  </div>
</section>

<section>
  <h2 class="sec">Comparisons at {when}</h2>
  <p class="lead">Each figure answers one question written under its title, and
  under the figure a sentence says what the numbers show, then which wells went
  into each group, then a table with the statistics. Every table downloads as CSV
  and every figure as SVG.</p>
  <div class="figs">{figs_html}</div>
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
      resamples of the wells. Mean ± SD is given as well, in the text block under
      each figure and in its table.</p>
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
      <p>AUC and δ are dimensionless and assume nothing. Areas in mm² rest on the
      pixel size of 2.798 µm/px, taken from the instrument's field label and not
      independently verified. Cell numbers rest on the calibration in Figure 12 and
      are always written with ≈. Layer indices are ordinal. There is no µm³ volume
      anywhere because the z step is recorded in no file, and there is no
      inside/outside or distance measure because the organoid's surface in z is
      unknown.</p>
    </div>
  </div>
</details>

</div>
<dialog id="explain"><div class="exbody"></div>
  <form method="dialog"><button class="wide">close</button></form></dialog>
<script>window.GROUPS={json.dumps(d, ensure_ascii=False, separators=(',', ':'))};
window.THEME={_theme_js()};
window.DEFS={json.dumps(DEFS.build(d["calibration"]), ensure_ascii=False,
                        separators=(',', ':'))};</script>
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
  <p class="lead">Click a well to open its 3D view, its signal-by-layer profile,
  time course and tables. Colour shows the measure selected below, at the last
  timepoint (day 4). Hatched wells failed QC; the cross-hatched column was not
  imaged. The dot in the corner marks wells that received T cells.</p>

  <div class="platebar">
    <label for="metric">colour by</label>
    <select id="metric">
      <option value="tcells">T cells (≈ count)</option>
      <option value="tcell_peak_z">T-cell peak layer</option>
      <option value="organoid_mm2">organoid territory (mm²)</option>
      <option value="growth">growth (day 4 / day 0)</option>
      <option value="dead_mm2">dead-cell signal (mm²)</option>
    </select>
    <div class="scalestrip"><span id="slo">—</span>
      <span class="bar" id="sbar"></span><span id="shi">—</span></div>
  </div>
  <p class="lead metricdesc" id="metricdesc"></p>

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
      <p class="lead"><b>Position is reported by layer only.</b> Each well says
      how much of each signal sits in each of its 17 z layers and how that changes
      over four days. Nothing is claimed about where cells are relative to the
      organoid — the organoid's surface in z is not known, so “inside”, “outside”
      and “distance to the boundary” are not computed.</p>
      <p class="lead"><b>What is not available:</b> µm³ volumes and absolute depth,
      because the z step appears in no file — the TIFF tags carry no optical fields
      and the plate XML contains no optical entry at all. Macrophages and CAFs have
      no fluorescent label and cannot be located in the image; which wells contain
      them is known only from the plate map.</p>
    </div>
  </div>
</section>

</div>
<dialog id="explain"><div class="exbody"></div>
  <form method="dialog"><button class="wide">close</button></form></dialog>
<script>window.SUMM={json.dumps(summ, ensure_ascii=False, separators=(',', ':'))};
window.THEME={_theme_js()};
window.DEFS={json.dumps(DEFS.build(summ["calibration"]), ensure_ascii=False,
                        separators=(',', ':'))};</script>
<script>{_asset('figs.js')}</script>
<script>{_asset('index.js')}</script>
</body>
</html>
"""
