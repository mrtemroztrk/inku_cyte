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
  function depth(host, d, T, cal, onLayer) {
    const W = 600, H = 268, top = 46, bot = 52, left = 36, gap = 30;
    const pw = (W - left - gap * 2 - 10) / 3, ph = H - top - bot;
    const svg = el("svg", { class: "plot", viewBox: `0 0 ${W} ${H}`, role: "img" });
    const nz = d.by_z.green.length;
    const bh = ph / nz;

    for (let i = 0; i < nz; i++) {
      if (i % 4 && i !== nz - 1) continue;
      svg.append(text(left - 7, top + (nz - 1 - i + 0.7) * bh + 3, zpad(i),
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
        const y = top + (nz - 1 - z) * bh;
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

    svg.append(text(left, 12, "z00 at the bottom; layer spacing is not to scale " +
      "(z step is not recorded)", { fill: MUTED, "font-size": 9.5 }));
    host.replaceChildren(svg);
    return svg;
  }

  // ======================================================== distance profile
  /* Figure: where each population sits relative to the organoid boundary.

     Enrichment is dimensionless, so all three channels share one axis. The axis
     is logarithmic because the quantity is a ratio: 0.5 and 2 are equal and
     opposite departures, and within one well tumour can reach 140× while T
     cells fall to 0.05× — a linear axis would have to either clip or crush.
     Exact zero (no signal at all in that band) is undefined on a log axis and
     is drawn on its own row below an axis break, as open symbols. */
  function bands(host, d, T, labels) {
    const W = 600, H = 274, top = 22, bot = 82, left = 48, right = 76;
    const pw = W - left - right, ph = H - top - bot - 16;
    const svg = el("svg", { class: "plot", viewBox: `0 0 ${W} ${H}`, role: "img" });
    const n = labels.length;
    const zeroY = top + ph + 16;

    let lo = 1, hi = 1;
    for (const ch of ["green", "orange", "nir"])
      for (const v of d.bands[ch].enrich)
        if (v != null && v > 0) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    const l0 = Math.log10(Math.max(lo, 1e-3)), l1 = Math.log10(hi);
    const pad = Math.max(0.12, (l1 - l0) * 0.08);
    const y0 = l0 - pad, y1 = l1 + pad;
    const Y = v => top + ph - (Math.log10(v) - y0) / Math.max(y1 - y0, 1e-9) * ph;
    const X = i => left + (i + 0.5) * (pw / n);

    for (const t of [0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 10, 25, 100, 1000]
                    .filter(v => Math.log10(v) >= y0 && Math.log10(v) <= y1)) {
      svg.append(el("line", { x1: left, y1: Y(t), x2: left + pw, y2: Y(t), stroke: RULE }));
      svg.append(text(left - 7, Y(t) + 3.4, fmt(t, t < 1 ? 2 : 0),
        { "text-anchor": "end", fill: MUTED }));
    }
    svg.append(el("line", { x1: left - 12, y1: top + ph + 5, x2: left + 4, y2: top + ph + 1,
      stroke: "#c9c8c3", "stroke-width": 1.2 }));
    svg.append(el("line", { x1: left - 12, y1: top + ph + 9, x2: left + 4, y2: top + ph + 5,
      stroke: "#c9c8c3", "stroke-width": 1.2 }));
    svg.append(text(left - 7, zeroY + 3.4, "none", { "text-anchor": "end", fill: MUTED }));

    const bx = left + 5 * (pw / n);
    svg.append(el("line", { x1: bx, y1: top, x2: bx, y2: top + ph, stroke: "#b9b8b3",
      "stroke-dasharray": "3 3" }));
    svg.append(text(bx - 6, top + 11, "inside organoid", { "text-anchor": "end",
      fill: MUTED, "font-size": 10 }));
    svg.append(text(bx + 6, top + 11, "outside", { fill: MUTED, "font-size": 10 }));
    svg.append(el("line", { x1: left, y1: Y(1), x2: left + pw, y2: Y(1), stroke: INK2,
      "stroke-width": 1.2 }));
    svg.append(text(left + pw + 6, Y(1) + 3.4, "1.0 = as expected", { fill: INK2,
      "font-size": 10 }));

    const NAME = { green: "tumour", orange: "T cells", nir: "dead cells" };
    for (const ch of ["green", "orange", "nir"]) {
      const v = d.bands[ch].enrich;
      const pts = [], zeros = [];
      for (let i = 0; i < n; i++) {
        if (v[i] == null) continue;                    // band lies outside the field
        (v[i] > 0 ? pts : zeros).push([X(i), v[i] > 0 ? Y(v[i]) : zeroY, i, v[i]]);
      }
      const info = (i, val) =>
        `<b>${labels[i]} µm</b><br><span class="k">${NAME[ch]}</span> ` +
        (val > 0 ? `${fmt(val, 2)}× enrichment` : "no signal in this band") +
        `<br><span class="k">signal area</span> ${fmt(d.bands[ch].area_mm2[i], 5)} mm²` +
        `<br><span class="k">band area</span> ${fmt(d.band_area_mm2[i], 3)} mm²`;

      if (pts.length > 1)
        svg.append(el("polyline", { points: pts.map(p => p[0] + "," + p[1]).join(" "),
          fill: "none", stroke: T.colors[ch], "stroke-width": 2,
          "stroke-linejoin": "round", "stroke-linecap": "round" }));
      for (const p of pts)
        svg.append(hoverable(el("circle", { cx: p[0], cy: p[1], r: 3.4,
          fill: T.colors[ch], stroke: "#fcfcfb", "stroke-width": 1.6 }), info(p[2], p[3])));
      for (const p of zeros)
        svg.append(hoverable(el("circle", { cx: p[0], cy: p[1], r: 3.2, fill: "#fcfcfb",
          stroke: T.colors[ch], "stroke-width": 1.6 }), info(p[2], 0)));
      const last = pts[pts.length - 1] || zeros[zeros.length - 1];
      if (last)
        svg.append(text(last[0] + 7, last[1] + 3.4, NAME[ch],
          { fill: T.colors[ch], "font-size": 10.5, "font-weight": 600 }));
    }

    labels.forEach((l, i) => {
      if (i % 2 && i !== labels.length - 1) return;
      svg.append(text(X(i), zeroY + 18, l, { "text-anchor": "middle", fill: MUTED,
        "font-size": 9.5 }));
    });
    svg.append(text(left + pw / 2, H - 22,
      "signed distance to the organoid boundary (µm)",
      { "text-anchor": "middle", fill: INK2, "font-size": 10.5 }));
    svg.append(text(left + pw / 2, H - 9,
      "negative = inside the brightfield territory · positive = outside",
      { "text-anchor": "middle", fill: MUTED, "font-size": 9.5 }));
    svg.append(text(12, top + ph / 2, "enrichment (× expected if uniform)",
      { "text-anchor": "middle", fill: INK2, "font-size": 10.5,
        transform: `rotate(-90 12 ${top + ph / 2})` }));
    host.replaceChildren(svg);
    return svg;
  }

  // ====================================================== depth × distance
  /* Figure: are depth and lateral position independent?

     Each cell is the share of that channel's own total signal. Panels are
     normalised separately, so a panel says where its population sits, never how
     much of it there is relative to another channel. Sequential single-hue ramp:
     colour carries magnitude, not identity. */
  function zband(host, d, T, labels) {
    const W = 600, H = 288, top = 42, bot = 78, left = 40, gap = 24;
    const nz = d.by_z.green.length, nb = labels.length;
    const pw = (W - left - gap * 2 - 14) / 3, ph = H - top - bot;
    const cw = pw / nb, ch_ = ph / nz;
    const svg = el("svg", { class: "plot", viewBox: `0 0 ${W} ${H}`, role: "img" });

    for (let i = 0; i < nz; i++) {
      if (i % 4 && i !== nz - 1) continue;
      svg.append(text(left - 6, top + (nz - 1 - i + 0.7) * ch_ + 3, zpad(i),
        { "text-anchor": "end", fill: MUTED, "font-size": 9.5 }));
    }

    [["green", "tumour"], ["orange", "T cells"], ["nir", "dead cells"]]
      .forEach(([ch, lbl], k) => {
        const m = d.zband[ch];
        let tot = 0;
        for (const row of m) for (const v of row) tot += v;
        const x0 = left + k * (pw + gap);
        const hiv = tot ? Math.max(...m.flat()) / tot : 1;
        svg.append(text(x0, top - 22, lbl, { fill: INK, "font-size": 11.5,
          "font-weight": 600 }));
        svg.append(text(x0, top - 10, tot
          ? `darkest cell = ${fmt(hiv * 100, 1)} % of this channel`
          : "no signal", { fill: MUTED, "font-size": 10 }));

        for (let z = 0; z < nz; z++) for (let b = 0; b < nb; b++) {
          const share = tot ? m[z][b] / tot : 0;
          const q = hiv > 0 ? Math.min(1, share / hiv) : 0;
          const col = share === 0 ? "#f7f6f4"
            : T.seq[Math.min(T.seq.length - 1, Math.floor(Math.pow(q, 0.62) * T.seq.length))];
          svg.append(hoverable(el("rect", { x: x0 + b * cw, y: top + (nz - 1 - z) * ch_,
            width: cw - 0.6, height: ch_ - 0.6, fill: col }),
            `<b>${lbl}</b><br><span class="k">layer</span> ${zpad(z)}` +
            `<br><span class="k">distance</span> ${labels[b]} µm` +
            `<br><span class="k">share</span> ${fmt(share * 100, 2)} % of channel total`));
        }
        const bx = x0 + 5 * cw;
        svg.append(el("line", { x1: bx, y1: top, x2: bx, y2: top + ph, stroke: "#0b0b0b",
          "stroke-width": 1, opacity: .45 }));
        svg.append(text(x0, top + ph + 13, "in", { fill: MUTED, "font-size": 9.5 }));
        svg.append(text(x0 + pw, top + ph + 13, "out", { fill: MUTED, "font-size": 9.5,
          "text-anchor": "end" }));
      });

    const sw = 104, sx = left, sy = H - 36;
    T.seq.forEach((c, i) => svg.append(el("rect",
      { x: sx + i * (sw / T.seq.length), y: sy, width: sw / T.seq.length + .4,
        height: 8, fill: c })));
    svg.append(text(sx, sy + 20, "0", { fill: MUTED, "font-size": 9.5 }));
    svg.append(text(sx + sw, sy + 20, "panel maximum", { fill: MUTED, "font-size": 9.5,
      "text-anchor": "end" }));
    svg.append(text(sx + sw + 16, sy + 7,
      "each panel is scaled to its own total — panels are not comparable to each other",
      { fill: MUTED, "font-size": 9.5 }));
    svg.append(text(left, 12, "rows: z layer · columns: signed distance to the " +
      "organoid boundary", { fill: MUTED, "font-size": 9.5 }));
    host.replaceChildren(svg);
    return svg;
  }

  // ============================================================ time course
  /* Figure: how each quantity changed over the four days.
     Four quantities, four units, four panels. */
  function timecourse(host, frames, times, T, tcur, cal) {
    const W = 600, H = 206, top = 42, bot = 42, left = 8, gap = 18;
    const pw = (W - left - gap * 3 - 12) / 4, ph = H - top - bot;
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
        svg.append(hoverable(el("circle", { cx: X(days[i]), cy: Y(v),
          r: i === tcur ? 4.2 : 2.4, fill: i === tcur ? s.col : "#fcfcfb", stroke: s.col,
          "stroke-width": i === tcur ? 1.6 : 1.4 }),
          `<b>${s.lbl}</b><br><span class="k">day</span> ${fmt(days[i], 2)}` +
          `<br><span class="k">value</span> ${fmt(v, s.dec)} ${s.unit.split(" ")[0]}${extra}`));
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

  /* Journal-style table: a caption above, a units row under the header, a
     footnote below. Numeric columns are right-aligned and tabular. */
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
      if (c && typeof c === "object") { e.innerHTML = c.html; if (c.cls) e.className = c.cls; }
      else e.textContent = c;
      tr.append(e);
    }
    return tr;
  }

  return { depth, bands, zband, timecourse, download, downloadCSV, table, fmt, ticks,
           untip, hoverable, el, text, zpad, INK, INK2, MUTED, RULE };
})();
