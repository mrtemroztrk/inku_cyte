/* Segmentation check: the photograph and the reconstruction move together.

   One z slider drives both panels. The left panel swaps between the raw plane
   and the same plane with the measured mask outline on top; the right panel
   isolates that single layer in the voxel scene. The point is that a claim about
   a layer can be checked against the pixels it was made from without leaving the
   page. */

(() => {
  const C = window.CHECK, V = window.VOX, T = window.THEME;
  const $ = s => document.querySelector(s);
  const fmt = FIG.fmt, zpad = FIG.zpad;
  let z = 0, playing = null;

  const scene = new SCENE.Scene($("#scene"), {
    vox_um: V.voxel_um, colors: T.scene, terrColor: T.terrScene,
    // In overlay mode the photograph has to follow zoom and pan exactly, or the
    // check stops being a check the moment anyone scrolls.
    onView: v => {
      const o = $("#ovl");
      if (o && !o.hidden)
        o.style.transform =
          `translate(${scene.px}px, ${scene.py}px) scale(${v.zoom})`;
    },
  });
  if (V && V.vox) {
    scene.load(0, { vox: V.vox, terr_map: V.terr_map, terr_shape: V.terr_shape,
                    dome: V.dome }, V.grid).then(rec => { scene.show(rec); paint(); });
  }

  function paint() {
    const outline = $("#outline").checked;
    const bf = $("#showbf").checked;
    const over = $("#overlay").checked;
    const cum = $("#stack").value === "cum";
    const img = $("#shot");
    if (bf) {
      img.src = outline ? C.bf.over : C.bf.raw;
      $("#shotcap").innerHTML =
        "Brightfield — a single plane, no z stack. The outline is the organoid " +
        `territory: <b>${fmt(C.bf.terr_mm2, 3)} mm²</b>, ` +
        `${fmt(C.bf.terr_frac * 100, 0)} % of the field. This mask defines ` +
        "“inside the organoid” for every distance measurement in the atlas.";
    } else {
      img.src = cum && !outline ? C.cum[z] : (outline ? C.over[z] : C.raw[z]);
      const s = C.stats[z];
      $("#shotcap").innerHTML =
        (cum ? `Layers <b>${zpad(0)}–${zpad(z)}</b> of ${C.nz}, maximum projection. `
           + "Above threshold in the topmost plane: "
           : `Layer <b>${zpad(z)}</b> of ${C.nz}. Above threshold in this plane: `) +
        `tumour ${fmt(s.green.mm2, 4)} mm², T cells ${fmt(s.orange.mm2, 4)} mm², ` +
        `dead cells ${fmt(s.nir.mm2, 5)} mm². Scale: 1 displayed pixel = ` +
        `${fmt(C.um_per_px, 2)} µm.`;
    }
    $("#zlabel").textContent = bf ? "brightfield (single plane)"
                                  : `layer ${zpad(z)} of ${C.nz}`;
    $("#z").disabled = bf;
    // "everything below" keeps layers 0..z lit, so the reconstruction shows the
    // same accumulation the photograph does.
    scene.setSlice(bf ? 0 : (cum ? 0 : z), bf ? C.nz - 1 : z, bf ? 0.6 : 0.35);

    /* Overlay mode: the camera is locked straight down and the projection scaled
       so one voxel covers exactly the pixels it came from, then the photograph is
       blended on top. Misregistration would show as dots sitting beside their
       blobs rather than on them. */
    $("#grid").classList.toggle("overlay", over);
    $("#leftfig").hidden = over;
    $("#mixwrap").hidden = !over;
    $("#ovl").hidden = !over;
    $("#scenehint").hidden = over;
    scene.setExact(over);
    if (over) {
      /* Always the raw plane here, never the outlined one: the outline is drawn
         from the same mask as the voxels, so comparing the reconstruction with it
         would be circular. The test is whether the voxels land on the stain. */
      $("#ovl").src = bf ? C.bf.raw : (cum ? C.cum[z] : C.raw[z]);
      $("#ovl").style.opacity = (+$("#mix").value / 100).toFixed(2);
      $("#ovl").style.transform =
        `translate(${scene.px}px, ${scene.py}px) scale(${scene.zoom})`;
      $("#scenecap").innerHTML =
        "<b>Overlay.</b> Straight top-down view, scaled so one voxel covers the " +
        "pixels it was measured from, with the photograph blended on top " +
        `(${$("#mix").value} % photo). The photograph is shown <b>without</b> the ` +
        "mask outline on purpose — the outline comes from the same mask as the " +
        "voxels, so comparing the two would be circular. What is tested is " +
        "whether the voxels land on the stain itself. Sweep the slider: the dots " +
        "should disappear into the bright patches, not slide across them. Only " +
        "XY placement is tested; the z axis carries no micron scale.";
    } else {
      $("#scenecap").innerHTML =
        "The same layer isolated in the voxel reconstruction. Every dot is one " +
        "5.6 µm voxel above threshold — one dot here for a patch that crossed the " +
        "threshold on the left.";
    }
    table();
  }

  function table() {
    const s = C.stats[z];
    const rows = [
      ["Tumour (green)", C.thresholds.green, s.green.px, fmt(s.green.mm2, 5),
       s.green.px ? fmt(s.green.in_terr / s.green.px * 100, 1) : "—"],
      ["T cells (orange)", C.thresholds.orange, s.orange.px, fmt(s.orange.mm2, 5),
       s.orange.px ? fmt(s.orange.in_terr / s.orange.px * 100, 1) : "—"],
      ["Dead cells (NIR)", C.thresholds.nir, s.nir.px, fmt(s.nir.mm2, 6),
       s.nir.px ? fmt(s.nir.in_terr / s.nir.px * 100, 1) : "—"],
    ];
    $("#tbl_plane").replaceChildren(FIG.table({
      caption: `<b>Table.</b> Pixels selected by the threshold in layer ` +
        `${zpad(z)} of well ${C.well}, timepoint t${String(C.t).padStart(2, "0")}.`,
      head: ["Channel", "Threshold", "Pixels", "Area", "Inside organoid"],
      units: ["", "channel units", "count", "mm²", "% of the channel's pixels"],
      rows,
      note: "Thresholds are fixed across the whole plate and are not adapted per " +
        "well; each plane's own median is subtracted first, because the background " +
        "level drifts both between wells and along z. Pixel counts are the raw " +
        "measurement — the area column is the same number multiplied by " +
        `${fmt(C.um_per_px / 2, 3)} µm per pixel squared.`,
      file: `${C.well}_t${String(C.t).padStart(2, "0")}_${zpad(z)}_plane`,
    }));
  }

  $("#z").addEventListener("input", e => { z = +e.target.value; paint(); });
  $("#outline").addEventListener("change", paint);
  $("#showbf").addEventListener("change", paint);
  $("#overlay").addEventListener("change", paint);
  $("#stack").addEventListener("change", paint);
  $("#mix").addEventListener("input", e => {
    $("#mixlabel").textContent = e.target.value + " %";
    paint();
  });
  $("#playz").addEventListener("click", () => {
    if (playing) { clearInterval(playing); playing = null; $("#playz").textContent = "▶";
                   return; }
    $("#playz").textContent = "❚❚";
    playing = setInterval(() => {
      z = z >= C.nz - 1 ? 0 : z + 1;
      $("#z").value = z;
      paint();
    }, 380);
  });
  document.addEventListener("keydown", e => {
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    if (e.key === "ArrowUp" || e.key === "ArrowRight") {
      z = Math.min(C.nz - 1, z + 1); $("#z").value = z; paint(); e.preventDefault();
    }
    if (e.key === "ArrowDown" || e.key === "ArrowLeft") {
      z = Math.max(0, z - 1); $("#z").value = z; paint(); e.preventDefault();
    }
  });
  for (const b of document.querySelectorAll("[data-tbl]"))
    b.addEventListener("click", () => {
      const box = $("#tbl_" + b.dataset.tbl);
      b.textContent = box.classList.toggle("on") ? "hide table" : "table";
    });

  window.SHOOT = {
    z(n) { z = Math.max(0, Math.min(C.nz - 1, n)); $("#z").value = z; paint();
           scene.draw(); },
    outline(on) { $("#outline").checked = !!on; paint(); },
    stack(mode) { $("#stack").value = mode; paint(); scene.draw(); },
    overlay(on, mix) {
      $("#overlay").checked = !!on;
      if (mix != null) { $("#mix").value = mix; $("#mixlabel").textContent = mix + " %"; }
      paint(); scene.draw();
    },
  };
  function runShootHook() {
    const m = /#shoot=(.*)$/.exec(location.hash);
    if (!m) return;
    try { new Function(decodeURIComponent(m[1]))(); scene.draw(); }
    catch (err) { console.error("shoot hook", err); }
  }

  paint();
  setTimeout(runShootHook, 400);
})();
