/* Grup karşılaştırma figürleri.

   Renk burada kimlik taşımıyor: gruplar zaten x ekseninde ayrılıyor, üstüne bir
   de renk vermek gereksiz bir kodlama olurdu — ve kanal renkleriyle çakışırdı
   (turuncu bu atlasta "T hücresi" demek, "PDA+CAF" değil). Aynı sebeple büyüme
   eğrileri tek bir grafikte üst üste değil, ko-kültür başına küçük panellerde.

   Kutu grafiği yok: koşul başına 4–17 kuyu var, bir kutu grafiği o örneklemde
   çeyrekleri uydurur. Her kuyu bir nokta, medyan kalın çizgi, önyükleme %95
   güven aralığı arka şerit. Yatay dağıtma deterministik (kuyu sırasına göre),
   rastgele değil — sayfa her açıldığında aynı figür çıksın diye. */

const GRP = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const INK = "#0b0b0b", INK2 = "#52514e", MUTED = "#8a8983", RULE = "#e6e5e1";
  const DOT = "#3b4655", CI = "#dcdbd6";

  const el = (t, a = {}, k = []) => {
    const e = document.createElementNS(NS, t);
    for (const n in a) if (a[n] != null) e.setAttribute(n, a[n]);
    for (const c of [].concat(k)) e.append(c);
    return e;
  };
  const text = (x, y, s, a = {}) => {
    const e = el("text", { x, y, fill: INK2, "font-size": 10.5, ...a });
    e.textContent = s; return e;
  };
  const fmt = FIG.fmt;

  /* Deterministik yatay dağıtma: aynı değere sahip noktalar üst üste binmesin. */
  const jitter = (i, n) => n <= 1 ? 0 : ((i % 5) - 2) * 3.4 + (i > 4 ? 0 : 0);

  /* Nokta şeridi. log=true ise oran verisi (zenginleşme) için logaritmik eksen. */
  function strip(host, data, opt) {
    const { title, unit, ref, log, d } = opt;
    const gs = data.groups;
    const W = 560, H = 250, top = 26, bot = 58, left = 58, right = 14;
    const pw = W - left - right, ph = H - top - bot;
    const svg = el("svg", { class: "plot", viewBox: `0 0 ${W} ${H}`, role: "img" });
    if (!gs.length) { host.replaceChildren(svg); return svg; }

    const all = gs.flatMap(g => g.values).concat(gs.flatMap(g => g.ci));
    let lo = Math.min(...all), hi = Math.max(...all);
    if (ref != null) { lo = Math.min(lo, ref); hi = Math.max(hi, ref); }
    let Y, tk;
    if (log) {
      const pos = all.filter(v => v > 0);
      const l0 = Math.log10(Math.min(...pos)) - 0.12, l1 = Math.log10(hi) + 0.12;
      Y = v => top + ph - (Math.log10(Math.max(v, Math.pow(10, l0))) - l0) / (l1 - l0) * ph;
      tk = [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 10, 25, 100]
        .filter(v => Math.log10(v) >= l0 && Math.log10(v) <= l1);
    } else {
      const pad = (hi - lo) * 0.1 || 1;
      const y0 = lo - pad, y1 = hi + pad;
      Y = v => top + ph - (v - y0) / (y1 - y0) * ph;
      tk = FIG.ticks(y0, y1, 5);
    }
    for (const t of tk) {
      svg.append(el("line", { x1: left, y1: Y(t), x2: left + pw, y2: Y(t), stroke: RULE }));
      svg.append(text(left - 8, Y(t) + 3.4, fmt(t, t < 1 ? 2 : d), { "text-anchor": "end",
        fill: MUTED }));
    }
    if (ref != null) {
      svg.append(el("line", { x1: left, y1: Y(ref), x2: left + pw, y2: Y(ref),
        stroke: INK2, "stroke-width": 1.2 }));
      svg.append(text(left + pw, Y(ref) - 5, "uniform scatter", { "text-anchor": "end",
        fill: INK2, "font-size": 10 }));
    }

    const slot = pw / gs.length;
    gs.forEach((g, k) => {
      const cx = left + slot * (k + 0.5);
      // önyükleme %95 GA — medyanın belirsizliği, dağılımın genişliği değil
      svg.append(el("rect", { x: cx - 20, y: Math.min(Y(g.ci[0]), Y(g.ci[1])),
        width: 40, height: Math.max(2, Math.abs(Y(g.ci[1]) - Y(g.ci[0]))),
        fill: CI, rx: 1 }));
      g.values.forEach((v, i) => {
        const c = el("circle", { cx: cx + jitter(i, g.values.length), cy: Y(v), r: 3.6,
          fill: DOT, "fill-opacity": .78, stroke: "#fcfcfb", "stroke-width": 1.2 });
        c.addEventListener("pointerenter", e => tipShow(
          `<b>${g.wells[i]}</b><br><span class="k">${g.label}</span><br>` +
          `${fmt(v, d)} ${unit}`, e));
        c.addEventListener("pointermove", e => tipShow(
          `<b>${g.wells[i]}</b><br><span class="k">${g.label}</span><br>` +
          `${fmt(v, d)} ${unit}`, e));
        c.addEventListener("pointerleave", tipHide);
        svg.append(c);
      });
      svg.append(el("line", { x1: cx - 24, y1: Y(g.median), x2: cx + 24, y2: Y(g.median),
        stroke: INK, "stroke-width": 2.4, "stroke-linecap": "round" }));
      svg.append(text(cx, top + ph + 17, g.label, { "text-anchor": "middle", fill: INK,
        "font-size": 11 }));
      svg.append(text(cx, top + ph + 30, `n = ${g.n} · med ${fmt(g.median, d)}`,
        { "text-anchor": "middle", fill: MUTED, "font-size": 10 }));
    });
    svg.append(el("line", { x1: left, y1: top + ph, x2: left + pw, y2: top + ph,
      stroke: "#c9c8c3" }));
    svg.append(text(13, top + ph / 2, unit, { "text-anchor": "middle", fill: INK2,
      "font-size": 10.5, transform: `rotate(-90 13 ${top + ph / 2})` }));
    svg.append(text(left, 12, title, { fill: INK, "font-size": 11.5, "font-weight": 600 }));
    host.replaceChildren(svg);
    return svg;
  }

  /* Büyüme: ko-kültür başına panel. Ortak birim olduğu için ortak y ekseni —
     paneller burada gerçekten karşılaştırılabilir. */
  function curves(host, data, opt) {
    const gs = data.groups;
    const W = 560, H = 200, top = 34, bot = 40, left = 44, gap = 14;
    const pw = (W - left - gap * (gs.length - 1) - 10) / gs.length, ph = H - top - bot;
    const svg = el("svg", { class: "plot", viewBox: `0 0 ${W} ${H}`, role: "img" });
    if (!gs.length) { host.replaceChildren(svg); return svg; }

    const hi = Math.max(...gs.flatMap(g => g.wells.flatMap(w => w.v)));
    const days = gs[0].days, dmax = Math.max(...days);
    const tk = FIG.ticks(0, hi, 4);
    const ymax = Math.max(tk[tk.length - 1], hi);
    const Y = v => top + ph - v / ymax * ph;

    gs.forEach((g, k) => {
      const x0 = left + k * (pw + gap);
      const X = dd => x0 + dd / dmax * pw;
      for (const t of tk)
        svg.append(el("line", { x1: x0, y1: Y(t), x2: x0 + pw, y2: Y(t), stroke: RULE }));
      if (k === 0) for (const t of tk)
        svg.append(text(left - 7, Y(t) + 3.4, fmt(t, 1), { "text-anchor": "end", fill: MUTED }));

      for (const w of g.wells) {
        const pl = el("polyline", { points: w.v.map((v, i) => X(days[i]) + "," + Y(v)).join(" "),
          fill: "none", stroke: "#9aa0a8", "stroke-width": 1, "stroke-opacity": .5 });
        pl.addEventListener("pointerenter", e => tipShow(
          `<b>${w.well}</b><br><span class="k">${g.label}</span><br>` +
          `day 4: ${fmt(w.v[w.v.length - 1], 2)} ${opt.unit}`, e));
        pl.addEventListener("pointermove", e => tipShow(
          `<b>${w.well}</b><br><span class="k">${g.label}</span><br>` +
          `day 4: ${fmt(w.v[w.v.length - 1], 2)} ${opt.unit}`, e));
        pl.addEventListener("pointerleave", tipHide);
        svg.append(pl);
      }
      svg.append(el("polyline", { points: g.median.map((v, i) => X(days[i]) + "," + Y(v)).join(" "),
        fill: "none", stroke: INK, "stroke-width": 2.2, "stroke-linejoin": "round" }));

      svg.append(text(x0, top - 18, g.label, { fill: INK, "font-size": 11, "font-weight": 600 }));
      svg.append(text(x0, top - 6, `n = ${g.n} wells`, { fill: MUTED, "font-size": 10 }));
      svg.append(el("line", { x1: x0, y1: top + ph, x2: x0 + pw, y2: top + ph,
        stroke: "#c9c8c3" }));
      svg.append(text(x0, top + ph + 14, "0", { fill: MUTED, "font-size": 9.5 }));
      svg.append(text(x0 + pw, top + ph + 14, Math.round(dmax) + " d",
        { fill: MUTED, "font-size": 9.5, "text-anchor": "end" }));
    });
    svg.append(text(13, top + ph / 2, opt.unit, { "text-anchor": "middle", fill: INK2,
      "font-size": 10.5, transform: `rotate(-90 13 ${top + ph / 2})` }));
    host.replaceChildren(svg);
    return svg;
  }

  /* Eşleşmiş ±T karşılaştırması: her ko-kültür içinde iki nokta bulutu ve
     medyanları birleştiren çizgi. Ko-kültür sabit tutuluyor çünkü kendisi de
     hem ölümü hem T dağılımını etkiliyor. */
  function matched(host, data, opt) {
    const rows = data.rows;
    const W = 560, H = 236, top = 26, bot = 62, left = 58, right = 14;
    const pw = W - left - right, ph = H - top - bot;
    const svg = el("svg", { class: "plot", viewBox: `0 0 ${W} ${H}`, role: "img" });
    if (!rows.length) { host.replaceChildren(svg); return svg; }

    const all = rows.flatMap(r => r.values_t.concat(r.values_ctrl));
    const hi = Math.max(...all), lo = Math.min(...all);
    const tk = FIG.ticks(Math.min(0, lo), hi, 4);
    const ymax = Math.max(tk[tk.length - 1], hi) || 1;
    const Y = v => top + ph - v / ymax * ph;
    for (const t of tk) {
      svg.append(el("line", { x1: left, y1: Y(t), x2: left + pw, y2: Y(t), stroke: RULE }));
      svg.append(text(left - 8, Y(t) + 3.4, fmt(t, opt.d), { "text-anchor": "end", fill: MUTED }));
    }

    const slot = pw / rows.length;
    rows.forEach((r, k) => {
      const c0 = left + slot * (k + 0.5) - 22, c1 = left + slot * (k + 0.5) + 22;
      [[c0, r.values_ctrl, r.med_ctrl, "no T cells"],
       [c1, r.values_t, r.med_t, "+ T cells"]].forEach(([cx, vals, med, lbl]) => {
        vals.forEach((v, i) => {
          const c = el("circle", { cx: cx + ((i % 3) - 1) * 3.2, cy: Y(v), r: 3.2,
            fill: DOT, "fill-opacity": .72, stroke: "#fcfcfb", "stroke-width": 1.1 });
          c.addEventListener("pointerenter", e => tipShow(
            `<b>${r.group}</b><br><span class="k">${lbl}</span><br>${fmt(v, opt.d)} ${opt.unit}`, e));
          c.addEventListener("pointermove", e => tipShow(
            `<b>${r.group}</b><br><span class="k">${lbl}</span><br>${fmt(v, opt.d)} ${opt.unit}`, e));
          c.addEventListener("pointerleave", tipHide);
          svg.append(c);
        });
        svg.append(el("line", { x1: cx - 14, y1: Y(med), x2: cx + 14, y2: Y(med),
          stroke: INK, "stroke-width": 2.2, "stroke-linecap": "round" }));
      });
      svg.append(el("line", { x1: c0, y1: Y(r.med_ctrl), x2: c1, y2: Y(r.med_t),
        stroke: INK, "stroke-width": 1, "stroke-dasharray": "3 3" }));
      svg.append(text(left + slot * (k + 0.5), top + ph + 17, r.group,
        { "text-anchor": "middle", fill: INK, "font-size": 11 }));
      const sig = r.q == null ? "" : r.q < 0.05 ? ` · q = ${fmt(r.q, 3)}` : " · n.s.";
      svg.append(text(left + slot * (k + 0.5), top + ph + 30,
        `${fmt(r.ratio, 2)}× · δ ${r.delta > 0 ? "+" : ""}${fmt(r.delta, 2)}${sig}`,
        { "text-anchor": "middle", fill: MUTED, "font-size": 9.5 }));
    });
    svg.append(text(left, 12, "left: no T cells · right: + T cells",
      { fill: MUTED, "font-size": 10 }));
    svg.append(el("line", { x1: left, y1: top + ph, x2: left + pw, y2: top + ph,
      stroke: "#c9c8c3" }));
    svg.append(text(13, top + ph / 2, opt.unit, { "text-anchor": "middle", fill: INK2,
      "font-size": 10.5, transform: `rotate(-90 13 ${top + ph / 2})` }));
    host.replaceChildren(svg);
    return svg;
  }

  // ------------------------------------------------------------------- ipucu
  let tipEl;
  function tipShow(html, ev) {
    if (!tipEl) { tipEl = document.createElement("div"); tipEl.id = "tip";
                  document.body.append(tipEl); }
    tipEl.innerHTML = html; tipEl.style.display = "block";
    const r = tipEl.getBoundingClientRect();
    let x = ev.clientX + 14, y = ev.clientY - 10;
    if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - 14;
    if (y + r.height > innerHeight - 8) y = innerHeight - r.height - 8;
    tipEl.style.left = x + "px"; tipEl.style.top = Math.max(8, y) + "px";
  }
  const tipHide = () => { if (tipEl) tipEl.style.display = "none"; };

  return { strip, curves, matched };
})();


