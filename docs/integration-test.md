# Integration tests on rented machines

Unit tests and the image smoke tests run in GitHub Actions on every push. What CI cannot show needs real machines:
a GPU, a real engine login and a real rental. These runs cost money and are started by a person, never by CI.

## Test 1: compute end to end (about $0.10 to $0.30)

Proves: offers, rent, upload probe, a Blender render on the GPU, fetch, destroy, the cap, the guard, the cost book and
the proof "0 own machines left". Runs from any computer with Python, ssh and rsync (no Docker needed there).

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
export CREWCUT_STUDIO=$PWD/studio-itest
read -rs VAST_API_KEY && export VAST_API_KEY          # paste the key, hidden
.venv/bin/crewcut compute estimate --kind blender --frames 75 --json
.venv/bin/crewcut compute rent --episode itest --gpus 1 --minutes 30 --max-usd 0.30   # exit 3: accept the spend card
.venv/bin/crewcut card list --status open                                             # card id
.venv/bin/crewcut card accept <card id>                       # the yes; at the terminal it counts as the user's button
.venv/bin/crewcut compute rent --episode itest --gpus 1 --minutes 30 --max-usd 0.30   # prints the machine id
.venv/bin/crewcut compute run <machine> --timeout 900 -- "/opt/blender/blender --version && nvidia-smi -L"
.venv/bin/crewcut compute destroy --all-ours
.venv/bin/crewcut compute ledger --episode itest                                      # cost and the proof line
```

Then the cap test: the same with `--max-usd 0.10` and a long `sleep` as the command; the session must destroy the
machine when the cap is reached and say so.

## Test 2: the studio on a rented Linux machine (amd64 with GPU, then arm64 without)

Proves: the image runs outside CI, `doctor --probe` with a real `CLAUDE_CODE_OAUTH_TOKEN`, one short episode
(a 30-second recording of test speech) through idea, title, script, ingest, transcription, speaker cut, 2D, preview.

1. The images: every push to main publishes `:edge` and `:<sha>`, a version tag `v*` `:<version>` and `:latest`; a manual run (`gh workflow run image.yml -f push=true`) publishes `:latest`.
2. Rent a Docker-capable VM (not a container host): an amd64 VM with an NVIDIA GPU and an arm64 VM (any cloud with
   arm64 Linux). Install Docker and the NVIDIA Container Toolkit on the GPU VM.
3. `docker login ghcr.io` with a read-only package token, clone the repo, `./start.sh` (the token goes in hidden),
   open the UI through an SSH tunnel: `ssh -L 4747:localhost:4747 <vm>`.
4. Measure and write down: image pull time, first-start engine install time, transcription speed on CPU and GPU,
   the time per 2D scene, the preview time.
5. Destroy the VMs.

## Test 3: Codex (beta)

Same as test 2 with "use Codex" in the chat: device-code login in the chat, one episode up to the script card.
Until this has run, Codex stays marked beta in the README.
