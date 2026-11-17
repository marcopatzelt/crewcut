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
    return { W: W, H: H, u: u, fps: k.fps, duration: k.duration, format: k.format, safe: safe, face: face,
             side: side, sideBox: box, anchor: [ax, ay], transparent: k.transparent };
  };

  C.px = function (n) { return n * C.frame().u; };
  C.brand = function () { return C.ctx().brand; };
  C.mg = function () { return C.ctx().brand.mg; };
  // content colours in order; i = 0 is the accent (only for the one thing that matters)
  C.color = function (i) { var p = C.mg().palette; return p[((i || 0) % p.length + p.length) % p.length]; };
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
    var f = C.frame().face;
    if (!f) return true;
    return b.x + b.w <= f.x || b.x >= f.x + f.w || b.y + b.h <= f.y || b.y >= f.y + f.h;
  };
  return C;
})();
