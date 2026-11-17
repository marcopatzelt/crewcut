/* @template cursor
 * @description A pointer for screen recordings: it flies along a path of points (fractions of the frame, the tip
 *   lands on each) with an expo ease and motion blur, squashes on each click, and a thin ring in the accent colour
 *   opens from the tip and fades with every click (clickAt, then any moreClicks). It enters from outside the
 *   frame and leaves the same way.
 * @kind overlay
 * @formats ["landscape", "portrait", "stage"]
 * @version 1
 * @sounds [{"at": "clickAt", "sound": "click"}]
 * @params {"comp": "Main", "path": [[0.0, 1.06, 0.30], [0.5, 0.62, 0.46], [0.85, 0.60, 0.47]], "clickAt": 1.0,
 *   "moreClicks": [], "height": 60, "ease": "expo", "ring": true, "leave": true, "image": "", "layer": "Cursor"}
 * @end */
function cursor(P) {
  var c = P.comp, F = CC.frame(), u = F.u, D = F.duration, W = F.W, H = F.H;
  var img = P.image || (EC_ASSETS + "/cursor.png");
  var id = EC.footage(c, img, { name: P.layer });
  var info = EC.dims(c, id), h = (info && info.height) || 160, w = (info && info.width) || 128;
  var s = 100 * P.height * u / h;
  EC.set(c, id, "transform/anchor", [w * 2 / 32, h * 2 / 40]);            // the tip of the drawn arrow
  EC.set(c, id, "transform/scale", [s, s]);
  var keys = [], last = P.path[P.path.length - 1];
  for (var i = 0; i < P.path.length; i++) keys.push([P.path[i][0], [P.path[i][1] * W, P.path[i][2] * H]]);
  if (P.leave && last[0] < D - 0.45) {                                     // it leaves the way it came, 0.4 s before the end
    var first = P.path[0];
    keys.push([D - 0.45, [last[1] * W, last[2] * H]]);
    keys.push([D - 0.05, [first[1] * W, first[2] * H]]);
  }
  var ez = []; for (var e = 0; e + 1 < keys.length; e++) ez.push(e === keys.length - 3 && P.leave ? "linear" : (e === keys.length - 2 && P.leave ? "expoIn" : P.ease));
  EC.keys(c, id, "transform/position", keys, ez);
  var clicks = (P.clickAt === null || P.clickAt === undefined ? [] : [P.clickAt]).concat(P.moreClicks || []);
  var sk = [];
  for (var k = 0; k < clicks.length; k++) {
    var t = clicks[k];
    sk.push([t - 0.06, [s, s]], [t, [s * 0.82, s * 0.82]], [t + 0.12, [s, s]]);
  }
  if (sk.length) EC.keys(c, id, "transform/scale", sk, "smooth");
  EC.sw(c, id, "motionBlur", true);
  EC.fx(c, id, "Drop Shadow", { opacity: 32, distance: 4 * u, softness: 10 * u, direction: 160 });
  // the click ring: opens from the tip and fades (where the pointer is at that moment)
  var rings = [];
  if (P.ring) {
    for (var q = 0; q < clicks.length; q++) {
      var tc = clicks[q], at = null;
      for (var j = 0; j < P.path.length; j++) if (P.path[j][0] <= tc) at = P.path[j];
      if (!at) at = P.path[0];
      var r = EC.shape(c, { kind: "ellipse", size: [90 * u, 90 * u], stroke: CC.color(0), strokeWidth: 3 * u, fillOpacity: 0, name: P.layer + " ring " + q });
      EC.set(c, r, "transform/position", [at[1] * W, at[2] * H]);
      EC.keys(c, r, "transform/scale", [[tc, [10, 10]], [tc + 0.35, [100, 100]]], "out");
      EC.keys(c, r, "transform/opacity", [[tc, 90], [tc + 0.35, 0]], "linear");
      EC.trim(c, r, tc - 0.02, tc + 0.4);
      rings.push(r);
    }
  }
  return { layer: id, scale: s, rings: rings };
}
