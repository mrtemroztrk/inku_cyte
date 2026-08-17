/* Group page: the figures are rendered server-side with matplotlib (see
   atlas/figures.py) and embedded as SVG, so what the reader sees is exactly what
   goes into the manuscript. This file only builds the statistics tables under
   each figure. */

(() => {
  const G = window.GROUPS;
  const $ = s => document.querySelector(s);
  const fmt = FIG.fmt;

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
})();
