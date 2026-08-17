// inc_tests viewer — client. Channels arrive as separate 8-bit grayscale PNGs and
// are tinted + additively blended here, so colour/opacity changes are free and only
// contrast (which is applied server-side on float32 data) costs a round trip.

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const state = {
  meta: null,
  wells: [],            // per panel
  active: 0,
  panelCount: 1,
  t: 0,
  z: 8,
  // MIP by default: a single plane through a thick spheroid is mostly out-of-focus
  // haze, and the projection is what matches the instrument's own composite.
  mip: true,
  gamma: 1,
  umPerPx: 1.24,
  showScale: true,
  showProbe: true,
  chans: {},            // id -> {on, color, opacity, mode, lo, hi, bounds}
  view: { zoom: 1, cx: 0.5, cy: 0.5 },
  playing: false,
  fps: 4,
  plateColorBy: 'coculture',
  extraMode: false,
  advanced: false,
  mode: '2d',
  zStepUm: 10,
};

let panels = [];

// ------------------------------------------------------------------ bitmap cache
// Bounded by bytes, not count: a decoded 1040×1408 bitmap is ~5.9 MB, and four
// panels × four channels × 13 timepoints would be 1.2 GB if left uncapped.
// Evictions are cheap — the server keeps the decoded float32 planes, so a
// re-fetch is just a PNG re-encode (~80 ms).
const BITMAP_BUDGET = 600 * 1024 * 1024;
const bitmaps = new Map();  // key -> {bmp, lo, hi, bytes}
let bitmapBytes = 0;

function cacheGet(key) {
  const v = bitmaps.get(key);
  if (v) { bitmaps.delete(key); bitmaps.set(key, v); }
  return v;
}
function cachePut(key, v) {
  v.bytes = v.bmp.width * v.bmp.height * 4;
  bitmaps.set(key, v);
  bitmapBytes += v.bytes;
  while (bitmapBytes > BITMAP_BUDGET && bitmaps.size > 1) {
    const [k, old] = bitmaps.entries().next().value;
    bitmaps.delete(k);
    bitmapBytes -= old.bytes || 0;
    old.bmp?.close?.();
  }
}

const inflight = new Map();

// Plane and MIP frames have different background levels, so they carry separate stats.
function chanStat(id, mip) {
  const e = state.meta.ranges?.[id];
  if (!e) return null;
  return (mip ? e.mip : null) || e.plane || null;
}

// What to send as the display range. `bright` is the only knob in the simple UI:
// it narrows the window (brighter) without moving the black point.
//   rel:    black point = this frame's median → per-well background drift cancels,
//           gain measured across the plate so brightness stays comparable
//   abs:    fixed window — brightfield uses the instrument's own [57.5, 187.5]
//   auto:   per-frame percentiles
//   manual: user's numbers
function rangeParams(id, mip) {
  const c = state.chans[id];
  const b = Math.max(c.bright, 1e-3);
  if (c.mode === 'auto') return {};
  if (c.mode === 'manual') return { lo: c.lo, hi: c.hi };
  if (c.mode === 'abs') {
    const lo = c.absLo, hi = c.absHi;
    return { lo, hi: lo + (hi - lo) / b };
  }
  const s = chanStat(id, mip);
  if (!s) return {};
  return { off_lo: s.off_lo, off_hi: s.off_hi / b };
}

async function fetchLayer(well, ch, t, z, mip) {
  const rp = rangeParams(ch, mip);
  const sig = Object.entries(rp).map(([k, v]) => `${k}=${v}`).join(',') || 'auto';
  const key = `${well}|${ch}|${t}|${mip ? 'mip' : 'z' + z}|${sig}|g${state.gamma}`;
  const hit = cacheGet(key);
  if (hit) return hit;
  if (inflight.has(key)) return inflight.get(key);

  const q = new URLSearchParams({ t, z, mip: mip ? 1 : 0, gamma: state.gamma, ...rp });
  const p = (async () => {
    const res = await fetch(`/api/frame/${well}/${ch}?${q}`);
    if (!res.ok) throw new Error(`${ch} ${well} t${t}: ${res.status}`);
    const hdr = (res.headers.get('X-Range') || '').split(',').map(Number);
    const bmp = await createImageBitmap(await res.blob());
    const v = { bmp, lo: hdr[0], hi: hdr[1] };
    cachePut(key, v);
    return v;
  })().finally(() => inflight.delete(key));
  inflight.set(key, p);
  return p;
}

// ------------------------------------------------------------------------ panel
class Panel {
  constructor(index) {
    this.index = index;
    this.el = document.createElement('div');
    this.el.className = 'panel';
    this.canvas = document.createElement('canvas');
    this.ctx = this.canvas.getContext('2d');
    this.tag = document.createElement('div');
    this.tag.className = 'tag';
    this.probeEl = document.createElement('div');
    this.probeEl.className = 'probe';
    this.spin = document.createElement('div');
    this.spin.className = 'spin';
    this.el.append(this.canvas, this.tag, this.probeEl, this.spin);

    this.composed = document.createElement('canvas');
    this.cctx = this.composed.getContext('2d');
    this.iw = 0; this.ih = 0;
    this.token = 0;
    this.ranges = {};

    this.el.addEventListener('pointerdown', () => setActive(this.index));
    this.bindNav();
    new ResizeObserver(() => this.resize()).observe(this.el);
  }

  get well() { return state.wells[this.index]; }

