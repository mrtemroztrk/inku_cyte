# atlas/ — 3D view, figures and evidence pages, one file per well

This directory turns the measurements into something you can open and look at.
Each well becomes a single self-contained HTML file: double-click it, no server,
no internet.

![building the stack layer by layer](../docs/slice.gif)

## Running it

```bash
python3 atlas/build.py  --all --jobs 7   # measure + pages       ~30 min (once)
python3 atlas/thumbs.py --all --jobs 7   # evidence thumbnails   ~15 min (once)
python3 atlas/check.py  --all --jobs 7   # segmentation pages     ~5 min
python3 atlas/build.py  --pages          # rebuild pages          seconds
xdg-open atlas/site/index.html
```

The measurement runs once and is cached under `atlas/cache/`. Changing wording, a
figure or a unit only needs `--pages`; the 30-minute measurement does not repeat.

Checks:

```bash
python3 atlas/calib.py                  # the signal-to-cell calibration and its tests
python3 atlas/palette_check.py          # colour-vision check on the channel colours
python3 atlas/selftest.py               # anything broken in the generated pages
python3 atlas/selftest.py --vs-analysis # do the numbers match the analysis/ pipeline
python3 atlas/shoot.py B04.html         # screenshot a page (headless Chrome)
python3 atlas/shoot.py B04.html --gif slice   # the animations in this README
```

## Four kinds of page

| file | what it shows |
|---|---|
| `site/index.html` | The 96-well plate, coloured by whichever measure you pick. Click a well to open it. |
| `site/<well>.html` | That well in 3D, two figures, three tables, and a methods section explaining where every number comes from. |
| `site/groups.html`, `site/groups_tNN.html` | Comparisons across wells at one imaging time — one page per timepoint (13), `groups.html` is the last. Twelve figures, each with a one-sentence reading, the wells behind every group, and a statistics table. These are the manuscript figures. |
| `site/check/<well>.html` | **Evidence.** The raw plane on the left with the measured mask outlined, the same layer in 3D on the right, moving together through z. Plus an overlay mode that proves the reconstruction sits where the stain is. |

### The overlay check

![sweeping the photograph over the reconstruction](../docs/overlay.gif)

Ticking **overlay photo on the reconstruction** locks the camera straight down and
scales the projection so one voxel covers exactly the pixels it was measured from,
then blends the photograph on top with a slider. If the reconstruction were
shifted, rotated, flipped or mis-scaled, the sweep would show two offset copies of
the same pattern; instead the dots fade in place.

The photograph is shown **without** the mask outline in this mode on purpose — the
outline comes from the same mask as the voxels, so comparing the two would be
circular. The test is whether the voxels land on the stain itself. Zoom and pan
apply to both layers at once, so the check survives being examined closely.

The **layers** control decides what both sides show:

| setting | photograph | reconstruction |
|---|---|---|
| this layer only | the single raw plane | only that layer lit |
| z00 → this layer | maximum projection of planes 0…z | layers 0…z lit |
| this layer → z16 | maximum projection of planes z…16 | layers z…16 lit |
| all layers | maximum projection of the whole stack | every layer lit |

Both sides always show the same accumulation — comparing a single-plane photograph
against a multi-layer slab would break the very thing the overlay is meant to
demonstrate. The projections are built in the browser from the raw planes (a
per-pixel maximum, which is what a maximum projection is), so nothing is embedded
twice.

**Link panels** (on by default) ties the two sides together: scroll to zoom, drag
the photograph to pan, shift-drag the reconstruction to pan, and the other side
follows to the same place at the same magnification. Orbiting keeps the linked
point at the centre. Turn it off to move one side alone.

**z00 on top** flips the ordinal z axis so the first plane is drawn uppermost —
for stacks acquired from the apex of the dome downwards. XY is untouched, so the
top view still matches the photograph. The choice is remembered across pages.

The z slider is a full-width bar with a tick every layer; the mouse wheel over it
steps one layer at a time, and the arrow keys do the same.

Only XY placement is testable this way. The z axis carries no micron scale, so
there is nothing to register it against.

**+ what a more sensitive threshold would add** draws a second, paler outline
around the pixels a threshold at 0.24× the plate gain would select and the
measured one does not, and the table gives both counts. It is not used for any
number; it exists so that "the threshold misses dim cells" can be checked on the
pixels rather than argued about.

What the sweep shows on real data: the bright cores of the stain are covered by
voxels, and the diffuse halo around each core is not — that halo is the
out-of-focus light a 4× objective spreads over neighbouring planes, and it falls
below threshold. So the overlay tests two things at once: that the reconstruction
is in the right place, and that the threshold is selecting cores rather than haze.

> A note on how this check is verified. The overlay is drawn on top of an opaque
> WebGL canvas, and the scene appends that canvas last, so without an explicit
> stacking order the photograph is hidden completely — and a comparison of "before
> and after" then shows two identical pictures, which looks like perfect
> registration and is in fact nothing at all. `atlas/shoot.py` now refuses to write
> an animation whose frames are identical, which is what caught it.

