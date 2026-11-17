/* @template cursor_flyin
 * @description Mouse pointer that flies along a path with expo easing and motion blur, and clicks
 *   (squash to 80 % and back) at given times. path: [[t, x, y], ...] in comp seconds and pixels (tip position).
 * @params {"comp": "Main", "path": [[0.0, 2050, 300], [0.55, 1010, 560], [0.9, 990, 548]],
 *   "ease": "expo", "clicks": [1.05], "height": 64, "image": "", "in": 0.0, "out": null, "shadow": true, "name": "Cursor"}
 * @end */
function cursor_flyin(P) {
  var c = P.comp;
  var img = P.image || (EC_ASSETS + "/cursor.png");
  var id = EC.footage(c, img, { name: P.name });
  var info = EC.dims(c, id);
  var h = (info && info.height) ? info.height : 160, w = (info && info.width) ? info.width : 128;
  var s = 100 * P.height / h;
  // anchor at the tip (top-left of the arrow drawing: 2/32 and 2/40 of the image)
  EC.set(c, id, "transform/anchor", [w * 2 / 32, h * 2 / 40]);
  EC.set(c, id, "transform/scale", [s, s]);
  var keys = [];
  for (var i = 0; i < P.path.length; i++) keys.push([P.path[i][0], [P.path[i][1], P.path[i][2]]]);
  EC.keys(c, id, "transform/position", keys, P.ease);
  var sk = [];
  for (var k = 0; k < P.clicks.length; k++) {
    var t = P.clicks[k];
    sk.push([t - 0.06, [s, s]], [t, [s * 0.8, s * 0.8]], [t + 0.12, [s, s]]);
  }
  if (sk.length) EC.keys(c, id, "transform/scale", sk, "smooth");
  EC.sw(c, id, "motionBlur", true);
  if (P.shadow) EC.fx(c, id, "Drop Shadow", { opacity: 35, distance: 4, softness: 10, direction: 160 });
  if (P["in"] || P.out !== null) EC.trim(c, id, P["in"] || 0, P.out === null ? undefined : P.out);
  return { layer: id, scale: s };
}