  resize() {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    const w = Math.max(1, Math.round(this.el.clientWidth * dpr));
    const h = Math.max(1, Math.round(this.el.clientHeight * dpr));
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w; this.canvas.height = h;
    }
    this.draw();
  }

  baseScale() {
    if (!this.iw) return 1;
    return Math.min(this.canvas.width / this.iw, this.canvas.height / this.ih);
  }
  scale() { return this.baseScale() * state.view.zoom; }
  transform() {
    const s = this.scale();
    return {
      s,
      tx: this.canvas.width / 2 - state.view.cx * this.iw * s,
      ty: this.canvas.height / 2 - state.view.cy * this.ih * s,
    };
  }
  toImage(clientX, clientY) {
    const r = this.el.getBoundingClientRect();
    const dpr = this.canvas.width / r.width;
    const { s, tx, ty } = this.transform();
    return [((clientX - r.left) * dpr - tx) / s, ((clientY - r.top) * dpr - ty) / s];
  }

  // ---- data ----
  async load() {
    const my = ++this.token;
    const well = this.well;
    if (!well) return;
    this.spin.textContent = '…';

    if (state.extraMode && state.meta.extras?.well === well) {
      try {
        const res = await fetch(`/api/extra/${state.t}`);
        if (!res.ok) throw new Error(res.status);
        const bmp = await createImageBitmap(await res.blob());
        if (my !== this.token) { bmp.close(); return; }
        this.setSize(bmp.width, bmp.height);
        this.cctx.clearRect(0, 0, this.iw, this.ih);
        this.cctx.globalCompositeOperation = 'source-over';
        this.cctx.drawImage(bmp, 0, 0);
        bmp.close();
        this.ranges = {};
        this.spin.textContent = '';
        this.draw(); this.updateTag();
      } catch (e) { this.fail(e); }
      return;
    }

    const chans = state.meta.channels.filter(c => state.chans[c.id].on);
    if (!chans.length) {
      this.spin.textContent = '';
      this.iw && this.cctx.clearRect(0, 0, this.iw, this.ih);
      this.draw(); this.updateTag();
      return;
    }

    try {
      const got = await Promise.all(chans.map(async c => {
        const useZ = c.nz > 1 ? state.z : 0;
        const useMip = c.nz > 1 && state.mip;
        return [c, await fetchLayer(well, c.id, state.t, useZ, useMip)];
      }));
      if (my !== this.token) return;

      const first = got[0][1].bmp;
      this.setSize(first.width, first.height);
      const cx = this.cctx;
      cx.globalCompositeOperation = 'source-over';
      cx.globalAlpha = 1;
      cx.clearRect(0, 0, this.iw, this.ih);

      // Brightfield is the base layer; fluorescence adds light on top.
      const ordered = [...got].sort((a, b) => (b[0].base ? 1 : 0) - (a[0].base ? 1 : 0));
      this.ranges = {};
      let firstDrawn = true;
      for (const [c, layer] of ordered) {
        this.ranges[c.id] = [layer.lo, layer.hi];
        const st = state.chans[c.id];
        const tint = tintTo(layer.bmp, st.color, this.iw, this.ih);
        cx.globalAlpha = st.opacity;
        cx.globalCompositeOperation = (c.base && firstDrawn) ? 'source-over' : 'lighter';
        cx.drawImage(tint, 0, 0);
        firstDrawn = false;
      }
      cx.globalAlpha = 1;
      cx.globalCompositeOperation = 'source-over';
      this.spin.textContent = '';
      this.draw(); this.updateTag(); renderChannelRanges();
    } catch (e) { this.fail(e); }
  }

  fail(e) {
    this.spin.textContent = 'yüklenemedi';
    console.warn(e);
  }

  setSize(w, h) {
    if (this.iw !== w || this.ih !== h) {
      this.iw = w; this.ih = h;
      this.composed.width = w; this.composed.height = h;
    }
  }

  // ---- render ----
  draw() {
    const ctx = this.ctx;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    if (!this.iw) return;
    const { s, tx, ty } = this.transform();
    ctx.imageSmoothingEnabled = s < 2;
    ctx.drawImage(this.composed, tx, ty, this.iw * s, this.ih * s);
    if (state.showScale) this.drawScale(s);
  }

  drawScale(s) {
    const ctx = this.ctx;
    const dpr = Math.min(devicePixelRatio || 1, 2);
    const targetPx = 110 * dpr;
    const want = targetPx / s * state.umPerPx;
    const steps = [5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000];
    const um = steps.reduce((a, b) => Math.abs(b - want) < Math.abs(a - want) ? b : a);
    const px = um / state.umPerPx * s;
    const x = this.canvas.width - px - 12 * dpr;
    const y = this.canvas.height - 16 * dpr;
    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,.5)';
    ctx.fillRect(x - 6 * dpr, y - 13 * dpr, px + 12 * dpr, 24 * dpr);
    ctx.fillStyle = '#fff';
    ctx.fillRect(x, y, px, 2.5 * dpr);
    ctx.font = `${11 * dpr}px ui-monospace, monospace`;
    ctx.textAlign = 'center';
    ctx.fillText(um >= 1000 ? `${um / 1000} mm` : `${um} µm`, x + px / 2, y - 3 * dpr);
    ctx.restore();
  }

  updateTag() {
    const well = this.well;
    const cond = state.meta.plate?.[well]?.condition || '';
    this.tag.innerHTML = `<b>${well ?? '—'}</b><span class="cond">${cond}</span>`;
  }

  // ---- interaction ----
  bindNav() {
    const cv = this.canvas;
    let drag = null;

    cv.addEventListener('pointerdown', e => {
      if (e.button !== 0) return;
      drag = { x: e.clientX, y: e.clientY };
      cv.classList.add('drag');
      cv.setPointerCapture(e.pointerId);
    });
    cv.addEventListener('pointermove', e => {
      if (drag) {
        const dpr = this.canvas.width / this.el.clientWidth;
        const s = this.scale();
        state.view.cx -= (e.clientX - drag.x) * dpr / (this.iw * s);
        state.view.cy -= (e.clientY - drag.y) * dpr / (this.ih * s);
        clampView();
        drag = { x: e.clientX, y: e.clientY };
        drawAll();
      } else if (state.showProbe) {
        this.probeAt(e.clientX, e.clientY);
      }
    });
    const end = e => {
      if (!drag) return;
      drag = null; cv.classList.remove('drag');
      cv.releasePointerCapture?.(e.pointerId);
    };
    cv.addEventListener('pointerup', end);
    cv.addEventListener('pointercancel', end);
    cv.addEventListener('pointerleave', () => { this.probeEl.textContent = ''; });

    cv.addEventListener('wheel', e => {
      e.preventDefault();
      if (!this.iw) return;
      const [ix, iy] = this.toImage(e.clientX, e.clientY);
      const f = Math.exp(-e.deltaY * 0.0016);
      const z = Math.min(40, Math.max(1, state.view.zoom * f));
      if (z === state.view.zoom) return;
      // keep the point under the cursor fixed
      const r = this.el.getBoundingClientRect();
      const dpr = this.canvas.width / r.width;
      const px = (e.clientX - r.left) * dpr, py = (e.clientY - r.top) * dpr;
      const ns = this.baseScale() * z;
      state.view.zoom = z;
      state.view.cx = (ix * ns - px + this.canvas.width / 2) / (this.iw * ns);
      state.view.cy = (iy * ns - py + this.canvas.height / 2) / (this.ih * ns);
      clampView();
      drawAll();
    }, { passive: false });
  }

  probeAt(clientX, clientY) {
    const now = performance.now();
    if (now - (this._probeAt || 0) < 110) return;
    this._probeAt = now;
    if (!this.iw || !this.well) return;
    const [ix, iy] = this.toImage(clientX, clientY);
    const x = Math.round(ix), y = Math.round(iy);
    if (x < 0 || y < 0 || x >= this.iw || y >= this.ih) { this.probeEl.textContent = ''; return; }
    const q = new URLSearchParams({ t: state.t, z: state.z, mip: state.mip ? 1 : 0, x, y });
    fetch(`/api/pixel/${this.well}?${q}`).then(r => r.json()).then(d => {
      const lines = [`x${x} y${y}`];
      for (const c of state.meta.channels) {
        if (d.values[c.id] == null) continue;
        lines.push(`${c.id.padEnd(6)} ${fmt(d.values[c.id])}`);
      }
      this.probeEl.textContent = lines.join('\n');
    }).catch(() => {});
  }
}

