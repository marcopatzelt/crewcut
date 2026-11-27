/* cc.js: Crewcut's helpers for HyperFrames templates (part of Crewcut, MIT).
 *
 * Crewcut inlines this file into every insert's index.html, after window.CC_DATA (crewcut/render/hyperframes.py):
 *   data        the template's params (template.json defaults with the plan's data over them)
 *   cues        name -> seconds inside the insert (a cue on a spoken word)
 *   format      landscape | portrait;  size [w, h];  fps;  frames;  duration (seconds, incl. the 2 extra frames)
 *   transparent true for an overlay (nothing may paint the page background then)
 *   face        {x, y, w, h} fractions of the frame (overlays only), or null
 *   backdrop_luma  brightness 0..1 of the speaker picture under an overlay (16 x 9 grid, one number, or null)
 *   safe        {x, y, w, h} pixels inside the safe areas
 *   palette     {ink, paper, accent, highlight};  fonts {display, body: {family, weight}};  min_text_px
 *   motion      {enter_s, exit_s, stagger_s, ease [4], out_ease [4], push_px, drift_pct_per_s}
 *   shapes      the pack's stored background shapes for this format (chapter card only)
 * Deterministic: no clock, no random numbers, no network. Everything visible is a function of timeline time.
 *
 * The channel's grammar (brand/references/grafik-system in a studio, mirrored by the defaults here):
 * - one entrance curve (cubic-bezier 0.2 0 0 1, 0.4 s) and one exit curve (cubic-bezier 0.3 0 0.8 0.15, 0.28 s),
 *   2 frames between the elements of one graphic, the most important element last;
 * - one transition, the push: an overlay slides push_px in from the speaker's side, opacity 0 to 100 % and scale
 *   96 to 100 %, and leaves the same way back; a full frame cuts in on a frame whose content already moves;
 * - 2D stands still while it holds (drift 0); type over video gets an ink halo, a side scrim and a soft shadow.
 */
