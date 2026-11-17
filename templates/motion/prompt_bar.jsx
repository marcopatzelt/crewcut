/* @template prompt_bar
 * @description "What I asked": the speaker's own picture blurs and calms, a frosted glass bar (the one allowed
 *   plate: it shows the picture through it) rises in, the prompt is typed into it with a caret in the accent
 *   colour, the camera pushes in on the text and pulls back, the bar drops away and the picture clears. The first
 *   and the last frame equal the speaker frame, so the cut in and out is invisible. Without a backdrop the bar sits
 *   on the pack ground.
 * @kind full
 * @formats ["landscape", "portrait", "stage"]
 * @version 1
 * @sounds [{"at": "typeAt", "sound": "typing"}]
 * @params {"comp": "Main", "text": "Cut my 40 minute recording into a 6 minute video", "size": 54, "minSize": 42,
 *   "maxLines": 3, "typeAt": 0.7, "charS": 0.045, "typeEnd": null, "push": 1.35, "backdropBlur": 26, "glassBlur": 44,
 *   "veil": 46, "outAt": null, "layer": "Prompt"}
 * @end */
function prompt_bar(P) {
  var c = P.comp, F = CC.frame(), u = F.u, D = F.duration, W = F.W, H = F.H, f1 = 1 / (F.fps || 25);
  var fps = EC.compItem(c) ? EC.compItem(c).frameRate : 60;
  var k = CC.ctx(), enter = CC.enterS(), exit = CC.exitS(), ink = CC.ink();

  // ── the backdrop comp: the speaker piece (footage, filling the frame) or the pack ground ──
  var BD = P.layer + " backdrop", ST = P.layer + " stage";
  EC.comp({ name: BD, width: W, height: H, fps: fps, duration: D, bg: CC.ground() });
  if (k.backdrop) {
    var fl = EC.footage(BD, k.backdrop, { name: P.layer + " picture" });
    var dm = EC.dims(BD, fl), sc = 100 * Math.max(W / ((dm && dm.width) || W), H / ((dm && dm.height) || H));
    EC.set(BD, fl, "transform/position", [W / 2, H / 2]);
    EC.set(BD, fl, "transform/scale", [sc, sc]);
  } else {
    CC.groundLayer(BD);
  }

  // ── the stage comp: blurred picture, glass bar, typed text, caret ──
  EC.comp({ name: ST, width: W, height: H, fps: fps, duration: D, bg: CC.ground() });
  var bd = EC.precompLayer(ST, BD, { name: P.layer + " picture blur" });
  var bIn = 0.05, bOut = D - 0.42;
  var tOut = P.outAt !== null && P.outAt !== undefined ? P.outAt : D - exit - 0.2;
  bOut = Math.max(tOut, bOut);
  EC.fx(ST, bd, "Gaussian Blur", { repeatEdge: true }, { blurriness: [[bIn, 0], [bIn + 0.45, P.backdropBlur * u], [bOut, P.backdropBlur * u], [D - f1, 0]] }, ["out", "linear", "smooth"]);
  EC.fx(ST, bd, "Hue/Saturation", {}, { saturation: [[bIn, 0], [bIn + 0.45, -28], [bOut, -28], [D - f1, 0]] }, ["out", "linear", "smooth"]);
  EC.fx(ST, bd, "Brightness & Contrast", {}, { brightness: [[bIn, 0], [bIn + 0.45, -6], [bOut, -6], [D - f1, 0]] }, ["out", "linear", "smooth"]);

  // text layout: greedy wrap by measured word widths into at most maxLines lines inside the safe width
  var safe = F.safe, padX = 0.62 * P.size * u, padY = 0.56 * P.size * u;
  var maxBar = F.format === "landscape" ? Math.min(safe.w, 0.62 * W) : 0.9 * safe.w, maxText = maxBar - 2 * padX;
  var size = P.size * u, words = String(P.text).split(/\s+/), lines;
  function wrap(sz) {
    var out = [], cur = "", sp = CC.measure(ST, " ", sz, "body").advance, cw = 0;
    for (var i = 0; i < words.length; i++) {
      var w = CC.measure(ST, words[i], sz, "body").advance;
      if (cur && cw + sp + w > maxText) { out.push(cur); cur = words[i]; cw = w; } else { cw += (cur ? sp : 0) + w; cur = cur ? cur + " " + words[i] : words[i]; }
    }
    if (cur) out.push(cur);
    return out;
  }
  // balanced lines: as many lines as the greedy wrap needs, the words split so the longest line is as short as can be
  function balance(sz, n) {
    if (n < 2) return [words.join(" ")];
    var adv = function (a, b) { return CC.measure(ST, words.slice(a, b).join(" "), sz, "body").advance; };
    var best = null, nw = words.length;
    if (n === 2) {
      for (var i = 1; i < nw; i++) { var w2 = Math.max(adv(0, i), adv(i, nw)); if (!best || w2 < best.w) best = { w: w2, at: [i] }; }
    } else {
      for (var a = 1; a < nw - 1; a++) for (var b = a + 1; b < nw; b++) {
        var w3 = Math.max(adv(0, a), adv(a, b), adv(b, nw)); if (!best || w3 < best.w) best = { w: w3, at: [a, b] };
      }
    }
    if (!best) return wrap(sz);
    var out = [], prev = 0;
    for (var k = 0; k < best.at.length; k++) { out.push(words.slice(prev, best.at[k]).join(" ")); prev = best.at[k]; }
    out.push(words.slice(prev).join(" "));
    return out;
  }
  lines = wrap(size);
  while (lines.length > P.maxLines && size > P.minSize * u) { size = Math.max(P.minSize * u, size * 0.92); lines = wrap(size); }
  if (lines.length > 1 && lines.length <= 3) lines = balance(size, lines.length);
  var lineH = 1.32 * size, cap = -CC.measure(ST, "H", size, "body").top;
  var widest = 0; for (var l = 0; l < lines.length; l++) widest = Math.max(widest, CC.measure(ST, lines[l], size, "body").advance);
  var barW = Math.min(maxBar, Math.max(0.55 * maxBar, widest + 2 * padX + 0.5 * size)), barH = (lines.length - 1) * lineH + cap + 2 * padY;
  var cx = safe.x + safe.w / 2, cy = F.format === "stage" ? H * 0.5 : H * 0.58;
  var rad = Math.min(barH / 2, 34 * u);

  // the bar rig: rises 5 % of the height with a small scale settle; everything of the bar hangs on it
  var bar = CC.rig(ST, P.layer + " bar", [cx, cy]);
  var rise = 0.05 * H, tb = 0.18;
  EC.keys(ST, bar, "transform/position", [[tb, [cx, cy + rise]], [tb + enter, [cx, cy]], [tOut, [cx, cy]], [tOut + exit, [cx, cy + rise * 0.8]]],
          [CC.ease(), "linear", "expoIn"]);
  EC.keys(ST, bar, "transform/scale", [[tb, [96, 96]], [tb + enter * 0.7, [101.5, 101.5]], [tb + enter * 1.3, [100, 100]], [tOut, [100, 100]], [tOut + exit, [97, 97]]],
          ["out", "smooth", "linear", "expoIn"]);
  EC.sw(ST, bar, "motionBlur", true);
  var opK = [[tb, 0], [tb + 0.14, 100], [tOut + exit * 0.4, 100], [tOut + exit, 0]];
  function part(id, dx, dy, op) {
    CC.child(ST, id, bar); EC.set(ST, id, "transform/position", [dx, dy]); EC.sw(ST, id, "motionBlur", true);
    var kk = []; for (var z = 0; z < opK.length; z++) kk.push([opK[z][0], opK[z][1] * op / 100]);
    EC.keys(ST, id, "transform/opacity", kk, "linear");
    return id;
  }
  var veilCol = CC.mix(CC.brand().colors.paper || "#FFFFFF", CC.ground(), 0.15);
  var gl = CC.glass(ST, { parent: bar, source: BD, w: barW, h: barH, radius: rad, blur: P.glassBlur, veil: P.veil, veilColor: veilCol, fade: opK, name: P.layer + " glass" });
  if (!gl) ink = CC.ink();                                                  // the pack turned the glass off: type on the picture

  // typing: one text layer per line, characters appear in order; the caret follows the front, then blinks
  var nChars = 0; for (var q = 0; q < lines.length; q++) nChars += lines[q].length;
  var typeAt = P.typeAt, cs = P.charS;
  if (P.typeEnd !== null && P.typeEnd !== undefined) cs = Math.max(0.02, (P.typeEnd - typeAt) / Math.max(1, nChars));
  var typeEnd = typeAt + cs * nChars;
  var x0 = -barW / 2 + padX, y0 = -barH / 2 + padY + cap, caretK = [], caretY = [], acc = CC.color(0), t = typeAt, ids = [];
  for (var li = 0; li < lines.length; li++) {
    var s = lines[li], n = s.length, yl = y0 + li * lineH, t1 = t + cs * n;
    var tx = CC.text(ST, { text: s, size: size, fill: ink, role: "body", name: P.layer + " line " + (li + 1) });
    part(tx, x0, yl, 100);
    var on = EC.animator(ST, tx, ["opacity"]);
    EC.set(ST, tx, on.path + "/properties/opacity", 0);
    EC.keys(ST, tx, on.path + "/selectors/#1/start", [[t, 0], [t1, 100]], "linear");
    var hi = EC.animator(ST, tx, ["fillColor"]);
    EC.set(ST, tx, hi.path + "/properties/fillColor", EC.rgba(acc));
    var win = 300 / Math.max(3, n);                                           // the newest ~3 letters in the accent
    EC.keys(ST, tx, hi.path + "/selectors/#1/start", [[t, -win], [t1, 100 - win], [t1 + 0.25, 100]], "linear");
    EC.keys(ST, tx, hi.path + "/selectors/#1/end", [[t, 0], [t1, 100]], "linear");
    for (var ch = 0; ch <= n; ch++) {
      var adv = ch ? CC.measure(ST, s.substring(0, ch), size, "body").advance : 0;
      caretK.push([t + cs * ch, [x0 + adv + 0.06 * size, yl - cap / 2]]);
    }
    ids.push(tx);
    t = t1;
  }
  var caret = EC.shape(ST, { kind: "rect", size: [Math.max(3, 0.06 * size), cap * 1.45], fill: acc, name: P.layer + " caret" });
  CC.child(ST, caret, bar);
  EC.set(ST, caret, "transform/position", caretK[0][1]);
  EC.hold(ST, caret, "transform/position", caretK);
  EC.expr(ST, caret, "transform/opacity", "var a=" + (typeAt - 0.3) + ",b=" + typeEnd + ",o=" + tOut + ";" +
          "time<" + (tb + 0.1) + "||time>o+0.05?0:(time<a?100:(time<b?100:(Math.floor((time-b)*2.2)%2?0:100)))");

  // ── Main: the stage, pushed in on the text and pulled back; motion blur only while the camera moves ──
  // the push may not carry the bar out of the frame (3 % margin on each side)
  var maxPush = Math.max(1, Math.min(P.push, (cx - 0.03 * W) / (barW / 2), (0.97 * W - cx) / (barW / 2)));
  var pc = [cx, cy];                                                          // the push centres on the bar
  var pIn0 = typeAt + 0.05, pIn1 = Math.min(typeEnd + 0.3, tOut - 0.9), pOut0 = Math.max(pIn1 + 0.3, tOut - 0.62), pOut1 = tOut - 0.05;
  var hold = maxPush * 100 * CC.driftAt(pOut0 - pIn1, 1.5);
  function stage(name, a, b, mb) {
    var id = EC.precompLayer(c, ST, { name: name });
    EC.set(c, id, "transform/anchor", pc);
    EC.set(c, id, "transform/position", pc);
    EC.keys(c, id, "transform/scale", [[pIn0, [100, 100]], [pIn1, [maxPush * 100, maxPush * 100]], [pOut0, [hold, hold]], [pOut1, [100, 100]]],
            ["smooth", "linear", "smooth"]);
    if (mb) EC.sw(c, id, "motionBlur", true);
    EC.trim(c, id, a, b);
    return id;
  }
  // three spans: still, moving (blur), holding, moving (blur), after
  var s1 = stage(P.layer + " stage a", 0, pIn0, false), s2 = stage(P.layer + " stage push", pIn0, pIn1, true);
  var s3 = stage(P.layer + " stage hold", pIn1, pOut0, false), s4 = stage(P.layer + " stage pull", pOut0, pOut1, true);
  var s5 = stage(P.layer + " stage b", pOut1, D, false);
  CC.measureDone(ST);
  return { stage: ST, backdrop: BD, bar: bar, lines: lines, size: size, barSize: [barW, barH], push: maxPush,
           typeAt: typeAt, typeEnd: typeEnd, outAt: tOut, layers: [s1, s2, s3, s4, s5] };
}
