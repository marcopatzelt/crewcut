# syntax=docker/dockerfile:1.7
# Builds effectcraft-cli (the headless EffectCraft engine) for the build machine's own architecture.
# CI runs it on native amd64 and arm64 runners (.github/workflows/effectcraft.yml), never under QEMU, never inside the
# app image. Build context: third_party/effectcraft. Output: a scratch image with
#   /effectcraft-cli    the stripped release binary (links only libc, libm, libgcc_s)
#   /licenses/          LICENSE-MIT, LICENSE-APACHE, NOTICE of upstream, unchanged
#   /PIN                the upstream commit and tarball checksum it was built from, plus the patch count
# ubuntu:22.04 (glibc 2.35) so the binary also runs on Debian bookworm (the app image) and on the CUDA runtime image
# of rented machines.

FROM ubuntu:22.04 AS build
ARG CARGO_BUILD_JOBS=
ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/root/.cargo/bin:$PATH \
    CARGO_TERM_COLOR=never
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential pkg-config cmake clang git curl ca-certificates patch \
      libasound2-dev libgtk-3-dev libxkbcommon-dev libwayland-dev libx11-dev libxrandr-dev libxi-dev libgl1-mesa-dev \
      libxcursor-dev libxinerama-dev libfontconfig1-dev libssl-dev \
 && rm -rf /var/lib/apt/lists/*
# EffectCraft needs Rust 1.95 or newer.
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain stable && rustc --version

WORKDIR /src
COPY PIN LICENSE-MIT LICENSE-APACHE NOTICE /pin/
COPY patches/ /pin/patches/
# Source by pinned commit, checked against the tarball's sha256; then every patch in order. The licence files in the
# repo must equal upstream's at the pin.
RUN set -eu; commit=$(awk '$1=="commit"{print $2}' /pin/PIN); sum=$(awk '$1=="sha256"{print $2}' /pin/PIN); \
    curl -fsSL -o /tmp/src.tar.gz "https://github.com/storytold/effectcraft/archive/${commit}.tar.gz"; \
    echo "${sum}  /tmp/src.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/src.tar.gz --strip-components=1; rm /tmp/src.tar.gz; \
    for f in LICENSE-MIT LICENSE-APACHE NOTICE; do cmp "$f" "/pin/$f"; done; \
    n=0; for p in /pin/patches/*.patch; do echo "applying $p"; patch -p1 --forward < "$p"; n=$((n+1)); done; \
    printf 'patches %s\n' "$n" >> /pin/PIN; cat /pin/PIN

# Build, test what the patches touch, prove the binary starts without a display or a GPU, then drop target/ in the
# same step so the cached layer stays small.
RUN set -eu; [ -n "${CARGO_BUILD_JOBS}" ] || unset CARGO_BUILD_JOBS; \
    cargo build --release --locked -p effectcraft-cli; \
    cargo test --release --locked -p effectcraft-engine key_time; \
    strip target/release/effectcraft-cli; cp target/release/effectcraft-cli /effectcraft-cli; \
    /effectcraft-cli --empty info --json | head -c 600; echo; \
    /effectcraft-cli --demo render-frame --out /tmp/demo.png --max-side 640 --json; test -s /tmp/demo.png; \
    ldd /effectcraft-cli; \
    rm -rf target /root/.cargo/registry /root/.cargo/git

FROM scratch
COPY --from=build /effectcraft-cli /effectcraft-cli
COPY --from=build /pin/LICENSE-MIT /pin/LICENSE-APACHE /pin/NOTICE /licenses/
COPY --from=build /pin/PIN /PIN