(function () {
  "use strict";
  var D = window.CC_DATA || {};
  var CC = {};
  var size = D.size || [1920, 1080];
  CC.D = D;
  CC.data = D.data || {};
  CC.format = D.format || "landscape";
  CC.W = size[0];
  CC.H = size[1];
  CC.portrait = CC.H > CC.W;
  CC.fps = D.fps || 25;
  CC.f = 1 / CC.fps;
  CC.duration = D.duration || 3;
  CC.u = Math.min(CC.W, CC.H) / 1080;
  CC.transparent = !!D.transparent;
  CC.palette = D.palette || { ink: "#141413", paper: "#FAF9F5", accent: "#2320D6", highlight: "#2320D6" };
  CC.safe = D.safe || { x: Math.round(0.05 * CC.W), y: Math.round(0.05 * CC.H), w: Math.round(0.9 * CC.W), h: Math.round(0.87 * CC.H) };
  CC.face = D.face || null;
  CC.minText = D.min_text_px || 40;
  var M = D.motion || {};
  CC.enter = M.enter_s || 0.4;
  CC.exit = M.exit_s || 0.28;
  CC.stagger = M.stagger_s || 0.08;
  CC.pushPx = (M.push_px === undefined ? 28 : M.push_px) * CC.u;
  CC.drift = (M.drift_pct_per_s || 0) / 100;

  // ---- time ----------------------------------------------------------------------------------------------------
  CC.cue = function (name, fallback) {
    var c = (D.cues || {})[name];
    if (typeof c === "number" && isFinite(c)) return Math.max(0, Math.min(c, CC.duration));
    return fallback;
  };
  // complete 1 frame before the cue (the word is there +-2 frames, the motion starts 0.3 to 0.5 s before)
  CC.landBy = function (cue) { return Math.max(0, cue - CC.f); };
  // the exit starts so that everything is gone 2 frames before the end
  CC.outAt = function (extra) { return Math.max(0, CC.duration - CC.exit - (extra || 0) - 2 * CC.f); };

  // cubic-bezier easing as a function of progress, Newton steps then bisection
  CC.bezier = function (x1, y1, x2, y2) {
    function a(p1, p2) { return 1 - 3 * p2 + 3 * p1; }
    function b(p1, p2) { return 3 * p2 - 6 * p1; }
    function c(p1) { return 3 * p1; }
    function at(t, p1, p2) { return ((a(p1, p2) * t + b(p1, p2)) * t + c(p1)) * t; }
    function slope(t, p1, p2) { return 3 * a(p1, p2) * t * t + 2 * b(p1, p2) * t + c(p1); }
    return function (x) {
      if (x <= 0) return 0;
      if (x >= 1) return 1;
      var t = x;
      for (var i = 0; i < 8; i++) {
        var s = slope(t, x1, x2);
        if (Math.abs(s) < 1e-6) break;
        var d = at(t, x1, x2) - x;
        if (Math.abs(d) < 1e-7) return at(t, y1, y2);
        t -= d / s;
      }
      var lo = 0, hi = 1;
      t = x;
      for (var j = 0; j < 40; j++) {
        var v = at(t, x1, x2);
        if (Math.abs(v - x) < 1e-7) break;
        if (v < x) lo = t; else hi = t;
        t = (lo + hi) / 2;
      }
      return at(t, y1, y2);
    };
  };
  var e = M.ease || [0.2, 0, 0, 1], o = M.out_ease || [0.3, 0, 0.8, 0.15];
  CC.easeIn = CC.bezier(e[0], e[1], e[2], e[3]);     // "emphasized": every entrance
  CC.easeOut = CC.bezier(o[0], o[1], o[2], o[3]);    // every exit
  CC.linear = function (p) { return p; };

  // ---- space -----------------------------------------------------------------------------------------------------
  CC.px = function (n) { return Math.round(n * CC.u) + "px"; };
  // the free side next to the face (overlays): "left" or "right" (or "below" in a narrow Short), its box inside safe,
  // and the direction the speaker is in (-1 left, +1 right): overlays push in from there
  CC.side = function (prefer) {
    var s = CC.safe;
    if (!CC.face) return { side: prefer === "left" ? "left" : "right", box: { x: s.x, y: s.y, w: s.w, h: s.h }, from: prefer === "left" ? 1 : -1 };
    var fx = CC.face.x * CC.W, fw = (Math.max(CC.face.w, 0.0) + 0.32) * CC.W;     // the face plus 16 % to each side
    var leftW = Math.max(0, fx - fw / 2 - s.x), rightW = Math.max(0, s.x + s.w - (fx + fw / 2));
    var side = prefer === "left" || prefer === "right" ? prefer : (rightW >= leftW ? "right" : "left");
    var box;
    if (CC.portrait && Math.max(leftW, rightW) < 0.3 * CC.W) {
      var top = (CC.face.y + CC.face.h * 0.75) * CC.H;
      return { side: "below", box: { x: s.x, y: top, w: s.w, h: Math.max(0, s.y + s.h - top) }, from: 0 };
    }
    if (side === "right") box = { x: Math.min(s.x + s.w, fx + fw / 2), y: s.y, w: rightW, h: s.h };
    else box = { x: s.x, y: s.y, w: leftW, h: s.h };
    if (box.w < 0.22 * CC.W) box = side === "right" ? { x: s.x + s.w * 0.55, y: s.y, w: s.w * 0.45, h: s.h } : { x: s.x, y: s.y, w: s.w * 0.45, h: s.h };
    return { side: side, box: box, from: side === "right" ? -1 : 1 };
  };
  // brightness of the speaker picture under a box (pixels): 0..1, or null without a picture
  CC.lumaUnder = function (box) {
    var L = D.backdrop_luma;
    if (L === null || L === undefined) return null;
    if (typeof L === "number") return L;
    var rows = L.length, cols = rows ? L[0].length : 0, sum = 0, n = 0;
    for (var r = 0; r < rows; r++) for (var q = 0; q < cols; q++) {
      var cx = (q + 0.5) / cols * CC.W, cy = (r + 0.5) / rows * CC.H;
      if (cx >= box.x && cx <= box.x + box.w && cy >= box.y && cy <= box.y + box.h) { sum += L[r][q]; n++; }
    }
    return n ? sum / n : null;
  };
  // colours of type: over video the highlight for the keyword and paper for side lines (both on an ink halo); on a
  // paper ground ink type and the accent in the highlight's role (the highlight is never text on paper)
  CC.colors = function (ground) {
    var pal = CC.palette;
    if (CC.transparent) return { main: pal.highlight, side: pal.paper, video: true };
    if (ground === "ink") return { main: pal.highlight, side: pal.paper, video: false };
    return { main: pal.accent, side: pal.ink, video: false };
  };
  CC.rgba = function (hex, a) {
    var h = String(hex).replace("#", "");
    return "rgba(" + parseInt(h.substring(0, 2), 16) + "," + parseInt(h.substring(2, 4), 16) + "," + parseInt(h.substring(4, 6), 16) + "," + a + ")";
  };
  CC.shadow = function () { return "0 " + CC.px(5) + " " + CC.px(16) + " " + CC.rgba(CC.palette.ink, 0.55); };

  // ---- elements and type -----------------------------------------------------------------------------------------
  CC.text = function (v, fallback) {
    if (v === null || v === undefined) return fallback || "";
    return String(v);
  };
  CC.el = function (tag, cls, text, parent) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    if (parent) parent.appendChild(n);
    return n;
  };
  // the largest font size <= size whose width fits maxW (never below min)
  CC.fit = function (el, maxW, size, min) {
    var s = Math.round(size);
    el.style.fontSize = s + "px";
    var floor = Math.round(min || CC.minText);
    while (el.scrollWidth > maxW && s > floor) {
      s = Math.max(floor, s - Math.max(1, Math.round(s * 0.04)));
      el.style.fontSize = s + "px";
    }
    return s;
  };
  // a word that rises out of its own baseline: <span class="cc-mask"><span class="cc-rise">word</span></span>
  CC.riser = function (text, parent, cls) {
    var mask = CC.el("span", "cc-mask" + (cls ? " " + cls : ""), null, parent);
    return CC.el("span", "cc-rise", text, mask);
  };
  // a ground for full-frame inserts (overlays paint nothing)
  CC.ground = function (root, color) {
    if (CC.transparent) return null;
    var g = CC.el("div", "cc-ground");
    g.style.background = color || CC.palette.paper;
    root.insertBefore(g, root.firstChild);
    return g;
  };
  // the halo behind type over video: an ink copy of the type, grown 27 px, blurred 28 px, 80 % opaque, in place
  CC.halo = function (el, root) {
    var h = el.cloneNode(true);
    h.removeAttribute("id");
    h.className = (h.className || "") + " cc-halo";
    var all = [h].concat(Array.prototype.slice.call(h.querySelectorAll("*")));
    all.forEach(function (n) {
      n.removeAttribute && n.removeAttribute("id");
      n.style.color = CC.palette.ink;
      n.style.textShadow = "none";
      n.style.webkitTextStroke = Math.round(54 * CC.u) + "px " + CC.palette.ink;
      if (n.classList && n.classList.contains("cc-mask")) n.style.overflow = "visible";
    });
    h.style.filter = "blur(" + Math.round(28 * CC.u) + "px)";
    h.style.opacity = "0.8";
    h.style.pointerEvents = "none";
    (root || el.parentNode).insertBefore(h, el);
    return h;
  };
  // a soft ink gradient over the free side, so light type reads over a bright set: 0 % from 58 % of the width to 35 %
  // at the edge (on the speaker's other side)
  CC.scrim = function (root, side) {
    if (!CC.transparent) return null;
    var s = CC.el("div", "cc-scrim");
    var dir = side === "left" ? "to left" : "to right";
    var a = CC.rgba(CC.palette.ink, 0.35), z = CC.rgba(CC.palette.ink, 0);
    s.style.background = "linear-gradient(" + dir + ", " + z + " 58%, " + a + " 100%)";
    if (side === "below") s.style.background = "linear-gradient(to bottom, " + z + " 45%, " + a + " 100%)";
    root.insertBefore(s, root.firstChild);
    return s;
  };

  // ---- the one transition ----------------------------------------------------------------------------------------
  // in: from the speaker's side (from = -1: the speaker is left, so the graphic slides in from the left)
  CC.pushIn = function (tl, targets, at, from, dur) {
    var dx = (from || 0) * CC.pushPx, dy = from ? 0 : CC.pushPx;
    tl.fromTo(targets, { x: dx, y: dy, opacity: 0, scale: 0.96 },
      { x: 0, y: 0, opacity: 1, scale: 1, duration: dur || CC.enter, ease: CC.easeIn }, at);
  };
  CC.pushOut = function (tl, targets, at, from, dur) {
    var dx = (from || 0) * CC.pushPx, dy = from ? 0 : CC.pushPx;
    tl.to(targets, { x: dx, y: dy, opacity: 0, scale: 0.96, duration: dur || CC.exit, ease: CC.easeOut }, at);
  };
  // a hold that drifts only when the pack asks for it (drift_pct_per_s; 0 keeps 2D still)
  CC.hold = function (tl, el, origin) {
    if (!CC.drift) return;
    tl.fromTo(el, { scale: 1 }, { scale: 1 + CC.drift * CC.duration, duration: CC.duration, ease: CC.linear, transformOrigin: origin || "50% 50%" }, 0);
  };

  // ---- start -----------------------------------------------------------------------------------------------------
  // build after the pack's fonts are loaded (measuring with a fallback font gives wrong widths), then register
  CC.start = function (id, build) {
    function go() {
      var tl = gsap.timeline({ paused: true });
      build(tl);
      tl.set({}, {}, CC.duration);            // the timeline is as long as the insert
      window.__timelines = window.__timelines || {};
      window.__timelines[id] = tl;
    }
    var fonts = D.fonts || {};
    var loads = [];
    if (document.fonts && document.fonts.load) {
      for (var r in fonts) if (Object.prototype.hasOwnProperty.call(fonts, r)) {
        loads.push(document.fonts.load(fonts[r].weight + " 100px \"" + fonts[r].family + "\""));
      }
    }
    if (loads.length && window.Promise) Promise.all(loads).then(go, go); else go();
  };

  window.CC = CC;
})();
