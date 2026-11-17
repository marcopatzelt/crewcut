/* @template sky_gradient
 * @description A sky built in the comp: vertical gradient (top colour to a nearly white horizon) and soft white cloud
 *   shapes (blurred ellipses) that drift slowly. clouds: [[x, y, w, h, opacity, blur, driftX per second], ...].
 * @params {"comp": "Main", "top": "#3FA9F5", "horizon": "#FFF3E2", "horizonY": 560, "size": [1920, 1080],
 *   "clouds": [[380, 200, 1000, 230, 88, 110, 6], [1400, 130, 1200, 260, 80, 140, 4], [960, 380, 1900, 190, 75, 90, 8],
 *     [150, 420, 700, 160, 70, 80, 5], [1750, 400, 800, 170, 70, 90, 3]],
 *   "duration": 10, "name": "Sky"}
 * @end */
function sky_gradient(P) {
  var c = P.comp;
  var s = EC.solid(c, { name: P.name, color: P.top, w: P.size[0], h: P.size[1] });
  EC.set(c, s, "transform/position", [P.size[0] / 2, P.size[1] / 2]);
  EC.fx(c, s, "Gradient Ramp", { start: [P.size[0] / 2, 0], startColor: EC.rgba(P.top), end: [P.size[0] / 2, P.horizonY], endColor: EC.rgba(P.horizon), shape: 0 });
  var cl = [];
  for (var i = 0; i < P.clouds.length; i++) {
    var k = P.clouds[i];
    var id = EC.shape(c, { kind: "ellipse", size: [k[2], k[3]], fill: "#FFFFFF", name: P.name + " cloud " + i });
    EC.keys(c, id, "transform/position", [[0, [k[0], k[1]]], [P.duration, [k[0] + k[6] * P.duration, k[1]]]], "linear");
    EC.set(c, id, "transform/opacity", k[4]);
    EC.fx(c, id, "Gaussian Blur", { blurriness: k[5] });
    cl.push(id);
  }
  return { sky: s, clouds: cl };
}
