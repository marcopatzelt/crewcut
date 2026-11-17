/* @template quote
 * @description A quote set large and dim (35 %), line by line out of their baselines; a light runs along the key
 *   words and brings them to full strength while a stroke in the accent colour draws itself under them; the source
 *   rises below. The camera pushes in slowly while it holds; at the end the stroke retracts and the lines sink.
 * @kind full
 * @formats ["landscape", "portrait", "stage"]
 * @version 1
 * @sounds [{"at": "lightAt", "sound": "whoosh"}]
 * @params {"comp": "Main", "text": "Most of the work is cutting what you already said twice.",
 *   "key": "cutting what you already said twice", "source": "From the comments", "size": 84, "minSize": 56,
 *   "dim": 35, "lightAt": 0.9, "lightS": 0.05, "outAt": null, "mark": true, "layer": "Quote"}
 * @end */
function quote(P) {
  var c = P.comp, F = CC.frame(), u = F.u, D = F.duration, f1 = 1 / (F.fps || 25);
  var enter = CC.enterS(), exit = CC.exitS(), ink = CC.ink(), acc = CC.color(0);
  CC.groundLayer(c);
  var area = F.safe, maxW = Math.min(area.w, F.format === "landscape" ? 0.74 * F.W : area.w) - 80 * u, grow = CC.driftAt(D);
  var text = String(P.text), words = text.split(/\s+/), size = P.size * u;
  // greedy wrap by measured words; shrink until it fits in 4 lines
  function wrap(sz) {
    var out = [], cur = "", cw = 0, sp = CC.measure(c, " ", sz).advance;
    for (var i = 0; i < words.length; i++) {
      var w = CC.measure(c, words[i], sz).advance;
      if (cur && (cw + sp + w) * grow > maxW) { out.push(cur); cur = words[i]; cw = w; } else { cw += (cur ? sp : 0) + w; cur = cur ? cur + " " + words[i] : words[i]; }
    }
    if (cur) out.push(cur);
    return out;
  }
  var lines = wrap(size);
  while (lines.length > 4 && size > P.minSize * u) { size = Math.max(P.minSize * u, size * 0.92); lines = wrap(size); }
  var lead = 1.22 * size, cap = -CC.measure(c, "H", size).top;
  var ss = Math.max(40 * u, 0.52 * size), scap = -CC.measure(c, "H", ss, "body").top;
  var blockH = cap + (lines.length - 1) * lead + (P.source ? 0.9 * size + scap : 0);
  var widest = 0; for (var l = 0; l < lines.length; l++) widest = Math.max(widest, CC.measure(c, lines[l], size).advance);
  var cx = area.x + area.w / 2, cy = area.y + area.h / 2;
  var rig = CC.rig(c, P.layer + " rig", [cx, cy]);
  var x0 = -widest / 2, y0 = -blockH / 2 + cap;
  var tOut = P.outAt !== null && P.outAt !== undefined ? P.outAt : D - exit - f1;

  // where the key words are: character range [k0, k1) of the whole text, mapped onto the lines
  var k0 = P.key ? text.indexOf(P.key) : 0, k1 = P.key && k0 >= 0 ? k0 + P.key.length : text.length;
  if (k0 < 0) { k0 = 0; k1 = text.length; }
  var pos = 0, t = P.lightAt, ids = [], strokes = [];
  for (var li = 0; li < lines.length; li++) {
    var s = lines[li], a = text.indexOf(s, pos), yl = y0 + li * lead;
    pos = a + s.length;
    var lo = Math.max(0, k0 - a), hi = Math.min(s.length, k1 - a);
    var parts = hi > lo ? [[0, lo, false], [lo, hi, true], [hi, s.length, false]] : [[0, s.length, false]];
    var tIn = 0.08 * li;
    for (var pi = 0; pi < parts.length; pi++) {
      var p = parts[pi], str = s.substring(p[0], p[1]);
      if (!str.replace(/\s/g, "")) continue;
      var off = p[0] ? CC.measure(c, s.substring(0, p[0]), size).advance : 0, m = CC.measure(c, str, size);
      var id = CC.text(c, { text: str, size: size, fill: ink, name: P.layer + " " + li + "." + pi });
      CC.rise(c, id, { parent: rig, x: x0 + off, y: yl, size: size, ink: m, t: tIn, dur: enter, outAt: tOut + 0.03 * li,
                       outDur: exit, name: P.layer + " " + li + "." + pi, pop: false });
      var dim = EC.animator(c, id, ["opacity"]);
      EC.set(c, id, dim.path + "/properties/opacity", P.dim);
      if (p[2]) {
        // the light run: the dim range starts behind the front, letter by letter; a short bright window rides on it
        var n = str.length, t1 = t + P.lightS * n;
        EC.keys(c, id, dim.path + "/selectors/#1/start", [[t, 0], [t1, 100]], "linear");
        var lit = EC.animator(c, id, ["fillColor"]);
        EC.set(c, id, lit.path + "/properties/fillColor", EC.rgba(acc));
        var win = 300 / Math.max(3, n);
        EC.keys(c, id, lit.path + "/selectors/#1/start", [[t, -win], [t1, 100 - win], [t1 + 0.3, 100]], "linear");
        EC.keys(c, id, lit.path + "/selectors/#1/end", [[t, 0], [t1, 100]], "linear");
        // the stroke under the key words follows the light
        var sk = CC.stroke(c, { pts: [[x0 + off + m.left, 0], [x0 + off + m.left + m.width, 0]], color: acc,
                                width: Math.max(4, 1.5 * (CC.brand().shape.line || 3)) * u, name: P.layer + " stroke " + li });
        CC.child(c, sk.layer, rig);
        EC.set(c, sk.layer, "transform/position", [0, yl + 0.2 * size]);
        EC.keys(c, sk.layer, sk.trim + "end", [[t, 0], [t1, 100]], [[30, 80]]);
        EC.keys(c, sk.layer, sk.trim + "start", [[tOut - 0.04, 0], [tOut - 0.04 + exit, 100]], "expoIn");
        EC.sw(c, sk.layer, "motionBlur", true);
        strokes.push(sk.layer);
        t = t1;
      }
      ids.push(id);
    }
  }
  // the opening mark hangs left of the first line, in the second palette colour
  if (P.mark) {
    var mk = "“", ms = 2.1 * size, mm = CC.measure(c, mk, ms);
    var mId = CC.text(c, { text: mk, size: ms, fill: CC.color(1), name: P.layer + " mark" });
    CC.rise(c, mId, { parent: rig, x: x0 - mm.advance - 0.14 * size, y: y0 + 0.62 * ms - cap, size: ms, ink: mm, t: 0, dur: enter,
                      outAt: tOut, outDur: exit, name: P.layer + " mark" });
    EC.set(c, mId, "transform/opacity", 80);
  }
  var src = null;
  if (P.source) {
    var sm = CC.measure(c, String(P.source), ss, "body");
    src = CC.text(c, { text: String(P.source), size: ss, fill: ink, role: "body", name: P.layer + " source" });
    CC.rise(c, src, { parent: rig, x: x0, y: y0 + (lines.length - 1) * lead + 0.9 * size + scap, size: ss, ink: sm,
                      t: Math.max(0.4, t - 0.2), dur: enter, outAt: tOut + 0.06, outDur: exit, name: P.layer + " source", pop: false });
    EC.set(c, src, "transform/opacity", 70);
  }
  CC.measureDone(c);
  // the cut in lands on a camera move: the quote settles from 104 % into the hold, then the slow push
  var tS = Math.min(1.0, P.lightAt), sE = 100 * CC.driftAt(D - tS);
  EC.keys(c, rig, "transform/scale", [[0, [104, 104]], [tS, [100, 100]], [D, [sE, sE]]], ["out", "linear"]);
  return { lines: lines, parts: ids, strokes: strokes, source: src, size: size, lightAt: P.lightAt, lit: t, outAt: tOut };
}
