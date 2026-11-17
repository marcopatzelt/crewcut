/* @template type_smash_splash
 * @description Typing in a design-tool selection box, then a heavy word smashes in: "lead" types inside a selection box
 *   with handles, "rest" types after it with an underscore caret; at smashAt a 3D type plate (RGBA sequence, e.g. from
 *   Blender) lands, a paint splash bursts behind it (blob + arms + droplets, organic edge via Turbulent Displace), a small
 *   card with handles pops in, and the frame takes a defocus hit, a flash and a short shake. All parts hang on a "stage"
 *   null that pushes in slowly.
 * @params {"comp": "Main", "lead": "Ship", "rest": "the", "textPos": [600, 594], "textSize": 150, "afterPos": [590, 380], "afterScale": 60, "font": "Manrope V5",
 *   "typeStart": 0.1, "typeEnd": 0.45, "restStart": 0.5, "restEnd": 0.75, "smashAt": 1.0, "plate": "", "plateStart": 0.0,
 *   "splashCenter": [1210, 610], "splashSize": 420, "splashColors": ["#FF6F5E", "#FF9EC4"], "accent": "#34C3A4", "throwAngle": -28, "strokes": 6, "droplets": 34,
 *   "box": "#34C3A4", "card": "", "cardPos": [1080, 340], "cardW": 120, "push": [1.0, 2.8, 108], "seed": 9, "name": "Smash"}
 * @end */
