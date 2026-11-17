/* @template word_reel
 * @description Steps or tools roll past like a slot machine: a column of words scrolls with motion blur, brakes
 *   and lands on the current one, and a thin selection frame with corner handles in the accent colour hugs the word
 *   in the middle, resizing smoothly as the words pass (measured widths). Words fade by their distance from the
 *   middle. The camera settles in on entry and pushes in slowly while it holds; at the end the column runs on
 *   upward and the frame closes. A short list wraps around so the reel always travels a few lines.
 * @kind full
 * @formats ["landscape", "portrait", "stage"]
 * @version 1
 * @sounds [{"at": "rollAt", "sound": "reel_tick"}, {"at": "landAt", "sound": "click"}]
 * @params {"comp": "Main", "words": ["Idea", "Script", "Record", "Cut", "Captions", "Music", "Thumbnail", "Title", "Upload"],
 *   "target": "Captions", "size": 120, "minSize": 72, "rollAt": 0.0, "landAt": null, "cueAt": null, "minTravel": 5,
 *   "outAt": null, "image": "", "layer": "Reel"}
 * @end */
function word_reel(P) {
  var c = P.comp, F = CC.frame(), u = F.u, D = F.duration, f1 = 1 / (F.fps || 25), W = F.W, H = F.H;
  var enter = CC.enterS(), exit = CC.exitS(), ink = CC.ink(), acc = CC.color(0);
  CC.groundLayer(c);
  var words = []; for (var w0 = 0; w0 < P.words.length; w0++) if (String(P.words[w0]).replace(/\s/g, "")) words.push(String(P.words[w0]));
  if (!words.length) words = ["Step"];
  var n = words.length, ti = typeof P.target === "number" ? P.target : -1;
  if (ti < 0) for (var q = 0; q < n; q++) if (words[q] === P.target) ti = q;
  if (ti < 0) ti = Math.min(n - 1, Math.floor(n / 2));

  // optional picture behind (a screenshot of the episode): tilted, blurred, desaturated, drifting
  if (P.image) {
    var im = EC.footage(c, P.image, { name: P.layer + " image", threeD: true });
    var dm = EC.dims(c, im), s = 100 * 1.25 * W / ((dm && dm.width) || W);
    EC.set(c, im, "transform/scale", [s, s, s]);
    EC.keys(c, im, "transform/position", [[0, [W * 0.54, H * 0.70, 260]], [D, [W * 0.47, H * 0.64, 230]]], "linear");
    EC.set(c, im, "transform/rotationX", 56); EC.set(c, im, "transform/rotation", -12);
    EC.set(c, im, "transform/opacity", 42);
    EC.fx(c, im, "Gaussian Blur", { blurriness: 22 * u, repeatEdge: true });
    EC.fx(c, im, "Hue/Saturation", { saturation: -75 });
  }

  // size: the widest word plus the frame fits the safe width, grown by the push
  var size = P.size * u, padX = 0.34 * size, grow = CC.driftAt(D) * 1.04;
  var widest = 0; for (var a = 0; a < n; a++) widest = Math.max(widest, CC.measure(c, words[a], size).advance);
  var fitted = CC.fit(size, (widest + 2 * padX) * grow, F.safe.w * 0.92, P.minSize * u);
  if (fitted !== size) { size = fitted; padX = 0.34 * size; }
  var L = 1.34 * size, cap = -CC.measure(c, "H", size).top, boxH = cap + 0.62 * size;

  // the column: lines j = -back .. +3 around the target (j = 0), words taken cyclically from the list
  var travel = Math.max(P.minTravel, ti), back = travel + 3, vis = Math.max(1, Math.min(3, Math.floor((n - 1) / 2)));
  var land = P.landAt !== null && P.landAt !== undefined ? P.landAt : P.rollAt + Math.min(1.5, Math.max(0.9, 0.4 + 0.11 * travel));
  if (P.cueAt !== null && P.cueAt !== undefined) land = CC.landBy(P.cueAt);
  var rollAt = Math.min(P.rollAt, land - 0.6);
  var tOut = P.outAt !== null && P.outAt !== undefined ? P.outAt : D - exit - f1;
  var cx = F.safe.x + F.safe.w / 2, cy = F.safe.y + F.safe.h / 2;
  var rig = CC.rig(c, P.layer + " rig", [cx, cy]);
  // entry carried by the camera: settles from 106 % into the hold, then the slow push
  var settle = 100 * 1.06;
  EC.keys(c, rig, "transform/scale", [[0, [settle, settle]], [land, [100, 100]], [D, [100 * CC.driftAt(D - land), 100 * CC.driftAt(D - land)]]],
          ["out", "linear"]);
  var col = EC.nul(c, { name: P.layer + " column" });
  CC.child(c, col, rig);
  EC.keys(c, col, "transform/position", [[rollAt, [0, travel * L]], [land, [0, 0]], [tOut, [0, 0]], [tOut + exit, [0, -2.6 * L]]],
          [[10, 82], "linear", "expoIn"]);
  EC.sw(c, col, "motionBlur", true);
  var widths = [], ids = [], colName = P.layer + " column";
  for (var j = -back; j <= 3; j++) {
    var wd = words[((ti + j) % n + n) % n], m = CC.measure(c, wd, size);
    widths.push(Math.round(m.width + 2 * padX));
    var id = CC.text(c, { text: wd, size: size, fill: ink, justify: "center", name: P.layer + " " + j + " " + wd });
    CC.child(c, id, col);
    EC.set(c, id, "transform/position", [0, j * L + cap / 2]);
    EC.sw(c, id, "motionBlur", true);
    EC.expr(c, id, "transform/opacity", "var y = thisComp.layer(\"" + colName + "\").transform.position[1];" +
            "var d = Math.abs(" + (j * L) + " + y) / " + L + "; var v = " + vis + ";" +
            "d <= 1 ? 100 - 48 * d : (d <= v ? Math.max(0, 52 - 26 * (d - 1)) : Math.max(0, 52 - 26 * (v - 1)) * Math.max(0, v + 1 - d))");
    ids.push(id);
  }
  // the selection frame: width follows the word in the middle, smoothly between neighbours
  var wexp = "var W = " + JSON.stringify(widths) + "; var y = thisComp.layer(\"" + colName + "\").transform.position[1];" +
             "var p = -y / " + L + " + " + back + "; p = Math.max(0, Math.min(W.length - 1, p)); var i = Math.floor(p), f = p - i;" +
             "var w = W[i] + (W[Math.min(W.length - 1, i + 1)] - W[i]) * f;";
  var bx = EC.nul(c, { name: P.layer + " frame" });
  CC.child(c, bx, rig);
  EC.set(c, bx, "transform/position", [0, 0]);
  var tb = rollAt + 0.12;
  EC.keys(c, bx, "transform/scale", [[tb, [70, 70]], [tb + enter, [102.5, 102.5]], [tb + enter * 1.5, [100, 100]], [tOut, [100, 100]], [tOut + exit, [0, 0]]],
          [CC.ease(), "smooth", "linear", "expoIn"]);
  // a null's opacity does not reach its children: the frame line and the handles fade in themselves
  function fadeIn(id) { EC.keys(c, id, "transform/opacity", [[tb, 0], [tb + 0.1, 100]], "linear"); }
  var lw = Math.max(2.5, (CC.brand().shape.line || 3)) * u;
  var box = EC.shape(c, { kind: "rect", size: [widths[back], boxH], stroke: acc, strokeWidth: lw, fillOpacity: 0, name: P.layer + " frame line" });
  CC.child(c, box, bx);
  EC.set(c, box, "transform/position", [0, 0]);
  EC.expr(c, box, "contents/group/contents/rect/size", wexp + "[w, " + boxH + "]");
  fadeIn(box);
  var hs = 0.11 * size;
  for (var h = 0; h < 4; h++) {
    var hd = EC.shape(c, { kind: "rect", size: [hs, hs], fill: CC.brand().colors.paper || "#FFFFFF", stroke: acc, strokeWidth: lw * 0.85, name: P.layer + " handle " + h });
    CC.child(c, hd, bx);
    var sx = h % 2 ? 1 : -1, sy = h < 2 ? -1 : 1;
    EC.expr(c, hd, "transform/position", wexp + "[" + sx + " * w / 2, " + (sy * boxH / 2) + "]");
    fadeIn(hd);
  }
  CC.measureDone(c);
  return { column: col, words: ids, frame: bx, target: words[ti], travel: travel, size: size, rollAt: rollAt, landAt: land, outAt: tOut };
}
