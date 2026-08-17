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
  });
  if (V && V.vox) {
    scene.load(0, { vox: V.vox, terr_map: V.terr_map, terr_shape: V.terr_shape,
                    dome: V.dome }, V.grid).then(rec => { scene.show(rec); paint(); });
  }

  function paint() {
    const outline = $("#outline").checked;
    const bf = $("#showbf").checked;
    const img = $("#shot");
    if (bf) {
      img.src = outline ? C.bf.over : C.bf.raw;
      $("#shotcap").innerHTML =
        "Brightfield — a single plane, no z stack. The outline is the organoid " +
        `territory: <b>${fmt(C.bf.terr_mm2, 3)} mm²</b>, ` +
        `${fmt(C.bf.terr_frac * 100, 0)} % of the field. This mask defines ` +
        "“inside the organoid” for every distance measurement in the atlas.";
    } else {
      img.src = outline ? C.over[z] : C.raw[z];
      const s = C.stats[z];
      $("#shotcap").innerHTML =
        `Layer <b>${zpad(z)}</b> of ${C.nz}. Above threshold in this plane: ` +
        `tumour ${fmt(s.green.mm2, 4)} mm², T cells ${fmt(s.orange.mm2, 4)} mm², ` +
        `dead cells ${fmt(s.nir.mm2, 5)} mm². Scale: 1 displayed pixel = ` +
        `${fmt(C.um_per_px, 2)} µm.`;
    }
    $("#zlabel").textContent = bf ? "brightfield (single plane)"
                                  : `layer ${zpad(z)} of ${C.nz}`;
    $("#z").disabled = bf;
    scene.setSlice(bf ? 0 : z, bf ? C.nz - 1 : z, bf ? 0.6 : 0.35);
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

  paint();
})();
