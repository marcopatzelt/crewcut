/* @template keyword_pop
 * @description One to three words beside the speaker, on the free side at chest height. Each word rises out of
 *   its own baseline with motion blur and a small scale settle, the group pushes in slowly while it holds, and the
 *   words sink back through the baseline at the end. Words that fit stay on one line, otherwise one word per line.
 *   When the insert goes behind the person (CC_CTX.layer "behind"), the type is as large as behindMax at head
 *   height, where only the head covers it (behindAt "shoulders": 1.6 times larger, centred behind the shoulders,
 *   where the body covers most of a long word). With the channel's graphic system (brand.graphics) the accent word
 *   takes the highlight over video (the accent on a light ground), every word sits on an ink halo and a soft scrim
 *   darkens the free side.
 * @kind overlay
 * @formats ["landscape", "portrait", "stage"]
 * @version 1
 * @sounds [{"at": "in", "sound": "pop"}]
 * @params {"comp": "Main", "words": ["runs", "offline"], "accentWord": 1, "size": 140, "minSize": 96,
 *   "inAt": 0.0, "cueAt": null, "outAt": null, "stagger": 0.07, "align": "auto", "behindScale": 1.6, "behindMax": 300,
 *   "behindAt": "head", "layer": "Keyword"}
 * @end */
function keyword_pop(P) {
  var c = P.comp, F = CC.frame(), u = F.u;
  var words = [];
  for (var i = 0; i < P.words.length && words.length < 3; i++) if (String(P.words[i]).replace(/\s/g, "")) words.push(String(P.words[i]));
  if (!words.length) words = ["keyword"];
  var n = words.length, box = F.sideBox, margin = 28 * u, maxW = box.w - 2 * margin;

  // layout: one line when it fits at the wanted size, else one word per line; then fit the widest line
  function widths(sz) {
    var sp = CC.measure(c, " ", sz).advance, one = 0, each = [];
    for (var k = 0; k < n; k++) { var a = CC.measure(c, words[k], sz).advance; each.push(a); one += a + (k ? sp : 0); }
    return { one: one, each: each, space: sp };
  }
  var behind = F.layer === "behind";                 // composited under the person: bigger, centred behind the shoulders
  var size = (behind ? (P.behindAt === "head" ? P.behindMax : Math.min(P.size * P.behindScale, P.behindMax)) : P.size) * u, m = widths(size);
  var lines = [];
  if (m.one <= maxW) lines.push(words.slice(0)); else for (var w = 0; w < n; w++) lines.push([words[w]]);
  function widest(mm) {
    var best = 0, idx = 0;
    for (var l = 0; l < lines.length; l++) {
      var lw = 0; for (var q = 0; q < lines[l].length; q++) { lw += mm.each[idx] + (q ? mm.space : 0); idx++; }
      best = Math.max(best, lw);
    }
    return best;
  }
  // fit the widest line; when even minSize is too wide, go smaller (never under 64 px) rather than leave the side
  var fitted = CC.fit(size, widest(m), maxW, Math.min(P.minSize, 64) * u);
  if (fitted !== size) { size = fitted; m = widths(size); }
  var cap = -CC.measure(c, "H", size).top, lead = 1.04 * size;
  var blockH = (lines.length - 1) * lead + cap;

  // placement: toward the face on the free side (left-aligned on the right, right-aligned on the left)
  var align = P.align;
  if (align === "auto") align = F.side === "right" ? "left" : (F.side === "left" ? "right" : "center");
  var ax = F.anchor[0], ay = F.anchor[1];
  // behind the person: at the shoulders (the contract's anchor) or at head height, where only the head covers the word
  if (behind && P.behindAt === "head" && F.face) ay = CC.clamp(F.face.cy + 0.02 * F.H, F.safe.y + blockH, F.safe.y + F.safe.h - blockH);
  if (align === "left") ax = box.x + margin; else if (align === "right") ax = box.x + box.w - margin;
  var bw = widest(m), ox = align === "left" ? bw / 2 : (align === "right" ? -bw / 2 : 0);
  if (align === "center") ax = CC.clamp(ax, F.safe.x + margin + bw / 2, F.safe.x + F.safe.w - margin - bw / 2);
  var rig = CC.rig(c, P.layer + " rig", [ax + ox, ay]);        // the push grows from the middle of the block
  var tone = CC.tone({ x: ax + ox - bw / 2, y: ay - blockH / 2, w: bw, h: blockH + 0.25 * size });

  // timing: the last word is complete 1.5 frames before its cue
  var enter = CC.enterS(), exit = CC.exitS(), st = P.stagger, D = F.duration, f1 = 1 / (F.fps || 25);
  var tIn = P.inAt;
  if (P.cueAt !== null && P.cueAt !== undefined) tIn = Math.max(0, CC.landBy(P.cueAt) - enter - st * (n - 1));
  var tOut = P.outAt !== null && P.outAt !== undefined ? P.outAt : D - exit - 0.04 * (n - 1) - f1;

  var ids = [], idx = 0, firstBase = -blockH / 2 + cap;
  for (var L = 0; L < lines.length; L++) {
    var lw = 0;
    for (var a = 0; a < lines[L].length; a++) lw += m.each[idx + a] + (a ? m.space : 0);
    var x = align === "left" ? -bw / 2 : (align === "right" ? bw / 2 - lw : -lw / 2), y = firstBase + L * lead;
    for (var b = 0; b < lines[L].length; b++) {
      var word = lines[L][b], k2 = idx;
      var fill = k2 === P.accentWord ? CC.keyColor() : tone.fill;
      var id = CC.text(c, { text: word, size: size, fill: fill, name: P.layer + " " + word });
      CC.legible(c, id, size, tone);
      CC.rise(c, id, { parent: rig, x: x, y: y, size: size, ink: CC.measure(c, word, size), t: tIn + st * k2, dur: enter,
                       outAt: tOut + 0.04 * k2, outDur: exit, name: P.layer + " " + word });
      CC.halo(c, { parent: rig, text: word, size: size, x: x, y: y, t: tIn + st * k2, dur: enter,
                   outAt: tOut + 0.04 * k2, outDur: exit, name: P.layer + " " + word });
      ids.push(id);
      x += m.each[idx] + m.space;
      idx++;
    }
  }
  CC.measureDone(c);
  CC.scrim(c, F.side, tIn, enter, tOut, exit);
  CC.halosBack(c);
  CC.drift(c, rig, 0, D);
  return { words: ids, rig: rig, size: size, behind: behind, lines: lines.length, align: align, inAt: tIn,
           landed: tIn + enter + st * (n - 1), outAt: tOut, anchor: [ax, ay], side: F.side };
}