// tint a grayscale bitmap with a colour: result = gray * colour
const tintCv = document.createElement('canvas');
const tintCtx = tintCv.getContext('2d');
function tintTo(bmp, color, w, h) {
  if (tintCv.width !== w || tintCv.height !== h) { tintCv.width = w; tintCv.height = h; }
  tintCtx.globalCompositeOperation = 'source-over';
  tintCtx.globalAlpha = 1;
  tintCtx.clearRect(0, 0, w, h);
  tintCtx.drawImage(bmp, 0, 0);
  if (color.toLowerCase() !== '#ffffff') {
    tintCtx.globalCompositeOperation = 'multiply';
    tintCtx.fillStyle = color;
    tintCtx.fillRect(0, 0, w, h);
  }
  return tintCv;
}

function clampView() {
  const m = 0.25 / state.view.zoom;
  state.view.cx = Math.min(1 + m, Math.max(-m, state.view.cx));
  state.view.cy = Math.min(1 + m, Math.max(-m, state.view.cy));
}

const fmt = v => Math.abs(v) >= 100 ? v.toFixed(0)
  : Math.abs(v) >= 1 ? v.toFixed(2) : v.toFixed(3);

function drawAll() { panels.forEach(p => p.draw()); }
function loadAll() { panels.forEach(p => p.load()); prefetch(); }

// ---------------------------------------------------------------------- prefetch
function prefetch() {
  const p = panels[state.active];
  if (!p?.well) return;
  const chans = state.meta.channels.filter(c => state.chans[c.id].on);
  const jobs = [];
  for (const dt of [1, -1]) {
    const t = state.t + dt;
    if (t < 0 || t >= state.meta.timepoints.length) continue;
    for (const c of chans) jobs.push([c, t, c.nz > 1 ? state.z : 0]);
  }
  if (!state.mip) {
    for (const dz of [1, -1]) {
      const z = state.z + dz;
      if (z < 0 || z >= state.meta.nz) continue;
      for (const c of chans) if (c.nz > 1) jobs.push([c, state.t, z]);
    }
  }
  jobs.slice(0, 12).forEach(([c, t, z]) =>
    fetchLayer(p.well, c.id, t, z, c.nz > 1 && state.mip).catch(() => {}));
}

// ------------------------------------------------------------------------ panels
function buildPanels() {
  const host = $('#panels');
  host.className = `panels p${state.panelCount}`;
  host.innerHTML = '';
  panels.forEach(p => p.token++);
  panels = [];
  for (let i = 0; i < state.panelCount; i++) {
    const p = new Panel(i);
    panels.push(p);
    host.append(p.el);
  }
  if (state.active >= state.panelCount) state.active = 0;
  markActive();
  requestAnimationFrame(() => { panels.forEach(p => p.resize()); loadAll(); });
}

function setActive(i) {
  state.active = i;
  markActive();
  renderWellInfo();
  renderPlateSelection();
  renderStamp();
  renderSeriesBox();
  if (state.mode === '3d') { render3d(); loadProfile(); }
}
function markActive() {
  panels.forEach((p, i) => p.el.classList.toggle('active', i === state.active));
}

// ------------------------------------------------------------------------- plate
const PALETTES = {
  coculture: { 'PDA': '#4c9ffe', 'PDA+CAF': '#39c5a6', 'PDA+MAC': '#c98cff', 'PDA+CAF+MAC': '#ffb020' },
  compound: {
    'control': '#6b7a90', 'Dye': '#8b93a3', 'kras low': '#4c9ffe', 'kras high': '#1f6fd0',
    'Src low': '#39c5a6', 'Src high': '#12876d', 'low kras+Src': '#ffb020', 'high kras+Src': '#ff6b3d',
  },
  t_cells: { 'T hücreli': '#ff6b8a', 'T hücresiz': '#3a4250' },
};

function wellCategory(well) {
  const row = state.meta.plate?.[well];
  if (!row) return null;
  if (state.plateColorBy === 't_cells') return row.t_cells ? 'T hücreli' : 'T hücresiz';
  return row[state.plateColorBy] || null;
}

function buildPlate() {
  const el = $('#plate');
  el.innerHTML = '';
  const rows = state.meta.rows, cols = state.meta.cols;
  const maxCol = Math.max(...cols, 12);
  el.style.gridTemplateColumns = `14px repeat(${maxCol}, 1fr)`;
  el.append(cell('div', 'hdr', ''));
  for (let c = 1; c <= maxCol; c++) el.append(cell('div', 'hdr', String(c)));

  for (const r of rows) {
    el.append(cell('div', 'rowhdr', r));
    for (let c = 1; c <= maxCol; c++) {
      const well = `${r}${String(c).padStart(2, '0')}`;
      const known = state.meta.wells.includes(well);
      const b = document.createElement('button');
      b.className = 'well' + (known ? '' : ' off');
      b.dataset.well = well;
      if (state.meta.extras?.well === well) b.classList.add('extra');
      if (known) {
        b.addEventListener('click', e => pickWell(well, e.shiftKey));
        b.addEventListener('mouseenter', e => showTip(e, wellTip(well)));
        b.addEventListener('mouseleave', hideTip);
      } else {
        b.title = `${well} · görüntülenmedi`;
      }
      el.append(b);
    }
  }
  paintPlate();
}

function cell(tag, cls, txt) {
  const e = document.createElement(tag);
  e.className = cls; e.textContent = txt;
  return e;
}

function paintPlate() {
  const pal = PALETTES[state.plateColorBy];
  for (const b of $$('#plate .well')) {
    const well = b.dataset.well;
    if (b.classList.contains('off')) { b.style.background = ''; continue; }
    const cat = wellCategory(well);
    b.style.background = pal[cat] || '#3a4250';
  }
  const used = new Set(state.meta.wells.map(wellCategory));
  $('#plateLegend').innerHTML = Object.entries(pal)
    .filter(([k]) => used.has(k))
    .map(([k, v]) => `<span><i style="background:${v}"></i>${k}</span>`).join('');
  renderPlateSelection();
}

function renderPlateSelection() {
  const shown = state.wells.slice(0, state.panelCount);
  for (const b of $$('#plate .well')) {
    const i = shown.indexOf(b.dataset.well);
    b.classList.toggle('sel', i >= 0);
    const q = b.querySelector('.idx');
    if (i >= 0 && state.panelCount > 1) {
      if (q) q.textContent = i + 1;
      else { const s = document.createElement('span'); s.className = 'idx'; s.textContent = i + 1; b.append(s); }
    } else q?.remove();
  }
}

function wellTip(well) {
  const r = state.meta.plate?.[well];
  if (!r) return well;
  const bits = [`<b>${well}</b>`, r.condition];
  if (r.cafs) bits.push(`CAF ${r.cafs}`);
  if (r.macrophages) bits.push(`MAC ${r.macrophages}`);
  if (r.t_cells) bits.push(`T ${r.t_cells}`);
  if (state.meta.extras?.well === well) bits.push('<i>VID119 kompozit var</i>');
  return bits.join('<br>');
}

function pickWell(well, shift) {
  if (shift && state.panelCount > 1) {
    const slot = (state.active + 1) % state.panelCount;
    state.wells[slot] = well;
    setActive(slot);
    panels[slot].load();
  } else {
    state.wells[state.active] = well;
    panels[state.active].load();
    renderWellInfo(); renderPlateSelection(); renderStamp(); renderSeriesBox();
    if (state.mode === '3d') { render3d(); loadProfile(); }
  }
  updateExtraButton();
}

