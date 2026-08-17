/* 3D scene — sparse voxel cloud, parallel (orthographic) projection.

   Orthographic, not perspective: in a figure two objects of equal size must be
   drawn the same size wherever they sit on screen, otherwise visual comparison
   lies.

   Performance. Every timepoint × channel is uploaded to the GPU once, as one
   interleaved buffer, and the CPU-side arrays are released. A frame is then 3–4
   draw calls with no data transfer, so orbiting, slicing and scrubbing time are
   all free. Layer slicing happens in the vertex shader (a uniform), not by
   re-uploading a filtered subset.

   Geometry. The XY axes are metric (2.798 µm/px × 2 = 5.596 µm per voxel) and
   carry a scale bar. The Z axis is **ordinal**: layers are drawn evenly spaced,
   but the spacing between layers is recorded nowhere in the data, so no µm claim
   is made. The Z axis is therefore drawn as a labelled ladder and deliberately
   carries no scale bar — the asymmetry is the point. */

const SCENE = (() => {
  const DEG = Math.PI / 180;
  // Visual thickness of the stack as a fraction of the XY extent. A drawing
  // choice, not a measurement — which is why the axis says "layer", not "µm".
  const SLAB_FRAC = 0.34;

  // ------------------------------------------------------------------ decode
  async function gunzip(b64) {
    const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const ds = new DecompressionStream("gzip");
    return new Uint8Array(await new Response(
      new Blob([bin]).stream().pipeThrough(ds)).arrayBuffer());
  }

  /* delta-encoded sparse cube → {idx, val}. Leading uint32 is the element count. */
  async function unpackVox(b64) {
    const raw = await gunzip(b64);
    const n = new Uint32Array(raw.buffer, 0, 1)[0];
    const d = new Uint32Array(raw.buffer.slice(4, 4 + n * 4));
    const val = new Uint8Array(raw.buffer, 4 + n * 4, n);
    const idx = new Uint32Array(n);
    let acc = 0;
    for (let i = 0; i < n; i++) { acc += d[i]; idx[i] = acc; }
    return { idx, val, n };
  }

  // ---------------------------------------------------------------- shaders
  const VS = `
    attribute vec3 pos; attribute float layer; attribute float w;
    uniform mat3 rot; uniform vec2 scale; uniform vec2 pan;
    uniform float psize; uniform vec3 slice;   // x=lo, y=hi, z=softness
    varying float vw;
    void main() {
      float vis = 1.0;
      if (layer < slice.x - slice.z || layer > slice.y + slice.z) vis = 0.0;
      else if (layer < slice.x) vis = (layer - slice.x + slice.z) / max(slice.z, 1e-4);
      else if (layer > slice.y) vis = (slice.y + slice.z - layer) / max(slice.z, 1e-4);
      vw = w * vis;
      vec3 p = rot * pos;
      gl_Position = vec4(p.x * scale.x + pan.x, -p.y * scale.y + pan.y, 0.0, 1.0);
      gl_PointSize = vis > 0.0 ? psize : 0.0;
    }`;
  const FS = `
    precision mediump float; uniform vec3 col; uniform float boost;
    varying float vw;
    void main() {
      vec2 d = gl_PointCoord - vec2(0.5);
      float r = dot(d, d);
      if (r > 0.25 || vw <= 0.0) discard;
      float a = min(1.0, vw * (1.0 - r * 2.4) * 0.42 * boost);
      gl_FragColor = vec4(col * a, a);
    }`;

  function compile(gl, type, src) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  }
  function program(gl) {
    const p = gl.createProgram();
    gl.attachShader(p, compile(gl, gl.VERTEX_SHADER, VS));
    gl.attachShader(p, compile(gl, gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    return p;
  }
  const hex2rgb = h => [0, 1, 2].map(k => parseInt(h.substr(1 + k * 2, 2), 16) / 255);

  /* model → screen, matching the vertex shader exactly (used for the SVG
     annotation layer so axes and marks cannot drift from the points). */
  function projector(az, el) {
    const ca = Math.cos(az * DEG), sa = Math.sin(az * DEG);
    const ce = Math.cos(el * DEG), se = Math.sin(el * DEG);
    return (x, y, z) => {
      const xr = x * ca - y * sa, yr = x * sa + y * ca;
      return [xr, yr * se - z * ce, yr * ce + z * se];
    };
  }

  // ================================================================== Scene
  class Scene {
    constructor(el, cfg) {
      this.host = el;
      this.cfg = cfg;                  // {vox_um, colors, terrColor, onView}
      this.home = { az: -35, elev: 24, zoom: 1, px: 0, py: 0 };
      Object.assign(this, this.home);
      this.on = { green: true, orange: true, nir: true, terr: true };
      this.slice = { lo: 0, hi: 99, soft: 0.6 };
      this.frames = new Map();
      this.cur = null;
      this.dirty = true;

      this.canvas = document.createElement("canvas");
      this.svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      this.svg.setAttribute("preserveAspectRatio", "none");
      el.append(this.canvas, this.svg);

      const gl = this.gl = this.canvas.getContext("webgl", {
        alpha: false, antialias: false, preserveDrawingBuffer: true,
      });
      if (!gl) return this.fallback();
      this.prog = program(gl);
      this.loc = {};
      for (const n of ["rot", "scale", "pan", "psize", "col", "slice", "boost"])
        this.loc[n] = gl.getUniformLocation(this.prog, n);
      this.attr = { pos: gl.getAttribLocation(this.prog, "pos"),
                    layer: gl.getAttribLocation(this.prog, "layer"),
                    w: gl.getAttribLocation(this.prog, "w") };
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE);   // additive — how fluorescence behaves

      this.bindInput();
      new ResizeObserver(() => this.resize()).observe(el);
      this.resize();
      const loop = () => {
        if (this.dirty) { this.draw(); this.dirty = false; }
        requestAnimationFrame(loop);
      };
      requestAnimationFrame(loop);
    }

    fallback() {
      this.host.innerHTML = '<div style="color:#9aa3b2;font-size:13px;padding:24px;' +
        'text-align:center">This browser has no WebGL — the 3D scene cannot be ' +
        'drawn. The figures below are unaffected.</div>';
    }

    // ------------------------------------------------------------ navigation
    /* Blender-style. Left-drag orbits (turntable: horizontal spins about the
       stack axis, vertical raises and lowers the eye); middle-drag or
       shift+left-drag pans; wheel zooms about the pointer. Numpad-style keys
       jump to canonical views. Elevation runs the full −90…+90 so the stack can
       be viewed from below as well as from directly above. */
    bindInput() {
      let mode = null, px = 0, py = 0;
      const el = this.host;

      el.addEventListener("pointerdown", e => {
        mode = (e.button === 1 || e.shiftKey) ? "pan" : "orbit";
        px = e.clientX; py = e.clientY;
        el.setPointerCapture(e.pointerId);
        el.classList.add(mode === "pan" ? "pan" : "drag");
        e.preventDefault();
      });
      el.addEventListener("pointermove", e => {
        if (!mode) return;
        const dx = e.clientX - px, dy = e.clientY - py;
        px = e.clientX; py = e.clientY;
        if (mode === "orbit") {
          // drag right → the near face swings right; drag down → look from above
          this.az -= dx * 0.4;
          this.elev = Math.max(-90, Math.min(90, this.elev + dy * 0.34));
        } else {
          this.px += dx; this.py += dy;
        }
        this.changed();
      });
      const end = e => {
        if (!mode) return;
        mode = null;
        el.classList.remove("drag", "pan");
        try { el.releasePointerCapture(e.pointerId); } catch (_) {}
      };
      el.addEventListener("pointerup", end);
      el.addEventListener("pointercancel", end);
      el.addEventListener("auxclick", e => e.preventDefault());
      el.addEventListener("contextmenu", e => e.preventDefault());

      el.addEventListener("wheel", e => {
        e.preventDefault();
        const r = el.getBoundingClientRect();
        const mx = e.clientX - r.left - r.width / 2 - this.px;
        const my = e.clientY - r.top - r.height / 2 - this.py;
        const k = e.deltaY < 0 ? 1.12 : 1 / 1.12;
        const z = Math.max(0.4, Math.min(12, this.zoom * k));
        const f = z / this.zoom;
        this.px -= mx * (f - 1); this.py -= my * (f - 1);   // zoom toward cursor
        this.zoom = z;
        this.changed();
      }, { passive: false });

      el.addEventListener("dblclick", () => this.view("home"));
      el.tabIndex = 0;
      el.addEventListener("keydown", e => {
        const k = { "1": "front", "3": "right", "7": "top", "9": "bottom",
                    "5": "back", "0": "home", "h": "home" }[e.key];
        if (k) { this.view(k); e.preventDefault(); }
      });
    }

    view(name) {
      const V = {
        home: this.home,
        top: { az: 0, elev: 90 }, bottom: { az: 0, elev: -90 },
        front: { az: 0, elev: 0 }, back: { az: 180, elev: 0 },
        right: { az: 90, elev: 0 }, left: { az: -90, elev: 0 },
      }[name] || this.home;
      Object.assign(this, { px: 0, py: 0, zoom: 1 }, V);
      this.changed();
    }

    changed() {
      this.dirty = true;
      if (this.cfg.onView) this.cfg.onView({ az: this.az, elev: this.elev, zoom: this.zoom });
    }

    setSlice(lo, hi, soft) {
      this.slice = { lo, hi, soft: soft == null ? this.slice.soft : soft };
      this.dirty = true;
    }
    toggle(ch, v) { this.on[ch] = v; this.dirty = true; }

    resize() {
      const r = this.host.getBoundingClientRect();
      // The canvas caps device pixel ratio at 2; the screen scale must use the
      // same capped value or the scene overflows on 3× displays.
      const dpr = this.dpr = Math.min(2, window.devicePixelRatio || 1);
      this.w = r.width; this.h = r.height;
      this.canvas.width = Math.round(r.width * dpr);
      this.canvas.height = Math.round(r.height * dpr);
      this.svg.setAttribute("viewBox", `0 0 ${r.width} ${r.height}`);
      this.dirty = true;
    }

    // ---------------------------------------------------------------- upload
    /* Decode one timepoint and hand it to the GPU. Interleaved as
       [x, y, z, layer, weight]; the CPU arrays are dropped straight after so a
       whole plate's worth of timepoints does not sit in JS memory. */
    async load(t, frame, grid) {
      if (this.frames.has(t)) return this.frames.get(t);
      const gl = this.gl;
      if (!gl) return null;
      const { nz, h, w } = grid, vox = this.cfg.vox_um;
      const zspace = SLAB_FRAC * Math.max(h, w) * vox / Math.max(nz - 1, 1);
      this.zspace = zspace; this.grid = grid;
      this.extent = { x: w * vox, y: h * vox, z: (nz - 1) * zspace };
      this.nz = nz;

      const clouds = {};
      for (const ch of ["green", "orange", "nir"]) {
        const { idx, val, n } = await unpackVox(frame.vox[ch]);
        const a = new Float32Array(n * 5);
        const hw = h * w, maxv = grid.bin * grid.bin;
        for (let i = 0; i < n; i++) {
          const k = idx[i];
          const z = (k / hw) | 0, rem = k - z * hw;
          const y = (rem / w) | 0, x = rem - y * w;
          const o = i * 5;
          a[o] = (x - w / 2) * vox;
          a[o + 1] = (y - h / 2) * vox;
          a[o + 2] = (z - (nz - 1) / 2) * zspace;
          a[o + 3] = z;
          a[o + 4] = Math.min(1, val[i] / maxv);
        }
        clouds[ch] = { buf: this.upload(a), n, size: vox };
      }

      // Brightfield organoid footprint: a base plane below the stack.
      const [th, tw] = frame.terr_shape;
      const tm = await gunzip(frame.terr_map);
      const tbin = (h * grid.bin) / th, tvox = (vox / grid.bin) * tbin;
      const zb = -(nz - 1) / 2 * zspace - zspace * 1.9;
      let cnt = 0;
      for (let i = 0; i < tm.length; i++) if (tm[i]) cnt++;
      const ta = new Float32Array(cnt * 5);
      let j = 0;
      for (let i = 0; i < tm.length; i++) {
        if (!tm[i]) continue;
        const y = (i / tw) | 0, x = i - y * tw, o = j++ * 5;
        ta[o] = (x - tw / 2) * tvox; ta[o + 1] = (y - th / 2) * tvox; ta[o + 2] = zb;
        ta[o + 3] = -1;                       // never sliced away
        ta[o + 4] = Math.min(1, tm[i] / (tbin * tbin)) * 0.45;
      }
      clouds.terr = { buf: this.upload(ta), n: cnt, size: tvox, base: true };

      const rec = { clouds, dome: frame.dome, zb };
      this.frames.set(t, rec);
      return rec;
    }

    upload(arr) {
      const gl = this.gl;
      const b = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, b);
      gl.bufferData(gl.ARRAY_BUFFER, arr, gl.STATIC_DRAW);
      return b;
    }

    show(rec) { this.cur = rec; this.dirty = true; }

    /* Normal kipte sahne kutuya boşluk bırakarak sığar. `exact` kipinde model
       genişliği kutu genişliğine **birebir** eşlenir ve kamera tam tepeden
       kilitlenir: o zaman izdüşüm, ham düzlemin kendisiyle aynı piksel
       eşlemesine sahip olur ve ikisi üst üste bindirilebilir. Hizalama yanlışsa
       noktalar lekelerin yanına düşer ve hata gözle görünür. */
    metrics(w, h) {
      const e = this.extent;
      if (this.exact) return { s: (w / e.x) * this.zoom };
      return { s: (Math.min(w, h) / (Math.max(e.x, e.y) * 1.2)) * this.zoom };
    }

    setExact(on) {
      this.exact = !!on;
      if (on) { this.az = 0; this.elev = 90; this.px = 0; this.py = 0; this.zoom = 1; }
      this.dirty = true;
    }

    // ------------------------------------------------------------------ draw
    draw(target) {
      const gl = this.gl;
      if (!gl) return;
      const W = target ? target.w : this.canvas.width;
      const H = target ? target.h : this.canvas.height;
      const dpr = target ? target.dpr : this.dpr;
      gl.viewport(0, 0, W, H);
      gl.clearColor(0.055, 0.063, 0.075, 1);
      gl.clear(gl.COLOR_BUFFER_BIT);
      if (!target) this.annotate();
      if (!this.cur) return;

      const { s } = this.metrics(W / dpr, H / dpr);
      const ca = Math.cos(this.az * DEG), sa = Math.sin(this.az * DEG);
      const ce = Math.cos(this.elev * DEG), se = Math.sin(this.elev * DEG);
      gl.useProgram(this.prog);
      gl.uniformMatrix3fv(this.loc.rot, false, new Float32Array(
        [ca, sa * se, sa * ce, -sa, ca * se, ca * ce, 0, -ce, se]));
      gl.uniform2f(this.loc.scale, 2 * s * dpr / W, 2 * s * dpr / H);
      gl.uniform2f(this.loc.pan, 2 * this.px * dpr / W, -2 * this.py * dpr / H);
      gl.uniform3f(this.loc.slice, this.slice.lo, this.slice.hi, this.slice.soft);
      // Bindirme kipinde tek bir katman çiziliyor ve noktalar ekranda ~1 piksel;
      // hizalamayı gözle yargılayabilmek için daha parlak ve daha iri çizilirler.
      gl.uniform1f(this.loc.boost, this.exact ? 3.6 : 1.0);

      const A = this.attr;
      for (const ch of ["terr", "green", "nir", "orange"]) {
        const c = this.cur.clouds[ch];
        if (!c || !c.n || !this.on[ch]) continue;
        gl.bindBuffer(gl.ARRAY_BUFFER, c.buf);
        gl.enableVertexAttribArray(A.pos);
        gl.vertexAttribPointer(A.pos, 3, gl.FLOAT, false, 20, 0);
        gl.enableVertexAttribArray(A.layer);
        gl.vertexAttribPointer(A.layer, 1, gl.FLOAT, false, 20, 12);
        gl.enableVertexAttribArray(A.w);
        gl.vertexAttribPointer(A.w, 1, gl.FLOAT, false, 20, 16);
        gl.uniform1f(this.loc.psize, this.exact
          ? Math.max(3.2, c.size * s * dpr * 2.6)
          : Math.max(1.3, c.size * s * dpr * 1.3));
        const col = hex2rgb(c.base ? this.cfg.terrColor : this.cfg.colors[ch]);
        gl.uniform3f(this.loc.col, col[0], col[1], col[2]);
        gl.drawArrays(gl.POINTS, 0, c.n);
      }
    }

    /* Axis frame, layer ladder, scale bar and dome outline live in an SVG layer
       so the type stays sharp and the annotation can be exported as vector. */
    annotate() {
      const ns = "http://www.w3.org/2000/svg";
      while (this.svg.firstChild) this.svg.removeChild(this.svg.firstChild);
      if (!this.extent) return;
      const { s } = this.metrics(this.w, this.h);
      const P = projector(this.az, this.elev);
      const cx = this.w / 2 + this.px, cy = this.h / 2 + this.py;
      const to = (x, y, z) => { const p = P(x, y, z); return [cx + p[0] * s, cy + p[1] * s]; };
      const mk = (t, a) => { const e = document.createElementNS(ns, t);
                             for (const k in a) e.setAttribute(k, a[k]); return e; };
      const line = (a, b, at = {}) => this.svg.append(mk("line",
        { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: "#39414f",
          "stroke-width": 1, ...at }));
      const txt = (p, str, at = {}) => {
        const e = mk("text", { x: p[0], y: p[1], fill: "#7d8694", "font-size": 10.5, ...at });
        e.textContent = str; this.svg.append(e);
      };

      const ex = this.extent, hx = ex.x / 2, hy = ex.y / 2;
      const zb = this.cur ? this.cur.zb : -ex.z / 2;

      if (this.exact) {
        // Üst üste bindirme kipinde tek gereken ölçek çubuğu; kutu çerçevesi ve
        // katman merdiveni fotoğrafın üstünü kapatırdı.
        const t = ex.x * 0.25;
        const n = [100, 200, 250, 500, 1000].reduce(
          (a, b) => Math.abs(b - t) < Math.abs(a - t) ? b : a);
        const a1 = to(hx - n, hy * 0.93, 0), b1 = to(hx * 0.97, hy * 0.93, 0);
        line([a1[0], a1[1]], [a1[0] + (b1[0] - a1[0]), a1[1]],
             { stroke: "#e6e9ef", "stroke-width": 2.4 });
        txt([(a1[0] + b1[0]) / 2, a1[1] - 6], `${n} µm`,
            { "text-anchor": "middle", fill: "#e6e9ef", "font-size": 11 });
        return;
      }

      // footprint frame
      const c = [[-hx, -hy], [hx, -hy], [hx, hy], [-hx, hy]].map(p => to(p[0], p[1], zb));
      for (let i = 0; i < 4; i++) line(c[i], c[(i + 1) % 4], { stroke: "#2b3240" });

      // dome outline — only when one mass dominates; defined in XY only
      const dm = this.cur && this.cur.dome;
      if (dm && dm.dominant) {
        const vox = this.cfg.vox_um, g = this.grid;
        const ox = (dm.cx_px / g.bin - g.w / 2) * vox;
        const oy = (dm.cy_px / g.bin - g.h / 2) * vox;
        const pts = [];
        for (let i = 0; i <= 72; i++) {
          const a = i / 72 * 2 * Math.PI;
          pts.push(to(ox + dm.r90_um * Math.cos(a), oy + dm.r90_um * Math.sin(a), zb).join(","));
        }
        this.svg.append(mk("polyline", { points: pts.join(" "), fill: "none",
          stroke: "#8d97a6", "stroke-width": 1.2, "stroke-dasharray": "5 4" }));
        const lp = to(ox, oy + dm.r90_um, zb);
        txt([lp[0] + 6, lp[1] + 13], `dome R90 = ${Math.round(dm.r90_um)} µm`,
            { fill: "#8d97a6" });
      }

      // layer ladder — ordinal axis, indices not microns
      const nz = this.nz || 17;
      const kx = -hx * 1.05, ky = hy * 1.05;
      const inRange = z => z >= this.slice.lo - 1e-6 && z <= this.slice.hi + 1e-6;
      line(to(kx, ky, -ex.z / 2), to(kx, ky, ex.z / 2), { stroke: "#39414f" });
      for (let z = 0; z < nz; z++) {
        const zz = (z - (nz - 1) / 2) * this.zspace;
        const a = to(kx, ky, zz);
        const major = z % 4 === 0 || z === nz - 1;
        const b = to(kx - (major ? 62 : 30) / s, ky, zz);
        const lit = inRange(z);
        line(a, b, { stroke: lit ? (major ? "#6d7789" : "#3a4250") : "#232935" });
        if (major) txt([b[0] - 5, b[1] + 3.5], "z" + String(z).padStart(2, "0"),
                       { "text-anchor": "end", fill: lit ? "#98a2b1" : "#4b5464" });
      }
      const zc = to(kx - 152 / s, ky, 0);
      txt([zc[0], zc[1]], "z layer (ordinal)", { "text-anchor": "middle", fill: "#8d97a6",
        transform: `rotate(-90 ${zc[0]} ${zc[1]})`, "letter-spacing": ".06em" });

      // XY scale bar — metric, at the base plane
      const target = ex.x * 0.3;
      const nice = [100, 200, 250, 500, 1000, 2000].reduce(
        (a, b) => Math.abs(b - target) < Math.abs(a - target) ? b : a);
      const a0 = to(hx - nice, hy * 1.02, zb), b0 = to(hx, hy * 1.02, zb);
      line(a0, b0, { stroke: "#c6ccd6", "stroke-width": 2.2 });
      txt([(a0[0] + b0[0]) / 2, (a0[1] + b0[1]) / 2 + 15], `${nice} µm`,
          { "text-anchor": "middle", fill: "#c6ccd6", "font-size": 11 });
    }

    // ---------------------------------------------------------------- export
    /* Render at higher resolution than the screen for a figure panel. The GL
       context is reused, so this costs one extra frame. */
    png(scale = 3) {
      const gl = this.gl;
      if (!gl) return null;
      const w0 = this.canvas.width, h0 = this.canvas.height;
      this.canvas.width = Math.round(this.w * scale);
      this.canvas.height = Math.round(this.h * scale);
      this.draw({ w: this.canvas.width, h: this.canvas.height, dpr: scale });
      const url = this.canvas.toDataURL("image/png");
      this.canvas.width = w0; this.canvas.height = h0;
      this.dirty = true;
      return url;
    }

    /* Four canonical views as one strip — what a methods figure needs. */
    async panel(scale = 2) {
      const views = [["top", "top (XY)"], ["front", "front (XZ)"],
                     ["right", "right (YZ)"], ["home", "oblique"]];
      const keep = { az: this.az, elev: this.elev, zoom: this.zoom, px: this.px, py: this.py };
      const urls = [];
      for (const [v] of views) { this.view(v); urls.push(this.png(scale)); }
      Object.assign(this, keep); this.dirty = true;
      return { urls, labels: views.map(v => v[1]) };
    }
  }

  return { Scene, unpackVox };
})();
