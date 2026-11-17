/* @template flash
 * @description Short additive light flash: a white (or tinted) soft ellipse that snaps on at t and fades out over a
 *   few frames. Used on the click and inside the iris.
 * @params {"comp": "Main", "t": 1.0, "center": [960, 540], "size": 220, "blur": 60, "opacity": 70, "frames": 5,
 *   "color": "#FFFFFF", "fps": 60, "name": "Flash"}
 * @end */
function flash(P) {
  var c = P.comp, f = 1 / P.fps;
  var id = EC.shape(c, { kind: "ellipse", size: [P.size, P.size], fill: P.color, name: P.name });
  EC.set(c, id, "transform/position", P.center);
  EC.fx(c, id, "Gaussian Blur", { blurriness: P.blur });
  EC.keys(c, id, "transform/opacity", [[P.t - f, 0], [P.t, P.opacity], [P.t + P.frames * f, 0]], "linear");
  EC.run("layer.setBlendMode", { comp: c, layers: [id], mode: "Add" });
  EC.trim(c, id, P.t - 2 * f, P.t + (P.frames + 1) * f);
  return { layer: id };
}