function renderWellInfo() {
  const well = panels[state.active]?.well;
  const r = state.meta.plate?.[well];
  const rows = [];
  if (r) {
    rows.push(['kuyu', well]);
    rows.push(['koşul', r.condition]);
    if (r.pda_30364) rows.push(['PDA 30364', `${r.pda_30364} hücre`]);
    if (r.cafs) rows.push(['CAFs', `${r.cafs} hücre`]);
    if (r.macrophages) rows.push(['Macrophages', `${r.macrophages} hücre`]);
    rows.push(['T hücresi', r.t_cells ? `${r.t_cells} hücre` : '—']);
    if (r.compound) rows.push(['bileşik', `${r.compound} ${r.concentration} ${r.concentration_units}`]);
  } else if (well) rows.push(['kuyu', well]);
  $('#wellInfo').innerHTML = rows
    .map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('');
}

// ---------------------------------------------------------------------- channels
// Defaults come from the server (/api/meta → defaults), which encodes what was
// measured against the instrument's own composite export.
function defaultChanState(c) {
  const d = state.meta.defaults?.[c.id] || {};
  const s = state.meta.ranges?.[c.id]?.plane;
  return {
    on: true,
    color: c.color,
    bright: 1,
    opacity: d.opacity ?? 1,
    mode: d.mode || (s ? 'rel' : 'auto'),
    absLo: d.lo ?? s?.lo ?? 0,
    absHi: d.hi ?? s?.hi ?? 1,
    lo: d.lo ?? s?.lo ?? 0,
    hi: d.hi ?? s?.hi ?? 1,
  };
}

function resetDisplay() {
  state.meta.channels.forEach(c => {
    const keep = state.chans[c.id].on;
    state.chans[c.id] = { ...defaultChanState(c), on: keep };
  });
  state.gamma = 1;
  $('#gamma').value = 1;
  $('#gammaOut').textContent = '1.00';
  buildChannels();
  loadAll();
}

function buildChannels() {
  const host = $('#channels');
  host.innerHTML = '';
  state.meta.channels.forEach((c, i) => {
    const st = state.chans[c.id];
    const d = document.createElement('div');
    d.className = 'chan' + (st.on ? '' : ' off');
    d.dataset.ch = c.id;
    d.innerHTML = `
      <div class="chanhead">
        <input type="checkbox" ${st.on ? 'checked' : ''} class="on" title="görünürlük">
        <input type="color" class="sw" value="${st.color}" title="renk">
        <span class="nm">${c.label}</span>
        <span class="key">${i + 1}</span>
        <span class="det">${c.nz > 1 ? c.nz + ' z' : '1 z'}</span>
      </div>
      <div class="chanbody">
        <div class="crow">
          <label>parlaklık</label>
          <input type="range" class="bright" min="-1" max="1" step="0.02"
                 value="${Math.log2(st.bright) / 2}">
          <span class="val bright-val">${brightLabel(st.bright)}</span>
        </div>
        <div class="crow adv">
          <label>opak</label>
          <input type="range" class="op" min="0" max="1" step="0.02" value="${st.opacity}">
          <span class="val op-val">${st.opacity.toFixed(2)}</span>
        </div>
        <div class="crow adv">
          <label>ölçek</label>
          <div class="modes">
            <button data-mode="rel" title="siyah nokta = kare arkaplanı">arkaplan</button>
            <button data-mode="abs" title="sabit mutlak pencere">mutlak</button>
            <button data-mode="auto" title="bu kareye göre yüzdelik">oto</button>
            <button data-mode="manual">elle</button>
          </div>
        </div>
        <div class="crow adv r-manual">
          <label>min</label>
          <input type="range" class="lo" min="0" max="1000" step="1" value="0">
          <span class="val lo-val">—</span>
        </div>
        <div class="crow adv r-manual">
          <label>max</label>
          <input type="range" class="hi" min="0" max="1000" step="1" value="1000">
          <span class="val hi-val">—</span>
        </div>
        <div class="crow adv applied">
          <label>uygulanan</label>
          <span class="val wide-val">—</span>
        </div>
      </div>`;
    host.append(d);

    const body = $('.chanbody', d);
    $('.on', d).addEventListener('change', e => {
      st.on = e.target.checked;
      d.classList.toggle('off', !st.on);
      if (state.mode === '3d') render3d(); else loadAll();
    });
    $('.sw', d).addEventListener('input', e => { st.color = e.target.value; loadAll(); });
    const op = $('.op', d);
    op.addEventListener('input', e => {
      st.opacity = +e.target.value;
      $('.op-val', d).textContent = st.opacity.toFixed(2);
      loadAll();
    });

    const bright = $('.bright', d);
    const pushBright = debounce(loadAll, 150);
    bright.addEventListener('input', () => {
      st.bright = Math.pow(2, +bright.value * 2);   // ×0.25 … ×4
      $('.bright-val', d).textContent = brightLabel(st.bright);
      pushBright();
    });

    const b = channelBounds(c.id);
    const toVal = v => b.min + (v / 1000) * (b.max - b.min);
    const toSlider = v => Math.round((v - b.min) / (b.max - b.min) * 1000);
    const lo = $('.lo', d), hi = $('.hi', d);
    const push = debounce(loadAll, 150);
    lo.addEventListener('input', () => {
      st.lo = toVal(+lo.value);
      if (st.lo >= st.hi) { st.hi = st.lo + (b.max - b.min) / 1000; hi.value = toSlider(st.hi); }
      renderChannelRanges(); push();
    });
    hi.addEventListener('input', () => {
      st.hi = toVal(+hi.value);
      if (st.hi <= st.lo) { st.lo = st.hi - (b.max - b.min) / 1000; lo.value = toSlider(st.lo); }
      renderChannelRanges(); push();
    });
    d._sliders = { lo, hi, toSlider };

    $$('.modes button', d).forEach(btn => btn.addEventListener('click', () => {
      const mode = btn.dataset.mode;
      if (mode === 'manual') {
        // seed the manual sliders from whatever is on screen right now
        const r = panels[state.active]?.ranges[c.id];
        if (r) { st.lo = r[0]; st.hi = r[1]; }
      }
      setMode(c.id, mode);
      loadAll();
    }));
  });
  renderChannelModes();
  renderChannelRanges();
}

function channelBounds(id) {
  const s = chanStat(id, false);
  if (s) {
    // slider_max, not the absolute max: a handful of very bright pixels would
    // otherwise squeeze the whole useful range into the first 3% of slider travel.
    return { min: state.meta.ranges[id].min ?? 0, max: (s.slider_max || s.hi * 4) || 1 };
  }
  const r = panels[state.active]?.ranges[id];
  if (r) return { min: 0, max: Math.max(r[1] * 2, 1) };
  return { min: 0, max: 255 };
}

function setMode(id, mode) {
  state.chans[id].mode = mode;
  renderChannelModes();
}
const brightLabel = v => (Math.abs(v - 1) < 0.03 ? 'normal' : `×${v.toFixed(2)}`);

