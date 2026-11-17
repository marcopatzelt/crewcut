/* @template lower_third
 * @description Name and role on the free side, low in the frame. The name rises out of its baseline, a thin
 *   stroke in the accent colour draws itself under it, the role follows a beat later; everything pushes in
 *   slowly while it holds; at the end the stroke retracts and both lines sink back. No box, no plate.
 * @kind overlay
 * @formats ["landscape", "portrait", "stage"]
 * @version 1
 * @sounds [{"at": "in", "sound": "whoosh"}]
 * @params {"comp": "Main", "name": "Jordan Lee", "role": "Editor and host", "nameSize": 84, "roleSize": 46,
 *   "minNameSize": 60, "inAt": 0.0, "cueAt": null, "outAt": null, "align": "auto", "line": null, "layer": "Lower third"}
 * @end */
function lower_third(P) {
  var c = P.comp, F = CC.frame(), u = F.u, box = F.sideBox, margin = 28 * u;
  var maxW = box.w - 2 * margin;
  if (F.side === "below" || F.side === "center") maxW = Math.min(maxW, F.safe.w - 2 * margin);

  // sizes: the name fits the free side; the role never wider than the name allows, never under 40 px
  var ns = P.nameSize * u, rs = P.roleSize * u;
  var nm = CC.measure(c, P.name, ns);
  var ns2 = CC.fit(ns, nm.advance, maxW, P.minNameSize * u);
  if (ns2 !== ns) { rs = Math.max(40 * u, rs * ns2 / ns); ns = ns2; nm = CC.measure(c, P.name, ns); }
  var rm = CC.measure(c, P.role, rs, "body");
  var rs2 = CC.fit(rs, rm.advance, maxW, 40 * u);
  if (rs2 !== rs) { rs = rs2; rm = CC.measure(c, P.role, rs, "body"); }
  var capN = -CC.measure(c, "H", ns).top, capR = -CC.measure(c, "H", rs, "body").top;
  var lw = P.line !== null && P.line !== undefined ? P.line * u : Math.max(3, (CC.brand().shape.line || 3) * 1.4) * u;

  // vertical stack (baselines, relative to the block top): name, stroke, role
  var gapNS = 0.34 * ns, gapSR = 0.34 * ns + capR;
  var yName = capN, yStroke = yName + gapNS, yRole = yStroke + gapSR;
  var blockH = yRole + 0.25 * rs, blockW = Math.max(nm.advance, rm.advance);

  // placement: the outer edge of the free side, low in the safe box (portrait: the lower part of the band below the face)
  var align = P.align;
  if (align === "auto") align = F.side === "right" ? "right" : "left";
  var left = align === "right" ? box.x + box.w - margin - blockW : (F.side === "left" || F.side === "right" ? box.x + margin : F.safe.x + margin);
  if (F.side === "right" && align === "left") left = box.x + margin;
  var top = F.safe.y + F.safe.h - margin - blockH;
  if (F.format === "portrait") top = Math.min(top, box.y + box.h * 0.82 - blockH);
  var cx = left + blockW / 2, cy = top + blockH / 2;
  var rig = CC.rig(c, P.layer + " rig", [cx, cy]);
  var tone = CC.tone({ x: left, y: top, w: blockW, h: blockH });
  function lx(w) { return align === "right" ? blockW / 2 - w : -blockW / 2; }   // line start, rig space

  // timing: the name is complete 1.5 frames before the cue
  var enter = CC.enterS(), exit = CC.exitS(), D = F.duration, f1 = 1 / (F.fps || 25);
  var tIn = P.inAt;
  if (P.cueAt !== null && P.cueAt !== undefined) tIn = Math.max(0, CC.landBy(P.cueAt) - enter);
  var tOut = P.outAt !== null && P.outAt !== undefined ? P.outAt : D - exit - 0.08 - f1;

  var name = CC.text(c, { text: P.name, size: ns, fill: tone.fill, name: P.layer + " name" });
  CC.legible(c, name, ns, tone);
  CC.rise(c, name, { parent: rig, x: lx(nm.advance), y: yName - blockH / 2, size: ns, ink: nm, t: tIn, dur: enter,
                     outAt: tOut + 0.04, outDur: exit, name: P.layer + " name", popPct: 2 });
  var role = CC.text(c, { text: P.role, size: rs, fill: tone.fill, role: "body", name: P.layer + " role" });
  CC.legible(c, role, rs, tone, 0.8);
  CC.rise(c, role, { parent: rig, x: lx(rm.advance), y: yRole - blockH / 2, size: rs, ink: rm, t: tIn + 0.16, dur: enter,
                     outAt: tOut, outDur: exit, name: P.layer + " role", pop: false });
  EC.set(c, role, "transform/opacity", 78);

  // the stroke: from the aligned edge across the name's ink, drawn by a trim path, retracted at the end
  var sw = nm.width + 0.04 * ns, x0 = align === "right" ? blockW / 2 : -blockW / 2 + nm.left, x1 = align === "right" ? x0 - sw : x0 + sw;
  var sk = CC.stroke(c, { pts: [[x0, 0], [x1, 0]], color: CC.color(0), width: lw, name: P.layer + " stroke" });
  var st = sk.layer;
  CC.child(c, st, rig);
  EC.set(c, st, "transform/position", [0, yStroke - blockH / 2]);
  EC.keys(c, st, sk.trim + "end", [[tIn + 0.06, 0], [tIn + 0.06 + 0.55, 100]], "expo");
  EC.keys(c, st, sk.trim + "start", [[tOut - 0.02, 0], [tOut - 0.02 + exit, 100]], "expoIn");
  EC.sw(c, st, "motionBlur", true);
  CC.measureDone(c);
  CC.drift(c, rig, 0, D);
  return { name: name, role: role, stroke: st, rig: rig, nameSize: ns, roleSize: rs, align: align,
           box: { x: left, y: top, w: blockW, h: blockH }, inAt: tIn, landed: tIn + enter, outAt: tOut, side: F.side };
}
