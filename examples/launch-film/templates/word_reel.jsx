/* @template word_reel
 * @description Vertical word reel like a slot machine: a column of words scrolls up with motion blur and decelerates
 *   (expo) until the target word sits in the centre; words fade by distance from the centre; a selection box with
 *   corner handles hugs the centred word and resizes as words pass. Optional blurred backdrop image tilted in 3D.
 * @params {"comp": "Main", "words": ["Idea", "Script", "Record", "Cut", "Captions", "Thumbnail", "Title", "Shorts", "Schedule", "Upload", "Analyze", "Grow"],
 *   "target": "Upload", "startIndex": 1, "t0": 0.1, "t1": 1.25, "center": [960, 540], "lineH": 96, "size": 74,
 *   "color": "#FFFFFF", "box": "#34C3A4", "font": "Manrope V5", "style": "ExtraBold", "backdrop": "", "backdropBlur": 26,
 *   "bg": "#0C0E12", "backdropSat": -70, "baseline": 0, "name": "Reel"}
 * @end */
function word_reel(P) {
  var c = P.comp, n = P.words.length, cx = P.center[0], cy = P.center[1], Lh = P.lineH;
  var ti = P.words.indexOf(P.target); if (ti < 0) ti = n - 1;
  var bgl = EC.solid(c, { name: P.name + " ground", color: P.bg });
  EC.set(c, bgl, "transform/position", [cx, cy]);
  EC.fx(c, bgl, "Gradient Ramp", { start: [960, 300], startColor: EC.rgba("#1A2420"), end: [960, 1200], endColor: EC.rgba(P.bg), shape: 1 });
  if (P.backdrop) {
    var bd = EC.footage(c, P.backdrop, { name: P.name + " backdrop", threeD: true });
    var d = EC.dims(c, bd), s = 100 * 2300 / ((d && d.width) || 1920);
    EC.set(c, bd, "transform/scale", [s, s, s]);
    EC.keys(c, bd, "transform/position", [[0, [cx + 80, cy + 260, 300]], [P.t1 + 1.0, [cx - 60, cy + 200, 260]]], "linear");
    EC.set(c, bd, "transform/rotationX", 58); EC.set(c, bd, "transform/rotation", -14);
    EC.set(c, bd, "transform/opacity", 55);
    EC.fx(c, bd, "Gaussian Blur", { blurriness: P.backdropBlur, repeatEdge: true });
    EC.fx(c, bd, "Hue/Saturation", { saturation: P.backdropSat });     // keep the dark scene neutral, the words carry it
  }
  // the column hangs on a null that scrolls: offset(t) = (i_t) * lineH, eased to the target
  var col = EC.nul(c, { name: P.name + " column" });
  EC.keys(c, col, "transform/position", [[P.t0, [cx, cy - P.startIndex * Lh]], [P.t1, [cx, cy - ti * Lh]]], [[18, 96]]);
  EC.sw(c, col, "motionBlur", true);
  var ids = [];
  for (var i = 0; i < n; i++) {
    var id = EC.text(c, { text: P.words[i], size: P.size, fill: P.color, font: P.font, style: P.style, justify: "center", name: P.name + " " + P.words[i] });
    EC.run("layer.setParent", { comp: c, layers: [id], parent: col, compensate: false });
    EC.set(c, id, "transform/position", [0, i * Lh + P.size * 0.36 + P.baseline]);
    EC.sw(c, id, "motionBlur", true);
    // fade by distance from the centre line (expression keeps it right while the column moves)
    EC.expr(c, id, "transform/opacity", "var y = toComp([0, -" + (P.size * 0.36 + P.baseline) + ", 0])[1]; var d = Math.abs(y - " + cy + ") / " + Lh + "; Math.max(8, 100 - d * 32)");
    ids.push(id);
  }
  // selection box: width follows the word nearest the centre (glyph width ~0.58 em)
  var widths = []; for (var w = 0; w < n; w++) widths.push(Math.round(P.words[w].length * P.size * 0.58 + 44));
  var box = EC.shape(c, { kind: "rect", size: [300, Lh - 14], stroke: P.box, strokeWidth: 3, fillOpacity: 0, name: P.name + " box" });
  EC.set(c, box, "transform/position", [cx, cy]);
  EC.expr(c, box, "contents/group/contents/rect/size", "var W = " + JSON.stringify(widths) + "; var col = thisComp.layer(\"" + P.name + " column\"); var y = col.transform.position[1]; var i = Math.round((" + cy + " - y) / " + Lh + "); i = Math.max(0, Math.min(W.length - 1, i)); [W[i], " + (Lh - 14) + "]");
  var hs = [];
  for (var hk = 0; hk < 4; hk++) {
    var hd = EC.shape(c, { kind: "rect", size: [11, 11], fill: "#FFFFFF", stroke: P.box, strokeWidth: 2.5, name: P.name + " handle " + hk });
    var sx = hk % 2 ? 1 : -1, sy = hk < 2 ? -1 : 1;
    EC.expr(c, hd, "transform/position", "var W = " + JSON.stringify(widths) + "; var y = thisComp.layer(\"" + P.name + " column\").transform.position[1]; var i = Math.round((" + cy + " - y) / " + Lh + "); i = Math.max(0, Math.min(W.length - 1, i)); [" + cx + " + " + sx + " * W[i] / 2, " + cy + " + " + sy + " * " + ((Lh - 14) / 2) + "]");
    hs.push(hd);
  }
  return { column: col, words: ids, box: box, target: ti };
}
