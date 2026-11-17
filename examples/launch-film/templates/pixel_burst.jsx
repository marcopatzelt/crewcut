/* @template pixel_burst
 * @description The clicked icon breaks into a grid of small squares that fly outward with motion blur, with a
 *   short additive flash. Shatter (Squares) on a full-frame precomp of the icon; the layer starts at t, so the
 *   simulation's time 0 is the click.
 * @params {"comp": "Main", "icon": "", "center": [960, 540], "size": 112, "t": 1.0, "dur": 0.45, "repetitions": 90,
 *   "strength": 40, "radius": 0.08, "depth": 0.02, "forceDepth": -0.03, "randomness": 0.7, "rotationSpeed": 0.12, "tint": ["#0B5A4B", "#3CCFAE"], "fade": 0.32, "flash": true, "flashColor": "#FFFFFF",
 *   "flashSize": 220, "flashOpacity": 70, "compSize": [1920, 1080], "fps": 60, "name": "Pixels"}
 * @end */
function pixel_burst(P) {
  var c = P.comp, plate = P.name + " plate";
  EC.comp({ name: plate, width: P.compSize[0], height: P.compSize[1], fps: P.fps, duration: P.t + P.dur + 1, motionBlur: false });
  var ic = EC.footage(plate, P.icon, { name: "icon" });
  var d = EC.dims(plate, ic), s = 100 * P.size / ((d && d.width) || 512);
  EC.set(plate, ic, "transform/scale", [s, s]);
  EC.set(plate, ic, "transform/position", P.center);
  var id = EC.precompLayer(c, plate, { name: P.name, start: P.t });
  EC.trim(c, id, P.t, P.t + P.dur);
  var path = EC.fx(c, id, "Shatter", { "view": 0, "render": 0, "shape/pattern": 3, "shape/repetitions": P.repetitions,
    "shape/extrusionDepth": P.depth, "shape/origin": P.center,
    "force1/force1Position": P.center, "force1/force1Depth": P.forceDepth, "force1/force1Radius": P.radius, "force1/force1Strength": P.strength,
    "physics/rotationSpeed": P.rotationSpeed, "physics/randomness": P.randomness, "physics/viscosity": 0.0, "physics/gravity": 0,
    "lighting/lightType": 1, "lighting/lightIntensity": 0.3, "lighting/ambientLight": 0.72 });
  // pale tile pieces vanish on light grounds: map the icon's tones to a deeper green..mint range
  if (P.tint) EC.fx(c, id, "Tint", { black: EC.rgba(P.tint[0]), white: EC.rgba(P.tint[1]), amount: 100 });
  EC.fx(c, id, "Temporal Motion Blur", { motionBlurLevels: 8, overrideShutterAngle: true, shutterAngle: 240 });
  EC.keys(c, id, "transform/opacity", [[P.t + 0.06, 100], [P.t + P.fade, 0]], "in");   // squares clear the disc before the logo
  var fl = null;
  if (P.flash) {
    fl = EC.shape(c, { kind: "ellipse", size: [P.flashSize, P.flashSize], fill: P.flashColor, name: P.name + " flash" });
    EC.set(c, fl, "transform/position", P.center);
    EC.fx(c, fl, "Gaussian Blur", { blurriness: P.flashSize * 0.18 });
    EC.keys(c, fl, "transform/opacity", [[P.t - 0.01, 0], [P.t + 0.03, P.flashOpacity], [P.t + 0.16, 0]], [[1, 99], [8, 92]]);
    EC.keys(c, fl, "transform/scale", [[P.t - 0.01, [40, 40]], [P.t + 0.18, [160, 160]]], "expo");
    EC.run("layer.setBlendMode", { comp: c, layers: [fl], mode: "Add" });
    EC.trim(c, fl, P.t - 0.02, P.t + 0.2);
  }
  return { layer: id, plate: plate, flash: fl, shatter: path };
}
