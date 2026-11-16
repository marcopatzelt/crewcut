# Your first real episode: bring earlier work, record, edit, thumbnail

This is the path for an episode whose idea, script and B-roll already exist (made by hand or with an earlier setup):
Crewcut takes them as inputs, you record, and the crew does Record → Edit → Thumbnail with a card for each decision.
Upload stays switched off until you switch it on.

## Two rules this setup must keep

1. **Raw footage and private data never go to rented machines.** Recordings, transcripts and the cut stay where the
   footage is. Crewcut enforces this: `crewcut compute put` refuses recordings, `work/` (transcripts), the studio state
   and keys; a rented GPU only gets scene code, fonts and render data.
2. **Production, not experiments, on your own computer.** Running the released image to make a real video is normal use
   of the tool; building images, trying new versions and benchmarks happen in CI or on rented machines.

## Where the work runs: three ways (you choose)

| Way | Footage | Your computer | Cost | Fits rule 1 | Fits rule 2 |
|---|---|---|---|---|---|
| **A. Crewcut on your computer, heavy 3D rented** (recommended) | stays on your computer | runs the container with memory and CPU limits; ingest, transcription, cut, 2D and assembly run here on the CPU | only rented 3D, if any (a few cents to dollars, with a card) | yes | yes: the released image, used for production; nothing is built here |
| B. Everything on a rented VM you control | uploaded to your own VM (not a marketplace host), only with your explicit yes | only a browser | the VM per hour | only with an exception you make for your own footage on your own VM | yes |
| C. Everything on your computer, no renting | stays | also 3D on the CPU (slow) | none | yes | yes, but 3D can take hours |

Way A in numbers (honest, from the author's earlier setup): ffmpeg cut, grade and checks take minutes for a 4-minute
video; speech recognition on a laptop CPU took over half an hour for a long recording (a one-minute Short takes a few
minutes); 2D needs no GPU. Without 3D in the plan, nothing is rented at all.

## Setup for way A (once)

1. Allow Docker to pull the private image: `gh auth refresh -h github.com -s read:packages` (one click in the
   browser), then `gh auth token | docker login ghcr.io -u <your GitHub name> --password-stdin`.
2. In the Crewcut folder, put these lines into `.env` (`./start.sh` creates it and asks for the engine token):

   ```
   # memory and CPU limits for the container
   COMPOSE_FILE=compose.yaml:compose.limits.yaml
   CREWCUT_MEM_LIMIT=14g
   CREWCUT_CPUS=6
   # pull the released image; never build on this computer
   CREWCUT_PULL_POLICY=always
   # Crewcut's own studio folder, and the folder with your earlier work (mounted read only at /import)
   CREWCUT_STUDIO_DIR=<a folder for Crewcut's studio>
   CREWCUT_IMPORT_DIR=<the folder that holds your earlier work>
   ```
3. `./start.sh`, then open http://localhost:4747.
4. Your style pack, from an existing pack plus your own font and logo files (they stay in your studio, never in the
   repository):

   ```
   docker compose exec crewcut crewcut brand init --from /app/examples/striq \
     --font display=/import/<path to your display font> --font body=/import/<path to your body font> \
     --logo /import/<path to your logo> --accept
   ```

## Each episode

```
docker compose exec crewcut crewcut episode import /import/<episode folder> --title "<title>" \
  [--format portrait] [--script /import/<script file>] [--broll /import/<file> ...] [--skip upload,thumbnail]
```

- The script (default: the newest `SCRIPT-*.md`) becomes `brief/SCRIPT-v001.md`; B-roll (default: everything in
  `04-broll/` or `broll/`) is copied to `broll/`. Files with the same name get their folder name in front.
- Steps idea, title, proof and script are marked done (they happened before Crewcut); upload is switched off unless you
  pass another `--skip` list; the record step starts at once and the chat shows the teleprompter link.
- Nothing is ever written into the import folder.

Then:

1. **Record.** The teleprompter runs on any phone in your network (QR code in the episode header). If your computer
   has a firewall that blocks network access to containers, allow port 4748 from your home network, or read from the
   computer screen.
2. **Bring the files.** Copy the camera files into `<studio>/inbox/<episode id>/` or drop them into the chat. Crewcut
   notices finished copies by itself and the Editor starts: ingest with checksums, sound checked to the end of every
   file, transcription, takes, speaker cut.
3. **Cards you answer** (one button each, or say what to change): the mix of inserts (`mix`), the preview (`preview`),
   the final version (`final`), the thumbnail (`thumbnail`). Spend cards appear only if the plan has 3D and renting
   would save a lot; "local is fine" is always an answer.
4. **Thumbnail.** Way A needs Codex logged in (say "use Codex" once; the engine for the crew can stay Claude Code),
   way B needs an OpenAI key and a spend card. Skip it with `--skip upload,thumbnail` for a Short.
5. The chat says when every switched-on step is done. Upload: switch it on later with
   `crewcut episode step <id> upload open`.

## What this first run will show (and what it cannot)

It is the first time the whole chain runs on real footage. Expect corrections; each one can become a rule with one yes.
Untested until then: speech recognition speed in the container on your CPU, the speaker cut on new footage, the
assembly of real B-roll clips into a portrait Short, Codex image generation inside the container.
