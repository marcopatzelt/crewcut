/* @template lottie_clip
 * @description An imported template: a Lottie file that `crewcut motion imports` turned into the pack's palette,
 *   fonts and frame rate, laid into the frame by EffectCraft. It is fitted into the safe area ("contain") or fills the
 *   whole frame ("cover"), placed at x and y (shares of the frame), played from its first frame (offset seconds into
 *   it, speed times its own speed) and held on its last frame when the insert runs longer. The file comes from
 *   `crewcut motion imports use NAME EPISODE INSERT_ID` (motion/<insert>/<name>.json in the episode); the source
 *   stays private and is never copied into the app.
 * @kind overlay
 * @formats ["landscape", "portrait", "stage"]
 * @version 1
 * @sounds []
 * @params {"comp": "Main", "file": "", "fit": "contain", "x": 0.5, "y": 0.5, "scale": 1.0, "speed": 1.0,
 *   "offset": 0.0, "layer": "Imported"}
 * @end */
function lottie_clip(P) {
  var c = P.comp, F = CC.frame();
  // without a file (a sample run of the shelf) the overlay stays empty; a plan always names one
  if (!P.file) return { layer: null, note: "no file: run `crewcut motion imports use NAME EPISODE INSERT_ID`" };
  var r = EC.run("file.importLottie", { path: P.file });
  var src = r.comp;
  if (src === undefined || src === null) throw new Error("the Lottie file did not import: " + P.file);
  var info = EC.run("comp.info", { comp: src });
  var w = info.width || F.W, h = info.height || F.H, own = info.duration || F.duration;
  // fit: the whole animation inside the safe area, or the whole frame covered
  var box = P.fit === "cover" ? { w: F.W, h: F.H } : { w: F.safe.w, h: F.safe.h };
  var k = P.fit === "cover" ? Math.max(box.w / w, box.h / h) : Math.min(box.w / w, box.h / h);
  k = k * (P.scale || 1);
  var id = EC.precompLayer(c, src, { name: P.layer });
  EC.set(c, id, "transform/position", [P.x * F.W, P.y * F.H]);
  EC.set(c, id, "transform/scale", [k * 100, k * 100]);
  // time: the animation's own clock (speed), from offset; a longer insert holds the last frame
  var speed = P.speed || 1, offset = P.offset || 0;
  if (Math.abs(speed - 1) > 1e-6) EC.run("layer.timeStretch", { comp: c, layers: [id], percent: 100 / speed });
  if (offset) EC.run("layer.timing", { comp: c, layers: [id], start: -offset / speed });
  if ((own - offset) / speed < F.duration - 1e-3) EC.run("layer.freezeOnLastFrame", { comp: c, layers: [id] });
  return { layer: id, comp: src, size: [w, h], scale: k, seconds: own };
}
