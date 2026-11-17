/* @template card_gallery
 * @description The episode's real screenshots as a gallery in space: the first picture lands in the middle with a
 *   small scale spring and a turn, then the others fly in from the camera side into a tilted masonry grid, staggered
 *   by their distance from the middle, while the camera pulls back; the grid drifts and turns slowly in the hold;
 *   at the end the camera pushes through. Once per video.
 * @kind full
 * @formats ["landscape", "portrait", "stage"]
 * @version 1
 * @sounds [{"at": "gridAt", "sound": "whoosh"}]
 * @params {"comp": "Main", "images": [], "heroAt": 0.0, "gridAt": 0.45, "fly": 0.5, "stagger": 0.035,
 *   "tilt": [22, -18, 5], "tiltEnd": [18, -11, 3], "pull": [1.55, 0.82], "shadow": 26, "seed": 5, "outAt": null,
 *   "layer": "Gallery"}
 * @end */
function card_gallery(P) {
  var c = P.comp, F = CC.frame(), u = F.u, D = F.duration, W = F.W, H = F.H, f1 = 1 / (F.fps || 25);
  var exit = CC.exitS(), rnd = EC.rng(P.seed);
  CC.groundLayer(c);
  var imgs = P.images || [];
  if (!imgs.length) return { cards: 0, note: "no images: give the episode's screenshots as images" };
  var portrait = H > W, cols = portrait ? 4 : 7, colW = (portrait ? 0.34 : 0.19) * W, gap = 0.022 * Math.max(W, H);
  var heroW = colW * 1.05, cx = W / 2, cy = H / 2, step = colW + gap, mid = Math.floor(cols / 2);
  var reach = 0.75 * Math.max(W, H);                                       // how far the columns run up and down
  var tOut = P.outAt !== null && P.outAt !== undefined ? P.outAt : D - exit - f1;
  // camera: the zoom puts z = 0 at 100 %; the pull moves it back from pull[0] to pull[1], then it pushes through
  var Z = 1.6 * Math.max(W, H);
  var cam = EC.camera(c, { name: P.layer + " camera", type: "twoNode", zoom: Z, position: [cx, cy, -Z], poi: [cx, cy, 0] });
  var t1 = P.gridAt + 0.95;
  EC.keys(c, cam, "transform/position", [[0, [cx, cy, -Z / P.pull[0]]], [P.heroAt + 0.3, [cx, cy, -Z / (P.pull[0] * 0.97)]],
                                         [t1, [cx, cy, -Z / P.pull[1]]], [tOut, [cx, cy, -Z / (P.pull[1] * CC.driftAt(tOut - t1))]],
                                         [D, [cx, cy, -Z / (P.pull[1] * 1.6)]]], ["smooth", "strong", "linear", "expoIn"]);
  EC.sw(c, cam, "motionBlur", true);
  var g = EC.nul(c, { name: P.layer + " grid", threeD: true });
  EC.set(c, g, "transform/position", [cx, cy, 0]);
  var rx = [[0, P.tilt[0]], [D, P.tiltEnd[0]]], ry = [[0, P.tilt[1]], [D, P.tiltEnd[1]]], rz = [[0, P.tilt[2]], [D, P.tiltEnd[2]]];
  EC.keys(c, g, "transform/rotationX", rx, "smooth"); EC.keys(c, g, "transform/rotationY", ry, "smooth"); EC.keys(c, g, "transform/rotation", rz, "smooth");
  function card(path, w, name) {
    var id = EC.footage(c, path, { name: name, threeD: true });
    var d = EC.dims(c, id), s = 100 * w / ((d && d.width) || 640);
    CC.child(c, id, g);
    EC.set(c, id, "transform/scale", [s, s, s]);
    EC.sw(c, id, "motionBlur", true);
    if (P.shadow) EC.fx(c, id, "Drop Shadow", { opacity: P.shadow, distance: 14 * u, softness: 36 * u, direction: 170 });
    return { id: id, h: d ? d.height * s / 100 : w * 0.5625, s: s };
  }
  // the hero: lands with a turn and a 3 % scale spring
  var hero = card(imgs[0], heroW, P.layer + " hero"), th = P.heroAt, hs = hero.s;
  EC.keys(c, hero.id, "transform/position", [[th, [0, 0, -0.2 * Z]], [th + 0.4, [0, 0, 0]]], "expo");
  EC.keys(c, hero.id, "transform/scale", [[th, [hs * 0.7, hs * 0.7, hs]], [th + 0.3, [hs * 1.03, hs * 1.03, hs]], [th + 0.5, [hs, hs, hs]]], ["out", "smooth"]);
  EC.keys(c, hero.id, "transform/rotationY", [[th, -30], [th + 0.35, 6], [th + 0.7, 0]], "smooth");
  var colH = []; for (var q = 0; q < cols; q++) colH.push(-reach + rnd() * 0.25 * reach);
  colH[mid] = hero.h / 2 + gap;
  var midTop = -hero.h / 2 - gap, ci = 1, n = imgs.length, count = 1;
  function fly(id, x, y) {
    var dist = Math.sqrt(x * x + y * y), t0 = P.gridAt + P.stagger * dist / step + rnd() * 0.05;
    EC.keys(c, id, "transform/position", [[t0, [x * 1.25, y * 1.25, -0.9 * Z]], [t0 + P.fly, [x, y, 0]]], "expo");
    EC.keys(c, id, "transform/opacity", [[t0, 0], [t0 + 0.06, 100]], "linear");
    EC.trim(c, id, t0, undefined);
  }
  for (var guard = 0; guard < 120; guard++) {
    var best = -1, bh = 1e9;
    for (var o = 0; o < cols; o++) if (colH[o] < reach && colH[o] < bh) { bh = colH[o]; best = o; }
    if (best < 0) break;
    var cd = card(imgs[ci % n], colW, P.layer + " card " + count); ci++; count++;
    var x = (best - mid) * step, y = colH[best] + cd.h / 2;
    colH[best] += cd.h + gap;
    fly(cd.id, x, y);
  }
  for (var up = midTop, k = 0; up > -reach && k < 6; k++) {
    var cd2 = card(imgs[ci % n], colW, P.layer + " card " + count); ci++; count++;
    var y2 = up - cd2.h / 2; up -= cd2.h + gap;
    fly(cd2.id, 0, y2);
  }
  return { cards: count, camera: cam, grid: g, outAt: tOut };
}
