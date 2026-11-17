/* @template glass_prompt_typing
 * @description Frosted-glass prompt bar over a scene. Inside the bar a blurred, brightened copy of the backdrop comp
 *   (it stays registered with the backdrop, only the matte moves), a white veil, a light rim, a white search field
 *   with an icon, a placeholder that hands over to typed text (typewriter with an accent gradient on the newest
 *   letters and a blinking caret), a search glyph, and a row of faint icons. All bar parts hang on one null that slides
 *   in (slide: [[t, [x, y], opacity], ...]) and is pushed in/out (pushKeys: [[t, scale%], ...]) around pushAnchor
 *   (offset from the bar centre, default: where the text starts).
 * @params {"comp": "Main", "backdrop": "Backdrop", "center": [960, 610], "size": [900, 210], "radius": 46,
 *   "slide": [[0.0, [700, 760], 0.0], [0.25, [960, 610], 100]], "pushKeys": [], "pushEase": "strong", "pushAnchor": null,
 *   "blur": 38, "brighten": 12, "veil": 16, "icon": "", "placeholder": "Describe your next video", "text": "",
 *   "clickAt": null, "typeStart": 1.0, "typeEnd": 2.2, "font": "Manrope V5", "textSize": 38, "fieldH": 96,
 *   "accent": "#2FB596", "textColor": "#15171C", "out": null, "name": "Bar"}
 * @end */
