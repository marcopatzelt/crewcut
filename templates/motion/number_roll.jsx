/* @template number_roll
 * @description A number that counts up like a meter: every digit is a reel behind its own window, the units reel
 *   rolls with the count (blurred while fast, ticking whole digits when slow), every other reel turns only when the
 *   one on its right carries from 9 to 0, and the units reel lands with a small settle so the whole number is
 *   complete 1 frame before its cue. Digits are set tight with their real advances in one font, whole on every hold
 *   and never clipped by the frame; leading zeros stay hidden until the count reaches them. A unit in the accent
 *   colour and one line of text sit with it. Full frame on the pack ground, or an overlay beside the speaker when
 *   the insert is transparent.
 * @kind full
 * @formats ["landscape", "portrait", "stage"]
 * @version 1
 * @sounds [{"at": "rollAt", "sound": "reel_tick"}, {"at": "landAt", "sound": "tick"}]
 * @params {"comp": "Main", "value": "128", "prefix": "", "unit": "GB", "label": "of memory on one laptop",
 *   "size": 160, "minSize": 110, "unitScale": 0.46, "labelSize": 50, "rollAt": 0.0, "roll": 1.3, "landAt": null,
 *   "cueAt": null, "from": 0, "ease": 2.2, "outAt": null, "align": "auto", "layer": "Number"}
 * @end */
function number_roll(P) {
  var c = P.comp, F = CC.frame(), u = F.u, full = !F.transparent, D = F.duration, f1 = 1 / (F.fps || 25);
  CC.groundLayer(c);
  var chars = (String(P.prefix || "") + String(P.value)).split(""), unit = String(P.unit || ""), label = String(P.label || "");
  var area = full ? F.safe : F.sideBox, margin = 36 * u;

  // layout at a size: advances of every character, the unit after a small gap
  function lay(sz) {
    var o = { size: sz, items: [], w: 0, us: sz * P.unitScale };
    for (var i = 0; i < chars.length; i++) {
      var m = CC.measure(c, chars[i], sz);
      o.items.push({ ch: chars[i], adv: m.advance, ink: m, digit: /[0-9]/.test(chars[i]), x: o.w });
      o.w += m.advance;
    }
    o.numW = o.w;
    if (unit) { o.um = CC.measure(c, unit, o.us); o.ux = o.w + 0.06 * sz; o.w = o.ux + o.um.advance; }
    return o;
  }
  // fit: the whole row, grown by the push of the hold, stays inside the area
  var L0 = lay(P.size * u), grow = CC.driftAt(D), avail = area.w - 2 * margin;
  var sz = CC.fit(P.size * u, L0.w * grow, avail, P.minSize * u), Lx = sz === P.size * u ? L0 : lay(sz);
  var cap = -CC.measure(c, "0", sz).top;
  var ls = Math.max(40 * u, P.labelSize * u), lm = label ? CC.measure(c, label, ls, "body") : null;
  if (lm && lm.advance * grow > avail) { ls = CC.fit(ls, lm.advance * grow, avail, 40 * u); lm = CC.measure(c, label, ls, "body"); }
  var lcap = label ? -CC.measure(c, "H", ls, "body").top : 0;
  var gapL = 0.42 * sz, blockH = cap + (label ? gapL + lcap + 0.25 * ls : 0);
  var blockW = Math.max(Lx.w, lm ? lm.advance : 0);

  // placement: centred in the safe box (full frame) or on the free side at chest height (overlay)
  var align = P.align;
  if (align === "auto") align = full ? "center" : (F.side === "right" ? "left" : (F.side === "left" ? "right" : "center"));
  var ax = full ? area.x + area.w / 2 : F.anchor[0], ay = full ? area.y + area.h / 2 : F.anchor[1];
  if (!full && align === "left") ax = area.x + margin + blockW / 2;
  if (!full && align === "right") ax = area.x + area.w - margin - blockW / 2;
  var rig = CC.rig(c, P.layer + " rig", [ax, ay]);
  var rig2 = CC.rig(c, P.layer + " rig label", [ax, ay]);                 // the line drifts slower: depth
  var tone = CC.tone({ x: ax - blockW / 2, y: ay - blockH / 2, w: blockW, h: blockH });
  var base = -blockH / 2 + cap;                                             // the number's baseline, rig space
  function rowX(w) { return align === "left" ? -blockW / 2 : (align === "right" ? blockW / 2 - w : -w / 2); }
  var x0 = rowX(Lx.w);

  // timing
  var enter = CC.enterS(), exit = CC.exitS();
  var land = P.landAt !== null && P.landAt !== undefined ? P.landAt : P.rollAt + P.roll;
  if (P.cueAt !== null && P.cueAt !== undefined) land = P.cueAt - f1;     // whole 1 frame before the cue
  var rollAt = Math.min(P.rollAt, land - 0.6);
  var tOut = P.outAt !== null && P.outAt !== undefined ? P.outAt : D - exit - f1;

  var mt = CC.meter(c, { parent: rig, text: chars.join(""), x: x0, base: base, size: sz, tone: tone, rollAt: rollAt,
                         land: land, outAt: tOut, from: P.from, ease: P.ease, name: P.layer });
  var ids = mt.ids, target = mt.target, from = mt.from;
  // the unit (accent) and the line of text rise out of their baselines
  var un = null, lb = null;
  if (unit) {
    un = CC.text(c, { text: unit, size: Lx.us, fill: CC.color(0), name: P.layer + " unit" });
    CC.legible(c, un, Lx.us, tone);
    CC.rise(c, un, { parent: rig, x: x0 + Lx.ux, y: base, size: Lx.us, ink: Lx.um, t: Math.max(0, rollAt + 0.04), dur: enter,
                     outAt: tOut + 0.03, outDur: exit, name: P.layer + " unit" });
  }
  if (label) {
    lb = CC.text(c, { text: label, size: ls, fill: tone.fill, role: "body", name: P.layer + " label" });
    CC.legible(c, lb, ls, tone, 0.8);
    CC.rise(c, lb, { parent: rig2, x: rowX(lm.advance), y: base + gapL + lcap, size: ls, ink: lm, t: Math.max(0, rollAt + 0.12), dur: enter,
                     outAt: tOut + 0.05, outDur: exit, name: P.layer + " label", pop: false });
    EC.set(c, lb, "transform/opacity", 72);
  }
  CC.measureDone(c);
  // the cut in lands on a camera move: the number settles from 104 % while it counts, then the slow push
  var s0 = 104, sL = 100 * CC.driftAt(D - land);
  EC.keys(c, rig, "transform/scale", [[0, [s0, s0]], [land, [100, 100]], [D, [sL, sL]]], ["out", "linear"]);
  CC.drift(c, rig2, 0, D, 100, 1.5);
  return { reels: ids, target: target, from: from, unit: un, label: lb, rig: rig, size: sz, rollAt: rollAt, landAt: land, outAt: tOut,
           width: Lx.w, grownWidth: Lx.w * grow, area: area, align: align };
}
