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
      ? (m === "one" ? zpad(cut)
         : m === "up" ? `${zpad(0)}–${zpad(cut)}`
         : `${zpad(cut)}–${zpad(NZ - 1)}`)
      : `all ${NZ}`;
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

  $("#cloud").addEventListener("change", e => scene.setCloud(e.target.value));

  // z00 on top: the ordinal axis drawn the other way up, for stacks whose first
  // plane is the apex of the dome. Remembered across pages (same key as the
  // segmentation check), so it is chosen once, not per well.
  const ZUP_KEY = "atlas.zup";
  $("#zup").checked = localStorage.getItem(ZUP_KEY) === "1";
  scene.setZUp($("#zup").checked);
  $("#zup").addEventListener("change", e => {
    localStorage.setItem(ZUP_KEY, e.target.checked ? "1" : "0");
    scene.setZUp(e.target.checked);
    figures(F[t]);                                    // Figure 1 follows the scene
  });
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
    if (t === j && rec) { scene.show(rec); scene.setCloud($("#cloud").value); }
  }

  // ---------------------------------------------------------------- readout
  function readout(f) {
    const d = f.derived;
    const set = (id, val, unit, sub) => {
      $(`#q_${id} .val`).innerHTML = val + (unit ? `<span class="u">${unit}</span>` : "");
      $(`#q_${id} .sub`).innerHTML = sub || "";
    };
    set("organoid", fmt(d.organoid_mm2, 2), "mm²",
      `${fmt(f.bf.terr_frac * 100, 0)} % of the imaged field`);
    // Where along z the signal sits: its brightest layer and the narrowest run
    // of layers holding half of it. Layer indices, not microns.
    const where = k => d[`${k}_peak_z`] == null ? "no signal"
      : `peak ${zpad(d[`${k}_peak_z`])} · half of it in ` +
        (d[`${k}_half_z`][0] === d[`${k}_half_z`][1] ? zpad(d[`${k}_half_z`][0])
         : `${zpad(d[`${k}_half_z`][0])}–${zpad(d[`${k}_half_z`][1])}`);
    set("tumour", fmt(d.tumour_mm2, 3), "mm²",
      `volume ${fmt(d.tumour_vol_um2layer / 1e6, 2)} ×10⁶ µm²·layer · ${where("tumour")}`);
    set("tcell", fmt(d.tcell_mm2, 3), "mm²",
      `derived: <b>≈ ${fmt(d.tcells, 0)} cells</b> · ${where("tcell")}`);
    set("dead", fmt(d.dead_mm2, 4), "mm²", where("dead"));
  }

  // ---------------------------------------------------------------- figures
  /* Clicking a layer does two things at once: isolates it in the reconstruction
     and puts the actual photograph of that layer on screen. A number about a
     layer should be checkable against the pixels it came from without leaving
     the page. */
  /* The proof panel. Clicking a depth bar or a point on the time course opens
     the photograph the number was measured from, at that timepoint, with its own
     layer slider — the claim and the pixels behind it on the same screen. */
  let proofT = null;
  function showProof(ti, z, moveScene) {
    const th = D.thumbs;
    if (!th || !th.z[ti]) return;
    proofT = ti;
    const nz = th.z[ti].length;
    $("#proofz").max = nz - 1;
    $("#proofz").value = z;
    $("#proofimg").src = th.z[ti][z];
    $("#proofzlab").textContent = zpad(z);
    const d = F[ti].derived;
    $("#proofcap").innerHTML =
      `<b>Layer ${zpad(z)}</b> · day ${fmt(D.times[ti].hours / 24, 2)} — the raw ` +
      "plane with the measured mask outlined in each channel's colour. " +
      `Tumour ${fmt(d.tumour_area_by_z_mm2[z], 4)} mm², T cells ` +
      `${fmt(d.tcell_area_by_z_mm2[z], 4)} mm², dead ` +
      `${fmt(d.dead_area_by_z_mm2[z], 5)} mm². ` +
      '<a href="check/' + D.well + '.html">full resolution, channel by channel →</a>';
    $("#proof").hidden = false;
    if (moveScene) {
      sliceMode = "one"; cut = z;
      $("#slicemode").value = "one"; $("#cut").value = z;
      applySlice();
      $("#scene").scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }
  function showLayer(z) { showProof(t, z, true); }
  $("#proofz").addEventListener("input", e => {
    if (proofT != null) showProof(proofT, +e.target.value, false);
  });
  $("#proofclose").addEventListener("click", () => { $("#proof").hidden = true; });

  function figures(f) {
    svgs.depth = FIG.depth($("#fig_depth"), f, T, CAL, showLayer, $("#zup").checked);
    svgs.time = FIG.timecourse($("#fig_time"), F, D.times, T, t, CAL,
      ti => { showProof(ti, Math.min(8, (D.thumbs ? D.thumbs.z[ti].length : 9) - 1), false);
              $("#proof").scrollIntoView({ behavior: "smooth", block: "center" }); });
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
        [{ html: "Organoid territory (brightfield)", def: "organoid" },
         fmt(d.organoid_mm2, 3), "mm²", "measured"],
        [{ html: "Tumour signal area", def: "signal_area" },
         fmt(d.tumour_mm2, 4), "mm²", "measured"],
        [{ html: "Tumour signal volume", def: "volume" },
         fmt(d.tumour_vol_um2layer, 0), "µm²·layer", "measured"],
        [{ html: "T-cell signal area", def: "signal_area" },
         fmt(d.tcell_mm2, 4), "mm²", "measured"],
        [{ html: "Dead-cell signal area", def: "signal_area" },
         fmt(d.dead_mm2, 5), "mm²", "measured"],
        [{ html: "T cells, whole well", def: "tcells" },
         { html: "≈ " + fmt(d.tcells, 0) }, "cells",
         { html: `derived: signal area ÷ ${fmt(um2, 1)} µm² per cell` }],
        [{ html: "T-cell signal, brightest layer", def: "zorder" },
         d.tcell_peak_z == null ? "—" : zpad(d.tcell_peak_z), "layer", "measured"],
        [{ html: "Tumour signal, brightest layer", def: "zorder" },
         d.tumour_peak_z == null ? "—" : zpad(d.tumour_peak_z), "layer", "measured"],
        [{ html: "Tumour cells", def: "tumour_no_cells" },
         { html: "not derivable" }, "—",
         { html: "the calibration was computed and rejected" }],
        [{ html: "Layer areas ÷ projected area", def: "overcount" },
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
      head: [{ html: "Layer", def: "zorder" }, "Tumour",
             "T cells", { html: "T cells", def: "layer_cells" }, "Dead cells"],
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

    $("#tbl_time").replaceChildren(FIG.table({
      caption: `<b>Table 3.</b> Time course, well ${D.well}.`,
      head: ["Day", "Hours", { html: "Organoid", def: "organoid" }, "Tumour",
             "T cells", "T cells", "Dead cells",
             { html: "T-cell peak layer", def: "zorder" }],
      units: ["d", "h", "mm²", "mm²", "mm²", "≈ cells", "mm²", "layer"],
      rows: F.map((fr, i) => [fmt(D.times[i].hours / 24, 2), D.times[i].hours,
        fmt(fr.derived.organoid_mm2, 3), fmt(fr.derived.tumour_mm2, 4),
        fmt(fr.derived.tcell_mm2, 4), "≈ " + fmt(fr.derived.tcells, 0),
        fmt(fr.derived.dead_mm2, 5),
        fr.derived.tcell_peak_z == null ? "—" : zpad(fr.derived.tcell_peak_z)]),
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
    view(a, b) {
      // Hem ön ayar adı hem (azimut, yükseklik) çifti kabul eder.
      if (typeof a === "string") scene.view(a);
      else { scene.az = a; scene.elev = b; scene.changed(); }
      scene.draw();
    },
    time(i) { return setFrame(i); },
    channel(name, on) {
      const c = document.querySelector(`.chip[data-ch="${name}"]`);
      if (c) { c.setAttribute("aria-pressed", !!on); scene.toggle(name, !!on); }
      scene.draw();
    },
    clickLayer(z) { showLayer(z); scene.draw(); },
    cloud(kind) { $("#cloud").value = kind; scene.setCloud(kind); scene.draw(); },
    zup(v) { $("#zup").checked = !!v; scene.setZUp(!!v); figures(F[t]); scene.draw(); },
    scroll(y) { window.scrollTo(0, y); },
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
