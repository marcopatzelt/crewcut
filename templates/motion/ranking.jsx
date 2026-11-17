/* @template ranking
 * @description Three to five places on a tilted plane in 2.5D, first place on top. They come in dim; then the
 *   light goes on place by place from the last to the first while the list glides so the lit place sits in the
 *   middle of the frame; on place 1 the camera pushes in, its number turns to the accent and it settles with a small
 *   scale spring. The hold pushes slowly; at the end the camera pushes through the list.
 * @kind full
 * @formats ["landscape", "portrait", "stage"]
 * @version 1
 * @sounds [{"at": "firstAt", "sound": "hit"}, {"at": "startAt", "sound": "tick"}]
 * @params {"comp": "Main", "items": [{"label": "Whisper large", "value": "4.1 s"}, {"label": "Parakeet", "value": "6.8 s"},
 *   {"label": "Distil small", "value": "9.5 s"}, {"label": "Vosk", "value": "21 s"}], "size": 120, "minSize": 72,
 *   "tilt": [16, -18, 2], "startAt": 0.5, "firstAt": null, "dim": 22, "outAt": null, "layer": "Ranking"}
 * @end */
function ranking(P) {
  var c = P.comp, F = CC.frame(), u = F.u, D = F.duration, W = F.W, H = F.H, f1 = 1 / (F.fps || 25);
  var exit = CC.exitS(), ink = CC.ink(), area = F.safe;
  CC.groundLayer(c);
  var items = [];
  for (var i = 0; i < P.items.length && items.length < 5; i++) {
    var it = P.items[i];
    items.push(typeof it === "string" ? { label: it, value: "" } : { label: String(it.label || ""), value: String(it.value || "") });
  }
  var n = Math.max(1, items.length);
  // sizes: number, label and value of the widest row fit 86 % of the safe width
  var size = P.size * u;
  // columns: right-aligned numbers, labels, values in one column after the longest label
  function cols(sz) {
    var o = { num: 0, lab: 0, val: 0 };
    for (var k = 0; k < n; k++) {
      o.num = Math.max(o.num, CC.measure(c, String(k + 1), sz).advance);
      o.lab = Math.max(o.lab, CC.measure(c, items[k].label, 0.7 * sz).advance);
      if (items[k].value) o.val = Math.max(o.val, CC.measure(c, items[k].value, Math.max(48 * u, 0.42 * sz), "body").advance);
    }
    o.w = o.num + 0.35 * sz + o.lab + (o.val ? 0.45 * sz + o.val : 0);
    return o;
  }
  function rowW(sz) { return cols(sz).w; }
  size = CC.fit(size, rowW(size) * 1.12, area.w * 0.86, P.minSize * u);
  var ls = 0.7 * size, vs = Math.max(48 * u, 0.42 * size), rowH = 1.45 * size, C0 = cols(size), numW = C0.num;
  var cap = -CC.measure(c, "0", size).top, w0 = C0.w;
  var cx = area.x + area.w / 2, cy = area.y + area.h / 2;

  // camera: a two-node camera whose zoom puts the z = 0 plane at 100 %
  var Z = 1.6 * Math.max(W, H);
  EC.camera(c, { name: P.layer + " camera", type: "twoNode", zoom: Z, position: [cx, cy, -Z], poi: [cx, cy, 0] });
  // track (moves so the lit place sits in the middle) -> plane (the tilt) -> rows
  var track = EC.nul(c, { name: P.layer + " track", threeD: true });
  EC.set(c, track, "transform/position", [cx, cy, 0]);
  var plane = EC.nul(c, { name: P.layer + " plane", threeD: true });
  CC.child(c, plane, track);
  EC.set(c, plane, "transform/position", [0, 0, 0]);
  EC.set(c, plane, "transform/rotationX", P.tilt[0]); EC.set(c, plane, "transform/rotationY", P.tilt[1]); EC.set(c, plane, "transform/rotation", P.tilt[2]);
  var a = P.tilt[0] * Math.PI / 180, b = P.tilt[1] * Math.PI / 180;
  function world(y) { return [y * Math.sin(a) * Math.sin(b), y * Math.cos(a), y * Math.sin(a) * Math.cos(b)]; }

  var start = P.startAt, first = P.firstAt !== null && P.firstAt !== undefined ? CC.landBy(P.firstAt) : start + 0.62 * (n - 1) + 0.4;
  var step = n > 1 ? (first - start) / (n - 1) : 0, tOut = P.outAt !== null && P.outAt !== undefined ? P.outAt : D - exit - f1;
  var x0 = -w0 / 2, trackK = [], ids = [];
  function lit(id, t, peak) { EC.keys(c, id, "transform/opacity", [[0, P.dim * peak / 100], [t, P.dim * peak / 100], [t + 0.3, peak]], ["linear", "smooth"]); }
  for (var p = n - 1; p >= 0; p--) {                                       // place p + 1, lit from the last to the first
    var y = (p - (n - 1) / 2) * rowH, t = start + step * (n - 1 - p), num = String(p + 1);
    var numId = CC.text(c, { text: num, size: size, fill: p === 0 ? CC.color(0) : ink, name: P.layer + " " + num, justify: "right" });
    var lab = CC.text(c, { text: items[p].label, size: ls, fill: ink, name: P.layer + " label " + num });
    var parts = [[numId, x0 + numW, y + cap / 2], [lab, x0 + numW + 0.35 * size, y + cap / 2]];
    if (items[p].value) {
      var val = CC.text(c, { text: items[p].value, size: vs, fill: ink, role: "body", name: P.layer + " value " + num });
      parts.push([val, x0 + numW + 0.35 * size + C0.lab + 0.45 * size, y + cap / 2]);
    }
    for (var q = 0; q < parts.length; q++) {
      var id = parts[q][0];
      EC.sw(c, id, "threeD", true);
      CC.child(c, id, plane);
      EC.set(c, id, "transform/position", [parts[q][1], parts[q][2], 0]);
      EC.sw(c, id, "motionBlur", true);
      lit(id, t, q === 2 ? 70 : 100);
      ids.push(id);
    }
    if (p === 0) {                                                         // place 1 settles with a 3 % spring
      EC.keys(c, numId, "transform/scale", [[t, [100, 100, 100]], [t + 0.22, [106, 106, 106]], [t + 0.5, [103, 103, 103]]], ["out", "smooth"]);
    }
    var wv = world(y);
    trackK.push([t, [cx - wv[0], cy - wv[1], -wv[2]]]);
  }
  // the track glides from place to place; on place 1 it comes closer (the push), then holds, then rushes through
  var last = trackK[trackK.length - 1][1];
  if (trackK[0][0] > 0.05) trackK.unshift([0, [trackK[0][1][0], trackK[0][1][1] + 0.06 * H, trackK[0][1][2] + 0.10 * Z]]);
  trackK.push([first + 0.6, [last[0], last[1], last[2] - 0.18 * Z]]);
  trackK.push([tOut, [last[0], last[1], last[2] - 0.18 * Z - 0.02 * Z * (tOut - first - 0.6)]]);
  trackK.push([D, [last[0], last[1], last[2] - 0.75 * Z]]);
  var ez = []; for (var e = 0; e + 1 < trackK.length; e++) ez.push(e === trackK.length - 3 ? "linear" : (e === trackK.length - 2 ? "expoIn" : "smooth"));
  EC.keys(c, track, "transform/position", trackK, ez);
  EC.sw(c, track, "motionBlur", true);
  CC.measureDone(c);
  return { places: n, size: size, firstAt: first, step: step, outAt: tOut, layers: ids };
}