/* Figure 7 — the calibration itself, drawn so it can be checked rather than
   trusted. Left panel: the µm² per cell derived independently in each
   co-culture, with the pooled median and its bootstrap interval. Right panel:
   the equivalent cell diameter each scale implies, against the known size of a
   T cell — the check that decides whether a scale is usable at all. The tumour
   scale is drawn in the same units and falls below the size of a T cell, which
   is why it is rejected. */
const CALFIG = (cal) => {
  const NS = "http://www.w3.org/2000/svg";
  const INK = FIG.INK, INK2 = FIG.INK2, MUTED = FIG.MUTED, RULE = FIG.RULE;
  const el = FIG.el, text = FIG.text, fmt = FIG.fmt;
  const W = 600, H = 232, top = 40, bot = 54, gap = 54;
  const pw = (W - 60 - gap - 20) / 2, ph = H - top - bot;
  const svg = el("svg", { class: "plot", viewBox: `0 0 ${W} ${H}`, role: "img" });

  const t = cal.tcell, tu = cal.tumour;
  const groups = Object.entries(t.by_coculture);

  // --- left: area per cell, one estimate per co-culture
  const x0 = 52;
  const vals = groups.map(([, v]) => v.um2_per_cell).concat([t.um2_per_cell, t.ci95[0],
    t.ci95[1], tu.um2_per_cell]);
  const hi = Math.max(...vals) * 1.08, lo = Math.min(...vals) * 0.9;
  const Y = v => top + ph - (v - lo) / (hi - lo) * ph;
  for (const v of FIG.ticks(lo, hi, 4)) {
    svg.append(el("line", { x1: x0, y1: Y(v), x2: x0 + pw, y2: Y(v), stroke: RULE }));
    svg.append(text(x0 - 7, Y(v) + 3.4, fmt(v, 0), { "text-anchor": "end", fill: MUTED }));
  }
  svg.append(text(x0, top - 24, "Area per cell, derived independently per co-culture",
    { fill: INK, "font-size": 11.5, "font-weight": 600 }));
  svg.append(text(x0, top - 12, "µm² per cell", { fill: MUTED, "font-size": 10 }));
  svg.append(el("rect", { x: x0, y: Math.min(Y(t.ci95[0]), Y(t.ci95[1])), width: pw,
    height: Math.max(2, Math.abs(Y(t.ci95[1]) - Y(t.ci95[0]))), fill: "#dcdbd6" }));
  svg.append(el("line", { x1: x0, y1: Y(t.um2_per_cell), x2: x0 + pw, y2: Y(t.um2_per_cell),
    stroke: INK, "stroke-width": 2 }));
  svg.append(text(x0 + pw, Y(t.um2_per_cell) - 5,
    `pooled median ${fmt(t.um2_per_cell, 1)} (95 % CI ${fmt(t.ci95[0], 1)}–${fmt(t.ci95[1], 1)})`,
    { "text-anchor": "end", fill: INK2, "font-size": 10 }));
  groups.forEach(([name, v], i) => {
    const cx = x0 + pw * (i + 0.5) / groups.length;
    svg.append(FIG.hoverable(el("circle", { cx, cy: Y(v.um2_per_cell), r: 4,
      fill: "#3b4655", stroke: "#fcfcfb", "stroke-width": 1.3 }),
      `<b>${name}</b><br><span class="k">n</span> ${v.n_wells} wells<br>` +
      `${fmt(v.um2_per_cell, 1)} µm² per cell<br>` +
      `<span class="k">implied diameter</span> ${fmt(v.eq_diam_um, 2)} µm`));
    svg.append(text(cx, top + ph + 15, name.replace("PDA+", "+").replace("PDA", "PDA only"),
      { "text-anchor": "middle", fill: MUTED, "font-size": 9 }));
    svg.append(text(cx, top + ph + 26, `n = ${v.n_wells}`,
      { "text-anchor": "middle", fill: MUTED, "font-size": 9 }));
  });
  svg.append(el("line", { x1: x0, y1: top + ph, x2: x0 + pw, y2: top + ph, stroke: "#c9c8c3" }));

  // --- right: implied cell diameter against the known size of a T cell
  const x1 = x0 + pw + gap;
  const dmax = Math.max(t.eq_diam_um, tu.eq_diam_um, 12) * 1.25;
  const DY = v => top + ph - v / dmax * ph;
  for (const v of FIG.ticks(0, dmax, 4)) {
    svg.append(el("line", { x1: x1, y1: DY(v), x2: x1 + pw, y2: DY(v), stroke: RULE }));
    svg.append(text(x1 - 7, DY(v) + 3.4, fmt(v, 0), { "text-anchor": "end", fill: MUTED }));
  }
  svg.append(text(x1, top - 24, "Cell diameter each scale implies",
    { fill: INK, "font-size": 11.5, "font-weight": 600 }));
  svg.append(text(x1, top - 12, "µm", { fill: MUTED, "font-size": 10 }));
  // known size range of a T cell — the external fact the check is made against
  svg.append(el("rect", { x: x1, y: DY(10), width: pw, height: Math.abs(DY(7) - DY(10)),
    fill: "#e8f0fb" }));
  svg.append(text(x1 + pw - 3, DY(10) - 4, "a T cell is 7–10 µm",
    { "text-anchor": "end", fill: "#256abf", "font-size": 9.5 }));
  [["T-cell scale", t.eq_diam_um, "#1baf7a", "accepted"],
   ["tumour scale", tu.eq_diam_um, "#e34948", "rejected — smaller than a T cell"]]
    .forEach(([lbl, v, col, verdict], i) => {
      const cx = x1 + pw * (i + 0.5) / 2;
      svg.append(el("rect", { x: cx - 22, y: DY(v), width: 44, height: top + ph - DY(v),
        fill: col, "fill-opacity": .82, rx: 1 }));
      svg.append(text(cx, DY(v) - 6, fmt(v, 1), { "text-anchor": "middle", fill: INK,
        "font-size": 11, "font-weight": 600 }));
      svg.append(text(cx, top + ph + 15, lbl, { "text-anchor": "middle", fill: INK,
        "font-size": 9.5 }));
      svg.append(text(cx, top + ph + 26, verdict, { "text-anchor": "middle", fill: MUTED,
        "font-size": 9 }));
    });
  svg.append(el("line", { x1: x1, y1: top + ph, x2: x1 + pw, y2: top + ph, stroke: "#c9c8c3" }));
  return svg;
};

