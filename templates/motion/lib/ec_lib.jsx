// ec_lib.jsx: helpers for crewcut motion. Every helper calls EffectCraft engine commands
// (app.run(id, params)), the same registry the CLI, menus and shortcuts use. Times are comp seconds;
// layers are created at start 0 and trimmed with in/out points, so layer time == comp time.
var EC = (function () {
  var E = {};
  E.log = [];
  function run(id, p) { return app.run(id, p || {}); }
  E.run = run;

  // ── colours and values ──────────────────────────────────────────────
  E.hex = function (h, a) {
    if (h instanceof Array) return h;
    h = String(h).replace("#", "");
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var r = parseInt(h.substring(0, 2), 16) / 255, g = parseInt(h.substring(2, 4), 16) / 255, b = parseInt(h.substring(4, 6), 16) / 255;
    return a === undefined ? [r, g, b] : [r, g, b, a];
  };
  E.rgba = function (h) { var c = E.hex(h); return c.length === 4 ? c : [c[0], c[1], c[2], 1]; };
  E.lerp = function (a, b, t) { return a + (b - a) * t; };
  // deterministic random (seeded), so templates render the same every time
  E.rng = function (seed) {
    var s = (seed >>> 0) || 1;
    return function () { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return (s % 1000000) / 1000000; };
  };

  // ── comps ───────────────────────────────────────────────────────────
  E.comp = function (o) {
    var p = { name: o.name, width: o.width || 1920, height: o.height || 1080, frameRate: o.fps || 60, duration: o.duration || 5 };
    if (o.bg) p.background = o.bg;
    if (o.shutterAngle !== undefined) p.shutterAngle = o.shutterAngle;
    if (o.samples) p.motionBlurSamples = o.samples;
    if (o.renderer) p.renderer = o.renderer;
    var r = run("comp.new", p);
    if (o.motionBlur !== false) run("comp.setSwitch", { comp: o.name, "switch": "motionBlur", value: true });
    return r.comp !== undefined ? r.comp : o.name;
  };

  // ── layers ──────────────────────────────────────────────────────────
  function L(r) { return r.layer; }
  E.solid = function (c, o) {
    var p = { comp: c, name: o.name, color: o.color || "#ffffff" };
    if (o.w) p.width = Math.round(o.w); if (o.h) p.height = Math.round(o.h);
    var id = L(run("layer.newSolid", p)); E.after(c, id, o); return id;
  };
  E.text = function (c, o) {
    var p = { comp: c, text: o.text, name: o.name || o.text };
    var keys = ["font", "style", "size", "fill", "stroke", "strokeWidth", "tracking", "leading", "justify", "position", "box", "applyStroke", "fauxBold", "allCaps"];
    for (var i = 0; i < keys.length; i++) if (o[keys[i]] !== undefined) p[keys[i]] = o[keys[i]];
    if (p.fill && !(p.fill instanceof Array)) p.fill = p.fill;
    var id = L(run("layer.newText", p)); E.after(c, id, o); return id;
  };
  E.shape = function (c, o) {
    var p = { comp: c, kind: o.kind || "rect", name: o.name };
    var keys = ["size", "fill", "fillType", "fillBlend", "fillOpacity", "stroke", "strokeType", "strokeBlend", "strokeOpacity", "strokeWidth", "position"];
    for (var i = 0; i < keys.length; i++) if (o[keys[i]] !== undefined) p[keys[i]] = o[keys[i]];
    var id = L(run("layer.newShape", p)); E.after(c, id, o); return id;
  };
  // nulls are 100x100 with the anchor at (50, 50) like in After Effects; children are placed from the null's top-left
  // corner. Templates want "child at (0, 0) = the null's position", so the anchor goes to (0, 0, 0) (keepAnchor: true keeps it)
  E.nul = function (c, o) {
    var id = L(run("layer.newNull", { comp: c, name: o.name }));
    if (!o.keepAnchor) run("prop.set", { comp: c, layer: id, path: "transform/anchor", value: [0, 0, 0] });
    E.after(c, id, o); return id;
  };
  E.camera = function (c, o) {
    var p = { comp: c, name: o.name || "Camera", type: o.type || "twoNode" };
    var keys = ["preset", "zoom", "focalLength", "angleOfView", "dof", "focusDistance", "aperture", "fStop", "blurLevel", "position", "poi"];
    for (var i = 0; i < keys.length; i++) if (o[keys[i]] !== undefined) p[keys[i]] = o[keys[i]];
    var id = L(run("layer.newCamera", p)); E.after(c, id, o); return id;
  };
  E.light = function (c, o) {
    var p = { comp: c, name: o.name || "Light", kind: o.kind || "Point" };
    var keys = ["color", "intensity", "coneAngle", "coneFeather", "falloff", "radius", "falloffDistance", "castsShadows", "shadowDarkness", "shadowDiffusion", "position", "poi"];
    for (var i = 0; i < keys.length; i++) if (o[keys[i]] !== undefined) p[keys[i]] = o[keys[i]];
    var id = L(run("layer.newLight", p)); E.after(c, id, o); return id;
  };
  var _items = {};
  E.item = function (path, o) {
    o = o || {};
    var key = path + (o.sequence ? "#seq" : "");
    if (_items[key] !== undefined) return _items[key];
    var p = { paths: [path] };
    if (o.sequence) p.sequence = true;
    if (o.frameRate) p.frameRate = o.frameRate;
    var r = run("file.import", p);
    var id = (r.items && r.items[0] !== undefined) ? r.items[0] : (r.imported && r.imported[0] !== undefined ? r.imported[0] : r.item);
    if (id && typeof id === "object" && id.id !== undefined) id = id.id;
    _items[key] = id;
    return id;
  };
  E.footage = function (c, path, o) {
    o = o || {};
    var item = E.item(path, o);
    var p = { comp: c, item: item, time: 0 };
    if (o.position) p.position = o.position;
    if (o.duration) p.duration = o.duration;
    var id = L(run("layer.addItem", p));
    if (o.name) E.rename(c, id, o.name);
    E.after(c, id, o); return id;
  };
  E.precompLayer = function (c, compName, o) {
    o = o || {};
    var id = L(run("layer.addItem", { comp: c, item: compName, time: 0 }));
    if (o.name) E.rename(c, id, o.name);
    E.after(c, id, o); return id;
  };
  // common options after creation: in/out, 3D, motion blur, blend, opacity, position, scale
  E.after = function (c, id, o) {
    if (o.threeD) E.sw(c, id, "threeD", true);
    if (o.mb !== false && o.mb !== undefined) E.sw(c, id, "motionBlur", true);
    if (o["in"] !== undefined || o.out !== undefined) E.trim(c, id, o["in"], o.out);
    if (o.blend) run("layer.setBlendMode", { comp: c, layers: [id], mode: o.blend });
    var tr = { anchor: "anchor", pos: "position", scale: "scale", rot: "rotation", opacity: "opacity", orientation: "orientation" };
    for (var k in tr) if (o[k] !== undefined) E.set(c, id, "transform/" + tr[k], o[k]);
    if (o.start !== undefined) run("layer.timing", { comp: c, layers: [id], start: o.start });
    if (o.parent !== undefined) run("layer.setParent", { comp: c, layers: [id], parent: o.parent });
  };
  E.sw = function (c, id, sw, v) { run("layer.setSwitch", { comp: c, layers: [id], "switch": sw, value: v !== false }); };
  E.trim = function (c, id, a, b) {
    var p = { comp: c, layers: [id] };
    if (a !== undefined) p["in"] = a; if (b !== undefined) p.out = b;
    run("layer.timing", p);
  };
  E.rename = function (c, id, name) { run("layer.rename", { comp: c, layer: id, name: name }); };
  E.matte = function (c, id, matte, kind) { run("layer.setTrackMatte", { comp: c, layer: id, matte: matte, kind: kind || "alpha" }); };
  E.parent = function (c, id, par) { run("layer.setParent", { comp: c, layers: [id], parent: par }); };

  // ── properties, keys, ease ──────────────────────────────────────────
  E.set = function (c, id, path, v) { return run("prop.set", { comp: c, layer: id, path: path, value: v }); };
  E.expr = function (c, id, path, code) { return run("prop.setExpression", { comp: c, layer: id, path: path, expression: code }); };
  // ease presets: [outInfluence of the earlier key, inInfluence of the later key] (speed 0 at both)
  E.EASES = {
    linear: null, easy: [33.33, 33.33], smooth: [60, 60], strong: [85, 85],
    out: [8, 92], expo: [3, 97], "in": [92, 8], expoIn: [97, 3], soft: [40, 75], snap: [1, 99],
    // the channel's one curve: cubic-bezier(0.2, 0, 0, 1) in, cubic-bezier(0.3, 0, 0.8, 0.15) out (approximated)
    emphasized: [20, 100], emphasizedOut: [30, 20]
  };
  // keys: [[t, value], ...] in comp seconds. ease: preset name, [out,in] pair, or array per segment.
  E.startOf = function (c, id) { var l = E.layerObj(c, id); return l ? l.startTime : 0; };
  // keys.setEase takes timeBase since EffectCraft motion-quality d5c189d0; older builds only know layer time
  E.EASE_TIMEBASE = null;
  E.keys = function (c, id, path, keys, ease) {
    for (var i = 0; i < keys.length; i++) run("prop.addKey", { comp: c, layer: id, path: path, time: keys[i][0], value: keys[i][1], timeBase: "comp" });
    if (ease === undefined) ease = "smooth";
    var off = null;
    for (var j = 0; j + 1 < keys.length; j++) {
      var e = ease instanceof Array && (ease[j] instanceof Array || typeof ease[j] === "string") ? ease[j] : ease;
      if (typeof e === "string") e = E.EASES[e];
      if (!e) continue;
      var sides = [[keys[j][0], "out", e[0]], [keys[j + 1][0], "in", e[1]]];
      for (var q = 0; q < 2; q++) {
        if (E.EASE_TIMEBASE !== false) {
          try { run("keys.setEase", { comp: c, layer: id, path: path, time: sides[q][0], timeBase: "comp", side: sides[q][1], speed: 0, influence: sides[q][2] }); E.EASE_TIMEBASE = true; continue; }
          catch (err) { if (E.EASE_TIMEBASE === true) throw err; E.EASE_TIMEBASE = false; }
        }
        if (off === null) off = E.startOf(c, id);
        run("keys.setEase", { comp: c, layer: id, path: path, time: sides[q][0] - off, side: sides[q][1], speed: 0, influence: sides[q][2] });
      }
    }
  };
  // hold keys (step changes)
  E.hold = function (c, id, path, keys) {
    for (var i = 0; i < keys.length; i++) run("prop.addKey", { comp: c, layer: id, path: path, time: keys[i][0], value: keys[i][1], timeBase: "comp" });
    var sel = [];
    for (var k = 0; k < keys.length; k++) sel.push({ layer: id, path: path, time: keys[k][0] });
    run("keys.select", { comp: c, keys: sel, timeBase: "comp" });
    run("keys.interpolation", { interpolation: "hold" });
  };
  // spring after the last key (overshoot that settles); amp in units of velocity seconds
  E.SPRING = "var amp=%A,freq=%F,decay=%D;var n=0;if(numKeys>0){n=nearestKey(time).index;if(key(n).time>time)n--;}" +
    "if(n>0){var t=time-key(n).time;var v=velocityAtTime(key(n).time-thisComp.frameDuration/10);value+v*amp*Math.sin(freq*t*2*Math.PI)/Math.exp(decay*t);}else value";
  E.spring = function (c, id, path, amp, freq, decay) {
    E.expr(c, id, path, E.SPRING.replace("%A", amp || 0.05).replace("%F", freq || 2.5).replace("%D", decay || 6));
  };

  // ── effects ─────────────────────────────────────────────────────────
  // apply an effect and set its parameters: values {paramId: value} (ids from `effect params`), keys {paramId: [[t,v],...]}
  E.fx = function (c, id, effect, values, keys, ease) {
    var r = run("effect.apply", { comp: c, layers: [id], effect: effect });
    var path = r.paths ? r.paths[0] : ("effects/#" + r.index);
    if (values) for (var k in values) E.set(c, id, path + "/" + k, values[k]);
    if (keys) for (var k2 in keys) E.keys(c, id, path + "/" + k2, keys[k2], ease);
    return path;
  };

  // ── text animators ──────────────────────────────────────────────────
  // props: ["opacity","position",...]; returns {animator, path}
  E.animator = function (c, id, props, name) {
    var n = E.animatorCount(c, id) + 1;
    var p = { comp: c, layer: id, properties: props };
    if (name) p.name = name;
    var r = run("layer.addTextAnimator", p);
    return { uid: r.animator, index: n, path: "text/animators/#" + n };
  };

  // ── layer queries ───────────────────────────────────────────────────
  E.compItem = function (c) {
    for (var i = 1; i <= app.project.numItems; i++) {
      var it = app.project.item(i);
      if (it.name === c || it.id === c) return it;
    }
    return null;
  };
  E.layerObj = function (c, id) {
    var ci = E.compItem(c);
    if (!ci) return null;
    for (var i = 1; i <= ci.numLayers; i++) if (ci.layer(i).id === id) return ci.layer(i);
    return null;
  };
  // source size of a footage/solid layer: {width, height}
  E.dims = function (c, id) { var l = E.layerObj(c, id); return l ? { width: l.width, height: l.height } : null; };
  E.layerInfo = E.dims;
  E.compInfo = function (c) { return run("comp.info", { comp: c }); };
  E.animatorCount = function (c, id) {
    for (var n = 1; n < 64; n++) {
      try { run("prop.get", { comp: c, layer: id, path: "text/animators/#" + n + "/selectors/#1/start" }); }
      catch (e) { return n - 1; }
    }
    return 64;
  };
  return E;
})();
