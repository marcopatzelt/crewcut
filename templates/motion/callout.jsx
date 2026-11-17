/* @template callout
 * @description A hand-drawn stroke points at something in the picture: an optional word rises out of its
 *   baseline, a curved line in the accent colour draws itself from the word to the thing (tapered start, round
 *   end) and an arrow head snaps open where it arrives. Everything pushes in slowly while it holds; at the end the
 *   line retracts into the target, the head closes and the word sinks. It never starts on the face box.
 * @kind overlay
 * @formats ["landscape", "portrait", "stage"]
 * @version 1
 * @sounds [{"at": "drawAt", "sound": "whoosh"}]
 * @params {"comp": "Main", "target": [0.80, 0.62], "word": "this one", "wordAt": null, "size": 96, "minSize": 60,
 *   "bend": 0.28, "arrow": true, "drawAt": 0.0, "outAt": null, "layer": "Callout"}
 * @end */
function callout(P) {
  var c = P.comp, F = CC.frame(), u = F.u, D = F.duration, W = F.W, H = F.H, f1 = 1 / (F.fps || 25);
  var enter = CC.enterS(), exit = CC.exitS(), acc = CC.color(0), safe = F.safe;
  var T = [P.target[0] * W, P.target[1] * H];
  var size = P.size * u, word = String(P.word || "");
  var wm = word ? CC.measure(c, word, size) : null;
  if (wm && wm.advance > 0.42 * safe.w) { size = CC.fit(size, wm.advance, 0.42 * safe.w, P.minSize * u); wm = CC.measure(c, word, size); }
  var cap = -CC.measure(c, "H", size).top;

  // where the word sits: given, or above the target toward the middle of the frame, kept in safe and off the face
  var A;
  if (P.wordAt) A = [P.wordAt[0] * W, P.wordAt[1] * H];
  else {
    var dx = (T[0] > W * 0.55 ? -1 : 1) * 0.17 * W, dy = (T[1] > H * 0.45 ? -1 : 1) * 0.20 * H;
    A = [T[0] + dx, T[1] + dy];
  }
  var ww = wm ? wm.advance : 0;
  function clampA(a) { return [CC.clamp(a[0], safe.x + ww / 2 + 10 * u, safe.x + safe.w - ww / 2 - 10 * u), CC.clamp(a[1], safe.y + cap, safe.y + safe.h - 0.3 * size)]; }
  A = clampA(A);
  var wbox = function (a) { return { x: a[0] - ww / 2, y: a[1] - cap, w: ww, h: cap + 0.25 * size }; };
  if (word && !CC.clearOfFace(wbox(A))) { A = clampA([A[0], T[1] + (T[1] - A[1])]); }
  if (word && !CC.clearOfFace(wbox(A)) && F.face) {
    var f = F.face; A = clampA([T[0] > f.cx ? f.x + f.w + ww / 2 + 20 * u : f.x - ww / 2 - 20 * u, A[1]]);
  }

  // the line: from the word's edge toward the target, stopping short of it; bent to one side
  var start = word ? [A[0] + (T[0] > A[0] ? 1 : -1) * Math.min(ww / 2, Math.abs(T[0] - A[0]) * 0.5) * 0.9, A[1] + (T[1] > A[1] ? 0.35 * size : -cap - 0.15 * size)] : A;
  var vx = T[0] - start[0], vy = T[1] - start[1], len = Math.sqrt(vx * vx + vy * vy) || 1, ux = vx / len, uy = vy / len;
  var end = [T[0] - ux * 26 * u, T[1] - uy * 26 * u];
  var nx = -uy, ny = ux, bend = P.bend * len, side = (T[0] > A[0]) === (T[1] > A[1]) ? 1 : -1;
  var cpo = [start[0] + vx * 0.3 + nx * bend * side, start[1] + vy * 0.3 + ny * bend * side];
  var cpi = [end[0] - vx * 0.25 + nx * bend * side * 0.5, end[1] - vy * 0.25 + ny * bend * side * 0.5];
  var rig = CC.rig(c, P.layer + " rig", T);                                // the push centres on the thing it points at
  function rel(p) { return [p[0] - T[0], p[1] - T[1]]; }
  var lw = Math.max(4, 2 * (CC.brand().shape.line || 3)) * u, tone = CC.tone(wbox(A));
  var sk = CC.stroke(c, { pts: [rel(start), rel(end)], outT: [[cpo[0] - start[0], cpo[1] - start[1]], [0, 0]],
                          inT: [[0, 0], [cpi[0] - end[0], cpi[1] - end[1]]], color: acc, width: lw, name: P.layer + " line" });
  CC.child(c, sk.layer, rig);
  EC.set(c, sk.layer, "transform/position", [0, 0]);
  try {
    EC.set(c, sk.layer, "contents/group/contents/stroke/taper/startLength", 0.35 * len);
    EC.set(c, sk.layer, "contents/group/contents/stroke/taper/startWidth", 25);
  } catch (e) { /* older engines: an even line */ }
  CC.legible(c, sk.layer, size * 0.6, tone, 0.6);
  var t0 = P.drawAt + (word ? 0.12 : 0), tDraw = t0 + 0.5;
  var tOut = P.outAt !== null && P.outAt !== undefined ? P.outAt : D - exit - 0.06 - f1;
  EC.keys(c, sk.layer, sk.trim + "end", [[t0, 0], [tDraw, 100]], "expo");
  EC.keys(c, sk.layer, sk.trim + "start", [[tOut, 0], [tOut + exit, 100]], "expoIn");
  EC.sw(c, sk.layer, "motionBlur", true);

  // the arrow head: two short strokes along the end tangent, opening when the line arrives
  var head = null;
  if (P.arrow) {
    var hx = end[0] - cpi[0], hy = end[1] - cpi[1], hl = Math.sqrt(hx * hx + hy * hy) || 1, ang = Math.atan2(hy / hl, hx / hl);
    var hs = 30 * u, a1 = ang + Math.PI * 0.80, a2 = ang - Math.PI * 0.80;
    var hd = CC.stroke(c, { pts: [[Math.cos(a1) * hs, Math.sin(a1) * hs], [0, 0], [Math.cos(a2) * hs, Math.sin(a2) * hs]], color: acc,
                            width: lw, name: P.layer + " head" });
    try { EC.set(c, hd.layer, "contents/group/contents/stroke/join", 1); } catch (e2) { /* round join where known */ }
    CC.child(c, hd.layer, rig);
    EC.set(c, hd.layer, "transform/position", rel(end));
    var th = t0 + 0.16;
    EC.keys(c, hd.layer, "transform/scale", [[th, [0, 0]], [th + 0.22, [104, 104]], [th + 0.36, [100, 100]], [tOut, [100, 100]], [tOut + exit * 0.6, [0, 0]]],
            [CC.ease(), "smooth", "linear", "expoIn"]);
    CC.legible(c, hd.layer, size * 0.6, tone, 0.6);
    EC.sw(c, hd.layer, "motionBlur", true);
    head = hd.layer;
  }
  var wid = null;
  if (word) {
    wid = CC.text(c, { text: word, size: size, fill: tone.fill, name: P.layer + " word" });
    CC.legible(c, wid, size, tone);
    CC.rise(c, wid, { parent: rig, x: A[0] - T[0] - ww / 2, y: A[1] - T[1], size: size, ink: wm, t: P.drawAt, dur: enter,
                      outAt: tOut + 0.06, outDur: exit, name: P.layer + " word" });
  }
  CC.measureDone(c);
  CC.drift(c, rig, 0, D);
  return { line: sk.layer, head: head, word: wid, rig: rig, start: start, end: end, wordAt: A, size: size, outAt: tOut };
}