function type_smash_splash(P) {
  var c = P.comp, rnd = EC.rng(P.seed), f = 1 / 60;
  var stage = EC.nul(c, { name: P.name + " stage" });
  EC.set(c, stage, "transform/position", [960, 540]);
  EC.keys(c, stage, "transform/scale", [[P.push[0], [100, 100]], [P.push[1], [P.push[2], P.push[2]]]], "soft");
  // a short shake on impact (expression on the stage position)
  EC.expr(c, stage, "transform/position", "var t = time - " + P.smashAt + "; (t > 0 && t < 0.25) ? value + [Math.sin(t * 90) * 14 * (1 - t / 0.25), Math.cos(t * 77) * 10 * (1 - t / 0.25)] : value");
  function onStage(id, x, y) { EC.run("layer.setParent", { comp: c, layers: [id], parent: stage, compensate: false }); EC.set(c, id, "transform/position", [x - 960, y - 540]); return id; }
  // splash (behind the type): its own comp so one Turbulent Displace and one gradient shape the whole splash
  var sc = P.name + " splash";
  EC.comp({ name: sc, width: 1920, height: 1080, fps: 60, duration: 6, motionBlur: true });
  var cx = 960, cy = 540, S = P.splashSize, col = P.splashColors[0], pink = P.splashColors[1];
  var throwA = P.throwAngle * Math.PI / 180;
  function pick() { var q = rnd(); return q < 0.12 ? P.accent : (q < 0.5 ? pink : col); }
  function grow(id, t0, dur, overshoot) {
    EC.keys(sc, id, "transform/scale", overshoot ? [[t0 - f, [0, 0]], [t0 + dur * 0.6, [112, 108]], [t0 + dur, [100, 100]]] : [[t0 - f, [0, 0]], [t0 + dur, [100, 100]]], overshoot ? "smooth" : "expo");
  }
  // uneven core: overlapping blobs of different size, offset and squash
  for (var k = 0; k < 5; k++) {
    var w = S * (0.18 + rnd() * 0.24), hgt = w * (0.6 + rnd() * 0.5);
    var b0 = EC.shape(sc, { kind: "ellipse", size: [w, hgt], fill: k < 3 ? col : pink, name: "core " + k });
    EC.set(sc, b0, "transform/position", [cx + (rnd() - 0.4) * S * 0.28 + Math.cos(throwA) * S * 0.05 * k, cy + (rnd() - 0.5) * S * 0.2 + Math.sin(throwA) * S * 0.04 * k]);
    EC.set(sc, b0, "transform/rotation", rnd() * 180);
    grow(b0, P.smashAt + k * 0.01, 0.2, true);
  }
  // strokes: two long tapered throws to one side, the rest short and uneven
  function stroke(ang, len, wid, t0, colr) {
    var segs = 3;
    for (var s2 = 0; s2 < segs; s2++) {
      var L2 = len * (1 - s2 * 0.28), W2 = wid * (1 - s2 * 0.35);
      var st = EC.shape(sc, { kind: "ellipse", size: [L2, W2], fill: colr, name: "stroke" });
      EC.set(sc, st, "transform/anchor", [-L2 / 2, 0]);
      EC.set(sc, st, "transform/position", [cx + Math.cos(ang) * len * 0.12 * s2, cy + Math.sin(ang) * len * 0.12 * s2]);
      EC.set(sc, st, "transform/rotation", ang * 180 / Math.PI + (rnd() - 0.5) * 6);
      EC.keys(sc, st, "transform/scale", [[t0, [0, 100]], [t0 + 0.1 + s2 * 0.03, [100, 100]]], "expo");
      EC.sw(sc, st, "motionBlur", true);
    }
  }
  stroke(throwA + (rnd() - 0.5) * 0.15, S * 1.35, S * 0.07, P.smashAt + 0.01, col);
  stroke(throwA + 0.32 + (rnd() - 0.5) * 0.1, S * 1.05, S * 0.05, P.smashAt + 0.02, pink);
  for (var a2 = 0; a2 < P.strokes; a2++) {
    var ang = rnd() * Math.PI * 2, len = S * (0.18 + Math.pow(rnd(), 1.6) * 0.5);
    stroke(ang, len, S * (0.025 + rnd() * 0.05), P.smashAt + rnd() * 0.03, pick());
  }
  // secondary splats along the throw
  for (var sp = 0; sp < 4; sp++) {
    var da = throwA + (rnd() - 0.5) * 0.9, dd = S * (0.7 + rnd() * 0.7);
    var px = cx + Math.cos(da) * dd, py = cy + Math.sin(da) * dd, colr = pick();
    for (var q2 = 0; q2 < 3; q2++) {
      var r2 = S * (0.03 + rnd() * 0.07);
      var sb = EC.shape(sc, { kind: "ellipse", size: [r2, r2 * (0.6 + rnd() * 0.5)], fill: colr, name: "splat " + sp });
      EC.set(sc, sb, "transform/position", [px + (rnd() - 0.5) * r2 * 1.6, py + (rnd() - 0.5) * r2 * 1.4]);
      grow(sb, P.smashAt + 0.06 + dd / S * 0.08, 0.12, false);
    }
  }
  // droplets: many small, few large, biased along the throw
  for (var d = 0; d < P.droplets; d++) {
    var ang2 = rnd() < 0.6 ? throwA + (rnd() - 0.5) * 1.2 : rnd() * Math.PI * 2;
    var dist = S * (0.4 + rnd() * 1.1), r = 4 + Math.pow(rnd(), 2.4) * 34;
    var dr = EC.shape(sc, { kind: "ellipse", size: [r, r * (0.7 + rnd() * 0.5)], fill: pick(), name: "drop " + d });
    var t0 = P.smashAt + rnd() * 0.04;
    EC.keys(sc, dr, "transform/position", [[t0, [cx, cy]], [t0 + 0.25 + rnd() * 0.25, [cx + Math.cos(ang2) * dist, cy + Math.sin(ang2) * dist * 0.85]]], "expo");
    EC.keys(sc, dr, "transform/scale", [[t0, [40, 40]], [t0 + 0.1, [100, 100]]], "out");
    EC.sw(sc, dr, "motionBlur", true); EC.trim(sc, dr, t0, undefined);
  }
  var spl = EC.precompLayer(c, sc, { name: P.name + " splash" });
  EC.fx(c, spl, "Turbulent Displace", { amount: 22, size: 46, complexity: 2 });     // organic but crisp edges; colours stay per shape
  EC.run("layer.setParent", { comp: c, layers: [spl], parent: stage, compensate: false });
  EC.set(c, spl, "transform/position", [P.splashCenter[0] - 960, P.splashCenter[1] - 540]);
  EC.set(c, spl, "transform/anchor", [960, 540]);
  // typed lead word in a selection box with handles; the group sits on its own null (origin = text baseline, left)
  var tn = EC.nul(c, { name: P.name + " words" });
  EC.run("layer.setParent", { comp: c, layers: [tn], parent: stage, compensate: false });
  EC.keys(c, tn, "transform/position", [[P.smashAt - 0.02, [P.textPos[0] - 960, P.textPos[1] - 540]], [P.smashAt + 0.2, [P.afterPos[0] - 960, P.afterPos[1] - 540]]], "expo");
  EC.keys(c, tn, "transform/scale", [[P.smashAt - 0.02, [100, 100]], [P.smashAt + 0.2, [P.afterScale, P.afterScale]]], "expo");
  EC.sw(c, tn, "motionBlur", true);
  function onWords(id, x, y) { EC.run("layer.setParent", { comp: c, layers: [id], parent: tn, compensate: false }); EC.set(c, id, "transform/position", [x, y]); EC.sw(c, id, "motionBlur", true); return id; }
  var tx = 0, ty = 0, ts = P.textSize;
  var lead = EC.text(c, { text: P.lead, size: ts, fill: "#15171B", font: P.font, style: "ExtraBold", justify: "left", name: P.name + " lead" });
  onWords(lead, tx, ty);
  var on = EC.animator(c, lead, ["opacity"]); EC.set(c, lead, on.path + "/properties/opacity", 0);
  EC.keys(c, lead, on.path + "/selectors/#1/start", [[P.typeStart, 0], [P.typeEnd, 100]], "linear");
  var lw = P.lead.length * ts * 0.6 + 24, bh = ts * 1.05;
  // the box hugs the typed letters: it grows from one letter to the whole word while typing
  var w0 = ts * 0.62 + 24, y0 = ty - ts * 0.36;
  var box = EC.shape(c, { kind: "rect", size: [lw, bh], stroke: P.box, strokeWidth: 4, fillOpacity: 0, name: P.name + " box" });
  onWords(box, tx - 12 + lw / 2, y0);
  EC.keys(c, box, "contents/group/contents/rect/size", [[P.typeStart, [w0, bh]], [P.typeEnd, [lw, bh]]], "linear");
  EC.keys(c, box, "transform/position", [[P.typeStart, [tx - 12 + w0 / 2, y0]], [P.typeEnd, [tx - 12 + lw / 2, y0]]], "linear");
  EC.keys(c, box, "transform/opacity", [[P.typeStart, 0], [P.typeStart + 0.05, 100]], "linear");
  for (var h = 0; h < 4; h++) {
    var hd = EC.shape(c, { kind: "rect", size: [16, 16], fill: "#FFFFFF", stroke: P.box, strokeWidth: 3, name: P.name + " handle " + h });
    var hy = y0 + (h < 2 ? -bh / 2 : bh / 2);
    onWords(hd, tx - 12, hy);
    if (h % 2) EC.keys(c, hd, "transform/position", [[P.typeStart, [tx - 12 + w0, hy]], [P.typeEnd, [tx - 12 + lw, hy]]], "linear");
    EC.keys(c, hd, "transform/opacity", [[P.typeStart, 0], [P.typeStart + 0.05, 100]], "linear");
  }
  // the rest, grey, with an underscore caret
  var rest = EC.text(c, { text: P.rest + "_", size: ts, fill: "#8A8F98", font: P.font, style: "Medium", justify: "left", name: P.name + " rest" });
  onWords(rest, tx + lw + 22, ty);
  var on2 = EC.animator(c, rest, ["opacity"]); EC.set(c, rest, on2.path + "/properties/opacity", 0);
  EC.keys(c, rest, on2.path + "/selectors/#1/start", [[P.restStart, 0], [P.restEnd, 100]], "linear");
  // the 3D type plate lands at smashAt (its own animation is in the plate)
  var pl = null;
  if (P.plate) {
    pl = EC.footage(c, P.plate, { name: P.name + " type", sequence: true, frameRate: 60, start: P.plateStart });
    EC.run("layer.setParent", { comp: c, layers: [pl], parent: stage, compensate: false }); EC.set(c, pl, "transform/position", [0, 0]);
    EC.trim(c, pl, P.smashAt - 0.13, undefined);          // the plate's glyphs start flying at smashAt - 0.12
  }
  // small card with handles that pops in next to the rest word
  if (P.card) {
    var cd = EC.footage(c, P.card, { name: P.name + " card" }); var dd = EC.dims(c, cd), cs = 100 * P.cardW / ((dd && dd.width) || 640);
    onStage(cd, P.cardPos[0], P.cardPos[1]);
    EC.keys(c, cd, "transform/scale", [[P.smashAt + 0.06, [0, 0]], [P.smashAt + 0.2, [cs * 1.1, cs * 1.1]], [P.smashAt + 0.32, [cs, cs]]], "smooth");
    EC.keys(c, cd, "transform/rotation", [[P.smashAt + 0.06, -25], [P.smashAt + 0.5, 6]], "out");
  }
  // impact: defocus hit and flash over everything
  var adj = EC.run("layer.newAdjustment", { comp: c, name: P.name + " impact" }).layer;
  EC.fx(c, adj, "Camera Lens Blur", {}, { blurRadius: [[P.smashAt - 2 * f, 0], [P.smashAt, 22], [P.smashAt + 0.14, 0]] }, "out");
  EC.trim(c, adj, P.smashAt - 0.05, P.smashAt + 0.2);
  return { stage: stage, splash: spl, plate: pl };
}
