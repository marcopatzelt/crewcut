/* @template lower_third
 * @description Name and role on the free side, low in the frame. The name rises out of its baseline, a thin
 *   stroke in the accent colour draws itself under it, the role follows a beat later; everything pushes in
 *   slowly while it holds; at the end the stroke retracts and both lines sink back. No box, no plate. variant "card":
 *   the channel's one box form instead (a paper plate with 24 px rounding, a soft ink shadow and a 10 px accent edge
 *   on the left, name and role in ink), right-aligned on the free side in the lower third; it pushes in from the
 *   speaker's side and the two lines follow 2 frames apart.
 * @kind overlay
 * @formats ["landscape", "portrait", "stage"]
 * @version 1
 * @sounds [{"at": "in", "sound": "whoosh"}]
 * @params {"comp": "Main", "name": "Jordan Lee", "role": "Editor and host", "nameSize": 84, "roleSize": 46,
 *   "minNameSize": 60, "inAt": 0.0, "cueAt": null, "outAt": null, "align": "auto", "line": null, "layer": "Lower third",
 *   "variant": "plain"}
 * @end */
function lower_third(P) {
  if (P.variant === "card") return lower_third_card(P);
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

// The card variant: the channel's one box form (brand/references/grafik-system, type b).
function lower_third_card(P) {
  var c = P.comp, F = CC.frame(), u = F.u, g = CC.gfx() || {}, D = F.duration, f1 = 1 / (F.fps || 25);
  var paper = g.paper || (CC.brand().colors.paper || "#FFFFFF"), ink = g.ink || CC.ink(), accent = g.accent || CC.color(0);
  var padX = 44 * u, padY = 34 * u, edge = 10 * u, radius = 24 * u;
  var maxW = Math.min(F.safe.w, (F.format === "portrait" ? 0.9 : 0.56) * F.W) - 2 * padX - edge;
  var ns = (P.nameSize === 84 ? 72 : P.nameSize) * u, rs = (P.roleSize === 46 ? 56 : P.roleSize) * u, floor = 40 * u;
  var nm = CC.measure(c, P.name, ns);
  var ns2 = CC.fit(ns, nm.advance, maxW, P.minNameSize * u);
  if (ns2 !== ns) { ns = ns2; nm = CC.measure(c, P.name, ns); }
  var rm = P.role ? CC.measure(c, P.role, rs, "body") : null;
  if (rm) { var rs2 = CC.fit(rs, rm.advance, maxW, floor); if (rs2 !== rs) { rs = rs2; rm = CC.measure(c, P.role, rs, "body"); } }
  var capN = -CC.measure(c, "H", ns).top, capR = rm ? -CC.measure(c, "H", rs, "body").top : 0;
  var gap = rm ? 0.42 * rs : 0;
  var innerW = Math.max(nm.advance, rm ? rm.advance : 0), innerH = capN + 0.22 * ns + (rm ? gap + capR + 0.22 * rs : 0);
  var cw = innerW + 2 * padX + edge, ch = innerH + 2 * padY;
  // place: right-aligned at the safe edge (left when the speaker sits right), the lower edge on the safe bottom
  var right = P.align === "right" || (P.align === "auto" && F.side !== "left");
  var x = right ? F.safe.x + F.safe.w - cw : F.safe.x, y = F.safe.y + F.safe.h - ch;
  var cx = x + cw / 2, cy = y + ch / 2, from = right ? -1 : 1;            // the speaker's side: the push comes from there
  if (F.side === "below" || F.side === "center") from = 0;
  var rig = CC.rig(c, P.layer + " rig", [cx, cy]);
  var enter = CC.enterS(), exit = CC.exitS(), st = 2 * f1;
  var tIn = P.inAt;
  if (P.cueAt !== null && P.cueAt !== undefined) tIn = Math.max(0, CC.landBy(P.cueAt) - enter - 2 * st);
  var tOut = P.outAt !== null && P.outAt !== undefined ? P.outAt : D - exit - 2 * st - f1;

  function rounded(name, w, h, fill, op, dx, dy, blur) {
    var id = EC.shape(c, { kind: "rounded", size: [w, h], fill: fill, name: P.layer + " " + name });
    EC.set(c, id, "contents/group/contents/rect/roundness", radius);
    if (blur) EC.fx(c, id, "Gaussian Blur", { blurriness: blur });
    CC.child(c, id, rig);
    EC.set(c, id, "transform/position", [dx || 0, dy || 0]);
    EC.set(c, id, "transform/opacity", op);
    return id;
  }
  var shadow = rounded("shadow", cw, ch, ink, 35, 0, 14 * u, 22 * u);
  var spine = rounded("edge", cw, ch, accent, 100, 0, 0, 0);
  var plate = rounded("plate", cw - edge, ch, paper, 96, edge / 2, 0, 0);
  // the push: 24 px from the speaker's side, opacity 0 to 100 %, scale 96 to 100 %; out the same way back
  var push = 24 * u;
  EC.keys(c, rig, "transform/position", [[tIn, [cx + from * push, cy + (from ? 0 : push)]], [tIn + enter, [cx, cy]],
                                         [tOut + 2 * st, [cx, cy]], [tOut + 2 * st + exit, [cx + from * push, cy + (from ? 0 : push)]]],
          [CC.ease(), "linear", CC.easeOut()]);
  EC.keys(c, rig, "transform/scale", [[tIn, [96, 96]], [tIn + enter, [100, 100]], [tOut + 2 * st, [100, 100]],
                                      [tOut + 2 * st + exit, [96, 96]]], [CC.ease(), "linear", CC.easeOut()]);
  var parts = [shadow, spine, plate];
  for (var i = 0; i < parts.length; i++) {
    var op = i === 0 ? 35 : (i === 2 ? 96 : 100);
    EC.keys(c, parts[i], "transform/opacity", [[tIn, 0], [tIn + enter, op], [tOut + 2 * st, op], [tOut + 2 * st + exit, 0]],
            [CC.ease(), "linear", CC.easeOut()]);
    EC.sw(c, parts[i], "motionBlur", true);
  }
  // the lines: name (display) then role (body), in ink, each 2 frames after the card
  var left = -cw / 2 + edge + padX, top = -ch / 2 + padY;
  var name = CC.text(c, { text: P.name, size: ns, fill: ink, name: P.layer + " name" });
  CC.rise(c, name, { parent: rig, x: left, y: top + capN, size: ns, ink: nm, t: tIn + st, dur: enter,
                     outAt: tOut + st, outDur: exit, name: P.layer + " name", pop: false });
  var role = null;
  if (rm) {
    role = CC.text(c, { text: P.role, size: rs, fill: ink, role: "body", name: P.layer + " role" });
    CC.rise(c, role, { parent: rig, x: left, y: top + capN + 0.22 * ns + gap + capR, size: rs, ink: rm, t: tIn + 2 * st,
                       dur: enter, outAt: tOut, outDur: exit, name: P.layer + " role", pop: false });
  }
  CC.measureDone(c);
  return { name: name, role: role, plate: plate, edge: spine, shadow: shadow, rig: rig, nameSize: ns, roleSize: rs,
           box: { x: x, y: y, w: cw, h: ch }, inAt: tIn, landed: tIn + 2 * st + enter, outAt: tOut, side: F.side,
           variant: "card" };
}
