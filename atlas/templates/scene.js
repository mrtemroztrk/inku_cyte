/* 3D scene — sparse voxel cloud, parallel (orthographic) projection.

   Orthographic, not perspective: in a figure two objects of equal size must be
   drawn the same size wherever they sit on screen, otherwise visual comparison
   lies.

   Performance. Every timepoint × channel is uploaded to the GPU once, as one
   interleaved buffer, and the CPU-side arrays are released. A frame is then 3–4
   draw calls with no data transfer, so orbiting, slicing and scrubbing time are
   all free. Layer slicing happens in the vertex shader (a uniform), not by
   re-uploading a filtered subset.

   Colour. Points are not drawn straight to the screen. Each channel accumulates
   its own scalar density into one component of an off-screen RGBA target
   (green→R, orange→G, dead→B, footprint→A), and a final pass turns density into
   colour: rgb = Σ colour_k · tone(density_k). Additive drawing straight to the
   screen — the obvious way — saturates every RGB component towards white, so a
   dense green mass turned cyan, then white, and did so *more* the further one
   zoomed out (more voxels per pixel). Here a dense mass saturates towards its own
   channel colour and stays that colour at every zoom; hue is identity and cannot
   be sacrificed to brightness.

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
    uniform float zsign;                       // −1 draws z00 on top
    varying float vw;
    void main() {
      float vis = 1.0;
      if (layer < slice.x - slice.z || layer > slice.y + slice.z) vis = 0.0;
      else if (layer < slice.x) vis = (layer - slice.x + slice.z) / max(slice.z, 1e-4);
      else if (layer > slice.y) vis = (slice.y + slice.z - layer) / max(slice.z, 1e-4);
      vw = w * vis;
      // The footprint plane (layer < 0) is a base, not a layer: it stays below.
      vec3 q = vec3(pos.x, pos.y, layer < 0.0 ? pos.z : pos.z * zsign);
      vec3 p = rot * q;
      gl_Position = vec4(p.x * scale.x + pan.x, -p.y * scale.y + pan.y, 0.0, 1.0);
      gl_PointSize = vis > 0.0 ? psize : 0.0;
    }`;
  /* Her voksel bir ışık kaynağı gibi çizilir: dar, sıcak bir çekirdek ve onu
     saran hale; harmanlama toplamalı, üst üste binen vokseller birikir. Burada
     yalnızca **yoğunluk** yazılır — renk yok. Renk, tüm kanallar biriktikten
     sonra tek bir geçişte verilir (CFS), böylece yoğun bir bölge beyaza değil
     kendi kanal rengine doyar. */
  const FS = `
    precision mediump float; uniform float boost; uniform float flat_;
    varying float vw;
    void main() {
      if (vw <= 0.0) discard;
      if (flat_ > 0.5) {
        // Yakından: her voksel ekranda birkaç piksel — düz, dolu bir kare olarak
        // çizilir ki komşu vokseller boşluksuz döşensin ve bir boya yığını
        // fotoğraftaki gibi dolu görünsün, noktalı bir ızgara gibi değil.
        gl_FragColor = vec4(vw * boost);
        return;
      }
      float d = length(gl_PointCoord - vec2(0.5)) * 2.0;
      if (d > 1.0) discard;
      float core = smoothstep(0.60, 0.0, d);
      float halo = exp(-d * d * 2.4) * 0.85;
      float a = vw * (core * 0.7 + halo) * boost;
      gl_FragColor = vec4(a);
    }`;

  /* Yoğunluk → renk. Her bileşen bir kanalın birikmiş yoğunluğu (0…1, 8 bit).
     tone() doygunluğa yumuşak yaklaşır; en yoğun yerde renk tam kanal rengidir,
     daha fazlası beyaza değil hafif bir sıcak çekirdeğe gider — floresanın
     görünüşü, ama kimlik korunarak. */
  const CVS = `
    attribute vec2 corner; varying vec2 uv;
    void main() { uv = corner * 0.5 + 0.5; gl_Position = vec4(corner, 0.0, 1.0); }`;
  const CFS = `
    precision mediump float; uniform sampler2D acc;
    uniform vec3 c0; uniform vec3 c1; uniform vec3 c2; uniform vec3 c3;
    uniform float gain;
    varying vec2 uv;
    float tone(float x) { return 1.0 - exp(-x * gain); }
    void main() {
      vec4 I = texture2D(acc, uv);
      vec3 rgb = c0 * tone(I.r) + c1 * tone(I.g) + c2 * tone(I.b) + c3 * tone(I.a);
      // Beyaz çekirdek bilerek yok: doymuş bir bölge kanal renginin kendisidir.
      // Beyaza kayan her şey, tümörü T hücresinden ayıran tek ipucunu siler.
      gl_FragColor = vec4(rgb, 1.0);
    }`;

  /* Fotoğraf düzlemi. Bindirme, ekranın üstüne yapıştırılmış 2B bir görüntü
     olarak yapılırsa yalnızca tam tepeden bakışta anlamlıdır; sahne döndüğünde
     görüntü yerinde kalır ve karşılaştırma anlamını yitirir. Fotoğraf bu yüzden
     sahnenin içine, ait olduğu katmanın z yüksekliğine, dokulu bir dörtgen
     olarak konuyor: kamera döndüğünde fotoğraf da döner ve voksellerin boyanın
     üstünde durup durmadığı her açıdan görülebilir. */
  const QVS = `
    attribute vec2 corner;
    uniform mat3 rot; uniform vec2 scale; uniform vec2 pan;
    uniform vec2 half_xy; uniform float zpos;
    varying vec2 uv;
    void main() {
      uv = vec2(corner.x * 0.5 + 0.5, corner.y * 0.5 + 0.5);
      vec3 p = rot * vec3(corner.x * half_xy.x, corner.y * half_xy.y, zpos);
      gl_Position = vec4(p.x * scale.x + pan.x, -p.y * scale.y + pan.y, 0.0, 1.0);
    }`;
  const QFS = `
    precision mediump float; uniform sampler2D tex; uniform float alpha;
    varying vec2 uv;
    void main() {
      vec4 c = texture2D(tex, uv);
      gl_FragColor = vec4(c.rgb, alpha);
    }`;

  function compile(gl, type, src) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  }
  function program(gl, vs, fs) {
    const p = gl.createProgram();
    gl.attachShader(p, compile(gl, gl.VERTEX_SHADER, vs || VS));
    gl.attachShader(p, compile(gl, gl.FRAGMENT_SHADER, fs || FS));
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
      this.cfg = cfg;   // {vox_um, colors, terrColor, onView, boost}
      // Nokta başına katkı; tam çözünürlüklü bulutlarda daha çok nokta
      // üst üste bindiği için sayfa daha düşük bir değer verir.
      this.boostBase = cfg.boost == null ? 1.7 : cfg.boost;
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
      for (const n of ["rot", "scale", "pan", "psize", "slice", "boost", "zsign", "flat_"])
        this.loc[n] = gl.getUniformLocation(this.prog, n);
      // Yoğunluk → renk geçişi: tam ekran dörtgen ve birikim dokusu.
      this.cprog = program(gl, CVS, CFS);
      this.cloc = {};
      for (const n of ["acc", "c0", "c1", "c2", "c3", "gain"])
        this.cloc[n] = gl.getUniformLocation(this.cprog, n);
      this.cattr = gl.getAttribLocation(this.cprog, "corner");
      this.acc = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, this.acc);
      for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.NEAREST],
                            [gl.TEXTURE_MAG_FILTER, gl.NEAREST],
                            [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE],
                            [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]])
        gl.texParameteri(gl.TEXTURE_2D, k, v);
      this.fbo = gl.createFramebuffer();
      this.accW = 0; this.accH = 0;
      this.zsign = 1;
      this.attr = { pos: gl.getAttribLocation(this.prog, "pos"),
                    layer: gl.getAttribLocation(this.prog, "layer"),
                    w: gl.getAttribLocation(this.prog, "w") };
      // Fotoğraf düzlemi için ayrı program ve doku
      this.qprog = program(gl, QVS, QFS);
      this.qloc = {};
      for (const n of ["rot", "scale", "pan", "half_xy", "zpos", "tex", "alpha"])
        this.qloc[n] = gl.getUniformLocation(this.qprog, n);
      this.qattr = gl.getAttribLocation(this.qprog, "corner");
      this.qbuf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, this.qbuf);
      gl.bufferData(gl.ARRAY_BUFFER,
        new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
      this.tex = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, this.tex);
      for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR],
                            [gl.TEXTURE_MAG_FILTER, gl.LINEAR],
                            [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE],
                            [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]])
        gl.texParameteri(gl.TEXTURE_2D, k, v);
      this.plane = null;

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
       jump to canonical views. Neither angle is clamped: the eye can pass over
       the pole and keep going, so no drag ever runs into a wall — a camera that
       stops at 90° reads as broken to anyone who has used a 3D viewer. */
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
          this.elev += dy * 0.34;
          // keep both angles in (−180, 180] so labels and presets stay readable
          this.az = ((this.az + 180) % 360 + 360) % 360 - 180;
          this.elev = ((this.elev + 180) % 360 + 360) % 360 - 180;
        } else {
          this.px += dx; this.py += dy;
        }
        this.changed(mode);
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
        this.changed("zoom");
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
      this.changed("view");
    }

    /* `kind` says what moved — orbit, pan, zoom, view (preset), focus — so a
       page linking this camera to another panel can decide what to follow. */
    changed(kind) {
      this.dirty = true;
      if (this.cfg.onView) this.cfg.onView({ az: this.az, elev: this.elev, zoom: this.zoom,
                                             px: this.px, py: this.py, kind: kind || "" });
    }

    /* z00 on top. The z axis is ordinal and its direction is not recorded, so
       drawing it the other way up is a labelling choice, not a geometric one;
       XY is untouched, so the top view still matches the photograph. */
    setZUp(on) { this.zsign = on ? -1 : 1; this.dirty = true; }

    /* Model XY (µm) at the centre of the box on the z = 0 plane — the inverse of
       focusOn(). Undefined when the camera looks along the plane (elev ≈ 0);
       then null is returned and the caller keeps its previous centre. */
    centerXY() {
      const se = Math.sin(this.elev * DEG);
      if (Math.abs(se) < 0.05 || !this.extent) return null;
      const { s } = this.metrics(this.w, this.h);
      const ca = Math.cos(this.az * DEG), sa = Math.sin(this.az * DEG);
      const xr = -this.px / s, yr = -this.py / (s * se);
      return { x: xr * ca + yr * sa, y: -xr * sa + yr * ca };
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
    /* Field geometry from the voxel grid: metric XY, ordinal Z. */
    setGrid(grid) {
      const { nz, h, w } = grid, vox = this.cfg.vox_um;
      const zspace = SLAB_FRAC * Math.max(h, w) * vox / Math.max(nz - 1, 1);
      this.zspace = zspace; this.grid = grid;
      this.extent = { x: w * vox, y: h * vox, z: (nz - 1) * zspace };
      this.nz = nz;
      return { zspace, vox };
    }

    /* A scene with the field's geometry but no voxels — a box, a ladder and a
       scale bar to hang a photograph in. The check page uses one of these next
       to the real reconstruction, driven by the same camera, so a tilted
       photograph and a tilted reconstruction can be compared as twins. */
    blank(grid) {
      const { nz } = grid;
      const { zspace } = this.setGrid(grid);
      this.cur = { clouds: {}, focus: null, dome: null, zb: -(nz - 1) / 2 * zspace };
      this.dirty = true;
    }

    async load(t, frame, grid) {
      if (this.frames.has(t)) return this.frames.get(t);
      const gl = this.gl;
      if (!gl) return null;
      const { nz, h } = grid;
      const { zspace, vox } = this.setGrid(grid);

      const clouds = {};
      for (const ch of ["green", "orange", "nir"])
        clouds[ch] = await this.cloudFrom(frame.vox[ch], grid, vox, zspace);

      // Brightfield organoid footprint: a base plane below the stack. The check
      // page has no footprint layer — it compares one plane against one plane.
      if (!frame.terr_map || !frame.terr_shape) {
        const rec0 = { clouds, focus: await this.focusClouds(frame, grid, vox, zspace),
                       dome: frame.dome, zb: -(nz - 1) / 2 * zspace };
        this.frames.set(t, rec0);
        return rec0;
      }
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

      const rec = { clouds, focus: await this.focusClouds(frame, grid, vox, zspace),
                    dome: frame.dome, zb };
      this.frames.set(t, rec);
      return rec;
    }

    /* Odak düzlemine indirgenmiş bulutlar, varsa. Kendi ızgaraları olabilir
       (grid_focus: tam çözünürlük, piksel = voksel); yoksa ana ızgara. */
    async focusClouds(frame, grid, vox, zspace) {
      if (!frame.vox_focus) return null;
      const g = frame.grid_focus || grid;
      const v = vox * g.bin / grid.bin;
      const out = {};
      for (const ch of ["green", "orange", "nir"])
        out[ch] = await this.cloudFrom(frame.vox_focus[ch], g, v, zspace);
      return out;
    }

    /* Paketlenmiş seyrek küpü GPU tamponuna çevirir. */
    async cloudFrom(packed, grid, vox, zspace) {
      const { nz, h, w } = grid;
      const { idx, val, n } = await unpackVox(packed);
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
      return { buf: this.upload(a), n, size: vox };
    }

    upload(arr) {
      const gl = this.gl;
      const b = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, b);
      gl.bufferData(gl.ARRAY_BUFFER, arr, gl.STATIC_DRAW);
      return b;
    }

    show(rec) { this.cur = rec; this.dirty = true; }

    /* Hangi bulut çizilecek: eşik üstü her düzlem, ya da her XY konumunun en
       parlak olduğu tek düzlem. İkincisi varsayılan çünkü birincisi tek bir
       nesneyi dikey bir sütuna yayıyor — ölçülen yayılma 2,6–3,0×. */
    setCloud(kind) { this.cloudKind = kind; this.dirty = true; }

    /* Which cloud actually draws now. "auto": the raw per-plane masks whenever
       the view is a slice of the stack (a single layer, or a run of layers), the
       best-focus cloud when the whole stack is shown. Reason: a slice is compared
       with the photograph of those planes, and the photograph shows every pixel
       above threshold in them — the focus cloud, which places each XY position in
       one plane only, would show a blob with its middle missing. The whole stack
       is where the focus cloud earns its keep: no columns. */
    activeCloud() {
      if (this.cloudKind !== "auto") return this.cloudKind;
      const full = this.slice.lo <= 0 && this.slice.hi >= (this.nz || 1) - 1;
      return full ? "focus" : "all";
    }

    /* Model uzayındaki bir XY noktasını kutunun ortasına getirir. İki panelin
       aynı bölgeyi göstermesi için gerekli: fotoğrafta yakınlaştırılan yer 3B'de
       de ortada durmalı, yoksa karşılaştırma yapılamaz. */
    focusOn(xm, ym, zoom) {
      if (zoom != null) this.zoom = zoom;
      const { s } = this.metrics(this.w, this.h);
      const P = projector(this.az, this.elev);
      const p = P(xm, ym, 0);
      this.px = -p[0] * s;
      this.py = -p[1] * s;
      this.changed("focus");
    }

    /* Normal kipte sahne kutuya boşluk bırakarak sığar. `exact` kipinde model
       genişliği kutu genişliğine **birebir** eşlenir ve kamera tam tepeden
       kilitlenir: o zaman izdüşüm, ham düzlemin kendisiyle aynı piksel
       eşlemesine sahip olur ve ikisi üst üste bindirilebilir. Hizalama yanlışsa
       noktalar lekelerin yanına düşer ve hata gözle görünür. */
    metrics(w, h) {
      const e = this.extent;
      // cfg.fit === "width": the field's width fills the box at zoom 1, which is
      // exactly how a photograph of the field is laid out in a box of the same
      // aspect ratio — so a page showing the two side by side can link them at
      // equal magnification.
      if (this.exact || this.cfg.fit === "width") return { s: (w / e.x) * this.zoom };
      return { s: (Math.min(w, h) / (Math.max(e.x, e.y) * 1.2)) * this.zoom };
    }

    /* Fotoğrafı sahnenin içine, verilen katmanın z yüksekliğine yerleştirir.
       url=null düzlemi kaldırır. */
    setPlane(url, layer, alpha) {
      const gl = this.gl;
      if (!gl) return;
      this.planeAlpha = alpha == null ? 0.6 : alpha;
      this.planeLayer = layer;
      if (!url) { this.plane = null; this._planeURL = null; this.dirty = true; return; }
      if (this._planeURL === url) { this.dirty = true; return; }
      this._planeURL = url;
      const im = new Image();
      im.onload = () => {
        this._uploadPlane(im);
        // Draw now rather than on the next animation frame: a headless capture
        // taken right after the load must already show the photograph.
        this.draw();
      };
      im.src = url;
    }

    /* Same, from a canvas (or decoded image) already in hand — synchronous,
       no data-URL round trip; used when the photograph is redrawn on every
       slider step. */
    setPlaneSource(src, layer, alpha) {
      if (!this.gl) return;
      this.planeAlpha = alpha == null ? 0.6 : alpha;
      this.planeLayer = layer;
      this._planeURL = null;
      if (!src) { this.plane = null; this.dirty = true; return; }
      this._uploadPlane(src);
      this.dirty = true;
    }

    _uploadPlane(src) {
      const gl = this.gl;
      gl.bindTexture(gl.TEXTURE_2D, this.tex);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, src);
      this.plane = true;
    }

    /* Camera state as a plain object, and the reverse — for driving two scenes
       from one camera. setCamera() does not call onView, so mirroring one scene
       into another cannot echo. */
    camera() {
      return { az: this.az, elev: this.elev, zoom: this.zoom, px: this.px, py: this.py };
    }
    setCamera(c) {
      Object.assign(this, { az: c.az, elev: c.elev, zoom: c.zoom, px: c.px, py: c.py });
      this.dirty = true;
    }

    setExact(on) {
      this.exact = !!on;
      if (on) { this.az = 0; this.elev = 90; this.px = 0; this.py = 0; this.zoom = 1; }
      this.dirty = true;
    }

    // ------------------------------------------------------------------ draw
    /* Birikim dokusu tuvalle aynı boyda olmalı; boyut değişince yeniden kurulur
       (pencere, DPR ya da PNG dışa aktarımı). */
    ensureAcc(W, H) {
      const gl = this.gl;
      if (this.accW === W && this.accH === H) return;
      gl.bindTexture(gl.TEXTURE_2D, this.acc);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, W, H, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbo);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D,
                              this.acc, 0);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      this.accW = W; this.accH = H;
    }

    draw(target) {
      const gl = this.gl;
      if (!gl) return;
      const W = target ? target.w : this.canvas.width;
      const H = target ? target.h : this.canvas.height;
      const dpr = target ? target.dpr : this.dpr;
      const BG = [0.055, 0.063, 0.075];
      gl.viewport(0, 0, W, H);
      if (!target) this.annotate();
      if (!this.cur) {
        gl.bindFramebuffer(gl.FRAMEBUFFER, null);
        gl.clearColor(BG[0], BG[1], BG[2], 1);
        gl.clear(gl.COLOR_BUFFER_BIT);
        return;
      }

      const { s } = this.metrics(W / dpr, H / dpr);
      const ca = Math.cos(this.az * DEG), sa = Math.sin(this.az * DEG);
      const ce = Math.cos(this.elev * DEG), se = Math.sin(this.elev * DEG);
      const rot = new Float32Array([ca, sa * se, sa * ce, -sa, ca * se, ca * ce, 0, -ce, se]);
      const scale = [2 * s * dpr / W, 2 * s * dpr / H];
      const pan = [2 * this.px * dpr / W, -2 * this.py * dpr / H];

      // ---- 1. yoğunluk birikimi: kanal başına bir bileşen, ekran dışı
      this.ensureAcc(W, H);
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbo);
      gl.viewport(0, 0, W, H);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.blendFunc(gl.ONE, gl.ONE);
      gl.useProgram(this.prog);
      gl.uniformMatrix3fv(this.loc.rot, false, rot);
      gl.uniform2f(this.loc.scale, scale[0], scale[1]);
      gl.uniform2f(this.loc.pan, pan[0], pan[1]);
      gl.uniform3f(this.loc.slice, this.slice.lo, this.slice.hi, this.slice.soft);
      gl.uniform1f(this.loc.zsign, this.zsign);
      // Bindirme kipinde tek bir katman çiziliyor ve noktalar ekranda ~1 piksel;
      // hizalamayı gözle yargılayabilmek için daha parlak çizilirler.
      const boost = this.boostBase * (this.exact ? 1.3 : 1.0);

      const A = this.attr;
      const alt = this.activeCloud() === "focus" ? this.cur.focus : null;
      const MASK = { green: [1, 0, 0, 0], orange: [0, 1, 0, 0], nir: [0, 0, 1, 0],
                     terr: [0, 0, 0, 1] };
      for (const ch of ["terr", "green", "nir", "orange"]) {
        const c = (alt && alt[ch]) || this.cur.clouds[ch];
        if (!c || !c.n || !this.on[ch]) continue;
        gl.bindBuffer(gl.ARRAY_BUFFER, c.buf);
        gl.enableVertexAttribArray(A.pos);
        gl.vertexAttribPointer(A.pos, 3, gl.FLOAT, false, 20, 0);
        gl.enableVertexAttribArray(A.layer);
        gl.vertexAttribPointer(A.layer, 1, gl.FLOAT, false, 20, 12);
        gl.enableVertexAttribArray(A.w);
        gl.vertexAttribPointer(A.w, 1, gl.FLOAT, false, 20, 16);
        // Çizilen boy voksel ayak izinin kendisi (×1,15, hale için pay). Daha
        // büyük çizmek kaplamayı olduğundan geniş gösterirdi. Uzaklaşınca voksel
        // bir pikselden küçülür ve nokta en az ~2 piksel çizilir; o zaman ağırlık
        // alanla bölünür ki bir voksel her yakınlıkta aynı toplam ışığı versin —
        // uzaklaşmak sahneyi parlatmaz, yakınlaşmak soldurmaz.
        const px = c.size * s * dpr;                 // voxel footprint on screen
        // Large enough to tile: draw flat squares exactly one footprint wide (a
        // hair more, against seams). Otherwise a soft dot no smaller than ~2 px,
        // its weight divided by area so a voxel gives the same light at any zoom.
        const flat = px >= 1.6;
        const ps = flat ? px * 1.03 : Math.max(this.exact ? 2.0 : 1.7, px * 1.15);
        const energy = flat ? 1 : Math.min(1, Math.max(px * px / (ps * ps), 0.12));
        gl.uniform1f(this.loc.psize, ps);
        gl.uniform1f(this.loc.flat_, flat ? 1 : 0);
        gl.uniform1f(this.loc.boost, boost * energy);
        const m = MASK[c.base ? "terr" : ch];
        gl.colorMask(m[0], m[1], m[2], m[3]);
        gl.drawArrays(gl.POINTS, 0, c.n);
      }
      gl.colorMask(true, true, true, true);

      // ---- 2. ekran: zemin, (varsa) fotoğraf düzlemi, sonra renklendirilmiş yoğunluk
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, W, H);
      gl.clearColor(BG[0], BG[1], BG[2], 1);
      gl.clear(gl.COLOR_BUFFER_BIT);

      if (this.plane && this.grid) {
        const nz = this.grid.nz;
        const zl = ((this.planeLayer == null ? (nz - 1) / 2 : this.planeLayer)
                    - (nz - 1) / 2) * this.zspace * this.zsign;
        gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
        gl.useProgram(this.qprog);
        gl.uniformMatrix3fv(this.qloc.rot, false, rot);
        gl.uniform2f(this.qloc.scale, scale[0], scale[1]);
        gl.uniform2f(this.qloc.pan, pan[0], pan[1]);
        gl.uniform2f(this.qloc.half_xy, this.extent.x / 2, this.extent.y / 2);
        gl.uniform1f(this.qloc.zpos, zl);
        gl.uniform1f(this.qloc.alpha, this.planeAlpha);
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, this.tex);
        gl.uniform1i(this.qloc.tex, 0);
        gl.bindBuffer(gl.ARRAY_BUFFER, this.qbuf);
        gl.enableVertexAttribArray(this.qattr);
        gl.vertexAttribPointer(this.qattr, 2, gl.FLOAT, false, 0, 0);
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      }

      // Vokseller fotoğrafın ve zeminin üstüne ışık gibi eklenir.
      gl.blendFunc(gl.ONE, gl.ONE);
      gl.useProgram(this.cprog);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, this.acc);
      gl.uniform1i(this.cloc.acc, 0);
      const cols = [this.cfg.colors.green, this.cfg.colors.orange, this.cfg.colors.nir,
                    this.cfg.terrColor];
      cols.forEach((h, k) => {
        const c = hex2rgb(h);
        // Renk, kendi en parlak bileşeni 1'e gelecek biçimde yükseltilir: koyu
        // zeminde kanal rengi tam doygunlukta okunur, ton (hue) değişmez.
        const g = 0.9 / Math.max(c[0], c[1], c[2], 1e-3);
        gl.uniform3f(this.cloc["c" + k], c[0] * g, c[1] * g, c[2] * g);
      });
      gl.uniform1f(this.cloc.gain, 3.0);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.qbuf);
      gl.enableVertexAttribArray(this.cattr);
      gl.vertexAttribPointer(this.cattr, 2, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }

    /* Axis frame, layer ladder and scale bar live in an SVG layer
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

      // layer ladder — ordinal axis, indices not microns
      const nz = this.nz || 17;
      const kx = -hx * 1.05, ky = hy * 1.05;
      const inRange = z => z >= this.slice.lo - 1e-6 && z <= this.slice.hi + 1e-6;
      line(to(kx, ky, -ex.z / 2), to(kx, ky, ex.z / 2), { stroke: "#39414f" });
      for (let z = 0; z < nz; z++) {
        const zz = (z - (nz - 1) / 2) * this.zspace * this.zsign;
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
