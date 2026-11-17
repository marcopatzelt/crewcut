# EffectCraft (pinned, patched, built by our CI)

Crewcut's motion graphics run on **EffectCraft**, an open-source motion graphics and compositing engine written in
Rust (`github.com/storytold/effectcraft`, MIT OR Apache-2.0, copyright the ArtCraft Team and the EffectCraft
contributors). Crewcut uses only its headless command-line program `effectcraft-cli`: no window, no GPU needed, it
renders on the CPU.

This folder holds no EffectCraft source. It holds:

| File | What |
|---|---|
| `PIN` | the upstream commit we build and the sha256 of GitHub's tarball of that commit |
| `patches/NNNN-*.patch` | our changes to upstream, one change per file, applied in order (`git format-patch` files: author and message are kept) |
| `LICENSE-MIT`, `LICENSE-APACHE`, `NOTICE` | upstream's licence files at the pin, unchanged (the build checks that they are equal) |
| `build.Dockerfile` | downloads the tarball, checks the sha256, applies the patches, builds `effectcraft-cli`, tests it, and returns a `scratch` image with `/effectcraft-cli`, `/licenses/` and `/PIN` |

The workflow `.github/workflows/effectcraft.yml` runs the build on native amd64 and arm64 runners when this folder
changes, starts the binary in `debian:bookworm-slim` and in `nvidia/cuda:12.4.1-runtime-ubuntu22.04` with no extra
packages, and pushes `ghcr.io/marcopatzelt/crewcut-effectcraft:<sha12>-p<patches>` as one multi-arch tag. The app
image (`docker/Dockerfile`) copies the binary and the licences from that tag; it never builds Rust.

EffectCraft's name is used here as text only. Its brand folder (`docs/brand/`: name, wordmark and logos) is not open
source and never enters this repository or the image.

## The patches

| Patch | Why |
|---|---|
| `0001-keys-setEase-timeBase.patch` | `keys.setEase` takes `timeBase: "comp"` like `prop.addKey` and `keys.set` do, so an ease set in comp time lands on the right key of a layer that starts later. `EC.keys` in `templates/motion/lib/ec_lib.jsx` relies on it (with a fallback for builds without it). Tested by upstream's `key_time` tests. |

## Bump the pin

1. Pick the new upstream commit. Download `https://github.com/storytold/effectcraft/archive/<sha>.tar.gz` and write
   its full SHA and `sha256sum` into `PIN`.
2. Copy `LICENSE-MIT`, `LICENSE-APACHE` and `NOTICE` from that commit (the build refuses different files).
3. Apply each patch to the new tree (`patch -p1 --dry-run`). Delete a patch file when upstream has the change.
4. Update the tag in `docker/Dockerfile` (`ARG EFFECTCRAFT_IMAGE=…:<sha12>-p<patches>`); `tests/motion/test_pin.py`
   checks that `PIN`, the patch count and the Dockerfile agree.
5. Push. `effectcraft.yml` builds both architectures; then the image build and the engine tests run on the new
   binary.

## Add a patch

One change per patch, with a test upstream's way (`cargo test -p effectcraft-engine …`), made on a local branch of
upstream and exported with `git format-patch -1 <commit>`. Name it `NNNN-short-name.patch` with the next number and
add a row to the table above. If the patch touches other tests, add them to the `cargo test` line in
`build.Dockerfile`.
