/* @template card_grid_3d
 * @description Hero card springs in (scale spring, hue cycle, 3D wobble), then a masonry grid of cards (mixed
 *   aspect ratios) flies in from the camera side in tilted 3D with a stagger by distance, a hue flash that settles,
 *   motion blur, and a slow parallax drift of the whole grid. Optional pill button on the hero card that appears on
 *   hover. Cards are RGBA images (rounded corners baked in). Uses a two-node comp camera.
 * @params {"comp": "Main", "hero": "", "cards": [], "center": [960, 540], "colW": 330, "gap": 40, "cols": 7,
 *   "heroW": 330, "tHero": 0.0, "tGrid": 0.55, "stagger": 0.035, "fly": 0.5, "flyZ": -1600, "hueFlash": 150,
 *   "tilt": [24, -20, 6], "drift": [[0.0, [24, -20, 6]], [3.2, [20, -12, 4]]], "camZoom": [[0.0, 1.7], [0.45, 1.65], [1.35, 0.78], [3.2, 0.72]],
 *   "button": "Upload", "buttonColor": "#0F6E5C", "buttonAt": 1.9, "shadow": 30, "seed": 5, "duration": 3.2, "name": "Grid"}
 * @end */
function card_grid_3d(P) {
  var c = P.comp, rnd = EC.rng(P.seed);
  // camera: looks at the grid centre; zoom keys scale the distance (1 = hero fills about a third of the height)
  var D0 = 1500;
  var cam = EC.camera(c, { name: P.name + " camera", type: "twoNode", position: [P.center[0], P.center[1], -D0], poi: [P.center[0], P.center[1], 0] });
  var ck = []; for (var i = 0; i < P.camZoom.length; i++) ck.push([P.camZoom[i][0], [P.center[0], P.center[1], -D0 / P.camZoom[i][1]]]);
  EC.keys(c, cam, "transform/position", ck, "strong");
  // grid null: carries the tilt and the drift
  var g = EC.nul(c, { name: P.name + " null", threeD: true });
  EC.set(c, g, "transform/position", [P.center[0], P.center[1], 0]);
  var rx = [], ry = [], rz = [];
  for (var k = 0; k < P.drift.length; k++) { rx.push([P.drift[k][0], P.drift[k][1][0]]); ry.push([P.drift[k][0], P.drift[k][1][1]]); rz.push([P.drift[k][0], P.drift[k][1][2]]); }
  EC.keys(c, g, "transform/rotationX", rx, "smooth"); EC.keys(c, g, "transform/rotationY", ry, "smooth"); EC.keys(c, g, "transform/rotation", rz, "smooth");
  // masonry layout: columns around the hero (hero in the middle column, at the top of its stack)
  var colH = [], cols = P.cols, mid = Math.floor(cols / 2), step = P.colW + P.gap;
  for (var q = 0; q < cols; q++) colH.push(-760 + rnd() * 220);
  var layers = [], placed = [];
  function addCard(path, x, y, w, t0, isHero) {
    var id = EC.footage(c, path, { name: (isHero ? P.name + " hero" : P.name + " card " + layers.length), threeD: true });
    var d = EC.dims(c, id), s = 100 * w / ((d && d.width) || 640);
    EC.run("layer.setParent", { comp: c, layers: [id], parent: g, compensate: false });
    EC.set(c, id, "transform/scale", [s, s, s]);
    EC.sw(c, id, "motionBlur", true);
    if (P.shadow) EC.fx(c, id, "Drop Shadow", { opacity: P.shadow, distance: 16, softness: 40, direction: 170 });
    return { id: id, h: d ? d.height * s / 100 : w };
  }
  // hero
  var hero = addCard(P.hero, 0, 0, P.heroW, P.tHero, true);
  var hy = 0;
  EC.keys(c, hero.id, "transform/position", [[P.tHero, [0, hy, -300]], [P.tHero + 0.35, [0, hy, 0]]], "expo");
  var hs = 100 * P.heroW / ((EC.dims(c, hero.id) || {}).width || 640);
  EC.keys(c, hero.id, "transform/scale", [[P.tHero, [hs * 0.2, hs * 0.2, hs]], [P.tHero + 0.18, [hs * 1.12, hs * 0.9, hs]], [P.tHero + 0.32, [hs * 0.96, hs * 1.05, hs]], [P.tHero + 0.46, [hs, hs, hs]]], "smooth");
  EC.keys(c, hero.id, "transform/rotationY", [[P.tHero, -38], [P.tHero + 0.3, 10], [P.tHero + 0.55, -4], [P.tHero + 0.8, 0]], "smooth");
  EC.keys(c, hero.id, "transform/rotationX", [[P.tHero, 18], [P.tHero + 0.35, -6], [P.tHero + 0.7, 0]], "smooth");
  EC.fx(c, hero.id, "Hue/Saturation", {}, { hue: [[P.tHero, 200], [P.tHero + 0.12, 120], [P.tHero + 0.24, 50], [P.tHero + 0.4, 0]] }, "linear");
  layers.push(hero.id); placed.push([0, hy, P.heroW, hero.h]);
  colH[mid] = hy + hero.h / 2 + P.gap; var midTop = hy - hero.h / 2 - P.gap;
  // other cards: fill columns until each reaches +760
  var ci = 0, n = P.cards.length;
  var order = []; for (var col = 0; col < cols; col++) order.push(col);
  var guard = 0;
  while (guard++ < 200) {
    var best = -1, bh = 1e9;
    for (var o = 0; o < cols; o++) if (colH[o] < 800 && colH[o] < bh) { bh = colH[o]; best = o; }
    if (best < 0) break;
    var path = P.cards[ci % n]; ci++;
    var x = (best - mid) * step;
    var cd = addCard(path, x, 0, P.colW, 0, false);
    var y = colH[best] + cd.h / 2; colH[best] += cd.h + P.gap;
    var dist = Math.sqrt(x * x + y * y), t0 = P.tGrid + P.stagger * dist / step + rnd() * 0.05;
    EC.keys(c, cd.id, "transform/position", [[t0, [x * 1.25, y * 1.25, P.flyZ]], [t0 + P.fly, [x, y, 0]]], "expo");
    EC.keys(c, cd.id, "transform/opacity", [[t0, 0], [t0 + 0.06, 100]], "linear");
    if (P.hueFlash) EC.fx(c, cd.id, "Hue/Saturation", {}, { hue: [[t0, P.hueFlash], [t0 + 0.3, 0]] }, "out");
    EC.trim(c, cd.id, t0, undefined);
    layers.push(cd.id);
  }
  // cards above the hero in the middle column
  var up = midTop, guard2 = 0;
  while (up > -800 && guard2++ < 6) {
    var p2 = P.cards[ci % n]; ci++;
    var cd2 = addCard(p2, 0, 0, P.colW, 0, false);
    var y2 = up - cd2.h / 2; up -= cd2.h + P.gap;
    var t2 = P.tGrid + P.stagger * Math.abs(y2) / step;
    EC.keys(c, cd2.id, "transform/position", [[t2, [0, y2 * 1.25, P.flyZ]], [t2 + P.fly, [0, y2, 0]]], "expo");
    EC.keys(c, cd2.id, "transform/opacity", [[t2, 0], [t2 + 0.06, 100]], "linear");
    if (P.hueFlash) EC.fx(c, cd2.id, "Hue/Saturation", {}, { hue: [[t2, P.hueFlash], [t2 + 0.3, 0]] }, "out");
    EC.trim(c, cd2.id, t2, undefined);
    layers.push(cd2.id);
  }
  // pill button on the hero card (top right), appears with a pop at buttonAt
  var btn = null, lbl = null;
  if (P.button) {
    var bw = 26 + P.button.length * 15, bh2 = 46;
    btn = EC.shape(c, { kind: "rounded", size: [bw, bh2], fill: P.buttonColor, name: P.name + " button" });
    EC.set(c, btn, "contents/group/contents/rect/roundness", bh2 / 2);
    EC.sw(c, btn, "threeD", true);
    EC.run("layer.setParent", { comp: c, layers: [btn], parent: g, compensate: false });
    var bx = P.heroW / 2 - bw / 2 - 18, by = -hero.h / 2 + bh2 / 2 + 18;
    EC.set(c, btn, "transform/position", [bx, by, -2]);
    EC.keys(c, btn, "transform/scale", [[P.buttonAt, [40, 40, 100]], [P.buttonAt + 0.12, [108, 108, 100]], [P.buttonAt + 0.22, [100, 100, 100]]], "smooth");
    EC.keys(c, btn, "transform/opacity", [[P.buttonAt, 0], [P.buttonAt + 0.06, 100]], "linear");
    lbl = EC.text(c, { text: P.button, size: 24, fill: "#FFFFFF", font: "Manrope V5", style: "Bold", justify: "center", name: P.name + " button label" });
    EC.sw(c, lbl, "threeD", true);
    EC.run("layer.setParent", { comp: c, layers: [lbl], parent: g, compensate: false });
    EC.set(c, lbl, "transform/position", [bx, by + 8, -3]);
    EC.keys(c, lbl, "transform/opacity", [[P.buttonAt + 0.05, 0], [P.buttonAt + 0.12, 100]], "linear");
  }
  return { camera: cam, null: g, hero: hero.id, cards: layers.length, button: btn };
}