function renderChannelModes() {
  for (const d of $$('.chan')) {
    const st = state.chans[d.dataset.ch];
    $$('.modes button', d).forEach(b => b.classList.toggle('on', b.dataset.mode === st.mode));
    // advanced rows only when the advanced panel is open; manual rows only in manual mode
    $$('.adv', d).forEach(r => r.classList.toggle('hidden',
      !state.advanced || (r.classList.contains('r-manual') && st.mode !== 'manual')));
    $('.bright', d).disabled = st.mode === 'auto' || st.mode === 'manual';
  }
}

function renderChannelRanges() {
  const p = panels[state.active];
  for (const d of $$('.chan')) {
    const id = d.dataset.ch, st = state.chans[id];
    const applied = st.mode === 'manual' ? [st.lo, st.hi] : (p?.ranges[id] || null);
    $('.wide-val', d).textContent = applied ? `${fmt(applied[0])} – ${fmt(applied[1])}` : '—';
    $('.lo-val', d).textContent = applied ? fmt(applied[0]) : '—';
    $('.hi-val', d).textContent = applied ? fmt(applied[1]) : '—';
    if (applied && d._sliders && st.mode === 'manual') {
      d._sliders.lo.value = d._sliders.toSlider(applied[0]);
      d._sliders.hi.value = d._sliders.toSlider(applied[1]);
    }
  }
}

// ---------------------------------------------------------------------- timeline
function buildTimeline() {
  const tps = state.meta.timepoints;
  const ts = $('#tSlider');
  ts.max = tps.length - 1;
  ts.value = state.t;
  ts.addEventListener('input', () => { state.t = +ts.value; onTimeChange(); });

  const zs = $('#zSlider');
  zs.max = Math.max(0, state.meta.nz - 1);
  zs.value = state.z;
  zs.addEventListener('input', () => { state.z = +zs.value; onZChange(); });

  const ticks = $('#ticks');
  ticks.innerHTML = '';
  let lastDay = '';
  tps.forEach((tp, i) => {
    const day = tp.datetime.slice(0, 10);
    if (day === lastDay) return;
    lastDay = day;
    const s = document.createElement('span');
    s.style.left = `${(i / Math.max(1, tps.length - 1)) * 100}%`;
    s.textContent = day.slice(8) + '.' + day.slice(5, 7);
    ticks.append(s);
  });
  renderStamp();
}

function onTimeChange() {
  renderStamp(); markSeriesCursor();
  if (state.mode === '3d') { render3d(); loadProfile(); } else loadAll();
}
function onZChange() { renderStamp(); loadAll(); }

function renderStamp() {
  const tp = state.meta.timepoints[state.t];
  $('#tLabel').textContent = tp.t;
  $('#tClock').textContent = `${tp.datetime.replace('T', ' ')}  (+${tp.hours}s)`;
  $('#tSlider').value = state.t;
  $('#zSlider').value = state.z;
  $('#zSlider').disabled = state.mip;
  $('#zLabel').textContent = state.mip ? 'MIP' : `z${String(state.z).padStart(2, '0')}`;
  $('#stampWell').textContent = panels[state.active]?.well ?? '—';
  $('#stampTime').textContent = tp.datetime.replace('T', ' ');
  $('#stampZ').textContent = state.mip ? 'MIP' : `z${String(state.z).padStart(2, '0')}`;
}

let playGen = 0;

async function togglePlay() {
  state.playing = !state.playing;
  $('#btnPlay').textContent = state.playing ? '❚❚' : '▶';
  const gen = ++playGen;          // a second click must not leave two loops running
  if (!state.playing) { hideToast(); return; }

  const wells = state.wells.slice(0, state.panelCount).filter(Boolean);
  const chans = state.meta.channels.filter(c => state.chans[c.id].on);
  const total = state.meta.timepoints.length;
  for (const tp of state.meta.timepoints) {
    if (gen !== playGen) return;
    toast(`kareler önbelleğe alınıyor… ${tp.index + 1}/${total}`);
    await Promise.all(wells.flatMap(w => chans.map(c =>
      fetchLayer(w, c.id, tp.index, c.nz > 1 ? state.z : 0, c.nz > 1 && state.mip)
        .catch(() => {}))));
  }
  hideToast();

  const step = () => {
    if (gen !== playGen || !state.playing) return;
    state.t = (state.t + 1) % total;
    onTimeChange();
    setTimeout(step, 1000 / Math.max(1, state.fps));
  };
  setTimeout(step, 1000 / Math.max(1, state.fps));
}

// ------------------------------------------------------------------ well series
const SERIES_COLORS = { bf: '#8b93a3', green: '#3ddc50', orange: '#ff8a2b', nir: '#ff3b6b' };
let seriesData = null;

function renderSeriesBox() {
  seriesData = null;
  $('#seriesBox').innerHTML =
    `<button id="btnSeries" class="wide">bu kuyuyu ölç</button>
     <div class="hint">z-yığınları taranır; ilk ölçüm yavaş, sonra önbellekten.</div>`;
  $('#btnSeries').addEventListener('click', loadSeries);
}

async function loadSeries() {
  const well = panels[state.active]?.well;
  if (!well) return;
  const btn = $('#btnSeries');
  btn.disabled = true; btn.textContent = 'ölçülüyor…';
  try {
    const res = await fetch(`/api/wellseries/${well}`);
    seriesData = await res.json();
    drawSeries();
  } catch (e) {
    btn.disabled = false; btn.textContent = 'tekrar dene';
    console.warn(e);
  }
}