// ------------------------------------------------------------------- wiring
(() => {
  const G = window.GROUPS;
  const $ = s => document.querySelector(s);
  const fmt = FIG.fmt;
  const svgs = {};

  svgs.enrich_coc = GRP.strip($("#fig_enrich_coc"), G.enrich_coculture, {
    title: "day 4 · wells that received T cells",
    unit: "T-cell enrichment (× uniform)", ref: 1, log: true, d: 2 });

  svgs.enrich_cmp = GRP.strip($("#fig_enrich_cmp"), G.enrich_compound, {
    title: "day 4 · wells that received T cells",
    unit: "T-cell enrichment (× uniform)", ref: 1, log: true, d: 2 });

  svgs.dist = GRP.strip($("#fig_dist"), G.dist_coculture, {
    title: "day 4 · median signed distance of the T-cell signal",
    unit: "µm (negative = inside the organoid)", ref: 0, log: false, d: 0 });

  svgs.growth = GRP.curves($("#fig_growth"), G.growth,
    { unit: "organoid territory (mm²)" });

  svgs.dead = GRP.matched($("#fig_dead"), G.dead_matched,
    { unit: "dead-cell signal (mm²)", d: 4 });

  svgs.tumour = GRP.matched($("#fig_tumour"), G.tumour_matched,
    { unit: "tumour signal (mm²)", d: 3 });

  svgs.calib = CALFIG(G.calibration);
  $("#fig_calib").replaceChildren(svgs.calib);

  // ------------------------------------------------------------------ tables
  const pairTable = (data, num, what) => FIG.table({
    caption: `<b>${num}.</b> ${what} Pairwise Mann-Whitney tests with ` +
      "Benjamini-Hochberg correction across the comparisons in this figure.",
    head: ["Comparison", "n", "AUC", "Cliff's δ", "p", "q"],
    units: ["", "wells", "0.5 = no separation", "−1 to +1", "raw", "BH-corrected"],
    rows: data.tests.map(r => [`${r.a} vs ${r.b}`, `${r.n_a} / ${r.n_b}`,
      fmt(r.auc, 3), (r.delta > 0 ? "+" : "") + fmt(r.delta, 3),
      r.p == null ? "—" : fmt(r.p, 4), r.q == null ? "—" : fmt(r.q, 4)]),
    note: "Group medians and bootstrap intervals: " +
      data.groups.map(g => `${g.label} n = ${g.n}, median ${fmt(g.median, 3)} ` +
        `(95 % CI ${fmt(g.ci[0], 3)}–${fmt(g.ci[1], 3)})`).join("; ") + ".",
    file: "table_" + num.toLowerCase().replace(/\W+/g, "_"),
  });

  $("#tbl_enrich_coc").replaceChildren(
    pairTable(G.enrich_coculture, "Table 1", "T-cell enrichment by co-culture, day 4."));
  $("#tbl_enrich_cmp").replaceChildren(
    pairTable(G.enrich_compound, "Table 2", "T-cell enrichment by compound, day 4."));
  $("#tbl_dist").replaceChildren(
    pairTable(G.dist_coculture, "Table 3",
      "Median signed distance of the T-cell signal to the organoid boundary, day 4."));

  const matchedTable = (data, num, what, d) => FIG.table({
    caption: `<b>${num}.</b> ${what} Co-culture is held constant; ` +
      "Mann-Whitney within each co-culture, Benjamini-Hochberg across the four.",
    head: ["Co-culture", "n without T", "n with T", "median without T",
           "median with T", "ratio", "Cliff's δ", "p", "q"],
    units: ["", "wells", "wells", "mm²", "mm²", "×", "−1 to +1", "raw", "BH-corrected"],
    rows: data.rows.map(r => [r.group, r.n_ctrl, r.n_t, fmt(r.med_ctrl, d),
      fmt(r.med_t, d), fmt(r.ratio, 2), (r.delta > 0 ? "+" : "") + fmt(r.delta, 3),
      r.p == null ? "—" : fmt(r.p, 4), r.q == null ? "—" : fmt(r.q, 4)]),
    note: `Direction agrees in ${data.n_up} of ${data.n_groups} co-cultures; ` +
      `two-sided sign test p = ${data.sign_p}. A sign test is reported because ` +
      "the individual groups are small: a consistent direction across " +
      "independent groups is evidence that a single underpowered comparison is not.",
    file: "table_" + num.toLowerCase().replace(/\W+/g, "_"),
  });

  $("#tbl_dead").replaceChildren(matchedTable(G.dead_matched, "Table 4",
    "Effect of adding T cells on dead-cell signal at day 4.", 4));
  $("#tbl_tumour").replaceChildren(matchedTable(G.tumour_matched, "Table 5",
    "Effect of adding T cells on tumour signal at day 4.", 3));

  const cal = G.calibration;
  $("#tbl_calib").replaceChildren(FIG.table({
    caption: "<b>Table 6.</b> Calibration of signal area to cell number, and the " +
      "checks each candidate scale was held to.",
    head: ["Scale", "Seeded", "Area per cell", "Implied diameter", "Verdict", "Basis"],
    units: ["", "cells per well", "µm²", "µm", "", ""],
    rows: [
      ["T cells (orange)", cal.tcell.n_seeded, fmt(cal.tcell.um2_per_cell, 1),
       fmt(cal.tcell.eq_diam_um, 2), "accepted",
       `95 % CI ${fmt(cal.tcell.ci95[0], 1)}–${fmt(cal.tcell.ci95[1], 1)}; ` +
       `CV ${fmt(cal.tcell.cv * 100, 0)} %; n = ${cal.tcell.n_wells} wells`],
      ["Tumour (green)", cal.tumour.n_seeded, fmt(cal.tumour.um2_per_cell, 1),
       fmt(cal.tumour.eq_diam_um, 2), "rejected", cal.tumour.reason],
      ["Object counting", cal.object_counting.expected,
       "—", "—", "rejected", cal.object_counting.reason],
    ].concat(Object.entries(cal.tcell.by_coculture).map(([k, v]) =>
      [`T cells, ${k} only`, cal.tcell.n_seeded, fmt(v.um2_per_cell, 1),
       fmt(v.eq_diam_um, 2), "—", `independent replicate, n = ${v.n_wells} wells`])),
    note: "The T-cell scale is defined on the projected (maximum-intensity) mask. " +
      "It is not valid for per-layer areas, which sum to several times the " +
      "projected area because one cell appears in several layers; per-layer cell " +
      "equivalents on the well pages apportion the well total instead.",
    file: "table_6_calibration",
  }));

  for (const b of document.querySelectorAll("[data-tbl]"))
    b.addEventListener("click", () => {
      const box = $("#tbl_" + b.dataset.tbl);
      b.textContent = box.classList.toggle("on") ? "hide table" : "table";
    });
  for (const b of document.querySelectorAll("[data-svg]"))
    b.addEventListener("click", () => FIG.download(svgs[b.dataset.svg],
      `${b.dataset.svg}.svg`));
})();