function glass_prompt_typing(P) {
  var c = P.comp, W = P.size[0], H = P.size[1], cx = P.center[0], cy = P.center[1];
  var fw = W - 56, fh = P.fieldH, fy = -H / 2 + 22 + fh / 2;
  var tx0 = -fw / 2 + 98;                                            // where the text starts (after the icon)
  var A = P.pushAnchor || [tx0 + 140, fy];
  var nul = EC.nul(c, { name: P.name + " null" });
  // origin of the null's layer space stays at the bar centre; scaling happens around A
  EC.set(c, nul, "transform/anchor", A);
  var pk = [], ok = [];
  for (var i = 0; i < P.slide.length; i++) { pk.push([P.slide[i][0], [P.slide[i][1][0] + A[0], P.slide[i][1][1] + A[1]]]); ok.push([P.slide[i][0], P.slide[i][2]]); }
  if (pk.length > 1) EC.keys(c, nul, "transform/position", pk, "expo"); else EC.set(c, nul, "transform/position", [cx + A[0], cy + A[1]]);
  if (P.pushKeys.length > 1) { var sk = []; for (var q = 0; q < P.pushKeys.length; q++) sk.push([P.pushKeys[q][0], [P.pushKeys[q][1], P.pushKeys[q][1]]]);
    EC.keys(c, nul, "transform/scale", sk, P.pushEase); }
  EC.sw(c, nul, "motionBlur", true);
  function part(id, dx, dy, base) {
    EC.run("layer.setParent", { comp: c, layers: [id], parent: nul, compensate: false });
    EC.set(c, id, "transform/position", [dx, dy]); EC.sw(c, id, "motionBlur", true);
    var b = base === undefined ? 100 : base, kk = [];
    for (var z = 0; z < ok.length; z++) kk.push([ok[z][0], ok[z][1] * b / 100]);
    if (kk.length > 1) EC.keys(c, id, "transform/opacity", kk, "linear"); else EC.set(c, id, "transform/opacity", b);
    return id;
  }
  function rr(name, w, h, r, fill, base, dx, dy, blur) {
    var o = EC.shape(c, { kind: "rounded", size: [w, h], fill: fill, name: P.name + " " + name });
    EC.set(c, o, "contents/group/contents/rect/roundness", r); if (blur) EC.fx(c, o, "Gaussian Blur", { blurriness: blur });
    return part(o, dx, dy, base);
  }
  var sh = rr("shadow", W, H, P.radius, "#000000", 20, 0, 16, 42);
  // frosted body: blurred copy of the backdrop, not parented (stays registered), matte = rounded rect on the null
  var body = EC.precompLayer(c, P.backdrop, { name: P.name + " glass" });
  EC.fx(c, body, "Gaussian Blur", { blurriness: P.blur, repeatEdge: true });
  EC.fx(c, body, "Brightness & Contrast", { brightness: P.brighten, contrast: -8 });
  var mt = rr("matte", W, H, P.radius, "#FFFFFF", 100, 0, 0);
  EC.run("layer.setTrackMatte", { comp: c, layer: body, matte: mt, kind: "alpha" });
  var veil = rr("veil", W, H, P.radius, "#FFFFFF", P.veil, 0, 0);
  var rim = EC.shape(c, { kind: "rounded", size: [W, H], stroke: "#FFFFFF", strokeWidth: 2.5, fillOpacity: 0, name: P.name + " rim" });
  EC.set(c, rim, "contents/group/contents/rect/roundness", P.radius); part(rim, 0, 0, 70);
  // search field
  rr("field shadow", fw, fh, fh / 2, "#000000", 12, 0, fy + 8, 16);
  var fld = rr("field", fw, fh, fh / 2, "#FFFFFF", 100, 0, fy);
  var ic = null;
  if (P.icon) { ic = EC.footage(c, P.icon, { name: P.name + " icon" }); var d = EC.dims(c, ic); var s = 100 * (fh * 0.56) / ((d && d.width) || 512);
    EC.set(c, ic, "transform/scale", [s, s]); part(ic, -fw / 2 + 54, fy); }
  // search glyph: ring + handle
  var gx = fw / 2 - 52;
  var ring = EC.shape(c, { kind: "ellipse", size: [fh * 0.32, fh * 0.32], stroke: P.textColor, strokeWidth: 4.5, fillOpacity: 0, name: P.name + " glyph ring" });
  part(ring, gx - 4, fy - 4);
  var hdl = EC.shape(c, { kind: "rounded", size: [4.5, fh * 0.17], fill: P.textColor, name: P.name + " glyph handle" });
  part(hdl, gx + fh * 0.13, fy + fh * 0.13); EC.set(c, hdl, "transform/rotation", -45);
  // placeholder, then typed text
  var ph = EC.text(c, { text: P.placeholder, size: P.textSize, fill: "#9AA1A9", font: P.font, style: "SemiBold", justify: "left", name: P.name + " placeholder" });
  part(ph, tx0, fy + P.textSize * 0.36, 100);
  var tx = null, caret = null;
  if (P.text) {
    if (P.clickAt !== null) EC.keys(c, ph, "transform/opacity", [[P.clickAt, 100], [P.clickAt + 0.08, 0]], "linear");
    tx = EC.text(c, { text: P.text, size: P.textSize, fill: P.textColor, font: P.font, style: "Bold", justify: "left", name: P.name + " text" });
    part(tx, tx0, fy + P.textSize * 0.36, 100);
    var on = EC.animator(c, tx, ["opacity"]); EC.set(c, tx, on.path + "/properties/opacity", 0);
    EC.keys(c, tx, on.path + "/selectors/#1/start", [[P.typeStart, 0], [P.typeEnd, 100]], "linear");
    var hi = EC.animator(c, tx, ["fillColor"]); EC.set(c, tx, hi.path + "/properties/fillColor", EC.rgba(P.accent));
    EC.keys(c, tx, hi.path + "/selectors/#1/start", [[P.typeStart, -16], [P.typeEnd, 84], [P.typeEnd + 0.3, 100]], "linear");
    EC.keys(c, tx, hi.path + "/selectors/#1/end", [[P.typeStart, 0], [P.typeEnd, 100]], "linear");
    // caret: follows the typing front (glyph widths ~0.56 em), blinks after typing
    var chars = P.text.length, adv = P.textSize * 0.53 * chars;
    caret = EC.shape(c, { kind: "rect", size: [3, P.textSize * 1.1], fill: P.accent, name: P.name + " caret" });
    part(caret, tx0 - 4, fy, 100);
    EC.keys(c, caret, "transform/position", [[P.typeStart, [tx0 - 4, fy]], [P.typeEnd, [tx0 + adv + 4, fy]]], "linear");
    EC.expr(c, caret, "transform/opacity", "var on = time < " + (P.clickAt === null ? P.typeStart : P.clickAt) + " ? 0 : (time < " + P.typeEnd + " ? 100 : (Math.floor((time - " + P.typeEnd + ") * 2) % 2 ? 0 : 100)); on");
  }
  // faint icon row in the lower glass
  var row = [], gap = (W - 160) / 5;
  for (var k = 0; k < 6; k++) {
    var o = EC.shape(c, { kind: k % 2 ? "rounded" : "ellipse", size: [26, 26], stroke: "#FFFFFF", strokeWidth: 3, fillOpacity: 0, name: P.name + " sym " + k });
    part(o, -W / 2 + 80 + k * gap, H / 2 - 34, 40); row.push(o);
  }
  return { null: nul, glass: body, matte: mt, text: tx, placeholder: ph, field: fld, caret: caret, anchor: A, fieldY: fy, textX: tx0, glyphX: gx };
}
