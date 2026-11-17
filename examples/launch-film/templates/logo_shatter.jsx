/* @template logo_shatter
 * @description A logo pops in as an extruded, lit 3D slab that turns slowly, holds, then breaks into shards that
 *   burst outward while the camera pushes through them (Shatter on a full-frame precomp of the logo, keyed force
 *   radius, keyed effect camera), with temporal motion blur and a soft glow. logo: PNG with alpha.
 * @params {"comp": "Main", "logo": "", "center": [960, 540], "width": 380, "tIn": 0.6, "tShatter": 1.6, "tOut": 3.0,
 *   "pop": 0.35, "turn": [-42, 22], "tilt": [14, -4], "pattern": 1, "pieces": 40, "depth": 0.3, "strength": 13,
 *   "radius": 0.2, "forceDepth": 0.1, "breakTime": 0.18, "rotationSpeed": 0.3, "randomness": 0.5, "viscosity": 0.0,
 *   "sideColor": "#9FE3CF", "light": 0.9, "ambient": 0.62, "specular": 0.3, "push": [4.0, 1.2], "pushDur": 0.9,
 *   "motionBlur": true, "glow": false, "name": "Logo", "compSize": [1920, 1080], "fps": 60}
 * @end */
function logo_shatter(P) {
  var c = P.comp, plate = P.name + " plate";
  EC.comp({ name: plate, width: P.compSize[0], height: P.compSize[1], fps: P.fps, duration: P.tOut + 1, motionBlur: false });
  var lg = EC.footage(plate, P.logo, { name: "logo" });
  var d = EC.dims(plate, lg), s = 100 * P.width / ((d && d.width) || 1000);
  EC.set(plate, lg, "transform/scale", [s, s]);
  EC.set(plate, lg, "transform/position", P.center);
  var id = EC.precompLayer(c, plate, { name: P.name });
  EC.trim(c, id, P.tIn, P.tOut);
  // pop: scale on the layer (anchored at the logo centre so it grows in place)
  EC.set(c, id, "transform/anchor", P.center);
  EC.set(c, id, "transform/position", P.center);
  EC.keys(c, id, "transform/scale", [[P.tIn, [30, 30]], [P.tIn + P.pop, [100, 100]]], "expo");
  EC.spring(c, id, "transform/scale", 0.05, 2.4, 7);
  var lum = function (h) { var x = EC.hex(h); return [x[0], x[1], x[2], 1]; };
  var path = EC.fx(c, id, "Shatter", {
    "view": 0, "render": 0, "shape/pattern": P.pattern, "shape/repetitions": P.pieces, "shape/extrusionDepth": P.depth,
    "force1/force1Position": [P.center[0], P.center[1] + 20], "force1/force1Depth": P.forceDepth, "force1/force1Strength": P.strength,
    "force2/force2Radius": 0,
    "physics/rotationSpeed": P.rotationSpeed, "physics/randomness": P.randomness, "physics/viscosity": P.viscosity, "physics/gravity": 0,
    "textures/color": lum(P.sideColor), "textures/sideMode": 0, "textures/frontMode": 1, "textures/backMode": 1,
    "cameraPosition/xyPosition": [P.center[0], P.center[1]],
    "lighting/lightType": 1, "lighting/lightIntensity": P.light, "lighting/ambientLight": P.ambient,
    "lighting/lightPosition": [P.center[0] - 500, P.center[1] - 400], "material/specular": P.specular, "material/highlightSharpness": 20
  });
  // intact until tShatter: force radius 0, then it grows over breakTime and breaks the slab from the centre out
  EC.keys(c, id, path + "/force1/force1Radius", [[P.tIn, 0], [P.tShatter, 0], [P.tShatter + P.breakTime, P.radius]], "out");
  // a slow, steady turn across the hold so the extruded sides stay visible (the camera never stops)
  EC.keys(c, id, path + "/cameraPosition/yRotation", [[P.tIn, P.turn[0]], [P.tShatter, P.turn[1]]], "soft");
  EC.keys(c, id, path + "/cameraPosition/xRotation", [[P.tIn, P.tilt[0]], [P.tShatter, P.tilt[1]]], "soft");
  EC.keys(c, id, path + "/cameraPosition/cameraZ", [[P.tShatter, P.push[0]], [P.tShatter + P.pushDur, P.push[1]]], "expoIn");
  if (P.motionBlur) EC.fx(c, id, "Temporal Motion Blur", { motionBlurLevels: 8, overrideShutterAngle: true, shutterAngle: 200 });
  if (P.glow) EC.fx(c, id, "Glow", { threshold: 80, radius: 30, intensity: 0.45 });
  EC.sw(c, id, "motionBlur", true);
  return { layer: id, plate: plate, shatter: path, scale: s };
}
