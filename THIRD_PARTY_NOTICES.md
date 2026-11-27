# Third-party notices

Crewcut itself is MIT licensed (`LICENSE`). These parts come from others. Each keeps its own licence.

## EffectCraft (motion engine, shipped as a binary in the image)

- What: `effectcraft-cli`, the headless program of EffectCraft, built by our CI from a pinned upstream commit plus
  the patch files in `third_party/effectcraft/patches/`. Copied into the image at `/usr/local/bin/effectcraft-cli`.
- Source: https://github.com/storytold/effectcraft (commit in `third_party/effectcraft/PIN`).
- Licence: MIT OR Apache-2.0, at your option. Copyright (c) 2026 ArtCraft Team and the EffectCraft contributors.
  The licence files and upstream's `NOTICE` (which lists the fonts and libraries the binary embeds) are in
  `third_party/effectcraft/` and in the image at `/usr/share/licenses/effectcraft/`.
- Not included: EffectCraft's brand folder (name, wordmark, logos), which is not open source. Crewcut names
  EffectCraft in text only.

## HyperFrames (HTML building blocks, installed in the image)

- What: the `hyperframes` command-line program (npm package `hyperframes`), pinned in
  `tools/hyperframes/package-lock.json` and installed with `npm ci` in the image; with it the pinned
  `chrome-headless-shell` (Chrome for Testing, amd64) it renders with. Crewcut runs it as a separate program.
- Source: https://github.com/heygen-com/hyperframes (HeyGen). Licence: Apache-2.0.
- Inside the package: GSAP (GreenSock, "Standard No Charge" licence, free also commercially; Crewcut renders by code
  and is not a visual animation builder), puppeteer-core and others under MIT, Apache-2.0, ISC and BSD licences; the
  optional image library sharp brings libvips (LGPL-3.0-or-later) as a separate shared library.
- Crewcut's templates in `templates/hyperframes/` are Crewcut's own (MIT); nothing of HyperFrames' registry is copied.

## Imported motion templates (never in this repository)

- Templates from Mixkit, LottieFiles, Envato or other marketplaces stay in a studio's private folder
  (`library/templates-private/`) under their own licences; `tools/ci/no_private_templates.py` keeps them out of the
  repository. The one Lottie sample here, `templates/motion/assets/lottie/crewcut-card.json`, is Crewcut's own (MIT).

## CC0 assets for Blender (fetched at run time, never shipped)

- Poly Haven (https://polyhaven.com/license) and ambientCG (https://docs.ambientcg.com/license/), CC0 1.0. Fetched by
  `crewcut/render/blender_lib/crewcut_assets.py` into a cache; no file of theirs is in this repository or the image.

## The motion harness (`crewcut/motion/`)

- Written for Crewcut with the method of CLI-Anything (HKUDS, https://github.com/HKUDS/CLI-Anything, Apache-2.0).
  No file of CLI-Anything is copied into this repository: the one file the first version copied
  (`utils/repl_skin.py`, the interactive prompt) was dropped when the harness moved here. The harness is MIT like the
  rest of Crewcut.

## Blender (3D tool, in the image on amd64)

- Official Linux build, GPL-3.0-or-later, https://www.blender.org. Used as a separate program. The scene scripts in
  `templates/3d/`, `templates/motion/plates/` and `examples/launch-film/` are Crewcut's own (MIT); pictures they render
  belong to whoever renders them.

## Face models of the thumbnail identity gate (downloaded at build or first use, checked by SHA-256)

- YuNet face detector (`face_detection_yunet_2023mar.onnx`), MIT, and SFace face recognizer
  (`face_recognition_sface_2021dec.onnx`), Apache-2.0, both from the OpenCV model zoo,
  https://github.com/opencv/opencv_zoo. Run with OpenCV (`opencv-python-headless`, Apache-2.0). The image stores them
  in `/opt/face-models`; `crewcut/thumbnail/identity.py` pins their checksums.
- The real-photo fallback can call rembg (MIT, https://github.com/danielgatis/rembg) when the user installs it; it is
  not part of the image.

## Person matting on rented GPUs (downloaded at run time, never shipped)

- RobustVideoMatting (Peter Lin et al.), https://github.com/PeterL1n/RobustVideoMatting, GPL-3.0. Crewcut does not
  ship or import it: on a rented machine, `crewcut/compute` downloads it and runs its own `inference.py` as a separate
  program on the frames of one shot. See `docs/motion.md`, "Behind the speaker".

## Fonts and pictures in the launch film

- Manrope, SIL Open Font License 1.1, Mikhail Sharanda.
- HDRI "Kloofendal 48d Partly Cloudy (Pure Sky)", CC0, Poly Haven (Greg Zaal, Jarod Guest),
  https://polyhaven.com/a/kloofendal_48d_partly_cloudy_puresky. Used only to light the meadow in the launch film; not
  in the repository.
- Every sound in the film is synthesized by code (`docs/launch/SOUNDS.md`); no sample libraries.

## Web and Node parts

- See `web/THIRD_PARTY.md` for the web UI's packages and `site/media/CREDITS.md` for the landing page.
