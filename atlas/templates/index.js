/* Plaka sayfası: 96 kuyuluk ızgara, seçilen ölçüye göre renklendirilir.

   Renk burada büyüklük taşıyor, kimlik değil — o yüzden tek hue'lu sıralı ölçek.
   (Anlamlı bir orta noktası olan bir ölçü için ıraksak ölçek altyapısı duruyor:
   METRICS girdisine `div: <orta>` verilir.) Renk hiçbir zaman tek taşıyıcı
   değil: üstüne gelince kuyunun değeri ve koşulu yazılıyor.

   Ölçek sınırları yüzdeliklerden (p5–p95) alınır, uçlardan değil: tek bir aykırı
   kuyu bütün plakayı tek renge indirirdi. */

(() => {
  const S = window.SUMM, T = window.THEME;
  const fmt = FIG.fmt;
  const byWell = new Map(S.wells.map(w => [w.well, w]));
  const ROWS = "ABCDEFGH", COLS = 12;

  const DIV_LO = ["#0d366b", "#184f95", "#256abf", "#3987e5", "#86b6ef", "#cde2fb"];
  const DIV_HI = ["#f6c9c8", "#f0a6a5", "#e87b7a", "#e34948", "#c22e2d", "#9c1f1e"];
  const DIV_MID = "#f0efec";

  // Each measure carries the sentence a reader needs to interpret the colour;
  // it is shown under the selector, so nobody has to ask.
  const METRICS = {
    tcells: { lbl: "T cells", unit: "≈ cells", d: 0,
      desc: "How much T-cell (orange) signal the well holds at day 4, converted " +
        `to ≈ cells (signal area ÷ ${S.calibration.tcell.um2_per_cell} µm² per cell). Every T-cell well ` +
        "received 5000 T cells; darker = more T-cell signal remains detectable. " +
        "Wells without T cells show their orange background, which is small." },
    tcell_peak_z: { lbl: "T-cell peak layer", unit: "(z index)", d: 0,
      only: w => w.has_tcells,
      desc: "The z layer (z00–z16) that holds the most T-cell signal at day 4 — " +
        "where along the stack the T cells sit. Layers are ordinal: a higher " +
        "number is further from z00, but the distance between layers is not " +
        "recorded. Only wells that received T cells are coloured." },
    organoid_mm2: { lbl: "organoid territory", unit: "mm²", d: 2,
      desc: "The area of the well covered by dark (cellular) material in " +
        "brightfield at day 4, in mm² — the organoid mass's footprint, " +
        "independent of any stain. Darker = larger footprint." },
    growth: { lbl: "growth", unit: "× (day 4 / day 0)", d: 2,
      desc: "Footprint area at day 4 divided by the same well's footprint at " +
        "day 0. 1.0 = no change, 2.0 = doubled. Brightfield includes every dark " +
        "object, so this is growth of cellular mass, not of tumour specifically." },
    dead_mm2: { lbl: "dead-cell signal", unit: "mm²", d: 4,
      desc: "Dead-cell (NIR) signal area at day 4, in mm². The dye-only wells " +
        "(columns 10–12) did not receive the dead-cell dye and read zero." },
  };

  function quantiles(vals) {
    const v = vals.filter(x => x != null && isFinite(x)).sort((a, b) => a - b);
    if (!v.length) return [0, 1];
    const at = p => v[Math.min(v.length - 1, Math.max(0, Math.round(p * (v.length - 1))))];
    return [at(0.05), at(0.95)];
  }

  function build(key) {
    const M = METRICS[key];
    const active = S.wells.filter(w => !w.excluded && (!M.only || M.only(w)));
    const [lo, hi] = quantiles(active.map(w => w[key]));

    const color = v => {
      if (v == null || !isFinite(v)) return null;
      if (M.div != null) {
        // ıraksak: nötr orta noktadan iki yöne, her kol kendi aralığında
        const mid = M.div;
        if (Math.abs(v - mid) < 1e-9) return DIV_MID;
        if (v < mid) {
          const q = Math.min(1, (mid - v) / Math.max(mid - lo, 1e-9));
          return DIV_LO[DIV_LO.length - 1 - Math.min(DIV_LO.length - 1,
                        Math.floor(q * DIV_LO.length))];
        }
        const q = Math.min(1, (v - mid) / Math.max(hi - mid, 1e-9));
        return DIV_HI[Math.min(DIV_HI.length - 1, Math.floor(q * DIV_HI.length))];
      }
      const q = Math.min(1, Math.max(0, (v - lo) / Math.max(hi - lo, 1e-9)));
      return T.seq[Math.min(T.seq.length - 1, Math.floor(q * T.seq.length))];
    };

    const md = document.getElementById("metricdesc");
    if (md) md.textContent = M.desc || "";
    const plate = document.getElementById("plate");
    plate.replaceChildren();
    plate.append(el("div", "hd", ""));
    for (let c = 1; c <= COLS; c++) plate.append(el("div", "hd", String(c)));

    for (const r of ROWS) {
      plate.append(el("div", "rw", r));
      for (let c = 1; c <= COLS; c++) {
        const id = r + String(c).padStart(2, "0");
        const w = byWell.get(id);
        if (!w) { plate.append(el("div", "wellbox na", "")); continue; }
        const a = document.createElement("a");
        a.className = "wellbox" + (w.excluded ? " ex" : "");
        a.href = id + ".html";
        const col = color(w[key]);
        a.style.background = col || "#f2f1ee";
        if (!col) a.style.boxShadow = "inset 0 0 0 1px #e6e5e1";
        if (w.has_tcells) a.append(el("span", "tc", ""));
        const val = w[key] == null ? "not measured" : `${fmt(w[key], M.d)} ${M.unit}`;
        const note = M.only && !M.only(w) ? "<br><span class=\"k\">no T cells added — "
          + "this measure is not interpretable here</span>" : "";
        const info = `<b>${id}</b> · ${w.coculture}<br>` +
          `<span class="k">${w.compound}</span>` +
          (w.concentration != null ? ` ${fmt(w.concentration, null)} nM` : "") +
          (w.has_tcells ? "<br>+ T cells" : "") +
          (w.excluded ? "<br><span class=\"k\">excluded by QC</span>" : "") +
          `<br><br><span class="k">${M.lbl}</span> <b>${val}</b>` + note;
        bindTip(a, info);
        plate.append(a);
      }
    }

    document.getElementById("slo").textContent = fmt(lo, M.d);
    document.getElementById("shi").textContent = fmt(hi, M.d);
    const bar = document.getElementById("sbar");
    bar.style.background = M.div != null
      ? `linear-gradient(90deg, ${DIV_LO[0]}, ${DIV_MID} 50%, ${DIV_HI[DIV_HI.length - 1]})`
      : `linear-gradient(90deg, ${T.seq[0]}, ${T.seq[T.seq.length - 1]})`;
    document.getElementById("sbar").title = M.div != null
      ? "diverging scale, midpoint 1.0 = uniform scatter" : "sequential scale";
  }

  function el(tag, cls, txt) {
    const e = document.createElement(tag);
    e.className = cls; if (txt) e.textContent = txt;
    return e;
  }

  let tipEl;
  function bindTip(node, html) {
    node.addEventListener("pointerenter", e => show(html, e));
    node.addEventListener("pointermove", e => show(html, e));
    node.addEventListener("pointerleave", () => { if (tipEl) tipEl.style.display = "none"; });
  }
  function show(html, ev) {
    if (!tipEl) { tipEl = document.createElement("div"); tipEl.id = "tip";
                  document.body.append(tipEl); }
    tipEl.innerHTML = html; tipEl.style.display = "block";
    const r = tipEl.getBoundingClientRect();
    let x = ev.clientX + 14, y = ev.clientY - 10;
    if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - 14;
    if (y + r.height > innerHeight - 8) y = innerHeight - r.height - 8;
    tipEl.style.left = x + "px"; tipEl.style.top = Math.max(8, y) + "px";
  }

  document.getElementById("metric").addEventListener("change", e => build(e.target.value));
  build("tcells");

  window.SHOOT = {
    metric(k) { document.getElementById("metric").value = k; build(k); },
    scroll(y) { window.scrollTo(0, y); },
  };
})();
/* Screenshot hook — atlas/shoot.py drives the page through the URL fragment so
   the animations in the README come from the real page. Inert without #shoot=. */
(() => {
  const m = /#shoot=(.*)$/.exec(location.hash);
  if (!m) return;
  const run = () => { try { new Function(decodeURIComponent(m[1]))(); }
                      catch (e) { console.error("shoot", e); } };
  setTimeout(run, 350);
})();

