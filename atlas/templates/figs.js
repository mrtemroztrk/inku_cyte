/* Figures — SVG, drawn from the embedded data, redrawn on the time slider.

   Three rules hold in every figure here.

   One axis per unit. Quantities in different units are never overlaid on a
   shared scale; small multiples are used instead, each panel with its own axis
   and its own unit. A second y-axis would place two scales on one frame and
   make every crossing between the two curves an artefact of the scaling.

   The primary quantity is the measured one. Signal area (mm²) and voxel counts
   are what the images contain; a cell count is a derived estimate and is always
   marked as such, on a second tick row of the same axis (a unit conversion of
   the same data, not a second measure).

   Colour is never the only carrier. Every series is directly labelled, every
   figure has a table view, and the palette was checked for colour-vision
   deficiency (atlas/palette_check.py). */

const FIG = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const INK = "#0b0b0b", INK2 = "#52514e", MUTED = "#8a8983", RULE = "#e6e5e1";

  const el = (tag, at = {}, kids = []) => {
    const e = document.createElementNS(NS, tag);
    for (const k in at) if (at[k] != null) e.setAttribute(k, at[k]);
    for (const c of [].concat(kids)) e.append(c);
    return e;
  };
  const text = (x, y, s, at = {}) => {
    const e = el("text", { x, y, fill: INK2, "font-size": 10.5, ...at });
    e.textContent = s;
    return e;
  };

  /* Readable axis steps: 1, 2, 2.5 or 5 × 10ⁿ. */
  function ticks(lo, hi, want = 5) {
    if (!(hi > lo)) return [lo];
    const raw = (hi - lo) / want;
    const p = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].find(m => m * p >= raw) * p;
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step)
      out.push(+v.toFixed(10));
    return out;
  }

  const fmt = (v, d) => {
    if (v == null || !isFinite(v)) return "—";
    const o = d != null ? { minimumFractionDigits: d, maximumFractionDigits: d } : null;
    if (o) return v.toLocaleString("en-GB", o);
    const a = Math.abs(v);
    const dg = a === 0 ? 0 : a < 0.01 ? 4 : a < 1 ? 3 : a < 10 ? 2 : a < 1000 ? 1 : 0;
    return v.toLocaleString("en-GB", { minimumFractionDigits: dg, maximumFractionDigits: dg });
  };
  const zpad = z => "z" + String(z).padStart(2, "0");

  // ------------------------------------------------------------ hover layer
  let tipEl = null;
  function tip(html, ev) {
    if (!tipEl) { tipEl = document.createElement("div"); tipEl.id = "tip";
                  document.body.append(tipEl); }
    tipEl.innerHTML = html;
    tipEl.style.display = "block";
    const r = tipEl.getBoundingClientRect();
    let x = ev.clientX + 14, y = ev.clientY - 10;
    if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - 14;
    if (y + r.height > innerHeight - 8) y = innerHeight - r.height - 8;
    tipEl.style.left = x + "px"; tipEl.style.top = Math.max(8, y) + "px";
  }
  const untip = () => { if (tipEl) tipEl.style.display = "none"; };
  function hoverable(node, html) {
    node.addEventListener("pointerenter", e => tip(html, e));
    node.addEventListener("pointermove", e => tip(html, e));
    node.addEventListener("pointerleave", untip);
    return node;
  }

  // =========================================================== depth profile
  /* Figure: how much of each population sits in each z layer.

     Bars run left to right, layers bottom to top so the figure reads in the
     same orientation as the 3D scene. The three panels carry different units
     and are therefore not comparable to one another; each is read on its own.
     The T-cell panel carries a second tick row in cell equivalents — the same
     numbers divided by the calibrated area per cell, not a second measurement. */
  function depth(host, d, T, cal, onLayer, zup) {
    const W = 600, H = 276, top = 46, bot = 62, left = 36, gap = 30;
    const pw = (W - left - gap * 2 - 10) / 3, ph = H - top - bot;
    const svg = el("svg", { class: "plot", viewBox: `0 0 ${W} ${H}`, role: "img" });
    const nz = d.by_z.green.length;
    const bh = ph / nz;
    // Row order follows the 3D scene: z00 at the bottom, or on top when the
    // scene is flipped — the figure and the scene must never disagree.
    const row = z => zup ? z : nz - 1 - z;

    for (let i = 0; i < nz; i++) {
      if (i % 4 && i !== nz - 1) continue;
      svg.append(text(left - 7, top + (row(i) + 0.7) * bh + 3, zpad(i),
        { "text-anchor": "end", fill: MUTED, "font-size": 9.5 }));
    }

    // Layer areas are NOT converted with the plate-wide µm²/cell factor: they
    // sum to several times the projected area because out-of-focus spread puts
    // one cell in several layers. The second row apportions the well total
    // across layers instead (factor computed per frame in build.py).
    const panels = [
      { ch: "green", lbl: "Tumour signal", unit: "mm² per layer",
        vals: d.derived.tumour_area_by_z_mm2, dec: 4 },
      { ch: "orange", lbl: "T-cell signal", unit: "mm² per layer",
        vals: d.derived.tcell_area_by_z_mm2, dec: 4,
        second: { unit: "≈ cells (apportioned)",
                  conv: v => v * d.derived.layer_cell_per_mm2, dec: 0 } },
      { ch: "nir", lbl: "Dead-cell signal", unit: "mm² per layer",
        vals: d.derived.dead_area_by_z_mm2, dec: 5 },
    ];

    panels.forEach((p, k) => {
      const x = left + k * (pw + gap);
      const hi = Math.max(...p.vals, 1e-12);
      const tk = ticks(0, hi, 3);
      const xmax = Math.max(tk[tk.length - 1], hi);

      svg.append(text(x, top - 30, p.lbl, { fill: INK, "font-size": 11.5,
        "font-weight": 600 }));
      svg.append(text(x, top - 19, p.unit, { fill: MUTED, "font-size": 10 }));
      if (p.second)
        svg.append(text(x, top - 8, p.second.unit + " (derived)",
          { fill: MUTED, "font-size": 10, "font-style": "italic" }));

      for (const t of tk) {
        const px = x + t / xmax * pw;
        svg.append(el("line", { x1: px, y1: top, x2: px, y2: top + ph, stroke: RULE }));
        svg.append(text(px, top + ph + 12, fmt(t), { "text-anchor": "middle",
          fill: MUTED, "font-size": 9 }));
        if (p.second)
          svg.append(text(px, top + ph + 23, fmt(p.second.conv(t), p.second.dec),
            { "text-anchor": "middle", fill: MUTED, "font-size": 9,
              "font-style": "italic" }));
      }

      for (let z = 0; z < nz; z++) {
        const y = top + row(z) * bh;
        const bw = p.vals[z] / xmax * pw;
        const r = el("rect", { x, y: y + 0.9, height: Math.max(bh - 1.8, 1),
          width: Math.max(bw, p.vals[z] > 0 ? 0.8 : 0), fill: T.colors[p.ch], rx: 1 });
        const extra = p.second
          ? `<br><span class="k">derived</span> ≈ ${fmt(p.second.conv(p.vals[z]), 0)} cells`
          : "";
        hoverable(r, `<b>layer ${zpad(z)}</b><br><span class="k">${p.lbl}</span> ` +
          `${fmt(p.vals[z], p.dec)} mm²${extra}`);
        if (onLayer) { r.style.cursor = "pointer";
                       r.addEventListener("click", () => onLayer(z)); }
        svg.append(r);
      }
      svg.append(el("line", { x1: x, y1: top, x2: x, y2: top + ph, stroke: "#c9c8c3" }));
    });

    svg.append(text(left, H - 6, (zup ? "z00 on top" : "z00 at the bottom") +
      " · layer spacing is not to scale (the z step is not recorded)",
      { fill: MUTED, "font-size": 9.5 }));
    host.replaceChildren(svg);
    return svg;
  }

  // ============================================================ time course
  /* Figure: how each quantity changed over the four days.
     Four quantities, four units, four panels. */
  function timecourse(host, frames, times, T, tcur, cal, onTime) {
    const W = 1200, H = 250, top = 48, bot = 48, left = 16, gap = 36;
    const pw = (W - left - gap * 3 - 24) / 4, ph = H - top - bot;
    const svg = el("svg", { class: "plot", viewBox: `0 0 ${W} ${H}`, role: "img" });
    const days = times.map(t => t.hours / 24);
    const dmax = Math.max(...days);
    const um2 = cal.tcell.um2_per_cell;

    const series = [
      { lbl: "Organoid mass", unit: "mm² (brightfield)", col: "#7d7c77",
        get: f => f.derived.organoid_mm2, dec: 2 },
      { lbl: "Tumour signal", unit: "mm²", col: T.colors.green,
        get: f => f.derived.tumour_mm2, dec: 3 },
      { lbl: "T-cell signal", unit: "mm²", col: T.colors.orange,
        get: f => f.derived.tcell_mm2, dec: 3,
        second: { unit: "≈ cells", conv: v => v * 1e6 / um2 } },
      { lbl: "Dead-cell signal", unit: "mm²", col: T.colors.nir,
        get: f => f.derived.dead_mm2, dec: 4 },
    ];

    series.forEach((s, k) => {
      const x0 = left + k * (pw + gap);
      const vals = frames.map(s.get);
      const hi = Math.max(...vals, 1e-9);
      const tk = ticks(0, hi, 3);
      const ymax = Math.max(tk[tk.length - 1], hi);
      const X = dd => x0 + dd / dmax * pw;
      const Y = v => top + ph - v / ymax * ph;

      svg.append(text(x0, top - 30, s.lbl, { fill: INK, "font-size": 11.5,
        "font-weight": 600 }));
      svg.append(text(x0, top - 19, s.unit, { fill: MUTED, "font-size": 10 }));
      if (s.second)
        svg.append(text(x0, top - 8, `top = ≈ ${fmt(s.second.conv(ymax), 0)} cells`,
          { fill: MUTED, "font-size": 10, "font-style": "italic" }));

      for (const t of tk) {
        svg.append(el("line", { x1: x0, y1: Y(t), x2: x0 + pw, y2: Y(t), stroke: RULE }));
        svg.append(text(x0 + pw, Y(t) - 2.5, fmt(t), { "text-anchor": "end", fill: MUTED,
          "font-size": 9 }));
      }
      svg.append(el("polyline", { points: vals.map((v, i) => X(days[i]) + "," + Y(v)).join(" "),
        fill: "none", stroke: s.col, "stroke-width": 2, "stroke-linejoin": "round" }));
      vals.forEach((v, i) => {
        const extra = s.second ? `<br><span class="k">derived</span> ≈ ` +
          `${fmt(s.second.conv(v), 0)} cells` : "";
        const mk = hoverable(el("circle", { cx: X(days[i]), cy: Y(v),
          r: i === tcur ? 4.6 : 2.6, fill: i === tcur ? s.col : "#fcfcfb", stroke: s.col,
          "stroke-width": i === tcur ? 1.8 : 1.4 }),
          `<b>${s.lbl}</b><br><span class="k">day</span> ${fmt(days[i], 2)}` +
          `<br><span class="k">value</span> ${fmt(v, s.dec)} ${s.unit.split(" ")[0]}` +
          extra + (onTime ? "<br><span class=\"k\">click to see the images</span>" : ""));
        if (onTime) { mk.style.cursor = "pointer";
                      mk.addEventListener("click", () => onTime(i)); }
        svg.append(mk);
      });
      svg.append(el("line", { x1: x0, y1: top + ph, x2: x0 + pw, y2: top + ph,
        stroke: "#c9c8c3" }));
      svg.append(text(x0, top + ph + 14, "0", { fill: MUTED, "font-size": 9.5 }));
      svg.append(text(x0 + pw, top + ph + 14, Math.round(dmax) + " d",
        { "text-anchor": "end", fill: MUTED, "font-size": 9.5 }));
    });
    svg.append(text(W / 2, H - 6, "days after seeding", { "text-anchor": "middle",
      fill: MUTED, "font-size": 10 }));
    host.replaceChildren(svg);
    return svg;
  }

  // ---------------------------------------------------------------- export
  function download(svg, name) {
    const c = svg.cloneNode(true);
    c.setAttribute("xmlns", NS);
    c.setAttribute("style", "background:#fcfcfb");
    const blob = new Blob(['<?xml version="1.0" encoding="UTF-8"?>\n',
      new XMLSerializer().serializeToString(c)], { type: "image/svg+xml" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name;
    a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  function downloadCSV(head, rows, name) {
    const q = v => /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : v;
    const csv = [head, ...rows].map(r => r.map(q).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  /* A "?" button that opens the definition of a quantity: its formula, how it is
     computed, and what it does not measure. A table that shows a number without
     showing where it came from is asking to be trusted; in a scientific context
     that is not enough. Definitions live in atlas/defs.py, one source for all
     pages. */
  function explain(key) {
    const d = (window.DEFS || {})[key];
    if (!d) return;
    const dlg = document.getElementById("explain");
    dlg.querySelector(".exbody").innerHTML =
      `<h3>${d.title}</h3>` +
      `<p class="exform"><code>${d.formula}</code></p>` +
      "<ol>" + d.steps.map(x => `<li>${x}</li>`).join("") + "</ol>" +
      (d.caveat ? `<p class="excav">${d.caveat}</p>` : "");
    dlg.showModal();
  }

  function qmark(key) {
    if (!(window.DEFS || {})[key]) return "";
    const b = document.createElement("button");
    b.className = "qmark";
    b.type = "button";
    b.textContent = "?";
    b.title = "how this is computed";
    b.addEventListener("click", () => explain(key));
    return b;
  }

  /* Journal-style table: a caption above, a units row under the header, a
     footnote below. Numeric columns are right-aligned and tabular. A row whose
     first cell carries {def:"key"} gets a "?" next to it. */
  function table(spec) {
    const wrap = document.createElement("div");
    const t = document.createElement("table");
    t.className = "data";
    if (spec.caption) {
      const cap = document.createElement("caption");
      cap.innerHTML = spec.caption;
      t.append(cap);
    }
    const thead = document.createElement("thead");
    thead.append(rowOf(spec.head, "th"));
    if (spec.units) {
      const u = rowOf(spec.units, "th");
      u.className = "units";
      thead.append(u);
    }
    const tb = document.createElement("tbody");
    for (const r of spec.rows) tb.append(rowOf(r, "td"));
    t.append(thead, tb);
    wrap.append(t);
    if (spec.note) {
      const n = document.createElement("p");
      n.className = "tnote";
      n.innerHTML = spec.note;
      wrap.append(n);
    }
    if (spec.csv !== false) {
      const b = document.createElement("button");
      b.className = "csv";
      b.textContent = "download CSV";
      b.addEventListener("click", () => downloadCSV(spec.head, spec.rows,
        (spec.file || "table") + ".csv"));
      wrap.append(b);
    }
    return wrap;
  }
  function rowOf(cells, tag) {
    const tr = document.createElement("tr");
    for (const c of cells) {
      const e = document.createElement(tag);
      if (c && typeof c === "object") {
        e.innerHTML = c.html != null ? c.html : "";
        if (c.cls) e.className = c.cls;
        if (c.def) { const b = qmark(c.def); if (b) e.append(" ", b); }
      } else e.textContent = c;
      tr.append(e);
    }
    return tr;
  }

  return { depth, timecourse, download, downloadCSV, table, fmt, ticks,
           untip, hoverable, el, text, zpad, explain, qmark,
           INK, INK2, MUTED, RULE };
})();