## Moving around in 3D

Blender conventions:

| | |
|---|---|
| drag | orbit |
| shift-drag or middle-drag | pan |
| scroll | zoom toward the cursor |
| double-click | reset |
| `1` `3` `7` `9` | front, right, top, bottom |

Neither angle is clamped: the eye can go over the pole and keep turning, so no
drag ever hits a wall.

The toolbar above the scene slices the stack: from z00 up to a layer, from a layer
to z16, or a single layer. The play button animates it. While slicing,
a line underneath reports how much of each channel the visible slab actually
contains, so the eye is not left to guess.

None of these controls changes a measurement. Thresholds, background subtraction
and masks are fixed plate-wide in the extraction pipeline, because a threshold
that moves from well to well makes wells incomparable. What a number means is
written in the methods section, not adjusted with a slider.

## The two figures on a well page

Each answers one question:

| figure | question |
|---|---|
| 1 — signal by depth | at which z layer does each population sit, and how much of it |
| 2 — time course | how each quantity changed over four days |

Position is reported **by layer only**. Earlier versions also drew a distance-to-
boundary profile, a depth × distance heat map, an inside/outside enrichment and a
dome ring. All of them rested on the brightfield footprint standing in for the
organoid, and the organoid's surface in z is not known — a cell over the footprint
may be above, inside or below the dome. They were removed rather than caveated;
the underlying counts (`bands`, `zband`, `dome`) are still in the cache but no
page derives anything from them. What remains is defensible on its own: how much
of each signal there is in each layer, and how that changes over time.

Clicking a bar in Figure 1 does two things: it isolates that layer in the 3D
scene, and it puts **the actual photograph of that layer** on the page. A claim
about a layer can be checked against its pixels without leaving the page.

Every figure has a table view and an SVG download; tables download as CSV, the 3D
scene as PNG (3× resolution) or as a four-view panel. What is on screen is what
goes into the manuscript.

## Two kinds of figure, on purpose

The **group page** figures are drawn server-side with matplotlib
(`atlas/figures.py`). These are the figures that go into a paper, and readers in
this field have spent their careers reading matplotlib and R output — a figure
that looks like the ones they already read is one they can interpret without
first learning its conventions. They carry n per group, the median with its
bootstrap confidence interval, an omnibus test, and significance brackets only
where a comparison survives correction.

The **well page** figures are drawn in the browser, because they follow the time
slider. They use the same conventions.

No box plots anywhere: conditions hold 4 to 17 wells, and a box plot invents
quartiles at that size. Every well is a point.

## Cell numbers: what is claimed and what is not

This is the part that needs the most care.

**What is measured is signal area.** Everything written in mm² is the area of the
pixels above threshold — a direct measurement. A cell count is a **derived
estimate** and is written with `≈` everywhere it appears.

**Where the T-cell number comes from.** The seeding numbers are known: wells
marked for T cells received 5000. The difference in projected signal area between
those wells and matched T-cell-free wells, divided by 5000, gives **90.8 µm² per
cell**. Before using that scale it had to pass three checks:

1. It implies an equivalent cell diameter of **10.8 µm**. A T cell is 7–10 µm, and
   at 2.798 µm/px with fluorescence bloom this is the value one should get. The
   scale does not imply a biologically impossible cell.
2. The four co-culture groups reproduce it **independently**, at 84–102 µm².
3. The between-well spread is narrow (CV 20 %, 95 % CI ±9 %).

**Why the tumour is not counted in cells.** The same calculation for 2000 seeded
PDA cells gives an equivalent diameter of 8.9 µm — smaller than a T cell, which is
impossible for a tumour cell. The reason is known: the green stain misses most
organoids (a median 15 % of brightfield objects carry any green signal). This
calibration was computed and **rejected**; it is shown on the group page so the
rejection can be checked.

**Why objects are not counted.** The difference in connected-component count
between wells with and without T cells is 1155 against 5000 seeded — each
component holds about 4.3 cells at this resolution.

**The trap in per-layer counts.** The calibration is defined on the projected
(maximum-intensity) mask. Layer areas are a different quantity: they sum to 3–5×
the projected area, because the depth of field of a 4× objective is tens of
microns and one cell appears in several layers. Dividing a layer area by the same
scale would inflate the count severalfold. Per-layer cell equivalents therefore
**apportion the well total** across layers in proportion to signal, and sum
exactly to the well total. The pages and tables say so, and report the overcount
factor for that frame.

## What the group page compares

One page per imaging time (13 of them; the selector at the top switches, and the
exact capture time from `timepoints.csv` is printed). At the top a table says
what was done to which well — co-culture, compound and dose, T cells or not, and
the well IDs — so that "n = 7" is never a mystery. Then, at the chosen time:

