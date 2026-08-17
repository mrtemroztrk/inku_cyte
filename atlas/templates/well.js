/* Well page: data → 3D scene, figures, tables.

   The controls are view controls only — time, which channels are drawn, which
   layers are drawn, and the camera. Nothing here changes a measurement:
   thresholds, background subtraction and masks are fixed plate-wide in the
   extraction pipeline, because a threshold that moves from well to well makes
   wells incomparable. What a number means is written in the methods section,
   not adjusted with a slider. */

(() => {
  const D = window.DATA, T = window.THEME, F = D.frames, CAL = D.calibration;
  const $ = s => document.querySelector(s);
  const fmt = FIG.fmt, zpad = FIG.zpad;
  const NZ = F[0].grid.nz;

  let t = F.length - 1;
  let playT = null, playZ = null;
  let sliceMode = "all", cut = NZ - 1;
  const svgs = {};

  // -------------------------------------------------------------------- 3D
  const scene = new SCENE.Scene($("#scene"), {
    vox_um: D.voxel_um, colors: T.scene, terrColor: T.terrScene,
    onView: v => { $("#viewlabel").textContent =
      `az ${Math.round(((v.az % 360) + 360) % 360)}° · el ${Math.round(v.elev)}° · ` +
      `${fmt(v.zoom, 1)}×`; },
  });

  // ---------------------------------------------------------------- slicing
  /* Layers can be revealed from the bottom up, removed from the top down, or
     shown one at a time. The cut is a uniform in the vertex shader, so this is
     free — no data is re-uploaded and no measurement changes. */
  function applySlice() {
    const m = sliceMode;
    const lo = m === "up" ? 0 : m === "down" ? cut : m === "one" ? cut : 0;
    const hi = m === "up" ? cut : m === "down" ? NZ - 1 : m === "one" ? cut : NZ - 1;
    scene.setSlice(lo, hi, m === "one" ? 0.35 : 0.6);
    const on = m !== "all";
    $("#cut").disabled = !on;
    $("#playz").disabled = !on;
    $("#cutlabel").textContent = on
      ? (m === "one" ? `layer ${zpad(cut)}`
         : m === "up" ? `layers ${zpad(0)}–${zpad(cut)}`
         : `layers ${zpad(cut)}–${zpad(NZ - 1)}`)
      : `all ${NZ} layers`;
    $("#cutshare").textContent = on ? layerShare(lo, hi) : "";
  }

  /* How much of each channel the visible slab actually contains — otherwise a
     slice view invites the eye to conclude something the numbers do not say. */
  function layerShare(lo, hi) {
    const d = F[t].derived;
    const part = [];
    for (const [key, lbl] of [["tumour", "tumour"], ["tcell", "T cells"],
                              ["dead", "dead"]]) {
      const a = d[`${key}_area_by_z_mm2`];
      const tot = a.reduce((s, v) => s + v, 0);
      let s = 0;
      for (let z = Math.ceil(lo); z <= Math.floor(hi); z++) s += a[z] || 0;
      part.push(`${lbl} ${tot > 0 ? fmt(s / tot * 100, 0) : "0"} %`);
    }
    return "visible slab holds " + part.join(" · ");
  }

  $("#slicemode").addEventListener("change", e => {
    sliceMode = e.target.value;
    if (sliceMode === "down") cut = 0;
    if (sliceMode === "up") cut = NZ - 1;
    $("#cut").value = cut;
    applySlice();
  });
  $("#cut").max = NZ - 1;
  $("#cut").addEventListener("input", e => { cut = +e.target.value; applySlice(); });
  $("#playz").addEventListener("click", () => {
    if (playZ) { clearInterval(playZ); playZ = null; $("#playz").textContent = "▶"; return; }
    $("#playz").textContent = "❚❚";
    playZ = setInterval(() => {
      cut = cut >= NZ - 1 ? 0 : cut + 1;
      $("#cut").value = cut;
      applySlice();
    }, 260);
  });

  for (const b of document.querySelectorAll("[data-view]"))
    b.addEventListener("click", () => scene.view(b.dataset.view));

  // ------------------------------------------------------------------ frame
  async function setFrame(i) {
    const j = Math.max(0, Math.min(F.length - 1, i));
    t = j;
    const f = F[j];
    $("#tslider").value = j;
    $("#tlabel").innerHTML = `<b>day ${fmt(D.times[j].hours / 24, 2)}</b> · ` +
      `${D.times[j].hours} h · t${String(j).padStart(2, "0")}`;
    readout(f);
    figures(f);
    if (sliceMode !== "all") $("#cutshare").textContent = layerShare(
      sliceMode === "down" ? cut : 0, sliceMode === "up" ? cut : NZ - 1);
    const rec = await scene.load(j, f, f.grid);
    if (t === j && rec) scene.show(rec);
  }

  // ---------------------------------------------------------------- readout
  function readout(f) {
    const d = f.derived, o = f.totals.orange;
    const set = (id, val, unit, sub) => {
      $(`#q_${id} .val`).innerHTML = val + (unit ? `<span class="u">${unit}</span>` : "");
      $(`#q_${id} .sub`).innerHTML = sub || "";
    };
    set("organoid", fmt(d.organoid_mm2, 2), "mm²",
      `${fmt(f.bf.terr_frac * 100, 0)} % of the imaged field`);
    set("tumour", fmt(d.tumour_mm2, 3), "mm²",
      `volume ${fmt(d.tumour_vol_um2layer / 1e6, 2)} ×10⁶ µm²·layer`);
    set("tcell", fmt(d.tcell_mm2, 3), "mm²",
      `derived: <b>≈ ${fmt(d.tcells, 0)} cells</b>` +
      (o.frac_in_terr == null ? ""
        : ` · ${fmt(o.frac_in_terr * 100, 0)} % inside the organoid territory`));
    set("dead", fmt(d.dead_mm2, 4), "mm²",
      f.totals.nir.frac_in_terr == null ? "no signal"
        : `${fmt(f.totals.nir.frac_in_terr * 100, 0)} % inside the territory`);

    const e = o.enrich_terr;
    const verdict = e == null ? "not measurable"
      : e < 0.5 ? "excluded from the organoid"
      : e < 0.8 ? "weakly excluded"
      : e <= 1.25 ? "close to uniform"
      : e <= 2 ? "enriched" : "strongly enriched";
    $("#q_enrich .val").innerHTML = (e == null ? "—" : fmt(e, 2)) +
      '<span class="u">× uniform</span>';
    $("#q_enrich .sub").textContent = verdict;
  }

  // ---------------------------------------------------------------- figures
  const LAB = D.band_labels;
  /* Clicking a layer does two things at once: isolates it in the reconstruction
     and puts the actual photograph of that layer on screen. A number about a
     layer should be checkable against the pixels it came from without leaving
     the page. */
  function showLayer(z) {
    sliceMode = "one"; cut = z;
    $("#slicemode").value = "one"; $("#cut").value = z;
    applySlice();
    const box = $("#proof");
    const th = D.thumbs;
    if (th && th.z[t] && th.z[t][z]) {
      $("#proofimg").src = th.z[t][z];
      const d = F[t].derived;
      $("#proofcap").innerHTML =
        `<b>Layer ${zpad(z)}</b>, day ${fmt(D.times[t].hours / 24, 2)} — the raw ` +
        "plane with the measured mask outlined in each channel's colour. " +
        `Tumour ${fmt(d.tumour_area_by_z_mm2[z], 4)} mm², T cells ` +
        `${fmt(d.tcell_area_by_z_mm2[z], 4)} mm² (≈ ${fmt(d.tcells_by_z[z], 0)} ` +
        `cells apportioned), dead ${fmt(d.dead_area_by_z_mm2[z], 5)} mm². ` +
        '<a href="check/' + D.well + '.html">Open at full resolution →</a>';
      box.hidden = false;
    }
    $("#scene").scrollIntoView({ behavior: "smooth", block: "center" });
  }
  $("#proofclose").addEventListener("click", () => { $("#proof").hidden = true; });

  function figures(f) {
    svgs.depth = FIG.depth($("#fig_depth"), f, T, CAL, showLayer);
    svgs.bands = FIG.bands($("#fig_bands"), f, T, LAB);
    svgs.zband = FIG.zband($("#fig_zband"), f, T, LAB);
    svgs.time = FIG.timecourse($("#fig_time"), F, D.times, T, t, CAL);
    tables(f);
  }

  function tables(f) {
    const d = f.derived, day = fmt(D.times[t].hours / 24, 2);
    const um2 = CAL.tcell.um2_per_cell;

    $("#tbl_now").replaceChildren(FIG.table({
      caption: `<b>Table 1.</b> Well ${D.well} at day ${day} — measured signal and ` +
        "derived estimates.",
      head: ["Quantity", "Value", "Unit", "Basis"],
      rows: [
        ["Organoid territory (brightfield)", fmt(d.organoid_mm2, 3), "mm²", "measured"],
        ["Tumour signal area", fmt(d.tumour_mm2, 4), "mm²", "measured"],
        ["Tumour signal volume", fmt(d.tumour_vol_um2layer, 0), "µm²·layer", "measured"],
        ["T-cell signal area", fmt(d.tcell_mm2, 4), "mm²", "measured"],
        ["Dead-cell signal area", fmt(d.dead_mm2, 5), "mm²", "measured"],
        ["T-cell fraction inside territory",
         f.totals.orange.frac_in_terr == null ? "—" : fmt(f.totals.orange.frac_in_terr, 4),
         "—", "measured"],
        ["T-cell enrichment in territory",
         f.totals.orange.enrich_terr == null ? "—" : fmt(f.totals.orange.enrich_terr, 3),
         "× uniform", "measured"],
        [{ html: "T cells, whole well" }, { html: "≈ " + fmt(d.tcells, 0) }, "cells",
         { html: `derived: signal area ÷ ${fmt(um2, 1)} µm² per cell` }],
        [{ html: "T cells inside territory" },
         { html: d.tcells_in_terr == null ? "—" : "≈ " + fmt(d.tcells_in_terr, 0) },
         "cells", { html: "derived" }],
        ["Layer areas ÷ projected area",
         d.z_overcount == null ? "—" : fmt(d.z_overcount, 2), "×",
         "measured — the out-of-focus spread factor"],
      ],
      note: "Measured quantities are threshold-above signal areas; the only " +
        "assumption in them is the pixel size (2.798 µm/px, back-calculated from " +
        "the instrument's own field label and not independently verified). " +
        "Derived quantities additionally assume the calibration in the methods " +
        "section and are always marked ≈.",
      file: `${D.well}_t${String(t).padStart(2, "0")}_summary`,
    }));

    const rows = [];
    for (let z = NZ - 1; z >= 0; z--)
      rows.push([zpad(z), fmt(d.tumour_area_by_z_mm2[z], 5),
                 fmt(d.tcell_area_by_z_mm2[z], 5),
                 "≈ " + fmt(d.tcells_by_z[z], 0),
                 fmt(d.dead_area_by_z_mm2[z], 6)]);
    $("#tbl_depth").replaceChildren(FIG.table({
      caption: `<b>Table 2.</b> Signal per z layer, well ${D.well}, day ${day}.`,
      head: ["Layer", "Tumour", "T cells", "T cells", "Dead cells"],
      units: ["ordinal", "mm²", "mm²", "≈ cells", "mm²"],
      rows,
      note: "Layer areas are measured on each plane's own mask and sum to " +
        `${d.z_overcount == null ? "—" : fmt(d.z_overcount, 2)}× the projected ` +
        "area, because the depth of field of a 4× objective (NA ≈ 0.13) is tens " +
        "of microns and one cell appears in several layers. Cell equivalents " +
        "therefore <b>apportion the well total</b> across layers in proportion " +
        "to signal (they sum to the well total); they are not independent " +
        "per-layer counts.",
      file: `${D.well}_t${String(t).padStart(2, "0")}_layers`,
    }));

    $("#tbl_bands").replaceChildren(FIG.table({
      caption: `<b>Table 3.</b> Signal by signed distance to the organoid ` +
        `boundary, well ${D.well}, day ${day}.`,
      head: ["Distance", "Band area", "Tumour", "T cells", "Dead cells", "T cells"],
      units: ["µm", "mm²", "× uniform", "× uniform", "× uniform", "≈ cells"],
      rows: LAB.map((l, i) => [l, fmt(f.band_area_mm2[i], 4),
        f.bands.green.enrich[i] == null ? "—" : fmt(f.bands.green.enrich[i], 3),
        f.bands.orange.enrich[i] == null ? "—" : fmt(f.bands.orange.enrich[i], 3),
        f.bands.nir.enrich[i] == null ? "—" : fmt(f.bands.nir.enrich[i], 3),
        "≈ " + fmt(d.tcells_by_band[i], 0)]),
      note: "Negative distances are inside the brightfield organoid territory. " +
        "Enrichment is band density divided by whole-field density, so 1.0 is " +
        "the value a uniformly scattered population would give. Bands are " +
        "computed on the projected mask, so band areas sum exactly to the " +
        "projected signal area and the cell scale applies directly here.",
      file: `${D.well}_t${String(t).padStart(2, "0")}_distance`,
    }));

    $("#tbl_time").replaceChildren(FIG.table({
      caption: `<b>Table 4.</b> Time course, well ${D.well}.`,
      head: ["Day", "Hours", "Organoid", "Tumour", "T cells", "T cells",
             "Dead cells", "T-cell enrichment"],
      units: ["d", "h", "mm²", "mm²", "mm²", "≈ cells", "mm²", "× uniform"],
      rows: F.map((fr, i) => [fmt(D.times[i].hours / 24, 2), D.times[i].hours,
        fmt(fr.derived.organoid_mm2, 3), fmt(fr.derived.tumour_mm2, 4),
        fmt(fr.derived.tcell_mm2, 4), "≈ " + fmt(fr.derived.tcells, 0),
        fmt(fr.derived.dead_mm2, 5),
        fr.totals.orange.enrich_terr == null ? "—"
          : fmt(fr.totals.orange.enrich_terr, 3)]),
      file: `${D.well}_timecourse`,
    }));
  }

  // --------------------------------------------------------------- controls
  $("#tslider").max = F.length - 1;
  $("#tslider").addEventListener("input", e => setFrame(+e.target.value));
  $("#playt").addEventListener("click", () => {
    if (playT) { clearInterval(playT); playT = null; $("#playt").textContent = "▶"; return; }
    $("#playt").textContent = "❚❚";
    playT = setInterval(() => setFrame(t >= F.length - 1 ? 0 : t + 1), 620);
  });

  for (const chip of document.querySelectorAll(".chip[data-ch]"))
    chip.addEventListener("click", () => {
      const on = chip.getAttribute("aria-pressed") !== "true";
      chip.setAttribute("aria-pressed", on);
      scene.toggle(chip.dataset.ch, on);
    });

  document.addEventListener("keydown", e => {
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    if (e.key === "ArrowRight") { setFrame(t + 1); e.preventDefault(); }
    if (e.key === "ArrowLeft") { setFrame(t - 1); e.preventDefault(); }
  });

  // ----------------------------------------------------------------- export
  for (const b of document.querySelectorAll("[data-svg]"))
    b.addEventListener("click", () => FIG.download(svgs[b.dataset.svg],
      `${D.well}_t${String(t).padStart(2, "0")}_${b.dataset.svg}.svg`));

  $("#png3d").addEventListener("click", () => {
    const a = document.createElement("a");
    a.href = scene.png(3);
    a.download = `${D.well}_t${String(t).padStart(2, "0")}_3D.png`;
    a.click();
  });
  $("#panel3d").addEventListener("click", async () => {
    const { urls, labels } = await scene.panel(2);
    urls.forEach((u, i) => {
      const a = document.createElement("a");
      a.href = u;
      a.download = `${D.well}_t${String(t).padStart(2, "0")}_${labels[i].split(" ")[0]}.png`;
      a.click();
    });
  });

  for (const b of document.querySelectorAll("[data-tbl]"))
    b.addEventListener("click", () => {
      const box = $("#tbl_" + b.dataset.tbl);
      b.textContent = box.classList.toggle("on") ? "hide table" : "table";
    });

  window.addEventListener("blur", FIG.untip);

  /* Screenshot hook. atlas/shoot.py drives the page through the URL fragment so
     that the figures in the README are produced by the real page rather than
     mocked up. Inert unless a #shoot= fragment is present. */
  window.SHOOT = {
    slice(mode, z) {
      sliceMode = mode; cut = z;
      $("#slicemode").value = mode; $("#cut").value = z;
      applySlice(); scene.draw();
    },
    view(az, elev) { scene.az = az; scene.elev = elev; scene.changed(); scene.draw(); },
    time(i) { return setFrame(i); },
  };

  // -------------------------------------------------------------- start-up
  applySlice();
  setFrame(t).then(async () => {
    // Decode the rest in the background so scrubbing time never waits on gzip.
    for (let i = F.length - 1; i >= 0; i--)
      if (!scene.frames.has(i)) {
        await scene.load(i, F[i], F[i].grid);
        await new Promise(r => setTimeout(r, 0));       // keep the page responsive
      }
    runShootHook();
  });

  function runShootHook() {
    const m = /#shoot=(.*)$/.exec(location.hash);
    if (!m) return;
    try { new Function(decodeURIComponent(m[1]))(); scene.draw(); }
    catch (err) { console.error("shoot hook", err); }
  }
})();