function drawSeries() {
  if (!seriesData) return;
  const metric = $('#seriesMetric').value;
  const tps = state.meta.timepoints;
  const series = Object.entries(seriesData.channels)
    .map(([id, v]) => [id, v[metric]])
    .filter(([, arr]) => arr && arr.some(x => x != null));
  if (!series.length) { $('#seriesBox').innerHTML = '<div class="hint">veri yok</div>'; return; }

  const W = 300, H = 96, pad = { l: 4, r: 4, t: 8, b: 14 };
  const x = i => pad.l + (i / Math.max(1, tps.length - 1)) * (W - pad.l - pad.r);
  const parts = [];
  for (const [id, arr] of series) {
    const vals = arr.filter(v => v != null);
    const mn = Math.min(...vals), mx = Math.max(...vals);
    const y = v => H - pad.b - ((v - mn) / ((mx - mn) || 1)) * (H - pad.t - pad.b);
    const pts = arr.map((v, i) => v == null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`)
      .filter(Boolean).join(' ');
    parts.push(`<polyline points="${pts}" fill="none" stroke="${SERIES_COLORS[id]}"
      stroke-width="1.6" stroke-linejoin="round"/>`);
  }
  $('#seriesBox').innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
      <line id="scur" x1="0" x2="0" y1="${pad.t - 4}" y2="${H - pad.b + 3}"
            stroke="#4c9ffe" stroke-width="1"/>
      ${parts.join('')}
      <text x="${pad.l}" y="${H - 3}" fill="#8b93a3" font-size="8">t00</text>
      <text x="${W - pad.r}" y="${H - 3}" fill="#8b93a3" font-size="8"
            text-anchor="end">t${String(tps.length - 1).padStart(2, '0')}</text>
    </svg>
    <div class="slegend">${series.map(([id]) =>
      `<span><i style="background:${SERIES_COLORS[id]}"></i>${id}</span>`).join('')}</div>
    <div class="hint">${seriesData.well} · arkaplan (kare medyanı) çıkarılmış ·
      her kanal kendi ölçeğinde normalize</div>`;
  markSeriesCursor();
}

function markSeriesCursor() {
  const line = $('#scur');
  if (!line) return;
  const tps = state.meta.timepoints;
  const W = 300, pad = { l: 4, r: 4 };
  const px = pad.l + (state.t / Math.max(1, tps.length - 1)) * (W - pad.l - pad.r);
  line.setAttribute('x1', px); line.setAttribute('x2', px);
}

// ------------------------------------------------------------------ 3D / depth
// Three views over the same stack, in increasing order of assumption:
//   depth  — colour says which layer the signal came from. No geometry assumed.
//   ortho  — vertical cut; needs the z step to be right for the aspect ratio.
//   proj   — rotatable parallel projection; same, plus an optional exaggeration.
const TURBO_CSS = ['#30123b', '#3d54b3', '#2796eb', '#1ec8be', '#5ee369',
                   '#bcea37', '#f7be2d', '#f67420', '#cf3012', '#7a0403'];

const v3d = { view: 'dome', el: 60, az: 0, zex: 1, crop: false, ch: 'green',
              yz: false, token: 0 };

// Radial bands, blue (dome centre) to red (well outside) — matches the dots the
// server draws, so the chart and the picture read as one thing.
const BAND_COLORS = ['#5affff', '#3cdcff', '#5ac8ff', '#8caaff', '#ffaa5a', '#ff5a5a'];

function enabledStackChannels() {
  return state.meta.channels.filter(c => c.nz > 1 && state.chans[c.id].on).map(c => c.id);
}

function set3dView(view) {
  v3d.view = view;
  $$('#view3dSeg button').forEach(b => b.classList.toggle('on', b.dataset.view === view));
  $$('.v3d-proj').forEach(e => { e.hidden = view !== 'proj'; });
  $$('.v3d-ortho').forEach(e => { e.hidden = view !== 'ortho'; });
  $('#depthCh').style.display = view === 'depth' ? '' : 'none';
  $('#depthLegend').hidden = view !== 'depth';
  $('#domeBox').hidden = view !== 'dome';
  $('#zBox').hidden = view === 'dome';
  render3d();
  if (view === 'dome') loadDome();
}

function render3d() {
  const well = panels[state.active]?.well;
  if (!well || state.mode !== '3d') return;
  const img = $('#v3dimg');
  const chans = enabledStackChannels();
  const hint = $('#v3dhint');

  if (!chans.length && v3d.view !== 'depth') {
    img.removeAttribute('src');
    hint.textContent = 'z-stack kanallarının hepsi kapalı';
    return;
  }

  let url;
  if (v3d.view === 'dome') {
    url = `/api/domeview/${well}?t=${state.t}&channels=${
      ['orange', 'nir'].filter(c => state.chans[c]?.on).join(',') || 'orange'}`;
    hint.textContent = 'Sarı daire = dome sınırı (R90) ve R50 · daire = T hücresi, kare = ölü hücre';
  } else if (v3d.view === 'depth') {
    url = `/api/depth/${well}/${v3d.ch}?t=${state.t}`;
    hint.textContent = 'Renk = sinyalin ağırlıklı ortalama katmanı. Geometri varsayımı yok.';
  } else if (v3d.view === 'ortho') {
    url = `/api/ortho/${well}?t=${state.t}&plane=${v3d.yz ? 'yz' : 'xz'}`
        + `&channels=${chans.join(',')}&z_step_um=${state.zStepUm}`;
    hint.textContent = `Dikey kesit · z adımı ${state.zStepUm} µm varsayımıyla ölçekli`;
  } else {
    url = `/api/render3d/${well}?t=${state.t}&el=${v3d.el}&az=${v3d.az}`
        + `&channels=${chans.join(',')}&z_step_um=${state.zStepUm}`
        + `&z_exag=${v3d.zex}&crop=${v3d.crop ? 1 : 0}`;
    hint.textContent = `17 düzlem × ${state.zStepUm} µm = ${(17 * state.zStepUm).toFixed(0)} µm kalınlık`
      + (v3d.zex > 1 ? ` · z ×${v3d.zex} abartılı (gerçek geometri değil)` : '');
  }

  const my = ++v3d.token;
  img.classList.add('busy');
  $('#v3dspin').textContent = '…';
  const probe = new Image();
  probe.onload = () => {
    if (my !== v3d.token) return;
    img.src = probe.src;
    img.classList.remove('busy');
    $('#v3dspin').textContent = '';
  };
  probe.onerror = () => {
    if (my !== v3d.token) return;
    img.classList.remove('busy');
    $('#v3dspin').textContent = 'bu kuyu/zaman için yok';
  };
  probe.src = url;
}

function buildDepthLegend() {
  const stops = TURBO_CSS.map((c, i) =>
    `${c} ${(i / (TURBO_CSS.length - 1) * 100).toFixed(0)}%`).join(', ');
  const nz = state.meta.nz;
  const um = state.zStepUm;
  $('#depthLegend').innerHTML = `
    <div>katman (z)</div>
    <div class="bar" style="background:linear-gradient(90deg,${stops})"></div>
    <div class="ends"><span>z00</span><span>z${String(nz - 1).padStart(2, '0')}</span></div>
    <div class="ends"><span>0 µm</span><span>${((nz - 1) * um).toFixed(0)} µm *</span></div>
    <div style="margin-top:3px">* z adımı ${um} µm varsayımı</div>`;
}

async function loadDome() {
  const well = panels[state.active]?.well;
  if (!well || state.mode !== '3d') return;
  $('#domeSummary').innerHTML = '<div class="hint">ölçülüyor…</div>';
  try {
    const d = await (await fetch(`/api/dome/${well}?t=${state.t}`)).json();
    if (d.detail) throw new Error(d.detail);
    drawDome(d);
  } catch (e) {
    $('#domeSummary').innerHTML = `<div class="hint">ölçülemedi: ${e.message || e}</div>`;
    $('#domeChart').innerHTML = '';
  }
}

const CH_LABEL = { green: 'tümör', orange: 'T hücresi', nir: 'ölü hücre' };

function drawDome(d) {
  const dm = d.dome;
  const rows = [];
  rows.push(`<table class="kv">
    <tr><td>dome yarıçapı</td><td><b>${dm.r90_um.toFixed(0)} µm</b> (R90)</td></tr>
    <tr><td>çekirdek</td><td>${dm.r50_um.toFixed(0)} µm (R50)</td></tr>
    <tr><td>dome alanı</td><td>${dm.area_mm2.toFixed(2)} mm²</td></tr>
    <tr><td>şekil faktörü</td><td>${dm.shape_factor}</td></tr></table>`);

  for (const ch of ['orange', 'nir', 'green']) {
    const c = d.channels[ch];
    if (!c) continue;
    const ratio = c.ratio == null ? '—' : c.ratio.toFixed(2);
    const verdict = c.ratio == null ? ''
      : c.ratio < 0.5 ? 'dışlanmış' : c.ratio > 1.5 ? 'dome içinde yoğunlaşmış' : 'yaklaşık homojen';
    rows.push(`<div class="domerow">
      <div class="domehead"><i style="background:${state.chans[ch]?.color}"></i>
        <b>${CH_LABEL[ch]}</b> · ${c.count} nesne</div>
      <div class="hint">dome içinde <b>%${((c.frac_inside ?? 0) * 100).toFixed(0)}</b> ·
        iç/dış yoğunluk oranı <b>${ratio}</b> ${verdict ? '· ' + verdict : ''} ·
        medyan u=${c.median_u ?? '—'}</div></div>`);
  }
  $('#domeSummary').innerHTML = rows.join('');

  // density per band, per channel
  const chans = ['orange', 'nir', 'green'].filter(c => d.channels[c]);
  const maxD = Math.max(1e-9, ...chans.flatMap(c =>
    d.channels[c].density_mm2.map(v => v ?? 0)));
  const bars = d.bands.map((lab, i) => {
    const seg = chans.map(c => {
      const v = d.channels[c].density_mm2[i] ?? 0;
      const n = d.channels[c].counts[i] ?? 0;
      return `<div class="dbar" style="width:${Math.max(0.5, v / maxD * 100)}%;
              background:${state.chans[c]?.color}" title="${CH_LABEL[c]}: ${n} nesne,
              ${v.toFixed(1)}/mm²"></div>`;
    }).join('');
    const inside = i < 4;
    return `<div class="drow${inside ? ' in' : ''}">
      <span class="dlab" style="color:${BAND_COLORS[i]}">${lab}</span>
      <div class="dbars">${seg}</div></div>`;
  }).join('');
  $('#domeChart').innerHTML = bars;
  $('#domeHint').innerHTML = `Çubuklar <b>yoğunluk</b> (nesne/mm²), sayım değil —
    dış bantlar çok daha geniş alan kaplar. İlk dört bant dome içi.
    Oran 1 = homojen dağılım, &lt;1 dışlanma, &gt;1 zenginleşme.`;
}

async function loadProfile() {
  const well = panels[state.active]?.well;
  if (!well || state.mode !== '3d') return;
  $('#zsummary').textContent = 'ölçülüyor…';
  try {
    const d = await (await fetch(`/api/zprofile/${well}?t=${state.t}`)).json();
    drawProfile(d);
  } catch (e) {
    $('#zsummary').textContent = 'ölçülemedi';
  }
}

function drawProfile(d) {
  const chans = state.meta.channels.filter(c => d.channels[c.id]);
  const nz = Math.max(...chans.map(c => d.channels[c.id].share.length), 1);
  const maxShare = Math.max(0.01, ...chans.flatMap(c => d.channels[c.id].share));
  const rows = [];
  for (let z = 0; z < nz; z++) {
    const isFocus = chans.some(c => d.channels[c.id].focus_z === z);
    const bars = chans.map(c => {
      const v = d.channels[c.id].share[z] ?? 0;
      const w = Math.max(1, (v / maxShare) * 100);
      return `<div class="zbar" style="width:${w}%;background:${state.chans[c.id].color}"
                   title="${c.label}: %${(v * 100).toFixed(1)}"></div>`;
    }).join('');
    rows.push(`<div class="zrow${isFocus ? ' focus' : ''}">
      <span class="zlab">z${String(z).padStart(2, '0')}</span>
      <div class="zbars">${bars}</div></div>`);
  }
  $('#zchart').innerHTML = rows.join('');

  const lines = chans.map(c => {
    const p = d.channels[c.id];
    const top = p.share
      .map((v, z) => [v, z]).sort((a, b) => b[0] - a[0]).slice(0, 3);
    const pct = top.reduce((s, [v]) => s + v, 0) * 100;
    const zs = top.map(([, z]) => `z${String(z).padStart(2, '0')}`).sort().join(', ');
    return `<b>${c.label}</b>: sinyalin %${pct.toFixed(0)}'ı ${zs} katmanlarında ·
            odak z${String(p.focus_z).padStart(2, '0')} ·
            ağırlık merkezi z${p.centroid_z.toFixed(1)}`;
  });
  lines.push(`Yüzdeler kanalın <i>kendi</i> toplam sinyaline göre — kanallar arası
              miktar karşılaştırması değil.`);
  lines.push(`z00 mutlak bir yükseklik değil: odak kuyu başına ayarlanıyor, o yüzden
              kuyular arasında <i>dağılımın şeklini</i> karşılaştırın, katman
              numarasını değil.`);
  $('#zsummary').innerHTML = lines.join('<br>');
}

function setStageMode(mode) {
  state.mode = mode;
  $$('#modeSeg button').forEach(b => b.classList.toggle('on', b.dataset.mode === mode));
  $('#panels').hidden = mode !== '2d';
  $('#stage3d').hidden = mode !== '3d';
  $('#layoutSeg').style.display = mode === '2d' ? '' : 'none';
  if (mode === '3d') { buildDepthLegend(); render3d(); loadProfile(); }
  else drawAll();
}

function bind3d() {
  const sel = $('#depthCh');
  sel.innerHTML = state.meta.channels.filter(c => c.nz > 1)
    .map(c => `<option value="${c.id}">${c.label}</option>`).join('');
  sel.value = v3d.ch;
  sel.addEventListener('change', () => { v3d.ch = sel.value; render3d(); });

  $$('#view3dSeg button').forEach(b =>
    b.addEventListener('click', () => set3dView(b.dataset.view)));
  $$('#modeSeg button').forEach(b =>
    b.addEventListener('click', () => setStageMode(b.dataset.mode)));

  const push = debounce(render3d, 120);
  const slider = (id, out, key, fmt) => {
    $(id).addEventListener('input', e => {
      v3d[key] = +e.target.value;
      $(out).textContent = fmt(v3d[key]);
      push();
    });
  };
  slider('#el3d', '#el3dOut', 'el', v => `${v}°`);
  slider('#az3d', '#az3dOut', 'az', v => `${v}°`);
  slider('#zex3d', '#zex3dOut', 'zex', v => `×${v}`);
  $('#crop3d').addEventListener('change', e => { v3d.crop = e.target.checked; render3d(); });
  $('#orthoYZ').addEventListener('change', e => { v3d.yz = e.target.checked; render3d(); });

  // drag on the image to orbit
  const img = $('#v3dimg');
  let drag = null;
  img.addEventListener('pointerdown', e => {
    if (v3d.view !== 'proj') return;
    drag = { x: e.clientX, y: e.clientY, az: v3d.az, el: v3d.el };
    img.classList.add('drag');
    img.setPointerCapture(e.pointerId);
  });
  img.addEventListener('pointermove', e => {
    if (!drag) return;
    v3d.az = Math.max(-90, Math.min(90, drag.az + (e.clientX - drag.x) * 0.4));
    v3d.el = Math.max(0, Math.min(88, drag.el - (e.clientY - drag.y) * 0.3));
    $('#az3d').value = Math.round(v3d.az); $('#az3dOut').textContent = `${Math.round(v3d.az)}°`;
    $('#el3d').value = Math.round(v3d.el); $('#el3dOut').textContent = `${Math.round(v3d.el)}°`;
    push();
  });
  const stop = e => { if (drag) { drag = null; img.classList.remove('drag'); } };
  img.addEventListener('pointerup', stop);
  img.addEventListener('pointercancel', stop);

  $('#zstep').addEventListener('change', e => {
    state.zStepUm = +e.target.value || state.zStepUm;
    buildDepthLegend();
    if (state.mode === '3d') render3d();
  });
}

// -------------------------------------------------------------------- ui plumbing
function debounce(fn, ms) {
  let h;
  return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); };
}

