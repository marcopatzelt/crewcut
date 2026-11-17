/* @template particles_converge
 * @description Particles converge into a logo (an RGBA sequence that plays the converge, e.g. a Blender flake swirl
 *   rendered backwards), then the logo slides aside while a wordmark builds in letter by letter (opacity + offset
 *   cascade), and the frame keeps a slow push to the end.
 * @params {"comp": "Main", "plate": "", "plateFrames": 94, "skip": 0, "word": "Crewcut",
 *   "wordColor": "#0F6E5C", "wordSize": 170, "wordGap": 40, "logoW": 460, "font": "Manrope V5", "slideDelay": 0.08, "push": [0.0, 2.45, 104],
 *   "name": "Logo"}
 * @end */
function particles_converge(P) {
  var c = P.comp;
  var st = EC.nul(c, { name: P.name + " stage" });
  EC.set(c, st, "transform/position", [960, 540]);
  EC.keys(c, st, "transform/scale", [[P.push[0], [100, 100]], [P.push[1], [P.push[2], P.push[2]]]], "linear");
  // skip: leading frames of the plate left out (the widest part of the swirl is mostly outside the frame)
  var plateStart = -P.skip / 60;
  var pl = EC.footage(c, P.plate, { name: P.name + " converge", sequence: true, frameRate: 60, start: plateStart });
  EC.run("layer.setParent", { comp: c, layers: [pl], parent: st, compensate: false });
  EC.set(c, pl, "transform/position", [0, 0]);
  var endT = plateStart + P.plateFrames / 60;
  EC.trim(c, pl, 0, endT);
  // the lockup is centred: logo + gap + word (word width ~0.6 em per character)
  var wordW = P.word.length * P.wordSize * 0.6, total = P.logoW + P.wordGap + wordW, slide = total / 2 - P.logoW / 2;
  var slideAt = endT + P.slideDelay;
  // hold: the last frame (whole logo) as a still from the end of the converge; it carries the slide
  var last = P.plate.replace(/_(\d+)\.png$/, function (m, n) { var k = String(P.plateFrames); while (k.length < n.length) k = "0" + k; return "_" + k + ".png"; });
  var hold = EC.footage(c, last, { name: P.name + " hold" });
  EC.run("layer.setParent", { comp: c, layers: [hold], parent: st, compensate: false });
  EC.trim(c, hold, endT, undefined);
  EC.set(c, hold, "transform/position", [0, 0]);
  EC.keys(c, hold, "transform/position", [[slideAt, [0, 0]], [slideAt + 0.45, [-slide, 0]]], "expo");
  EC.sw(c, hold, "motionBlur", true);
  var wd = EC.text(c, { text: P.word, size: P.wordSize, fill: P.wordColor, font: P.font, style: "ExtraBold", justify: "left", name: P.name + " word" });
  EC.run("layer.setParent", { comp: c, layers: [wd], parent: st, compensate: false });
  EC.set(c, wd, "transform/position", [-slide + P.logoW / 2 + P.wordGap, P.wordSize * 0.36]);
  var an = EC.animator(c, wd, ["opacity", "position"]);
  EC.set(c, wd, an.path + "/properties/opacity", 0); EC.set(c, wd, an.path + "/properties/position", [60, 0]);
  EC.keys(c, wd, an.path + "/selectors/#1/start", [[slideAt + 0.12, 0], [slideAt + 0.6, 100]], "out");
  return { stage: st, plate: pl, hold: hold, word: wd };
}
