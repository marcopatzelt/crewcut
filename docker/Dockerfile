# syntax=docker/dockerfile:1.7
# Crewcut image. Two targets:
#   base  linux/amd64 + linux/arm64   the studio: web UI, conductor, ffmpeg, Chromium, Python, Node, speech recognition,
#                                      Blender on amd64 (there is no official Linux arm64 build of Blender)
#   gpu   linux/amd64                  base + NVIDIA libraries for speech recognition on a GPU; also the image that
#                                      rented GPU machines run (as a worker, without any login data)
# The engines are not inside the image: at every start the entrypoint brings in the newest version of the one the user
# chose (Claude Code by default, Codex when the user says so) from its official npm package into the engine volume,
# next to the last good one, and switches only after a smoke test. Claude Code's licence
# is not open, so it is never shipped; logins stay in the environment (Claude) or in the engine volume (Codex).

ARG BLENDER_VERSION=5.0.1
# The motion engine: effectcraft-cli, built by .github/workflows/effectcraft.yml from third_party/effectcraft (pinned
# upstream commit + patches) for amd64 and arm64. The tag must match third_party/effectcraft/PIN and the number of
# patch files (tests/motion/test_pin.py checks it). No Rust is built here.
ARG EFFECTCRAFT_IMAGE=ghcr.io/marcopatzelt/crewcut-effectcraft:7a34ceffe209-p1

FROM ${EFFECTCRAFT_IMAGE} AS effectcraft

# ---- web UI: built on the build machine's own architecture, no emulation needed ------------------------------------
FROM --platform=$BUILDPLATFORM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---- Blender, official build, amd64 only -----------------------------------------------------------------------------
FROM debian:bookworm-slim AS blender
ARG TARGETARCH
ARG BLENDER_VERSION
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl xz-utils \
 && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /opt/blender && if [ "$TARGETARCH" = "amd64" ]; then \
      curl -fsSL "https://download.blender.org/release/Blender${BLENDER_VERSION%.*}/blender-${BLENDER_VERSION}-linux-x64.tar.xz" \
      | tar -xJ -C /opt/blender --strip-components=1; \
    fi

# ---- base -------------------------------------------------------------------------------------------------------------
FROM node:22-bookworm-slim AS base
ARG TARGETARCH
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CREWCUT_APP=/app \
    CREWCUT_STUDIO=/studio \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    NODE_PATH=/app/tools/node_modules \
    DISABLE_AUTOUPDATER=1 \
    CODEX_HOME=/opt/engine/codex-home \
    CREWCUT_ENGINE_PREFIX=/opt/engine \
    PATH=/opt/venv/bin:/opt/engine/current/claude/bin:/opt/engine/current/codex/bin:/opt/engine/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip \
      ffmpeg fonts-inter fonts-dejavu-core fontconfig \
      rsync openssh-client git curl ca-certificates tini procps util-linux \
      libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 libsm6 libxkbcommon0 libegl1 libglu1-mesa \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Node side: the 2D frame renderer and its Chromium
COPY tools/package.json tools/package-lock.json* tools/
RUN cd tools && (npm ci --no-audit --no-fund || npm install --no-audit --no-fund) \
 && npx --yes playwright-core install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*

# Python side: the app with speech recognition and the YouTube API
COPY pyproject.toml README.md LICENSE ./
COPY crewcut/ crewcut/
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install ".[speech,youtube]"

COPY --from=blender /opt/blender /opt/blender
RUN if [ -x /opt/blender/blender ]; then ln -s /opt/blender/blender /usr/local/bin/blender; fi

# Motion graphics engine (MIT OR Apache-2.0; licences and upstream NOTICE next to it)
COPY --from=effectcraft /effectcraft-cli /usr/local/bin/effectcraft-cli
COPY --from=effectcraft /licenses /usr/share/licenses/effectcraft
COPY --from=effectcraft /PIN /usr/share/licenses/effectcraft/PIN
ENV EFFECTCRAFT_CLI=/usr/local/bin/effectcraft-cli

COPY skills/ skills/
COPY team/ team/
COPY templates/ templates/
COPY packs/ packs/
COPY config/ config/
COPY tools/ tools/
COPY third_party/ third_party/
COPY THIRD_PARTY_NOTICES.md ./
COPY examples/ examples/
COPY tests/ tests/
COPY host/ host/
COPY compose.development.yaml ./
COPY docker/entrypoint.sh docker/entrypoint.sh
COPY --from=web /web/dist web/dist

RUN mkdir -p /studio /opt/engine && chown node:node /studio /opt/engine && chmod +x docker/entrypoint.sh

EXPOSE 4747 4748
VOLUME ["/opt/engine"]
ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker/entrypoint.sh"]
CMD ["crewcut", "serve", "--host", "0.0.0.0"]

# ---- gpu (amd64) ------------------------------------------------------------------------------------------------------
FROM base AS gpu
ENV NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=all
# cuBLAS 12 and cuDNN 9 for faster-whisper (CTranslate2) on NVIDIA cards. Blender brings its own GPU kernels.
RUN /opt/venv/bin/pip install "nvidia-cublas-cu12" "nvidia-cudnn-cu12==9.*" \
 && /opt/venv/bin/python -c "import nvidia.cublas.lib as a, nvidia.cudnn.lib as b; print(list(a.__path__)[0]); print(list(b.__path__)[0])" \
    > /etc/ld.so.conf.d/crewcut-nvidia.conf \
 && ldconfig
