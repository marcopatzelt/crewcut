/* @template versus
 * @description Two things side by side: their names rise in (each in its own palette colour), a thin line draws
 *   itself between them, and for each row (2 to 3 at most) the two values count up like meters and land together.
 *   Then the winner grows by 5 % (a spring under 4 %), a stroke in the accent colour draws under its name, and the
 *   other side dims. The camera pushes in slowly while it holds; at the end everything sinks away.
 * @kind full
 * @formats ["landscape", "portrait", "stage"]
 * @version 1
 * @sounds [{"at": "countAt", "sound": "reel_tick"}, {"at": "decideAt", "sound": "hit"}]
 * @params {"comp": "Main", "left": "Laptop", "right": "Rented GPU",
 *   "rows": [{"label": "minutes per render", "left": "38", "right": "6", "better": "lower"},
 *            {"label": "renders per hour", "left": "2", "right": "10", "better": "higher"}],
 *   "winner": "auto", "size": 120, "minSize": 72, "nameSize": 72, "labelSize": 42, "countAt": 0.45, "count": 1.2,
 *   "decideAt": null, "outAt": null, "layer": "Versus"}
 * @end */
function versus(P) {
  var c = P.comp, F = CC.frame(), u = F.u, D = F.duration, f1 = 1 / (F.fps || 25);
  var enter = CC.enterS(), exit = CC.exitS(), ink = CC.ink(), tone = CC.tone();
  CC.groundLayer(c);
  var rows = (P.rows || []).slice(0, 3), area = F.safe, colW = area.w * 0.44, grow = CC.driftAt(D) * 1.08;
  // the winner: given, or the side that is better in more rows ("lower" or "higher" per row)
  var win = P.winner;
  if (win === "auto") {
    var sc = 0;
    for (var r = 0; r < rows.length; r++) {
      var a = parseFloat(String(rows[r].left).replace(/[^0-9.\-]/g, "")), b = parseFloat(String(rows[r].right).replace(/[^0-9.\-]/g, ""));
      if (isNaN(a) || isNaN(b) || a === b) continue;
      sc += ((rows[r].better === "lower") === (a < b)) ? -1 : 1;
    }
    win = sc > 0 ? "right" : (sc < 0 ? "left" : null);
  }
  // sizes: values and names fit their column (grown by the push and the winner's growth)
  var size = P.size * u, ns = P.nameSize * u, ls = Math.max(40 * u, P.labelSize * u);
  var widest = 0;
  for (var q = 0; q < rows.length; q++) widest = Math.max(widest, CC.rowWidth(c, rows[q].left, size), CC.rowWidth(c, rows[q].right, size));
  size = CC.fit(size, widest * grow, colW * 0.9, P.minSize * u);
  var nw = Math.max(CC.measure(c, P.left, ns).advance, CC.measure(c, P.right, ns).advance);
  ns = CC.fit(ns, nw * grow, colW * 0.92, 48 * u);
  var capV = -CC.measure(c, "0", size).top, capN = -CC.measure(c, "H", ns).top, capL = -CC.measure(c, "H", ls, "body").top;
  var rowH = capL + 0.32 * size + capV + 0.42 * size, headH = capN + 0.62 * size;
  var blockH = headH + rows.length * rowH - 0.42 * size;
  var cx = area.x + area.w / 2, cy = area.y + area.h / 2, top = -blockH / 2;
  var rig = CC.rig(c, P.layer + " rig", [cx, cy]);
  var dx = area.w * 0.25;
  // each side hangs on its own null at the column centre (the winner grows around it)
  var side = { left: CC.rig(c, P.layer + " left", [0, 0]), right: CC.rig(c, P.layer + " right", [0, 0]) };
  CC.child(c, side.left, rig); CC.child(c, side.right, rig);
  EC.set(c, side.left, "transform/position", [-dx, 0]);
  EC.set(c, side.right, "transform/position", [dx, 0]);
  var oy = 0;

  var count0 = P.countAt, land = P.countAt + P.count;
  var decide = P.decideAt !== null && P.decideAt !== undefined ? P.decideAt : land + 0.3;
  var tOut = P.outAt !== null && P.outAt !== undefined ? P.outAt : D - exit - f1;
  var names = {}, k = 0, kids = { left: [], right: [] };      // a null's opacity does not reach its children
  ["left", "right"].forEach(function (sd) {
    var nm = String(P[sd]), m = CC.measure(c, nm, ns);
    var id = CC.text(c, { text: nm, size: ns, fill: CC.textColor(1 + 2 * k), name: P.layer + " name " + sd });
    CC.rise(c, id, { parent: side[sd], x: -m.advance / 2, y: top + capN + oy, size: ns, ink: m, t: 0.06 * k, dur: enter,
                     outAt: tOut, outDur: exit, name: P.layer + " name " + sd });
    names[sd] = { id: id, m: m };
    kids[sd].push(id);
    k++;
  });
  // a short line between the two names draws itself from the top (the row labels sit on the middle below it)
  var ln = CC.stroke(c, { pts: [[0, top - 0.1 * ns], [0, top + capN + 0.2 * ns]], color: ink, width: 2 * u, name: P.layer + " divider" });
  CC.child(c, ln.layer, rig); EC.set(c, ln.layer, "transform/position", [0, 0]);
  EC.set(c, ln.layer, "transform/opacity", 30);
  EC.keys(c, ln.layer, ln.trim + "end", [[0.05, 0], [0.5, 100]], "expo");
  EC.keys(c, ln.layer, ln.trim + "start", [[tOut, 0], [tOut + exit, 100]], "expoIn");
  var meters = [];
  for (var i = 0; i < rows.length; i++) {
    var y0 = top + headH + i * rowH, base = y0 + capL + 0.32 * size + capV;
    var lab = String(rows[i].label || ""), lm = CC.measure(c, lab, ls, "body");
    if (lab) {
      var lb = CC.text(c, { text: lab, size: ls, fill: ink, role: "body", name: P.layer + " label " + i });
      CC.rise(c, lb, { parent: rig, x: -lm.advance / 2, y: y0 + capL, size: ls, ink: lm, t: count0 - 0.15 + 0.05 * i, dur: enter,
                       outAt: tOut + 0.03, outDur: exit, name: P.layer + " label " + i, pop: false });
      EC.set(c, lb, "transform/opacity", 62);
    }
    ["left", "right"].forEach(function (sd) {
      var v = String(rows[i][sd]), w = CC.rowWidth(c, v, size);
      var m = CC.meter(c, { parent: side[sd], text: v, x: -w / 2, base: base + oy, size: size, tone: tone, rollAt: count0 + 0.04 * i,
                            land: land, outAt: tOut + 0.02 * i, name: P.layer + " " + sd + " " + i });
      meters.push(m);
      for (var z = 0; z < m.ids.length; z++) kids[sd].push(m.ids[z]);
    });
  }
  // the decision: the winner grows (spring under 4 %) and gets the accent stroke; the other side dims
  var stroke = null;
  if (win === "left" || win === "right") {
    var lose = win === "left" ? "right" : "left", W0 = 100, W1 = 105;
    EC.keys(c, side[win], "transform/scale", [[decide, [W0, W0]], [decide + 0.22, [W1 * 1.03, W1 * 1.03]], [decide + 0.5, [W1, W1]]], ["out", "smooth"]);
    for (var dk = 0; dk < kids[lose].length; dk++) EC.keys(c, kids[lose][dk], "transform/opacity", [[decide, 100], [decide + 0.35, 38]], "smooth");
    EC.keys(c, side[lose], "transform/scale", [[decide, [100, 100]], [decide + 0.35, [97, 97]]], "smooth");
    var nmw = names[win].m;
    var sk = CC.stroke(c, { pts: [[-nmw.width / 2, 0], [nmw.width / 2, 0]], color: CC.color(0), width: Math.max(4, 1.6 * (CC.brand().shape.line || 3)) * u,
                            name: P.layer + " winner stroke" });
    CC.child(c, sk.layer, side[win]);
    EC.set(c, sk.layer, "transform/position", [nmw.left + nmw.width / 2 - nmw.advance / 2, top + capN + 0.24 * ns + oy]);
    EC.keys(c, sk.layer, sk.trim + "end", [[decide + 0.05, 0], [decide + 0.5, 100]], "expo");
    EC.keys(c, sk.layer, sk.trim + "start", [[tOut, 0], [tOut + exit, 100]], "expoIn");
    stroke = sk.layer;
  }
  CC.measureDone(c);
  // the cut in lands on a camera move: the two sides settle from 104 % while they count, then the slow push
  var sE = 100 * CC.driftAt(D - land);
  EC.keys(c, rig, "transform/scale", [[0, [104, 104]], [land, [100, 100]], [D, [sE, sE]]], ["out", "linear"]);
  return { winner: win, rows: rows.length, size: size, nameSize: ns, countAt: count0, landAt: land, decideAt: decide, outAt: tOut, stroke: stroke };
}
