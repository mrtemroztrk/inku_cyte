/* Segmentation check: the photograph and the reconstruction, side by side or
   superimposed, driven by one z slider.

   Channels are stored as separate greyscale layers and composed here rather than
   baked into one picture, so any subset can be shown — "only the green channel"
   is a different question from "everything at once", and both get asked. The same
   selection drives the 3D scene, so the two sides always show the same thing.

   The reconstruction on this page is drawn at full measurement resolution, not
   the binned resolution used on the well pages: this page exists to compare
   voxels against pixels, and a binned voxel would claim a thickness the
   measurement does not have.

   Only raw planes are embedded. The projections ("z00 → this layer", "this layer
   → z16", "all layers") are built here from those planes with the canvas
   "lighten" operator, which is a per-channel maximum — the definition of a
   maximum-intensity projection — so the photograph and the lit layers in 3D are
   always the same accumulation of the same planes. */

(() => {
  const C = window.CHECK, T = window.THEME;
  const $ = s => document.querySelector(s);
  const fmt = FIG.fmt, zpad = FIG.zpad;
  const CHS = ["green", "orange", "nir"];
  let z = 0, playing = null;
  const on = { green: true, orange: true, nir: true };

  // ------------------------------------------------------------------- 3D
  /* Two scenes, one camera. `scene` holds the reconstruction; `photo` is an
     empty copy of the same field with the photograph hung in it as a plane.
     While linked, whichever the hand moves, the other is set to the same camera
     — so the two panels tilt, pan and zoom as twins. */
  const linked = () => $("#link").checked;
  let mirroring = false;
  function mirror(from, to) {
    if (mirroring || !linked()) return;
    mirroring = true;
    to.setCamera(from.camera());
    to.draw();
    mirroring = false;
  }
  const sceneOpts = {
    vox_um: C.voxel_um, colors: C.colors, terrColor: T.terrScene, boost: 0.75,
    // At zoom 1 the field's width fills the box in both panels.
    fit: "width",
  };
  const scene = new SCENE.Scene($("#scene"), { ...sceneOpts,
    onView: v => {
      const l = $("#viewlabel");
      if (l) l.textContent =
        `az ${Math.round(((v.az % 360) + 360) % 360)}° · el ${Math.round(v.elev)}°`;
      zoomLabel(v.zoom);
      mirror(scene, photo);
    },
  });
  const photo = new SCENE.Scene($("#photo3d"), { ...sceneOpts,
    onView: v => { zoomLabel(v.zoom); mirror(photo, scene); },
  });
  photo.blank(C.grid);
  // Start looking straight down: the photograph then reads as a photograph, and
  // any orbit from there is the reader's own choice. "reset view" returns here.
  scene.home = photo.home = { az: 0, elev: 90, zoom: 1, px: 0, py: 0 };
  scene.view("home"); photo.view("home");
  scene.load(0, { vox: C.vox, vox_focus: C.vox_focus, dome: null }, C.grid)
       .then(rec => { scene.show(rec); scene.setCloud($("#cloud").value); paint(); });
  function zoomLabel(z) {
    $("#zoomlab").textContent = Math.abs(z - 1) > 0.02
      ? `${FIG.fmt(z, 1)}×${linked() ? " · both panels" : ""}` : "";
  }

  // z00 on top is remembered across pages: whoever knows their stack starts at
  // the apex of the dome should not have to say so on every well.
  const ZUP_KEY = "atlas.zup";
  $("#zup").checked = localStorage.getItem(ZUP_KEY) === "1";
  scene.setZUp($("#zup").checked);
  photo.setZUp($("#zup").checked);
  $("#zup").addEventListener("change", e => {
    localStorage.setItem(ZUP_KEY, e.target.checked ? "1" : "0");
    scene.setZUp(e.target.checked); photo.setZUp(e.target.checked);
    scene.draw(); photo.draw();
  });

  // ------------------------------------------------------- channel switches
  const chips = $("#chchips");
  for (const ch of CHS) {
    const b = document.createElement("button");
    b.className = "chip";
    b.dataset.ch = ch;
    b.setAttribute("aria-pressed", "true");
    b.innerHTML = `<span class="sw" style="background:${C.colors[ch]}"></span>` +
                  C.labels[ch];
    b.addEventListener("click", () => {
      on[ch] = b.getAttribute("aria-pressed") !== "true";
      b.setAttribute("aria-pressed", on[ch]);
      scene.toggle(ch, on[ch]);
      paint();
    });
    chips.append(b);
  }

  // -------------------------------------------------------- photo compositor
  /* Each enabled channel is tinted with its own colour and added, the way the
     light itself adds. The outline layer goes on top at full strength, so a mask
     boundary is never mistaken for signal. */
  const cv = $("#shot"), cx = cv.getContext("2d");
  const cache = new Map();
  const img = src => {
    let im = cache.get(src);
    if (!im) { im = new Image(); im.src = src; cache.set(src, im); }
    return im;
  };
  const hex = h => [0, 1, 2].map(k => parseInt(h.substr(1 + k * 2, 2), 16));

  /* Which planes the current layer mode covers: [lo, hi] inclusive. */
  function zRange() {
    const m = $("#stack").value;
    return m === "all" ? [0, C.nz - 1] : m === "up" ? [0, z]
         : m === "down" ? [z, C.nz - 1] : [z, z];
  }

  function compose() {
    const bf = $("#showbf").checked;
    const outline = $("#outline").checked;
    const mode = $("#stack").value;
    const [lo, hi] = zRange();
    const [h, w] = C.shape;
    if (cv.width !== w) { cv.width = w; cv.height = h; }

    // Each entry: a list of greyscale sources to max-project, one tint.
    const layers = [];
    if (bf) {
      layers.push({ srcs: [C.bf.raw], rgb: [255, 255, 255], outline: false });
      if (outline) layers.push({ srcs: [C.bf.outline], rgb: [107, 199, 255],
                                 outline: true });
    } else {
      for (const ch of CHS)
        if (on[ch]) layers.push({ srcs: C.raw[ch].slice(lo, hi + 1),
                                  rgb: hex(C.colors[ch]), outline: false });
      // The outline is the mask of the slider's own layer; in "all" no layer
      // is current, so no outline is drawn.
      if (outline && mode !== "all") for (const ch of CHS)
        if (on[ch]) layers.push({ srcs: [C.outline[ch][z]], rgb: hex(C.colors[ch]),
                                  outline: true });
      // What a more sensitive threshold would add: paler, so it reads as "not
      // counted" next to the measured outline.
      if ($("#outlo").checked && mode !== "all") for (const ch of CHS)
        if (on[ch]) layers.push({ srcs: [C.outline_lo[ch][z]],
                                  rgb: hex(C.colors[ch]).map(v => Math.round(140 + v * 0.45)),
                                  outline: true });
    }

    const waiting = layers.flatMap(l => l.srcs.map(img)).filter(im => !im.complete);
    if (waiting.length) {
      Promise.all(waiting.map(im => im.decode().catch(() => {})))
        .then(() => afterCompose(compose()));
      return null;
    }

    cx.globalCompositeOperation = "source-over";
    cx.fillStyle = "#000";
    cx.fillRect(0, 0, w, h);
    const tmp = document.createElement("canvas");
    tmp.width = w; tmp.height = h;
    const tc = tmp.getContext("2d");
    for (const l of layers) {
      tc.globalCompositeOperation = "source-over";
      tc.clearRect(0, 0, w, h);
      // maximum projection of the planes in range: per-channel max = "lighten"
      l.srcs.forEach((src, i) => {
        tc.globalCompositeOperation = i ? "lighten" : "source-over";
        tc.drawImage(img(src), 0, 0, w, h);
      });
      if (l.outline) {
        // outline PNGs carry alpha; tint through the alpha, keep it
        tc.globalCompositeOperation = "source-in";
        tc.fillStyle = `rgb(${l.rgb[0]},${l.rgb[1]},${l.rgb[2]})`;
        tc.fillRect(0, 0, w, h);
      } else {
        tc.globalCompositeOperation = "multiply";       // keep intensity, set hue
        tc.fillStyle = `rgb(${l.rgb[0]},${l.rgb[1]},${l.rgb[2]})`;
        tc.fillRect(0, 0, w, h);
      }
      cx.globalCompositeOperation = l.outline ? "source-over" : "lighter";
      cx.drawImage(tmp, 0, 0);
    }
    cx.globalCompositeOperation = "source-over";
    return cv;
  }

  // ------------------------------------------------------------------ paint
  function paint() {
    const bf = $("#showbf").checked;
    const mode = $("#stack").value;
    const over = $("#overlay").checked;
    const [lo, hi] = zRange();

    $("#z").disabled = bf || mode === "all";
    $("#playz").disabled = bf || mode === "all";
    $("#zlabel").textContent = bf ? "brightfield (single plane)"
      : mode === "all" ? `all ${C.nz} layers`
      : mode === "one" ? `layer ${zpad(z)} of ${C.nz}`
      : `layers ${zpad(lo)}–${zpad(hi)} of ${C.nz}`;
    // The lit layers are exactly the projected planes on the left.
    scene.setSlice(bf ? 0 : lo, bf ? C.nz - 1 : hi, (bf || mode !== "one") ? 0.6 : 0.35);

    $("#grid").classList.toggle("overlay", over);
    $("#leftfig").hidden = over;
    $("#mixwrap").hidden = !over;

    const url = compose();
    afterCompose(url);
    table();
  }

  function afterCompose(url) {
    const over = $("#overlay").checked;
    const bf = $("#showbf").checked;
    const mode = $("#stack").value;
    const planeZ = (bf || mode === "all") ? (C.nz - 1) / 2 : z;
    if (url) photo.setPlaneSource(url, planeZ, 1.0);
    photo.draw();
    if (over) {
      if (url) scene.setPlaneSource(url, planeZ, +$("#mix").value / 100);
      scene.draw();
      $("#scenecap").innerHTML =
        "<b>Overlay.</b> The photograph sits inside the scene as a plane at the z " +
        "height of its own layer, so the camera is free — rotate to check that the " +
        "voxels stand on the stain rather than beside or above it. Only the " +
        "channels selected above are drawn, on both sides.";
    } else {
      scene.setPlane(null);
      $("#scenecap").innerHTML =
        "The same layer in the reconstruction, at full measurement resolution — " +
        "one dot per pixel above threshold, not a binned approximation.";
    }

    const [lo, hi] = zRange();
    const s = C.stats[z];
    const sel = CHS.filter(c => on[c]);
    $("#shotcap").innerHTML = bf
      ? "Brightfield — a single plane, no z stack. The outline is the organoid " +
        `territory: <b>${fmt(C.bf.terr_mm2, 3)} mm²</b>, ` +
        `${fmt(C.bf.terr_frac * 100, 0)} % of the imaged field.`
      : (mode === "one" ? `Layer <b>${zpad(z)}</b> of ${C.nz}. `
         : `Layers <b>${zpad(lo)}–${zpad(hi)}</b>, maximum projection` +
           (mode === "all" ? " of the whole stack. " : `; outline of layer ${zpad(z)}. `)) +
        (mode === "all" ? "" : sel.length
          ? `Above threshold in layer ${zpad(z)}: ` +
            sel.map(c => `${C.labels[c]} ${fmt(s[c].mm2, 4)} mm²`).join(", ") + ". "
          : "No channel selected. ") +
        `One displayed pixel = ${fmt(C.um_per_px, 2)} µm.`;
  }

  function table() {
    const s = C.stats[z];
    $("#tbl_plane").replaceChildren(FIG.table({
      caption: `<b>Table.</b> Pixels selected by the threshold in layer ` +
        `${zpad(z)} of well ${C.well}, timepoint t${String(C.t).padStart(2, "0")}.`,
      head: ["Channel", "Threshold", "Min object", "Pixels", "Area",
             "Pixels at the sensitive threshold"],
      units: ["", "channel units", "px", "count", "mm²",
              "count (not used in any number)"],
      rows: CHS.map(c => [C.labels[c], C.thresholds[c], C.min_obj_px[c], s[c].px,
        fmt(s[c].mm2, 5),
        s[c].px_lo == null ? "—" : `${s[c].px_lo} (threshold ${C.thresholds_lo[c]})`]),
      note: "Thresholds are fixed across the whole plate and are not adapted per " +
        "well; each plane's own median is subtracted first, because the background " +
        "level drifts both between wells and along z. Connected components smaller " +
        "than the minimum are discarded — at this pixel size a real cell covers " +
        "several pixels, so the filter removes single-pixel noise without touching " +
        "objects.",
      file: `${C.well}_t${String(C.t).padStart(2, "0")}_${zpad(z)}_plane`,
    }));
  }

  // --------------------------------------------------------------- controls
  $("#z").addEventListener("input", e => { z = +e.target.value; paint(); });
  for (const id of ["outline", "outlo", "showbf", "overlay"])
    $("#" + id).addEventListener("change", paint);
  $("#stack").addEventListener("change", paint);
  $("#cloud").addEventListener("change", e => {
    scene.setCloud(e.target.value); paint();
  });
  $("#mix").addEventListener("input", e => {
    $("#mixlabel").textContent = e.target.value + " %";
    paint();
  });
  for (const b of document.querySelectorAll("#camseg [data-view]"))
    b.addEventListener("click", () => {
      scene.view(b.dataset.view);           // mirrors to the photograph if linked
      if (!linked()) photo.view(b.dataset.view);
    });
  $("#playz").addEventListener("click", () => {
    if (playing) { clearInterval(playing); playing = null;
                   $("#playz").textContent = "▶"; return; }
    $("#playz").textContent = "❚❚";
    playing = setInterval(() => {
      z = z >= C.nz - 1 ? 0 : z + 1;
      $("#z").value = z;
      paint();
    }, 420);
  });
  document.addEventListener("keydown", e => {
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    const d = (e.key === "ArrowUp" || e.key === "ArrowRight") ? 1
            : (e.key === "ArrowDown" || e.key === "ArrowLeft") ? -1 : 0;
    if (d) { z = Math.max(0, Math.min(C.nz - 1, z + d)); $("#z").value = z;
             paint(); e.preventDefault(); }
  });
  for (const b of document.querySelectorAll("[data-tbl]"))
    b.addEventListener("click", () => {
      const box = $("#tbl_" + b.dataset.tbl);
      b.textContent = box.classList.toggle("on") ? "hide table" : "table";
    });

  /* Linking is a checkbox; when it goes on, the photograph snaps to the
     reconstruction's camera so the two are twins from that moment. */
  $("#link").addEventListener("change", () => {
    if (linked()) { photo.setCamera(scene.camera()); photo.draw(); }
    zoomLabel(scene.zoom);
  });

  $("#zoomreset").addEventListener("click", () => {
    scene.view("home");                    // mirrors to the photograph if linked
    if (!linked()) photo.view("home");
  });

  // The z bar: wheel over it steps one layer at a time, so a hand on the mouse
  // can walk through the stack without aiming at a thumb.
  $("#zbar").addEventListener("wheel", e => {
    e.preventDefault();
    if ($("#z").disabled) return;
    const d = e.deltaY > 0 || e.deltaX > 0 ? 1 : -1;
    z = Math.max(0, Math.min(C.nz - 1, z + d));
    $("#z").value = z; paint();
  }, { passive: false });

  // ------------------------------------------------------------- shoot hook
  window.SHOOT = {
    z(n) { z = Math.max(0, Math.min(C.nz - 1, n)); $("#z").value = z; paint();
           scene.draw(); },
    outline(v) { $("#outline").checked = !!v; paint(); },
    outlo(v) { $("#outlo").checked = !!v; paint(); },
    stack(m) { $("#stack").value = m; paint(); scene.draw(); },
    link(v) { $("#link").checked = !!v; if (v) { photo.setCamera(scene.camera()); photo.draw(); } },
    zup(v) { $("#zup").checked = !!v; scene.setZUp(!!v); photo.setZUp(!!v);
             scene.draw(); photo.draw(); },
    pan(cx, cy) { scene.focusOn(cx, cy); scene.draw(); },
    channel(ch, v) {
      const b = document.querySelector(`#chchips .chip[data-ch="${ch}"]`);
      if (b) { on[ch] = !!v; b.setAttribute("aria-pressed", !!v);
               scene.toggle(ch, !!v); }
      paint(); scene.draw();
    },
    overlay(v, mix) {
      $("#overlay").checked = !!v;
      if (mix != null) { $("#mix").value = mix;
                         $("#mixlabel").textContent = mix + " %"; }
      paint(); scene.draw();
    },
    view(a, b) {
      if (typeof a === "string") scene.view(a);
      else { scene.az = a; scene.elev = b; scene.changed("orbit"); }
      scene.draw();
    },
    cloud(kind) { $("#cloud").value = kind; scene.setCloud(kind); paint();
                  scene.draw(); },
    zoom(f, cx, cy) { scene.focusOn(cx || 0, cy || 0, f); scene.draw(); },
  };
  paint();

  // Decode every raw plane in the background, so stepping through the stack
  // (or asking for a projection of all of it) never waits on a decode.
  const ready = Promise.all(CHS.flatMap(ch => C.raw[ch].map(
    src => img(src).decode().catch(() => {}))));

  // Screenshot hook (atlas/shoot.py) — runs once every plane is decoded, so a
  // headless capture never shows a half-built projection.
  (() => {
    const m = /#shoot=(.*)$/.exec(location.hash);
    if (!m) return;
    ready.then(() => { try { new Function(decodeURIComponent(m[1]))(); }
                       catch (e) { console.error("shoot", e); } });
  })();
})();