const tip = $('#tooltip');
function showTip(e, html) {
  tip.innerHTML = html; tip.hidden = false;
  const r = e.target.getBoundingClientRect();
  tip.style.left = `${Math.min(r.right + 8, innerWidth - 260)}px`;
  tip.style.top = `${r.top}px`;
}
function hideTip() { tip.hidden = true; }

let toastTimer;
function toast(msg, ms) {
  const el = $('#toast');
  el.textContent = msg; el.hidden = false;
  clearTimeout(toastTimer);
  if (ms) toastTimer = setTimeout(() => { el.hidden = true; }, ms);
}
function hideToast() { $('#toast').hidden = true; }

function updateExtraButton() {
  const has = state.meta.extras?.well
    && state.wells.slice(0, state.panelCount).includes(state.meta.extras.well);
  const b = $('#btnExtra');
  b.hidden = !has;
  b.classList.toggle('on', state.extraMode);
  b.textContent = state.extraMode ? 'VID119 ✓' : 'VID119';
}

function bindUi() {
  $$('#layoutSeg button').forEach(b => b.addEventListener('click', () => {
    $$('#layoutSeg button').forEach(x => x.classList.toggle('on', x === b));
    state.panelCount = +b.dataset.panels;
    const pool = state.meta.wells;
    for (let i = 0; i < state.panelCount; i++) {
      if (!state.wells[i]) state.wells[i] = pool[Math.min(i, pool.length - 1)];
    }
    buildPanels(); renderPlateSelection(); updateExtraButton();
  }));

  $('#btnReset').addEventListener('click', resetView);
  $('#btnHelp').addEventListener('click', () => $('#help').showModal());
  $('#btnPlay').addEventListener('click', togglePlay);
  $('#fps').addEventListener('change', e => { state.fps = +e.target.value || 4; });

  $('#mip').addEventListener('change', e => {
    state.mip = e.target.checked; renderStamp(); loadAll();
  });
  $('#gamma').addEventListener('input', debounce(e => {
    state.gamma = +e.target.value; loadAll();
  }, 120));
  $('#gamma').addEventListener('input', e => { $('#gammaOut').textContent = (+e.target.value).toFixed(2); });

  $('#umpx').addEventListener('change', e => {
    state.umPerPx = +e.target.value || state.umPerPx; drawAll();
  });
  $('#showScale').addEventListener('change', e => { state.showScale = e.target.checked; drawAll(); });
  $('#showProbe').addEventListener('change', e => {
    state.showProbe = e.target.checked;
    if (!state.showProbe) panels.forEach(p => p.probeEl.textContent = '');
  });

  $('#plateColor').addEventListener('change', e => {
    state.plateColorBy = e.target.value; paintPlate();
  });
  $('#seriesMetric').addEventListener('change', drawSeries);
  $('#btnResetDisplay').addEventListener('click', resetDisplay);
  $('#btnAdvanced').addEventListener('click', () => {
    state.advanced = !state.advanced;
    $('#advanced').hidden = !state.advanced;
    $('#btnAdvanced').textContent = state.advanced ? 'gizle' : 'göster';
    $('#btnAdvanced').setAttribute('aria-expanded', String(state.advanced));
    $('#statsCard').classList.toggle('collapsed', !state.advanced);
    renderChannelModes();
  });
  $('#btnExtra').addEventListener('click', () => {
    state.extraMode = !state.extraMode; updateExtraButton(); loadAll();
  });

  addEventListener('keydown', e => {
    if (e.target.matches('input, select, textarea')) return;
    const tps = state.meta.timepoints.length;
    switch (e.key) {
      case 'ArrowRight': state.t = Math.min(tps - 1, state.t + 1); onTimeChange(); break;
      case 'ArrowLeft': state.t = Math.max(0, state.t - 1); onTimeChange(); break;
      case 'ArrowUp': if (!state.mip) { state.z = Math.min(state.meta.nz - 1, state.z + 1); onZChange(); } break;
      case 'ArrowDown': if (!state.mip) { state.z = Math.max(0, state.z - 1); onZChange(); } break;
      case ' ': e.preventDefault(); togglePlay(); break;
      case 'm': case 'M': $('#mip').click(); break;
      case 'r': case 'R': resetView(); break;
      case '?': $('#help').showModal(); break;
      default:
        if (/^[1-9]$/.test(e.key)) {
          const c = state.meta.channels[+e.key - 1];
          if (c) $(`.chan[data-ch="${c.id}"] .on`).click();
        }
    }
  });
}