| figure | question |
|---|---|
| 1–2 | T-cell signal **by layer**, by co-culture and by compound |
| 3–4 | whole-well T-cell signal (≈ cells), by co-culture and by compound |
| 5 | T-cell signal over time, by co-culture |
| 6–8 | dead-cell signal, tumour signal and organoid growth by compound, wells with T cells beside wells without |
| 9 | organoid footprint area over time, by co-culture |
| 10–11 | the matched ±T-cell effect on dead-cell and tumour signal |
| 12 | the calibration behind every ≈ cell number |

Under every figure: a sentence saying what the numbers show (highest and lowest
group, which differences survive correction), then each group with its n, its
wells, median and mean ± SD, then the statistics table. The dye-only wells
(columns 10–12) did not receive the dead-cell dye — their NIR signal is zero in
all 21 — and are excluded from every dead-cell comparison.

Nothing about distance to the organoid or enrichment inside it: see above.

## Units

| quantity | unit | what it rests on |
|---|---|---|
| shares, ratios, AUC, Cliff's δ | dimensionless | **nothing** |
| pixel and voxel counts | count | **nothing** |
| area (mm², µm²) | µm-derived | 2.798 µm/px — from the instrument's field label, **not verified** |
| ≈ T-cell number | cells | the calibration above |
| signal volume | µm²·layer | × the z step gives µm³ |
| depth | z layer index | the z step is in no file |

`INC_UM_PER_PX=... python3 atlas/build.py --pages` changes the pixel size without
repeating the measurement.

### The z step is genuinely absent

The TIFF tags carry no optical field at all (`XResolution` is a constant 72 dpi
placeholder; there is nothing beyond `Software`). The plate XML contains **zero**
occurrences of *z*, *step*, *objective*, *plane*, *focus* or *micron* — it records
only well contents and seeding densities.

So the XY axes in the 3D scene are metric and carry a scale bar, while the **z
axis is ordinal**: layers are drawn evenly spaced, labelled by index, with no
micron claim. The z axis deliberately carries no scale bar — the asymmetry is the
point. Note also that z00 is not an absolute height: focus is set per well, so
compare the *shape* of a depth distribution between wells, not the layer number.

If the value turns up in the acquisition protocol, one multiplication converts
every volume to µm³.

## The channel colours were checked

The conventional green/orange/red fluorescence triple is not used. Measured: for a
red-blind reader green and orange separate by ΔE 3.2 against a floor of 6.0, and
orange and red separate by only ΔE 7.1 even in normal vision, against a floor of
15.0. About 8 % of male readers could not tell the tumour from the T cells. The
triple used here passes every threshold in both light and dark
(`python3 atlas/palette_check.py`). Colour is still never the only carrier: every
series is directly labelled and every figure has a table.

## Files

| | |
|---|---|
| `calib.py` | the signal-to-cell calibration, its validation tests, and the rejected alternatives |
| `measure.py` | the 3D measurement per well × timepoint; thresholds taken verbatim from `analysis/extract.py` |
| `build.py` | runs the measurement, derives the reported quantities, writes the pages |
| `groups.py` | across-well comparison and statistics |
| `figures.py` | the matplotlib figures for the group page |
| `check.py` | full-resolution segmentation evidence pages |
| `thumbs.py` | the evidence thumbnails embedded in each well page |
| `page.py` | HTML generation — no number is computed here, only layout and wording |
| `theme.py`, `palette_check.py` | colours, and the colour-vision check |
| `selftest.py` | checks the generated pages, and the measurement against `analysis/` |
| `shoot.py` | headless screenshots and the README animations |
| `templates/` | `app.css`, `scene.js` (WebGL), `figs.js`, `groups.js`, `well.js`, `check.js`, `index.js` |
| `cache/` | measurement and thumbnail cache — deletable, regenerated |
| `site/` | output |

### Relationship to `analysis/`

Thresholds, the brightfield mask and the band edges are taken verbatim from
`analysis/extract.py`, so the numbers here use the same definitions as the
analyses in `analysis/out/`. `selftest.py --vs-analysis` checks this on every run:
across all 1144 well × timepoint samples, area fraction and territory must be
identical (the cached enrichment is compared too, although no page shows it any
more). That check caught a real bug once — enrichment was being computed after
the ratio had been rounded, which produced relative errors above 60 % at small
ratios.

The atlas does not replace those analyses. They do plate-wide comparison and
statistics; the atlas opens one well in space and produces the figures in a form
that can go into a manuscript.

## What this atlas cannot answer

- **Where the macrophages and CAFs are.** No fluorescent label; indistinguishable
  from tumour cells in the image. Which wells contain them is known only from the
  plate map.
- **Tumour cell numbers.** See above.
- **Absolute depth and µm³ volumes.** The z step is not recorded.
- **Fine 3D structure.** At 4× (NA ≈ 0.13) the axial resolution is low; expect
  depth slabs. Every plane carries out-of-focus haze and no deconvolution is
  applied.
