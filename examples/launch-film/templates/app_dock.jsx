/* @template app_dock
 * @description Frosted-glass dock with app icons: translucent rounded bar with a soft shadow and a light rim,
 *   icons that lift and squash when the cursor passes (hovers: [[index, t], ...]) and one icon that is clicked
 *   (click: [index, t]: lift, squash on press). breakAt ends the clicked icon (for a pixel_burst taking over).
 * @params {"comp": "Main", "center": [960, 540], "icons": [], "size": 112, "gap": 24, "pad": 22, "radius": 40,
 *   "glass": "#FFFFFF", "glassOpacity": 62, "rim": "#FFFFFF", "shadowOpacity": 16, "hovers": [], "lift": 16,
 *   "click": null, "breakAt": null, "intro": null, "fadeOut": null, "out": null, "name": "Dock"}
 * @end */
function app_dock(P) {
  var c = P.comp, n = P.icons.length;
  var W = n * P.size + (n - 1) * P.gap + 2 * P.pad, H = P.size + 2 * P.pad;
  var sh = EC.shape(c, { kind: "rounded", size: [W, H], fill: "#000000", name: P.name + " shadow" });
  EC.set(c, sh, "transform/position", [P.center[0], P.center[1] + 14]);
  EC.set(c, sh, "transform/opacity", P.shadowOpacity);
  EC.fx(c, sh, "Gaussian Blur", { blurriness: 34 });
  var bar = EC.shape(c, { kind: "rounded", size: [W, H], fill: P.glass, stroke: P.rim, strokeWidth: 2, name: P.name + " glass" });
  EC.set(c, bar, "transform/position", P.center);
  EC.set(c, bar, "transform/opacity", P.glassOpacity);
  try { EC.set(c, bar, "contents/group/contents/rect/roundness", P.radius); EC.set(c, sh, "contents/group/contents/rect/roundness", P.radius); } catch (e) {}
  // a soft top highlight inside the glass
  EC.fx(c, bar, "Gradient Ramp", { start: [960, 540 - H / 2], startColor: [1, 1, 1, 1], end: [960, 540 + H / 2], endColor: [0.88, 0.9, 0.92, 1], blend: 0 });
  var ids = [], xs = [];
  for (var i = 0; i < n; i++) {
    var id = EC.footage(c, P.icons[i], { name: P.name + " icon " + i });
    var d = EC.dims(c, id), s = 100 * P.size / ((d && d.width) || 512);
    var x = P.center[0] - W / 2 + P.pad + P.size / 2 + i * (P.size + P.gap), y = P.center[1];
    EC.set(c, id, "transform/scale", [s, s]);
    var pk = [], sk = [];
    for (var h = 0; h < P.hovers.length; h++) {
      if (P.hovers[h][0] !== i) continue;
      var t = P.hovers[h][1];
      pk.push([t - 0.14, [x, y]], [t, [x, y - P.lift]], [t + 0.24, [x, y]]);
      sk.push([t - 0.14, [s, s]], [t - 0.05, [s * 1.07, s * 0.93]], [t + 0.04, [s * 1.08, s * 1.08]], [t + 0.24, [s, s]]);
    }
    if (P.click && P.click[0] === i) {
      var tc = P.click[1];
      pk.push([tc - 0.22, [x, y]], [tc - 0.08, [x, y - P.lift]], [tc, [x, y - P.lift * 0.4]]);
      sk.push([tc - 0.22, [s, s]], [tc - 0.08, [s * 1.1, s * 1.1]], [tc, [s * 0.9, s * 0.84]], [tc + 0.07, [s * 1.04, s * 1.04]]);
    }
    if (pk.length) { pk.sort(function (a, b) { return a[0] - b[0]; }); EC.keys(c, id, "transform/position", dedupe(pk), "smooth"); }
    else EC.set(c, id, "transform/position", [x, y]);
    if (sk.length) { sk.sort(function (a, b) { return a[0] - b[0]; }); EC.keys(c, id, "transform/scale", dedupe(sk), "smooth"); }
    EC.sw(c, id, "motionBlur", true);
    if (P.click && P.click[0] === i && P.breakAt !== null) EC.trim(c, id, 0, P.breakAt);
    else if (P.out !== null) EC.trim(c, id, 0, P.out);
    ids.push(id); xs.push(x);
  }
  if (P.fadeOut) { var fo = [[P.fadeOut[0], 100], [P.fadeOut[1], 0]];
    EC.keys(c, bar, "transform/opacity", [[P.fadeOut[0], P.glassOpacity], [P.fadeOut[1], 0]], "linear"); EC.keys(c, sh, "transform/opacity", [[P.fadeOut[0], P.shadowOpacity], [P.fadeOut[1], 0]], "linear");
    for (var z = 0; z < ids.length; z++) EC.keys(c, ids[z], "transform/opacity", fo, "linear"); }
  if (P.out !== null) { EC.trim(c, bar, 0, P.out); EC.trim(c, sh, 0, P.out); }
  return { glass: bar, shadow: sh, icons: ids, xs: xs, y: P.center[1], width: W };
}
function dedupe(k) {
  var out = [];
  for (var i = 0; i < k.length; i++) {
    if (out.length && Math.abs(out[out.length - 1][0] - k[i][0]) < 0.004) continue;
    out.push(k[i]);
  }
  return out;
}