function resetView() {
  state.view = { zoom: 1, cx: 0.5, cy: 0.5 };
  drawAll();
}

// ------------------------------------------------------------------------- start
async function main() {
  const meta = await (await fetch('/api/meta')).json();
  state.meta = meta;
  state.umPerPx = meta.um_per_px || 2.798;
  $('#umpx').value = state.umPerPx;
  state.zStepUm = meta.z_step_um || 10;
  $('#zstep').value = state.zStepUm;

  meta.channels.forEach(c => { state.chans[c.id] = defaultChanState(c); });
  if (!meta.ranges || !Object.keys(meta.ranges).length) {
    toast('ölçek istatistikleri yok — "python3 viewer/scan_stats.py" ile hesaplanır', 8000);
  }

  state.wells = [meta.wells[0]];
  buildPlate();
  buildChannels();
  buildTimeline();
  bindUi();
  bind3d();
  buildPanels();
  renderWellInfo();
  renderSeriesBox();
  updateExtraButton();

  setInterval(async () => {
    try {
      const s = await (await fetch('/api/stats')).json();
      $('#statsBox').textContent =
        `plane cache ${s.planes.mb} MB / ${s.plane_cache_mb} MB · ` +
        `hit ${s.planes.hits} miss ${s.planes.misses} · mip ${s.mips.mb} MB · ` +
        `bitmap ${bitmaps.size} (${(bitmapBytes / 1e6).toFixed(0)} MB)`;
    } catch {}
  }, 3000);
}

main().catch(e => {
  document.body.innerHTML =
    `<pre style="padding:20px;color:#ff6b6b">başlatılamadı: ${e}</pre>`;
});
