// cc_frame.jsx: Crewcut's frame helper for motion templates (ES5, like ec_lib.jsx).
// The workbench injects CC_CTX (format, size, fps, duration, transparent, face, backdrop, draft, brand) before this
// file runs; templates read it only through CC.*, so no template holds a frame size, a font name or a colour.
// Contract: templates/motion/README.md ("The contract between the workbench and a template").
var CC = (function () {
  var C = {};
  var SIZES = { landscape: [1920, 1080], portrait: [1080, 1920], stage: [1080, 960] };
  var WEIGHTS = { 100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium", 600: "SemiBold",
                  700: "Bold", 800: "ExtraBold", 900: "Black" };
  var MG = { palette: ["#E4572E", "#2F6FDE", "#F2B84B", "#3BA58B"], pastels: ["#F8D5C9", "#CDDBF7", "#FBEACB", "#CBE8DF"],
             ground: "#F1F1EF", ink: "#111111", glass: true, enter_s: 0.4, exit_s: 0.25, ease: "expo",
             drift_pct_per_s: 2.0, blur: { shutter: 180, samples: 16 },
             plate3d: { material: "glossy", bevel: 0.05, extrude: 0.2 } };

  function has(o, k) { return o && Object.prototype.hasOwnProperty.call(o, k) && o[k] !== null && o[k] !== undefined; }
  function over(base, top) {
    var out = {}, k;
    for (k in base) if (Object.prototype.hasOwnProperty.call(base, k)) out[k] = base[k];
    if (top) for (k in top) if (has(top, k)) out[k] = top[k];
    return out;
  }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  C.clamp = clamp;

  // The context with defaults filled in. A template run without the workbench (a sample) gets a landscape insert.
  C.ctx = function () {
    var x = (typeof CC_CTX !== "undefined" && CC_CTX) ? CC_CTX : {};
    var fmt = has(x, "format") && SIZES[x.format] ? x.format : "landscape";
    var size = has(x, "size") ? x.size : SIZES[fmt];
    var brand = x.brand || {};
    return {
      format: fmt, size: [size[0], size[1]], fps: x.fps || 25, duration: x.duration || 4.0,
      transparent: !!x.transparent, face: has(x, "face") ? x.face : null, backdrop: x.backdrop || null,
      draft: !!x.draft, right_free: has(x, "right_free") ? x.right_free : 0.18,
      // "behind": the overlay is composited under the person (the matte passed); "beside" and null: next to them
      layer: x.layer === "behind" || x.layer === "beside" ? x.layer : null,
      // Blender plates of the episode: {id: {first: "<path of 0001.png>", frames: N, ready: bool}}
      plates: x.plates && typeof x.plates === "object" ? x.plates : {},
      brand: { colors: brand.colors || {}, fonts: brand.fonts || {}, shape: brand.shape || {}, mg: over(MG, brand.mg) }
    };
  };

  // Safe box of a format: 16:9 keeps 5 % on every side (8 % at the bottom for overlays, the player bar); 9:16 keeps
  // top 10 %, bottom 20 %, right `right_free` (platform buttons), left 6 %; stage keeps 5 % (6 % at the seam below).
  C.safe = function (fmt, W, H, transparent, rightFree) {
    if (fmt === "portrait") return { x: 0.06 * W, y: 0.10 * H, w: W * (1 - 0.06 - rightFree), h: H * (1 - 0.10 - 0.20) };
    if (fmt === "stage") return { x: 0.05 * W, y: 0.05 * H, w: 0.90 * W, h: H * (1 - 0.05 - 0.06) };
    var bottom = transparent ? 0.08 : 0.05;
    return { x: 0.05 * W, y: 0.05 * H, w: 0.90 * W, h: H * (1 - 0.05 - bottom) };
  };

  // The frame: W, H, u (short side / 1080), safe box, face box (kept free), the free side next to the face, its box,
  // and an anchor at chest-to-shoulder height on that side.
  C.frame = function () {
    var k = C.ctx(), W = k.size[0], H = k.size[1];
    var u = Math.min(W, H) / 1080;
    var safe = C.safe(k.format, W, H, k.transparent, k.right_free);
    var face = null, side = "center", box = safe;
    if (k.face) {
      var cx = k.face.x * W, cy = k.face.y * H;
      var hw = Math.max((k.face.w || 0) / 2, 0.16) * W, hh = Math.max((k.face.h || 0) / 2, 0.14) * H;
      face = { x: cx - hw, y: cy - hh, w: 2 * hw, h: 2 * hh, cx: cx, cy: cy };
      var leftW = (face.x) - safe.x, rightW = (safe.x + safe.w) - (face.x + face.w);
      if (Math.max(leftW, rightW) >= 0.30 * W) {   // room for 120 px words beside the face
        side = rightW >= leftW ? "right" : "left";
        box = side === "right" ? { x: face.x + face.w, y: safe.y, w: rightW, h: safe.h }
                               : { x: safe.x, y: safe.y, w: leftW, h: safe.h };
      } else {
        // no room beside the face (a centred close-up in 9:16): the band below the face box
        side = "below";
        var top = Math.min(safe.y + safe.h, face.y + face.h);
        box = { x: safe.x, y: top, w: safe.w, h: (safe.y + safe.h) - top };
      }
    }
    var ay = face && side !== "below" ? clamp(face.cy + 0.20 * H, box.y + 0.12 * box.h, box.y + 0.88 * box.h)
                                      : box.y + box.h / 2;
    // 9:16 overlays centre left of the platform's buttons (like the keyword chips): (1 - right_free) / 2 of the width
    var ax = k.format === "portrait" && side !== "left" && side !== "right" ? (1 - k.right_free) / 2 * W : box.x + box.w / 2;
    var layer = k.layer === "behind" && face ? "behind" : null;
    if (layer) {
      // behind the person: centred on the face's x at shoulder height, a band across the whole safe width; the
      // person covers the graphic, so the face box rule does not apply
      var below = k.format === "portrait" ? 0.16 : (k.format === "stage" ? 0.20 : 0.22);
      var bh = Math.min(safe.h, 0.34 * H);
      ay = clamp(face.cy + below * H, safe.y + bh / 2, safe.y + safe.h - bh / 2);
      ax = clamp(face.cx, safe.x, safe.x + safe.w);
      side = "behind";
      box = { x: safe.x, y: ay - bh / 2, w: safe.w, h: bh };
    }
    return { W: W, H: H, u: u, fps: k.fps, duration: k.duration, format: k.format, safe: safe, face: face,
             side: side, sideBox: box, anchor: [ax, ay], transparent: k.transparent, layer: layer };
  };

  // A Blender plate from the context ({first, frames, ready}) or null when it is missing or not rendered yet
  C.plate = function (id) { var p = C.ctx().plates[id]; return p && p.first && p.ready !== false ? p : null; };
  C.px = function (n) { return n * C.frame().u; };
  C.brand = function () { return C.ctx().brand; };
  C.mg = function () { return C.ctx().brand.mg; };
  // content colours in order; i = 0 is the accent (only for the one thing that matters)
  C.color = function (i) { var p = C.mg().palette; return p[((i || 0) % p.length + p.length) % p.length]; };
  // the i-th content colour that reads as type on the full-frame ground (luminance apart by 0.3 at least); colours
  // that do not (a yellow on a light ground) are skipped in order; the ink when none reads
  C.textColor = function (i) {
    var p = C.mg().palette, g = C.luma(C.ground()), n = p.length, k = ((i || 0) % n + n) % n;
    for (var j = 0; j < n; j++) { var col = p[(k + j) % n]; if (Math.abs(C.luma(col) - g) >= 0.3) return col; }
    return C.ink();
  };
  C.pastel = function (i) { var p = C.mg().pastels; return p[((i || 0) % p.length + p.length) % p.length]; };
  C.ground = function () { return C.mg().ground; };
  C.ink = function () { return C.mg().ink || C.brand().colors.ink || "#111111"; };
  // {font, style} of a pack font role ("display" or "body") for EC.text
  C.font = function (role) {
    var f = C.brand().fonts[role || "display"] || C.brand().fonts.display || {};
    var w = Math.round((f.weight || (role === "body" ? 500 : 800)) / 100) * 100;
    return { font: f.family || "Inter", style: WEIGHTS[clamp(w, 100, 900)] || "Bold" };
  };
  C.blurSamples = function () { var b = C.mg().blur || {}; return C.ctx().draft ? 8 : (b.samples || 16); };
  C.shutter = function () { return (C.mg().blur || {}).shutter || 180; };

  // A box (in px) is clear of the face box?
  C.clearOfFace = function (b) {
    var F = C.frame(), f = F.face;
    if (!f || F.layer === "behind") return true;
    return b.x + b.w <= f.x || b.x >= f.x + f.w || b.y + b.h <= f.y || b.y >= f.y + f.h;
  };

  // ── colour helpers (pure) ───────────────────────────────────────────
  function rgb(h) {
    h = String(h).replace("#", "");
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    return [parseInt(h.substring(0, 2), 16), parseInt(h.substring(2, 4), 16), parseInt(h.substring(4, 6), 16)];
  }
  function hex2(v) { var s = Math.round(clamp(v, 0, 255)).toString(16); return s.length < 2 ? "0" + s : s; }
  // relative luminance 0..1 of a #hex colour
  C.luma = function (h) { var c = rgb(h); return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255; };
  // a + (b - a) * k for two #hex colours
  C.mix = function (a, b, k) { var x = rgb(a), y = rgb(b); return "#" + hex2(x[0] + (y[0] - x[0]) * k) + hex2(x[1] + (y[1] - x[1]) * k) + hex2(x[2] + (y[2] - x[2]) * k); };

  // Mean luminance (0..1) of the speaker picture under a box (px), from the context's `backdrop_luma`: a number
  // (a generated colour base), a list of rows top to bottom (the render path's 16x9 grid) or {cols, rows, values}
  // (row-major). null when the context has none.
  C.lumaUnder = function (b) {
    var x = typeof CC_CTX !== "undefined" && CC_CTX ? CC_CTX.backdrop_luma : null, F = C.frame();
    if (typeof x === "number") return x;
    if (x instanceof Array && x.length && x[0] instanceof Array) {          // rows top to bottom, as the render path writes it
      var flat = []; for (var rr = 0; rr < x.length; rr++) flat = flat.concat(x[rr]);
      x = { cols: x[0].length, rows: x.length, values: flat };
    }
    if (!x || !x.values || !x.cols || !x.rows) return null;
    if (!b) b = F.sideBox;
    var cw = F.W / x.cols, ch = F.H / x.rows, sum = 0, n = 0;
    for (var r = 0; r < x.rows; r++) for (var q = 0; q < x.cols; q++) {
      var ox = Math.min(b.x + b.w, (q + 1) * cw) - Math.max(b.x, q * cw), oy = Math.min(b.y + b.h, (r + 1) * ch) - Math.max(b.y, r * ch);
      if (ox > 0 && oy > 0) { var wgt = ox * oy; sum += wgt * x.values[r * x.cols + q]; n += wgt; }
    }
    return n > 0 ? sum / n : null;
  };
  // Type colour. Full frame: the pack's ink on its ground. Overlay: dark type where the picture under `box` is
  // light (luminance >= 0.55), else light type; light type when the context does not say. `shade` is the opposite
  // tone for the soft legibility shadow.
  C.tone = function (box) {
    var k = C.ctx(), cols = k.brand.colors, a = cols.ink || C.ink(), b = cols.paper || "#FFFFFF";
    var dark = C.luma(a) <= C.luma(b) ? a : b, light = dark === a ? b : a;
    if (!k.transparent) { var ink = C.ink(); return { fill: ink, shade: C.luma(ink) > 0.5 ? dark : light, onLight: C.luma(ink) < 0.5 }; }
    var x = C.lumaUnder(box);
    return x !== null && x >= 0.55 ? { fill: dark, shade: light, onLight: true, luma: x } : { fill: light, shade: dark, onLight: false, luma: x };
  };

  // ── time helpers (pure) ─────────────────────────────────────────────
  // the moment a word or number must be complete for a cue: 1.5 frames of the plan's fps before it
  C.landBy = function (cue) { return cue - 1.5 / (C.ctx().fps || 25); };
  C.enterS = function () { return clamp(C.mg().enter_s || 0.4, 0.35, 0.5); };
  C.exitS = function () { return C.mg().exit_s || 0.25; };
  C.ease = function () { return C.mg().ease || "expo"; };
  // the slow push of a hold: scale factor after `secs` seconds (linear, drift_pct_per_s clamped to 1.5..3 %)
  C.driftAt = function (secs, pct) {
    var p = clamp(pct === undefined ? (C.mg().drift_pct_per_s || 2) : pct, 1.5, 3);
    return 1 + p / 100 * Math.max(0, secs);
  };
  // a text size that fits `measured` (px at `size`) into `maxW`, never above `size`, never below `minPx`
  C.fit = function (size, measured, maxW, minPx) {
    var s = measured > maxW && measured > 0 ? size * maxW / measured : size;
    return Math.max(minPx || 40 * C.frame().u, s);
  };

  // ── engine helpers (need EC from ec_lib.jsx) ────────────────────────
  // Ink box of a text layer in its own space (origin = the anchor on the baseline): {left, top, width, height}.
  // EC.dims reports 0 for text layers; the object model's sourceRectAtTime measures the glyphs that render.
  C.rect = function (c, id, t) { return EC.layerObj(c, id).sourceRectAtTime(t || 0, false); };
  var _probe = {}, _mcache = {};
  function probe(c) {
    if (_probe[c] === undefined || !EC.layerObj(c, _probe[c])) {
      _probe[c] = EC.text(c, { text: "H", size: 100, fill: "#000000", name: "cc measure", justify: "left" });
    }
    return _probe[c];
  }
  // Measure a string set in a pack font role at `size`: ink box plus `advance` (the width it takes in a line,
  // side bearings included), so strings set one after the other line up exactly. Cached; call C.measureDone(c)
  // after the last measurement to remove the helper layer.
  C.measure = function (c, text, size, role) {
    var f = C.font(role || "display"), key = [c, f.font, f.style, size, text].join("|");
    if (_mcache[key]) return _mcache[key];
    var id = probe(c);
    EC.run("layer.setText", { comp: c, layer: id, text: "H" + text + "H", font: f.font, style: f.style, size: size });
    var withH = C.rect(c, id);
    EC.run("layer.setText", { comp: c, layer: id, text: "HH" });
    var hh = C.rect(c, id);
    var ink = { left: 0, top: 0, width: 0, height: 0 };
    if (String(text).replace(/\s/g, "") !== "") { EC.run("layer.setText", { comp: c, layer: id, text: text }); ink = C.rect(c, id); }
    var m = { left: ink.left, top: ink.top, width: ink.width, height: ink.height, advance: withH.width - hh.width };
    _mcache[key] = m;
    return m;
  };
  C.measureDone = function (c) {
    if (_probe[c] !== undefined) { var l = EC.layerObj(c, _probe[c]); if (l) l.remove(); delete _probe[c]; }
  };
  // A text layer in a pack font role. o: {text, size, fill, role, justify, name, tracking}
  C.text = function (c, o) {
    var f = C.font(o.role || "display");
    if (!o.fill) o.fill = C.tone().fill;
    var p = { text: o.text, size: o.size, fill: o.fill || C.tone().fill, font: f.font, style: f.style,
              justify: o.justify || "left", name: o.name || o.text };
    if (o.tracking !== undefined) p.tracking = o.tracking;
    return EC.text(c, p);
  };
  // Soft shadow in the opposite tone, only on overlays (type over a moving picture): a wide soft one that lifts the
  // word off a busy picture and a tight one that keeps the glyph edges crisp. Both follow the glyphs, never a box.
  C.legible = function (c, id, size, tone, strength) {
    if (!C.frame().transparent) return null;
    var t = tone || C.tone(), k = strength === undefined ? 1 : strength, col = EC.rgba(t.shade);
    var wide = EC.fx(c, id, "Drop Shadow", { color: col, opacity: (t.onLight ? 30 : 55) * k, direction: 180,
                                             distance: size * 0.02, softness: size * 0.32 });
    var tight = EC.fx(c, id, "Drop Shadow", { color: col, opacity: (t.onLight ? 18 : 34) * k, direction: 180,
                                              distance: size * 0.012, softness: size * 0.06 });
    return [wide, tight];
  };
  // An open stroke-only path on its own new shape layer (shape.newPath alone would add to a selected shape layer).
  // pts in layer space; returns {layer, group, trim} where trim is the path prefix of a Trim Paths operator.
  C.stroke = function (c, o) {
    var id = EC.shape(c, { kind: "none", name: o.name || "stroke" });
    var r = EC.run("shape.newPath", { comp: c, layer: id, vertices: o.pts, closed: !!o.closed, fill: false, space: "layer",
                                      stroke: o.color, strokeWidth: o.width, inTangents: o.inT, outTangents: o.outT });
    var g = "contents/group";
    try { EC.set(c, id, g + "/contents/stroke/cap", o.cap === undefined ? 1 : o.cap); } catch (e) { g = null; }
    var t = EC.run("layer.addShapeItem", { comp: c, layer: id, kind: "trim", group: r.group });
    return { layer: id, group: r.group, trim: t.path + "/" };
  };
  // The one allowed plate: frosted glass that shows the picture behind it. A blurred, brightened copy of the
  // `source` comp under a rounded matte, a light veil, a thin rim and one soft shadow. Every part hangs on
  // `parent` (a null at the plate's centre) and follows `fade` ([[t, 0..100], ...]). Refused when the pack turns
  // the glass off (brand.mg.glass false): the caller gets null and sets its type on the ground instead.
  // o: {parent, source, w, h, radius, blur, veil (0..100), veilColor, rim (0..100), shadow (0..100), fade, name}
  C.glass = function (c, o) {
    if (C.mg().glass === false) return null;
    var u = C.frame().u, fade = o.fade || [[0, 100]], nm = o.name || "glass", out = {};
    function hang(id, dy, op) {
      C.child(c, id, o.parent); EC.set(c, id, "transform/position", [0, dy || 0]); EC.sw(c, id, "motionBlur", true);
      var kk = []; for (var z = 0; z < fade.length; z++) kk.push([fade[z][0], fade[z][1] * op / 100]);
      if (kk.length > 1) EC.keys(c, id, "transform/opacity", kk, "linear"); else EC.set(c, id, "transform/opacity", kk[0][1]);
      return id;
    }
    function plate(name, fill, op, dy, blur, ws) {
      var id = EC.shape(c, { kind: "rounded", size: [o.w * (ws || 1), o.h], fill: fill, name: nm + " " + name });
      EC.set(c, id, "contents/group/contents/rect/roundness", o.radius);
      if (blur) EC.fx(c, id, "Gaussian Blur", { blurriness: blur });
      return hang(id, dy, op);
    }
    out.shadow = plate("shadow", "#000000", o.shadow === undefined ? 22 : o.shadow, 18 * u, 38 * u, 0.96);
    out.body = EC.precompLayer(c, o.source, { name: nm + " body" });
    EC.fx(c, out.body, "Gaussian Blur", { blurriness: (o.blur || 44) * u, repeatEdge: true });
    EC.fx(c, out.body, "Brightness & Contrast", { brightness: 10, contrast: -12 });
    out.matte = plate("matte", "#FFFFFF", 100, 0);
    EC.matte(c, out.body, out.matte, "alpha");
    out.veil = plate("veil", o.veilColor || "#FFFFFF", o.veil === undefined ? 46 : o.veil, 0);
    out.rim = EC.shape(c, { kind: "rounded", size: [o.w, o.h], stroke: "#FFFFFF", strokeWidth: 2 * u, fillOpacity: 0, name: nm + " rim" });
    EC.set(c, out.rim, "contents/group/contents/rect/roundness", o.radius);
    hang(out.rim, 0, o.rim === undefined ? 70 : o.rim);
    return out;
  };
  // A null as a local camera rig at `pos` (children are placed relative to it; scaling pushes around it).
  C.rig = function (c, name, pos) {
    var id = EC.nul(c, { name: name });
    EC.set(c, id, "transform/position", [pos[0], pos[1]]);
    return id;
  };
  C.child = function (c, id, parent) { EC.run("layer.setParent", { comp: c, layers: [id], parent: parent, compensate: false }); };
  // The slow push of a hold on a rig: linear scale from t0 to t1 (no motion blur needed: it only drifts).
  C.drift = function (c, id, t0, t1, base, pct) {
    var b = base === undefined ? 100 : base, s = b * C.driftAt(t1 - t0, pct);
    EC.keys(c, id, "transform/scale", [[t0, [b, b]], [t1, [s, s]]], "linear");
  };
  // Word rises out of its own baseline (a matte line it cannot cross) and sinks back for the exit.
  // o: {parent, x, y (baseline, parent space), size, ink (C.measure), t (start), dur, outAt, outDur, pop (scale 3 %)}
  // The word's anchor moves to its ink centre so a scale pop grows from the middle of the word.
  C.rise = function (c, id, o) {
    var ink = o.ink, s = o.size, cx = ink.left + ink.width / 2, cy = ink.top + ink.height / 2;
    // the line sits 0.42 em under the baseline (descenders and the soft shadow stay inside); its edge is feathered
    var dy = 1.24 * s, pad = 0.35 * s, below = 0.42 * s;
    EC.set(c, id, "transform/anchor", [cx, cy]);
    var mt = EC.shape(c, { kind: "rect", size: [ink.width + 2 * pad, (below - ink.top) + pad], fill: "#FFFFFF", name: (o.name || "word") + " line" });
    EC.fx(c, mt, "Gaussian Blur", { blurriness: 0.05 * s });
    if (o.parent !== undefined) { C.child(c, mt, o.parent); C.child(c, id, o.parent); }
    EC.set(c, mt, "transform/position", [o.x + cx, o.y + (ink.top - pad + below) / 2]);
    EC.matte(c, id, mt, "alpha");
    var x = o.x + cx, y = o.y + cy, ks = [[o.t, [x, y + dy]], [o.t + o.dur, [x, y]]], ez = [C.ease()];
    if (o.outAt !== undefined && o.outAt !== null) { ks.push([o.outAt, [x, y]]); ks.push([o.outAt + (o.outDur || C.exitS()), [x, y + dy]]); ez.push("linear"); ez.push("expoIn"); }
    EC.keys(c, id, "transform/position", ks, ez);
    if (o.pop !== false) {
      var p0 = 100 - (o.popPct || 3), p1 = 100 + Math.min(4, (o.popPct || 3));
      EC.keys(c, id, "transform/scale", [[o.t, [p0, p0]], [o.t + o.dur * 0.7, [p1 * 0.995, p1 * 0.995]], [o.t + o.dur * 1.25, [100, 100]]], ["out", "smooth"]);
    }
    EC.sw(c, id, "motionBlur", true);
    return mt;
  };
  // width of a string set character by character (as C.meter sets it): the sum of the advances
  C.rowWidth = function (c, text, size, role) {
    var w = 0, ch = String(text).split("");
    for (var i = 0; i < ch.length; i++) w += C.measure(c, ch[i], size, role).advance;
    return w;
  };
  // A number that counts up like a meter (number_roll, versus). The value eases from `from` to the target and lands
  // exactly at `land`; the units reel rolls with the value and ticks between whole digits, every higher reel turns
  // only when the reel to its right carries from 9 to 0, and the units reel settles with a small wobble, so a held
  // digit is always whole. Each reel sits behind its own feathered window (opens from a slit, closes at the exit).
  // Digits are set with their real advances in the display font; non-digits (a sign, separators) rise in place.
  // o: {parent, text, x (row start), base (baseline), size, tone, rollAt, land, outAt, from, ease (power), name}
  C.meter = function (c, o) {
    var s = o.size, base = o.base, tone = o.tone || C.tone(), fill = o.fill || tone.fill, nm = o.name || "meter";
    var rollAt = o.rollAt || 0, land = o.land, tOut = o.outAt, enter = C.enterS(), exit = C.exitS(), pe = o.ease || 2.2;
    var cap = -C.measure(c, "0", s).top, items = [], wx = 0, ch = String(o.text).split("");
    for (var i = 0; i < ch.length; i++) {
      var mm = C.measure(c, ch[i], s);
      items.push({ ch: ch[i], adv: mm.advance, ink: mm, digit: /[0-9]/.test(ch[i]), x: wx });
      wx += mm.advance;
    }
    var digits = 0; for (var q = 0; q < items.length; q++) if (items[q].digit) digits++;
    // leading zeros stay hidden until the count reaches them
    var digitStr = ""; for (var q2 = 0; q2 < items.length; q2++) if (items[q2].digit) digitStr += items[q2].ch;
    var target = parseInt(digitStr, 10) || 0, from = Math.max(0, Math.min(target, Math.round(Number(o.from) || 0)));
    // the units reel always shows; a higher reel shows once the count reaches it (or when the target never does)
    var vis = function (pw) { return "(" + (pw === 1 || target < pw ? "true" : "(k0 + (g0 > 0 ? 1 : 0) >= " + pw + ")") + ")"; };
    var core = "var t0=" + rollAt + ",tl=" + land + ",fr=" + from + ",to=" + target + ";" +
               "var uu=Math.max(0,Math.min(1,(time-t0)/(tl-t0)));var e=1-Math.pow(1-uu," + pe + ");" +
               "var w=fr+(to-fr)*e+1e-7;var k0=Math.floor(w),f0=w-k0;var g0=f0<0.75?0:(function(x){return x*x*(3-2*x);})((f0-0.75)/0.25);" +
               "if(time>=tl){k0=to;g0=0;}";
    var L = 1.3 * s, reel = "9";
    for (var r = 0; r <= 9; r++) reel += "\r" + r;
    reel += "\r0\r1";
    var di = 0, ids = [], colVis = [], pos = digits - 1;
    for (var k = 0; k < items.length; k++) {
      var it = items[k], cx = o.x + it.x + it.adv / 2;
      if (!it.digit) { colVis.push(null); continue; }
      var pw = Math.pow(10, pos);
      colVis.push(pw);
      var t0 = rollAt + 0.03 * di;
      var rl = EC.text(c, { text: reel, size: s, fill: fill, font: C.font("display").font, style: C.font("display").style,
                            justify: "center", leading: L, name: nm + " reel " + di });
      C.legible(c, rl, s, tone);
      C.child(c, rl, o.parent);
      var move = pos === 0 ? "var p=k0+g0;if(time>tl){var d=time-tl;p+=0.07*Math.exp(-12*d)*Math.sin(30*d);}"
                           : "var p=Math.floor(k0/" + pw + ")+(((k0+1)%" + pw + ")===0?g0:0);";
      EC.expr(c, rl, "transform/position", core + move +
              "if(time>" + tOut + "){var q=time-" + tOut + ";p+=0.5*(26/" + exit + ")*q*q;}" +
              "var m=((p%10)+10)%10;[" + cx + "," + base + "-(m+1)*" + L + "]");
      EC.expr(c, rl, "transform/opacity", core + vis(pw) + "?value:0");
      EC.sw(c, rl, "motionBlur", true);
      // the window: opens like a shutter from a slit, closes at the end (a feathered alpha matte, not drawn)
      var wTop = base - cap - 0.26 * s, wBot = base + 0.26 * s;
      var win = EC.shape(c, { kind: "rect", size: [it.adv + 0.14 * s, wBot - wTop], fill: "#FFFFFF", name: nm + " window " + di });
      EC.fx(c, win, "Gaussian Blur", { blurriness: 0.035 * s });
      C.child(c, win, o.parent);
      EC.set(c, win, "transform/position", [cx, (wTop + wBot) / 2]);
      EC.keys(c, win, "transform/scale", [[t0, [100, 40]], [t0 + enter, [100, 100]], [tOut, [100, 100]], [tOut + exit, [100, 0]]],
              [C.ease(), "linear", "expoIn"]);
      EC.matte(c, rl, win, "alpha");
      ids.push(rl);
      di++; pos--;
    }
    // separators and a sign: they rise when the digit on their left shows
    var leftPw = null;
    for (var k3 = 0; k3 < items.length; k3++) {
      var it3 = items[k3];
      if (it3.digit) { leftPw = colVis[k3]; continue; }
      var s1 = C.text(c, { text: it3.ch, size: s, fill: fill, name: nm + " " + it3.ch });
      C.legible(c, s1, s, tone);
      C.rise(c, s1, { parent: o.parent, x: o.x + it3.x, y: base, size: s, ink: it3.ink, t: rollAt + 0.05, dur: enter,
                       outAt: tOut, outDur: exit, name: nm + " sep " + k3, pop: false });
      if (leftPw !== null) EC.expr(c, s1, "transform/opacity", core + vis(leftPw) + "?value:0");
      ids.push(s1);
    }
    return { ids: ids, width: wx, target: target, from: from };
  };
  // Full-frame ground: the pack's ground colour, lit at its edges by large soft pools of the palette colours (mixed
  // into the ground by `strength`), which drift slowly so a hold never stands still. The middle stays the clean
  // ground the type sits on. Nothing on an overlay. o: {strength 0..1 (default 0.42), name}
  C.groundLayer = function (c, o) {
    o = o || {};
    var F = C.frame();
    if (F.transparent) return null;
    var g = o.color || C.ground(), k = o.strength === undefined ? 0.3 : o.strength, D = F.duration, W = F.W, H = F.H;
    var id = EC.solid(c, { name: o.name || "ground", color: g, w: Math.round(W * 1.3), h: Math.round(H * 1.3) });
    EC.set(c, id, "transform/position", [W / 2, H / 2]);
    var out = [id];
    if (k > 0) {
      var d = 0.78 * Math.max(W, H), m = Math.min(W, H);
      // pools just outside the corners, drifting a little inward: colour index, start and end centre (frame fractions)
      var pools = [[1, [-0.10, -0.06], [-0.05, -0.02]], [2, [1.10, -0.04], [1.05, 0.00]], [3, [1.06, 1.10], [1.01, 1.05]], [0, [-0.06, 1.10], [-0.02, 1.05]]];
      for (var i = 0; i < pools.length; i++) {
        var col = C.mix(g, C.color(pools[i][0]), pools[i][0] === 0 ? k * 0.8 : k);
        var e = EC.shape(c, { kind: "ellipse", size: [d, d * 0.75], fill: col, name: (o.name || "ground") + " light " + i });
        EC.fx(c, e, "Gaussian Blur", { blurriness: 0.26 * m });
        EC.keys(c, e, "transform/position", [[0, [pools[i][1][0] * W, pools[i][1][1] * H]], [D, [pools[i][2][0] * W, pools[i][2][1] * H]]], "linear");
        out.push(e);
      }
      // a fine grain over the ground keeps its soft gradients from banding in 8-bit video
      var gr = EC.solid(c, { name: (o.name || "ground") + " grain", color: "#808080", w: W, h: H });
      EC.set(c, gr, "transform/position", [W / 2, H / 2]);
      EC.sw(c, gr, "adjustment", true);
      EC.fx(c, gr, "Noise", { amount: 1.6, color: false });
      out.push(gr);
    }
    return out;
  };
  return C;
})();
