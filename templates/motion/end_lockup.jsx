/* @template end_lockup
 * @description The end card: the logo (when the pack or the plan gives one) settles with a small scale spring, the
 *   channel name cascades in letter by letter out of its baseline, a thin accent stroke draws itself under it and an
 *   optional line rises below. The camera settles in from 104 % and keeps pushing slowly to the last frame (it is
 *   the end of the video, so there is no exit).
 * @kind full
 * @formats ["landscape", "portrait", "stage"]
 * @version 1
 * @sounds [{"at": "in", "sound": "whoosh"}]
 * @params {"comp": "Main", "name": "Crew Notes", "line": "New video every Thursday", "logo": "", "size": 150,
 *   "minSize": 96, "lineSize": 52, "inAt": 0.0, "cascade": 0.035, "layer": "Lockup"}
 * @end */
function end_lockup(P) {
  var c = P.comp, F = CC.frame(), u = F.u, D = F.duration;
  var enter = CC.enterS(), ink = CC.ink(), area = F.safe, margin = 40 * u;
  CC.groundLayer(c);
  var name = String(P.name), chars = name.split("");
  var logoH = 0, lg = null, lgDims = null;
  var size = P.size * u, grow = CC.driftAt(D) * 1.04;
  if (P.logo) { lg = EC.footage(c, P.logo, { name: P.layer + " logo" }); lgDims = EC.dims(c, lg); }
  function rowW(sz) { var w = CC.rowWidth(c, name, sz); return lg ? w + 1.25 * sz : w; }
  size = CC.fit(size, rowW(size) * grow, area.w - 2 * margin, P.minSize * u);
  var cap = -CC.measure(c, "H", size).top, ls = Math.max(40 * u, P.lineSize * u);
  var lm = P.line ? CC.measure(c, String(P.line), ls, "body") : null, lcap = -CC.measure(c, "H", ls, "body").top;
  var rowWidth = rowW(size), blockH = cap + (lm ? 0.75 * size + lcap : 0);
  var cx = area.x + area.w / 2, cy = area.y + area.h / 2, rig = CC.rig(c, P.layer + " rig", [cx, cy]);
  var x0 = -rowWidth / 2, base = -blockH / 2 + cap, t0 = P.inAt;
  // the logo: as tall as 1.05 cap heights, left of the name, settles with a 3 % spring on its scale
  if (lg) {
    logoH = 1.05 * cap;
    var s = 100 * logoH / ((lgDims && lgDims.height) || 512), lw = ((lgDims && lgDims.width) || 512) * s / 100;
    CC.child(c, lg, rig);
    EC.set(c, lg, "transform/position", [x0 + lw / 2, base - cap / 2]);
    EC.keys(c, lg, "transform/scale", [[t0, [s * 0.6, s * 0.6]], [t0 + enter * 0.8, [s * 1.03, s * 1.03]], [t0 + enter * 1.4, [s, s]]], [CC.ease(), "smooth"]);
    EC.keys(c, lg, "transform/opacity", [[t0, 0], [t0 + 0.12, 100]], "linear");
    EC.sw(c, lg, "motionBlur", true);
    x0 += 1.25 * size;
  }
  // the name, letter by letter out of the baseline
  var x = x0, ids = [], tName = t0 + (lg ? 0.18 : 0);
  for (var i = 0; i < chars.length; i++) {
    var m = CC.measure(c, chars[i], size);
    if (chars[i].replace(/\s/g, "")) {
      var id = CC.text(c, { text: chars[i], size: size, fill: ink, name: P.layer + " " + i });
      CC.rise(c, id, { parent: rig, x: x, y: base, size: size, ink: m, t: tName + P.cascade * i, dur: enter, name: P.layer + " " + i, popPct: 2 });
      ids.push(id);
    }
    x += m.advance;
  }
  var tLand = tName + P.cascade * (chars.length - 1) + enter;
  var nameInk = CC.measure(c, name, size);
  var sk = CC.stroke(c, { pts: [[x0 + nameInk.left, 0], [x0 + nameInk.left + nameInk.width, 0]], color: CC.color(0),
                          width: Math.max(4, 1.6 * (CC.brand().shape.line || 3)) * u, name: P.layer + " stroke" });
  CC.child(c, sk.layer, rig);
  EC.set(c, sk.layer, "transform/position", [0, base + 0.2 * size]);
  EC.keys(c, sk.layer, sk.trim + "end", [[tLand - 0.2, 0], [tLand + 0.35, 100]], "expo");
  var lid = null;
  if (lm) {
    lid = CC.text(c, { text: String(P.line), size: ls, fill: ink, role: "body", name: P.layer + " line" });
    CC.rise(c, lid, { parent: rig, x: -lm.advance / 2, y: base + 0.75 * size + lcap, size: ls, ink: lm, t: tLand - 0.1, dur: enter,
                      name: P.layer + " line", pop: false });
    EC.set(c, lid, "transform/opacity", 70);
  }
  CC.measureDone(c);
  var sE = 100 * CC.driftAt(D - tLand);
  EC.keys(c, rig, "transform/scale", [[0, [104, 104]], [tLand, [100, 100]], [D, [sE, sE]]], ["out", "linear"]);
  return { name: ids, logo: lg, stroke: sk.layer, line: lid, size: size, landed: tLand };
}
