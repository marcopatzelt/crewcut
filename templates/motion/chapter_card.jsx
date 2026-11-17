/* @template chapter_card
 * @description A chapter opener caused by a motion: from one point a disc in the next chapter's ground colour
 *   grows over the frame with two thin rings running ahead of it and a short soft flash, then the chapter number
 *   (accent) and the title rise out of their baselines on the new ground. The camera pushes in slowly while it
 *   holds and pushes through at the end while the type sinks away.
 * @kind full
 * @formats ["landscape", "portrait", "stage"]
 * @version 1
 * @sounds [{"at": "in", "sound": "whoosh"}]
 * @params {"comp": "Main", "number": 2, "title": "Run it offline", "index": null, "point": [0.5, 0.5], "size": 140,
 *   "minSize": 96, "growAt": 0.0, "outAt": null, "layer": "Chapter"}
 * @end */
function chapter_card(P) {
  var c = P.comp, F = CC.frame(), u = F.u, D = F.duration, W = F.W, H = F.H, f1 = 1 / (F.fps || 25);
  var enter = CC.enterS(), exit = CC.exitS(), ink = CC.ink();
  var idx = P.index !== null && P.index !== undefined ? P.index : Math.max(0, (Number(P.number) || 1) - 1);
  var next = CC.pastel(idx), px = P.point[0] * W, py = P.point[1] * H;

  // the old ground (the pack's), then the next ground (a pastel with its own light, in a precomp) revealed by a disc
  // that grows from the point and covers the farthest corner
  CC.groundLayer(c);
  var NG = P.layer + " next ground";
  EC.comp({ name: NG, width: W, height: H, fps: EC.compItem(c) ? EC.compItem(c).frameRate : 60, duration: D, bg: next });
  // no pool in the ground's own hue: on a pastel ground it turned the whole frame one hue (hue check, image CI)
  CC.groundLayer(NG, { color: next, strength: 0.22, skip: idx, name: P.layer + " next" });
  var far = 0; var cs = [[0, 0], [W, 0], [0, H], [W, H]];
  for (var q = 0; q < 4; q++) far = Math.max(far, Math.sqrt(Math.pow(cs[q][0] - px, 2) + Math.pow(cs[q][1] - py, 2)));
  var dEnd = 2 * far * 1.04, t0 = P.growAt, tg = t0 + 0.3;
  var ngl = EC.precompLayer(c, NG, { name: NG });
  var disc = EC.shape(c, { kind: "ellipse", size: [dEnd, dEnd], fill: "#FFFFFF", name: P.layer + " disc" });
  EC.set(c, disc, "transform/position", [px, py]);
  EC.keys(c, disc, "transform/scale", [[t0, [3, 3]], [tg, [100, 100]]], [[20, 85]]);
  EC.sw(c, disc, "motionBlur", true);
  EC.matte(c, ngl, disc, "alpha");
  // two rings run ahead of the disc and thin out as they leave the frame
  for (var r = 0; r < 2; r++) {
    var ring = EC.shape(c, { kind: "ellipse", size: [dEnd, dEnd], stroke: CC.color(2 + r), strokeWidth: (r ? 4 : 6) * u,
                             fillOpacity: 0, name: P.layer + " ring " + (r + 1) });
    EC.set(c, ring, "transform/position", [px, py]);
    var tr = t0 + 0.02 * r;
    EC.keys(c, ring, "transform/scale", [[tr, [5, 5]], [tr + 0.34, [112 + 10 * r, 112 + 10 * r]]], [[20, 85]]);
    EC.keys(c, ring, "transform/opacity", [[tr, 100], [tr + 0.2, 90], [tr + 0.34, 0]], "linear");
    EC.sw(c, ring, "motionBlur", true);
    EC.trim(c, ring, 0, tr + 0.36);
  }
  var fl = EC.shape(c, { kind: "ellipse", size: [240 * u, 240 * u], fill: "#FFFFFF", name: P.layer + " flash" });
  EC.set(c, fl, "transform/position", [px, py]);
  EC.fx(c, fl, "Gaussian Blur", { blurriness: 60 * u });
  EC.keys(c, fl, "transform/opacity", [[t0, 55], [t0 + 0.08, 0]], "linear");
  EC.run("layer.setBlendMode", { comp: c, layers: [fl], mode: "Add" });
  EC.trim(c, fl, 0, t0 + 0.3);

  // type: the number (accent) over the title; the title wraps to two lines when it must
  var area = F.safe, margin = 40 * u, maxW = area.w - 2 * margin, size = P.size * u;
  var words = String(P.title).split(/\s+/), grow = CC.driftAt(D);
  function lines(sz) {
    var one = CC.measure(c, String(P.title), sz).advance;
    if (one * grow <= maxW || words.length < 2) return [String(P.title)];
    var best = null;
    for (var k = 1; k < words.length; k++) {
      var a = words.slice(0, k).join(" "), b = words.slice(k).join(" ");
      var w = Math.max(CC.measure(c, a, sz).advance, CC.measure(c, b, sz).advance);
      if (!best || w < best.w) best = { w: w, l: [a, b] };
    }
    return best.l;
  }
  var ls = lines(size), widest = 0;
  for (var i = 0; i < ls.length; i++) widest = Math.max(widest, CC.measure(c, ls[i], size).advance);
  var fit = CC.fit(size, widest * grow, maxW, P.minSize * u);
  if (fit !== size) { size = fit; ls = lines(size); }
  var num = (Number(P.number) < 10 ? "0" : "") + String(P.number), ns = 0.5 * size;
  var nm = CC.measure(c, num, ns), cap = -CC.measure(c, "H", size).top, ncap = -CC.measure(c, "H", ns).top;
  var lead = 1.06 * size, gap = 0.42 * size;
  var blockH = ncap + gap + cap + (ls.length - 1) * lead, cx = area.x + area.w / 2, cy = area.y + area.h / 2;
  var rig = CC.rig(c, P.layer + " rig", [cx, cy]);
  var tIn = tg - 0.08, tOut = P.outAt !== null && P.outAt !== undefined ? P.outAt : D - exit - f1;
  var top = -blockH / 2;
  var nId = CC.text(c, { text: num, size: ns, fill: CC.color(0), name: P.layer + " number" });
  CC.rise(c, nId, { parent: rig, x: -nm.advance / 2, y: top + ncap, size: ns, ink: nm, t: tIn, dur: enter,
                    outAt: tOut, outDur: exit, name: P.layer + " number" });
  var ids = [nId];
  for (var j = 0; j < ls.length; j++) {
    var m = CC.measure(c, ls[j], size);
    var tId = CC.text(c, { text: ls[j], size: size, fill: ink, name: P.layer + " title " + (j + 1) });
    CC.rise(c, tId, { parent: rig, x: -m.advance / 2, y: top + ncap + gap + cap + j * lead, size: size, ink: m,
                      t: tIn + 0.07 * (j + 1), dur: enter, outAt: tOut + 0.03 * (j + 1), outDur: exit, name: P.layer + " title " + (j + 1) });
    ids.push(tId);
  }
  CC.measureDone(c);
  // the camera: slow push in the hold, a push through at the end (carries the exit)
  var sEnd = 100 * CC.driftAt(tOut - tIn);
  EC.keys(c, rig, "transform/scale", [[tIn, [100, 100]], [tOut, [sEnd, sEnd]], [D, [sEnd * 1.08, sEnd * 1.08]]], ["linear", "expoIn"]);
  return { disc: disc, nextGround: NG, type: ids, rig: rig, ground: next, size: size, lines: ls, landed: tIn + 0.07 * ls.length + enter, outAt: tOut };
}
