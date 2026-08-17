/* Group page: the figures are rendered server-side with matplotlib (see
   atlas/figures.py) and embedded as SVG, so what the reader sees is exactly what
   goes into the manuscript. This file only builds the statistics tables under
   each figure. */

(() => {
  const G = window.GROUPS;
  const $ = s => document.querySelector(s);
  const fmt = FIG.fmt;
  const put = (id, node) => { const h = $("#tbl_" + id); if (h) h.replaceChildren(node); };
  const file = num => "table_" + num.toLowerCase().replace(/\W+/g, "_") +
                      `_t${String(G.t.index).padStart(2, "0")}`;
  const when = `day ${G.t.day}`;

  // -------------------------------------------------------------- pairwise
  const pairTable = (data, num, what, d) => FIG.table({
    caption: `<b>${num}.</b> ${what} Pairwise Mann-Whitney tests with ` +
      "Benjamini-Hochberg correction across the comparisons in this figure.",
    head: ["Comparison", "n", "AUC", "Cliff's δ", "p", "q"],
    units: ["", "wells", "0.5 = no separation", "−1 to +1", "raw", "BH-corrected"],
    rows: data.tests.map(r => [`${r.a} vs ${r.b}`, `${r.n_a} / ${r.n_b}`,
      fmt(r.auc, 3), (r.delta > 0 ? "+" : "") + fmt(r.delta, 3),
      r.p == null ? "—" : fmt(r.p, 4), r.q == null ? "—" : fmt(r.q, 4)]),
    note: "Per group: " +
      data.groups.map(g => `${g.label} n = ${g.n} [${g.wells.join(", ")}], median ` +
        `${fmt(g.median, d)} (95 % CI ${fmt(g.ci[0], d)}–${fmt(g.ci[1], d)}), ` +
        `mean ${fmt(g.mean, d)} ± ${g.sd == null ? "—" : fmt(g.sd, d)} SD`).join("; ") + ".",
    file: file(num),
  });

  // Two-panel figures get two tables in one box: with T cells, without.
  const pairPair = (sp, num, what, d) => {
    const box = document.createElement("div");
    box.append(pairTable(sp.t, num + "a", what + " Wells with T cells.", d));
    box.append(pairTable(sp.no_t, num + "b", what + " Wells without T cells.", d));
    return box;
  };

  // ------------------------------------------------------- layer profiles
  const layerTable = (data, num, what) => {
    const gs = data.groups;
    const nz = gs.length ? gs[0].nz : 17;
    const rows = [];
    for (let z = nz - 1; z >= 0; z--)
      rows.push([FIG.zpad(z), ...gs.map(g => fmt(g.median[z], 5))]);
    return FIG.table({
      caption: `<b>${num}.</b> ${what} Median T-cell signal per layer in each group.`,
      head: [{ html: "Layer", def: "zorder" }, ...gs.map(g => `${g.label} (n = ${g.n})`)],
      units: ["ordinal", ...gs.map(() => "mm²")],
      rows,
      note: "Peak layer of the group median: " +
        gs.map(g => `${g.label} ${FIG.zpad(g.peak)} [wells ${g.wells.map(w => w.well).join(", ")}]`).join("; ") +
        ". Layer areas are measured on each plane's own mask; one cell appears in " +
        "several neighbouring planes, so the profiles are wider than the cells.",
      file: file(num),
    });
  };

  // ---------------------------------------------------------- time courses
  const timeTable = (data, num, what, unit, d) => {
    const gs = data.groups;
    const days = gs.length ? gs[0].days : [];
    return FIG.table({
      caption: `<b>${num}.</b> ${what} Group median at each imaging time.`,
      head: ["Day", ...gs.map(g => `${g.label} (n = ${g.n})`)],
      units: ["d", ...gs.map(() => unit)],
      rows: days.map((day, i) => [fmt(day, 2), ...gs.map(g => fmt(g.median[i], d))]),
      note: gs.map(g => `${g.label}: ${g.wells.map(w => w.well).join(", ")}`).join("; ") + ".",
      file: file(num),
    });
  };

  // ------------------------------------------------------------- matched
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
      "independent groups is evidence that a single underpowered comparison is not. " +
      "Wells: " + data.rows.map(r => `${r.group} without T [${r.wells_ctrl.join(", ")}], ` +
        `with T [${r.wells_t.join(", ")}]`).join("; ") + ".",
    file: file(num),
  });

  put("tz_coc", layerTable(G.tz_coculture, "Table 1", `T-cell signal by layer, by co-culture, ${when}.`));
  put("tz_cmp", layerTable(G.tz_compound, "Table 2", `T-cell signal by layer, by compound, ${when}.`));
  put("tc_coc", pairTable(G.tcells_coculture, "Table 3", `T-cell signal (≈ cells) by co-culture, ${when}.`, 0));
  put("tc_cmp", pairTable(G.tcells_compound, "Table 4", `T-cell signal (≈ cells) by compound, ${when}.`, 0));
  put("tc_time", timeTable(G.tcell_time, "Table 5", "T-cell signal over time, by co-culture.", "≈ cells", 0));
  put("dead_cmp", pairPair(G.dead_compound, "Table 6", `Dead-cell signal by compound, ${when}.`, 5));
  put("tumour_cmp", pairPair(G.tumour_compound, "Table 7", `Tumour signal by compound, ${when}.`, 4));
  put("growth_cmp", pairPair(G.growth_compound, "Table 8", `Organoid growth (÷ day 0) by compound, ${when}.`, 3));
  put("growth", timeTable(G.growth, "Table 9", "Organoid footprint area over time, by co-culture.", "mm²", 3));
  put("dead", matchedTable(G.dead_matched, "Table 10", `Effect of adding T cells on dead-cell signal, ${when}.`, 4));
  put("tumour", matchedTable(G.tumour_matched, "Table 11", `Effect of adding T cells on tumour signal, ${when}.`, 3));

  const cal = G.calibration;
  put("calib", FIG.table({
    caption: "<b>Table 12.</b> Calibration of signal area to cell number, and the " +
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
    file: "table_12_calibration",
  }));

  for (const b of document.querySelectorAll("[data-tbl]"))
    b.addEventListener("click", () => {
      const box = $("#tbl_" + b.dataset.tbl);
      b.textContent = box.classList.toggle("on") ? "hide table" : "table";
    });
})();

window.SHOOT = { scroll(y) { window.scrollTo(0, y); } };

/* Screenshot hook — atlas/shoot.py drives the page through the URL fragment so
   the animations in the README come from the real page. Inert without #shoot=. */
(() => {
  const m = /#shoot=(.*)$/.exec(location.hash);
  if (!m) return;
  const run = () => { try { new Function(decodeURIComponent(m[1]))(); }
                      catch (e) { console.error("shoot", e); } };
  setTimeout(run, 350);
})();
