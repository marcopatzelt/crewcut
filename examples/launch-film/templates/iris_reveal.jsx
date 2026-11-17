/* @template iris_reveal
 * @description A circular window opens from a point into the next scene. The scene is a footage file/sequence (plate)
 *   or a comp (plateComp). Diameter keys are linear (a fly-through, not a fade): diameter: [[t, px], ...]. The matte edge
 *   is soft (feather), a light rim rides on the edge and fades, the plate arrives slightly too big and soft
 *   (plateScale / plateBlur keys, strong ease-out).
 * @params {"comp": "Main", "plate": "", "plateComp": null, "sequence": false, "frameRate": 60, "plateStart": 0,
 *   "center": [960, 540], "diameter": [[2.02, 0], [2.04, 400], [2.07, 1000], [2.10, 1900], [2.14, 2400]],
 *   "feather": 45, "rim": true, "rimWidth": 30, "rimBlur": 40, "rimOpacity": 70, "rimFrames": 8,
 *   "plateScale": [[2.04, 118], [2.34, 100]], "plateBlur": [[2.04, 12], [2.34, 0]], "fit": [1920, 1080], "fps": 60,
 *   "out": null, "name": "Iris"}
 * @end */
function iris_reveal(P) {
  var c = P.comp, f = 1 / P.fps, t0 = P.diameter[0][0];
  var pl = P.plateComp ? EC.precompLayer(c, P.plateComp, { name: P.name + " plate" })
                       : EC.footage(c, P.plate, { name: P.name + " plate", sequence: P.sequence, frameRate: P.frameRate, start: P.plateStart });
  var d = EC.dims(c, pl), fit = 100;
  if (d && d.width) fit = 100 * Math.max(P.fit[0] / d.width, P.fit[1] / d.height);
  EC.set(c, pl, "transform/position", [P.fit[0] / 2, P.fit[1] / 2]);
  var sk = []; for (var i = 0; i < P.plateScale.length; i++) { var v = fit * P.plateScale[i][1] / 100; sk.push([P.plateScale[i][0], [v, v]]); }
  if (sk.length > 1) EC.keys(c, pl, "transform/scale", sk, "expo"); else EC.set(c, pl, "transform/scale", [fit, fit]);
  if (P.plateBlur.length > 1) EC.fx(c, pl, "Gaussian Blur", {}, { blurriness: P.plateBlur }, "expo");
  var D = 2400;
  var m = EC.shape(c, { kind: "ellipse", size: [D, D], fill: "#FFFFFF", name: P.name + " matte" });
  EC.set(c, m, "transform/position", P.center);
  var mk = []; for (var j = 0; j < P.diameter.length; j++) { var s = Math.max(0.01, 100 * P.diameter[j][1] / D); mk.push([P.diameter[j][0], [s, s]]); }
  EC.keys(c, m, "transform/scale", mk, "linear");
  if (P.feather > 0) EC.fx(c, m, "Gaussian Blur", { blurriness: P.feather });
  EC.run("layer.setTrackMatte", { comp: c, layer: pl, matte: m, kind: "alpha" });
  var rim = null;
  if (P.rim) {
    rim = EC.shape(c, { kind: "ellipse", size: [D, D], stroke: "#FFFFFF", strokeWidth: P.rimWidth, fillOpacity: 0, name: P.name + " rim" });
    EC.set(c, rim, "transform/position", P.center);
    EC.keys(c, rim, "transform/scale", mk, "linear");
    EC.keys(c, rim, "transform/opacity", [[t0, 0], [t0 + f, P.rimOpacity], [t0 + (P.rimFrames + 1) * f, 0]], "linear");
    EC.fx(c, rim, "Gaussian Blur", { blurriness: P.rimBlur });
    EC.run("layer.setBlendMode", { comp: c, layers: [rim], mode: "Add" });
    EC.trim(c, rim, t0, t0 + (P.rimFrames + 2) * f);
  }
  if (P.out !== null) { EC.trim(c, pl, t0, P.out); EC.trim(c, m, t0, P.out); }
  else { EC.trim(c, pl, t0 - f, undefined); EC.trim(c, m, t0 - f, undefined); }
  return { plate: pl, matte: m, rim: rim };
}
