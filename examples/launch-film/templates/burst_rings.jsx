/* @template burst_rings
 * @description Click burst: filled discs expand from one point with expo ease and a stagger until they cover
 *   the frame (inner disc on top, outer rings below), a soft light sweep on each disc, and outlined and filled
 *   squares that fly out radially with motion blur. colors run from the inner disc to the outermost ring.
 * @params {"comp": "Main", "t": 0.5, "center": [960, 540],
 *   "colors": ["#0F6E5C", "#FFFFFF", "#FFFFFF", "#FFFFFF", "#FFC9A8"], "opacities": [100, 30, 20, 13, 100],
 *   "radii": [270, 450, 670, 940, 1300], "gradient4": ["#FFB896", "#FFDB8A", "#C9B3FF", "#93CDFF"], "dur": 0.5, "stagger": 0.035, "ease": "expo",
 *   "squares": 0, "squareColors": ["#FFFFFF", "#34C3A4", "#FF8A65", "#FFD166"], "squareSize": [14, 44],
 *   "squareDist": [260, 1100], "squareDur": 0.8, "seed": 7, "shade": true, "shadeBlend": 90, "compSize": [1920, 1080], "push": null, "pushKeys": [],
 *   "pushEase": ["linear", "expoIn"], "midLayer": null, "out": null}
 * @end */
function burst_rings(P) {
  var c = P.comp, n = P.colors.length, rings = [], squares = [];
  var rnd = EC.rng(P.seed);
  var mid = null;
  for (var i = n - 1; i >= 0; i--) {
    if (i === 0 && P.midLayer) {
      // a plate between the rings and the centre disc (e.g. the filled pixel cells): above the rings, below disc + logo
      var ml = P.midLayer;
      mid = EC.footage(c, ml.path, { name: ml.name || "burst mid", sequence: !!ml.sequence, frameRate: ml.frameRate || 60, start: ml.start || 0 });
      EC.set(c, mid, "transform/position", [P.compSize[0] / 2, P.compSize[1] / 2]);
    }
    var d = 2 * P.radii[i];
    var id = EC.shape(c, { kind: "ellipse", size: [d, d], fill: P.colors[i], name: "ring " + i });
    EC.set(c, id, "transform/position", P.center);
    var t0 = P.t + P.stagger * i;
    EC.keys(c, id, "transform/scale", [[t0, [0, 0]], [t0 + P.dur, [100, 100]]], P.ease);
    EC.sw(c, id, "motionBlur", true);
    if (P.opacities && P.opacities[i] !== undefined && P.opacities[i] < 100) EC.set(c, id, "transform/opacity", P.opacities[i]);
    if (P.gradient4 && i === n - 1) {
      // the outermost disc carries a four-colour gradient across the frame (warm top, cool bottom)
      var g = P.gradient4, W = P.compSize[0], H = P.compSize[1];
      EC.fx(c, id, "4-Color Gradient", { "positionsColors/point1": [W * 0.1, H * 0.05], "positionsColors/color1": EC.rgba(g[0]),
        "positionsColors/point2": [W * 0.95, H * 0.1], "positionsColors/color2": EC.rgba(g[1]),
        "positionsColors/point3": [W * 0.05, H * 0.95], "positionsColors/color3": EC.rgba(g[2]),
        "positionsColors/point4": [W * 0.9, H * 0.95], "positionsColors/color4": EC.rgba(g[3]), "blend": 220 });
    } else if (P.shade && (!P.opacities || P.opacities[i] === undefined || P.opacities[i] >= 100)) {
      // light from the top left, a little darker at the bottom right: a pressed-button, glossy disc
      // effect space of a shape layer: comp-sized, centred on the shape's origin
      var cx = P.compSize[0] / 2, cy = P.compSize[1] / 2, r0 = P.radii[i];
      EC.fx(c, id, "Gradient Ramp", { start: [cx - r0 * 0.8, cy - r0 * 0.8], startColor: [1, 1, 1, 1],
        end: [cx + r0 * 0.8, cy + r0 * 0.8], endColor: [0, 0, 0, 1], shape: 0, blend: P.shadeBlend });
    }
    if (P.out !== null) EC.trim(c, id, 0, P.out);
    rings.push(id);
  }
  // optional push-in of the whole burst: push = [tStart, tEnd, scaleEnd %] on a null that parents the rings
  var pusher = null;
  if (P.push || P.pushKeys.length) {
    pusher = EC.nul(c, { name: "burst push" });
    EC.set(c, pusher, "transform/position", P.center);
    for (var r = 0; r < rings.length; r++) EC.parent(c, rings[r], pusher);
    EC.sw(c, pusher, "motionBlur", true);
    if (P.pushKeys.length) {
      var kk = []; for (var q = 0; q < P.pushKeys.length; q++) kk.push([P.pushKeys[q][0], [P.pushKeys[q][1], P.pushKeys[q][1]]]);
      EC.keys(c, pusher, "transform/scale", kk, P.pushEase);
    } else EC.keys(c, pusher, "transform/scale", [[P.push[0], [100, 100]], [P.push[1], [P.push[2], P.push[2]]]], "expoIn");
  }
  for (var k = 0; k < P.squares; k++) {
    var a = rnd() * Math.PI * 2, dist = EC.lerp(P.squareDist[0], P.squareDist[1], Math.pow(rnd(), 0.7));
    var s = EC.lerp(P.squareSize[0], P.squareSize[1], rnd());
    var col = P.squareColors[Math.floor(rnd() * P.squareColors.length)];
    var filled = rnd() < 0.35;
    var o = { kind: "rect", size: [s, s], name: "square " + k };
    if (filled) o.fill = col; else { o.stroke = col; o.strokeWidth = Math.max(2, s * 0.12); o.fillOpacity = 0; }  // stroke only: no default fill
    var q = EC.shape(c, o);
    var t1 = P.t + rnd() * 0.08, start = [P.center[0] + Math.cos(a) * 40, P.center[1] + Math.sin(a) * 40];
    var end = [P.center[0] + Math.cos(a) * dist, P.center[1] + Math.sin(a) * dist];
    EC.keys(c, q, "transform/position", [[t1, start], [t1 + P.squareDur, end]], "expo");
    EC.keys(c, q, "transform/rotation", [[t1, 0], [t1 + P.squareDur, (rnd() - 0.5) * 240]], "expo");
    EC.keys(c, q, "transform/scale", [[t1, [40, 40]], [t1 + 0.12, [100, 100]], [t1 + P.squareDur, [60, 60]]], "smooth");
    EC.keys(c, q, "transform/opacity", [[t1, 0], [t1 + 0.04, 100], [t1 + P.squareDur * 0.6, 100], [t1 + P.squareDur, 0]], "linear");
    EC.sw(c, q, "motionBlur", true);
    EC.trim(c, q, t1, t1 + P.squareDur + 0.02);
    squares.push(q);
  }
  return { rings: rings, squares: squares, push: pusher, mid: mid };
}
