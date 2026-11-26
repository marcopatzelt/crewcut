# Rendering

One edit plan builds one version of a video: `episodes/<id>/edit/plan-vNNN.json` (schema in
[architecture.md](architecture.md#edit-plan-episodesideditplan-vnnnjson)). The workbench turns it into inserts and the
finished cut:

```
crewcut render plan  <plan.json>            show inserts, frames, cues and what is already rendered
crewcut render 2d    <plan.json>            2D inserts with Chromium
crewcut render motion <plan.json>           motion graphics with EffectCraft: here, or on one rented machine
crewcut render probe <plan.json> <id>,<id>  still frames at half size, to look at before the big render
crewcut render 3d    <plan.json>            3D inserts with Blender: here, or on rented GPUs after a yes
crewcut render cut   <plan.json>            the finished video with sound
crewcut render shown <plan.json>            lock the output right after someone has seen it
crewcut render all   <plan.json>            2d, motion, 3d, cut
crewcut render measure <still.png>          a 3D still against the style pack
crewcut render samples [--out DIR]          one frame of every 2D scene, both formats (screenshots, docs)
crewcut render capture <episode> --url URL  a web page or terminal recorded upright, for a Short (broll/)
crewcut render music-bed <voice.wav> --music TRACK   a licensed music bed under a Short's voice
crewcut render sfx-sheet [--voice WAV]                the effect layer's sound set to listen to, and its id
crewcut render sfx-approve <set id>                   the user's yes to that set (refused inside a crew job)
crewcut brand preview [--out f.mp4]         10-second sample in the style pack
```

Plain text by default, `--json` for machines. Exit codes: 0 ok, 1 error, 2 usage, 3 waiting for the user (a card is
open) or refused (cap reached), 4 missing key.

Nothing is rendered twice: every insert lives in `render/inserts/<id>-<hash>/` (PNG frames) plus `<id>-<hash>.mp4`
(or `.mov` for overlays). The hash covers the insert's data, the scene file and its shared files, and the look tokens
of the style pack. Change a number in the plan and only that insert renders again. Change the accent colour and
every insert renders again. Loudness and other edit-style values do not touch the hash. Motion graphics add the
template's context, the engine pin and the pack's font files to it (see below).

## The plan in short

```json
{
  "format": "landscape",
  "words": "work/words-v001.json",
  "base": "work/speaker-v001.mp4",
  "voice": "audio/voice-v001.wav",
  "face": [0.5, 0.38],
  "speaker": [{"at": 12.4, "zoom": 1.12}],
  "inserts": [
    {"id": "s1", "kind": "2d", "scene": "counter", "start": 10.0, "end": 14.2,
     "cues": {"value": {"word": "thirty"}, "label": 8}, "data": {"label": "1 million tokens", "value": "30", "unit": "cents"}},
    {"id": "k1", "kind": "2d", "scene": "keyword", "start": 20.0, "end": 22.0, "transparent": true, "data": {"text": "LOCAL"}},
    {"id": "d1", "kind": "3d", "scene": "stack", "start": 30.0, "end": 33.0, "cues": {"word": {"word": "rules"}}, "data": {"word": "Rules"}},
    {"id": "c1", "kind": "clip", "file": "broll/screen.mp4", "at": 3.0, "speed": 1.0, "start": 40.0, "end": 44.0}
  ],
  "sound": {"music": "audio/music.wav", "music_source": "made for this episode, licence CC0", "music_db": null,
            "duck": true, "gaps": [{"before": "s1@value", "frames": 15}], "hits": ["s1@value"], "hit_file": "audio/hit.wav",
            "typing": [], "whooshes": [], "lufs": null},
  "output": "export/003-local-llms-v001-preview.mp4",
  "crf": 17
}
```

- Times are seconds, frames are at the episode's fps (25 by default). `null` takes the style pack's value
  (`edit-style.json`).
- A cue is a frame inside the insert, `{"word": "thirty", "after": 9.5, "offset": -2}` (the first time the word, or a
  phrase of several words, is spoken at or after `after` seconds; punctuation and case are ignored) or
  `{"time": 12.4}`. Always anchor on words: when the speaker cut changes, the plan follows.
- A sound reference is `"s1"` (start of insert `s1`), `"s1@value"` (its cue `value`) or a number of seconds.
- `base` may also be a generated background: `{"color": "soft", "seconds": 20}` (a pack colour name or `#RRGGBB`).
- `tail` (seconds after the base) needs a full-frame insert up to the end, such as an end card.
- `sound.music_source` says where the music comes from and its rights; the workbench passes it into
  `<output>.cut.json` and the style check requires it whenever there is music.
- `sound.music_until` (new 26 Nov 2026) ends the music bed at a moment instead of the end of the video: seconds, a
  sound reference (`"ch1"`, `"ch1@cue"`) or a word anchor (`{"word": "first", "offset": -0.3}`). `sound.music_out` is
  `"fade"` (default, over `sound.music_fade` seconds, default 1.5) or `"whoosh"` (a hard stop with a 60 ms ramp and a
  whoosh at that moment, from the plan's, the pack's or the kit's whoosh file). Without `music_until` the music runs
  to the end as before. Gaps after the stop are dropped.
- `sound.bed` is `"music"` (default) or `"dry"`: a Short with voice and room only. A dry plan refuses `sound.music`
  and `sound.music_source`; its `hits`, `typing` and `whooshes` are left out with a note; the effect layer, when on and
  approved, gives it at most two quiet pops.
- `sound.events: "auto"` turns on the effect layer on picture events (`crewcut/render/sfx_events.py`): a quiet pop when
  text or a number appears (a number on its landing cue), the same quiet whoosh-and-pop pair on every part change, a
  swoosh on a B-roll change; at most `sfx.per_minute_max` (6) in any minute and `sfx.min_gap_s` (1 s) apart; an effect
  on a loud syllable of the voice moves up to 0.2 s to a quieter spot or is left out. An insert's `"sfx"` may be
  `false` or a class (`"part"`, `"number"`, `"text"`, `"broll"`). While the layer runs, the motion templates' own
  `@sounds` are left out. It runs only when the pack approved the exact effect set (`edit-style.json`
  `sfx.approved_set`, see [sfx-listening.md](sfx-listening.md)); otherwise the cut runs without it and says why.
  `<output>.cut.json` lists every effect (`sfx_events`).
- `plan` warns about overlapping full-frame inserts, cues outside their insert and more text cards than the pack
  allows (`text_cards_max`); with motion graphics also about their lengths and density (see below).
- `start` and `end` of any insert may be a word anchor too: `{"word": "costs", "offset": -0.6, "after": 10.0}`, the
  offset here in seconds (a cue's offset is in frames). An end anchor looks from the start on.

## 2D: Chromium, one frame after the other

Every 2D scene is an HTML page in `templates/2d/` that exposes `window.setFrame(n)`: a pure function of the frame
number, no clock, no CSS animation. `tools/render_html.js` opens the page in Chromium (Playwright), sets the data and
the brand tokens before any script runs, waits for fonts and images, checks that nothing failed, and takes one PNG per
frame. A missing font, an image that did not load or a page error fails the run instead of rendering a wrong picture.

Scenes: `counter`, `headline`, `keyword` (transparent, over the speaker), `cards`, `bars`, `post`, `clip-card`, `grid`.
Their data keys, cues and limits are in [templates/2d/BLOCKS.md](../templates/2d/BLOCKS.md). Planned: `area`, `flow`,
`wave`, `swap`, `untangle`.

How the style pack changes the look:

| In `brand.json` | Changes |
|---|---|
| `colors` | every colour; each key becomes a CSS variable `--c-<key>` (`colors.stage` and `colors.card` are optional extras) |
| `fonts.display`, `fonts.body` | family and weight; font files in the pack (`files`) are loaded into the page, otherwise the system font (Inter in the image) |
| `shape` | corner radius, line width, shadow |
| `motion` | entrance length and scale, stagger, counter roll, highlight speed, drift, decor (`none`, `shapes`, `float`) |
| `logo` | only when the pack has a logo file and a placement; never on transparent overlays |

From `edit-style.json` the scenes read `min_text_px` (no visible text is smaller; neutral 40 px). A pack can go
further and hold its own copy of the scene folder in `brand/templates/2d/`; the workbench then uses it. The app's
templates are never edited for one brand.

Encoding: full-frame inserts become H.264 MP4 (CRF 14), overlays QuickTime Animation MOV with alpha.

Speed: Chromium needs no GPU. Time per insert is not measured yet; by the way it works it is seconds to a few minutes.

## Motion graphics: EffectCraft, here or rented

A motion insert (`"kind": "motion"`, schema in [architecture.md](architecture.md#edit-plan-episodesideditplan-vnnnjson))
is an EffectCraft comp: a library template from `templates/motion/` (the pack's `brand/templates/motion/` wins) or a
comp in the episode folder. User guide: [motion.md](motion.md). `crewcut render motion <plan> [--ids a,b] [--draft]
[--local | --rented] [--max-usd X]` renders every motion insert with missing frames:

1. A work folder `render/motion-work/<id>-<hash>/` holds the project: one comp "Main" at the insert's size (1920 x
   1080, 1080 x 1920, or the 1080 x 960 stage of a proof-top insert with `place` top), the plan's fps, the insert's
   length plus 2 frames, the pack's ground colour (`motion_graphics.ground`; none for overlays), motion blur 180
   degrees with 16 samples.
2. The template runs with its params and the insert's context (`CC_CTX`: format, size, fps, duration, transparent,
   face, backdrop, draft, right_free, brand) in one engine process. `script.jsx` stays in the work folder.
3. PNG frames in chunks of 1 second, one engine process per chunk (EffectCraft keeps a whole chunk in memory), cores
   / 4 of them at a time (at least 1; a container's CPU limit counts), into `render/inserts/<id>-<hash>/` as
   `0000.png`, `0001.png`, ... like 2D. The first chunk is timed and the log says how long the rest should take.
4. The 2D encoder: H.264 CRF 14, or QuickTime Animation MOV with alpha for overlays.

Fonts: the pack's font files (`fonts.<role>.files`) are copied into `render/motion-work/fonts/` for every run, and
every engine process gets `EFFECTCRAFT_FONT_DIRS` pointing there (folders the user set stay after it). A pack font
needs no install.

Cache: the hash covers the params, the context (the speaker backdrop by what it is made of: the base file, the span,
the zoom), the `.jsx`, every lib file (`lib/ec_lib.jsx`, `lib/cc_frame.jsx`), the look tokens `colors`, `fonts`,
`shape` and `motion_graphics`, the engine pin (`third_party/effectcraft/PIN` and the patch count) and the font files'
sizes and times. Change an episode's own `comp.jsx` and only that insert renders again; update the engine and every
motion insert does.

`--draft` renders with 8 blur samples into its own folder (the context says `draft`, so the hash differs): drafts
are for looking, the cut never uses one.

`"backdrop": "speaker"`: the workbench cuts the speaker piece of exactly the insert's span from the base (the graded
speaker cut) with the zoom the cut shows at the insert's start, as picture-only ProRes 422 HQ
(`render/motion-work/<id>-<hash>/backdrop.mov`), and hands its path to the comp as `CC_CTX.backdrop`. The comp's first
frame is the speaker frame, so the join is invisible. The voice is untouched.

`"layer": "behind"` (overlays only): the overlay renders like any overlay. After its clip is encoded the workbench
calls the hook `crewcut.render.motion.behind_hook`, which hands the insert to `crewcut.motion.matte.composite_behind`
once the matte step has one ([motion-matte.md](motion-matte.md)); until then the overlay lies over the speaker.

Sounds: with `"sound": true` the template's `@sounds` become sound events of the cut: `"in"` at the insert's start,
`"out"` at its end minus `motion_graphics.exit_s`, a param name at the start plus that param's seconds. `whoosh` goes
to `whooshes`; `hit`, `pop`, `click` and `bell` to `hits`; `tick`, `reel_tick` and `typing` to `typing`. One sound per
motion graphic (the first that maps), none on a `keyword_pop` right after a `keyword_pop`.

### Where: `render.location`

`config/crewcut.toml` (a studio's own `config/crewcut.toml` wins):

```toml
[render]
location = "local"         # or "rented"
```

`--local` and `--rented` win for one run; `render all` passes its flag on.

- **local**: this computer's CPU. Needs `effectcraft-cli` (the Crewcut image has it at `/usr/local/bin`). Without it
  `render motion` stops with one sentence (exit 1); only motion inserts are affected.
- **rented**: one machine through `crewcut.compute` ([compute.md](compute.md)): the spend card first (exit 3 while it
  is open), a session cap of $2 for a video and $0.50 for a Short (`"motion_cap_usd"` in the plan may lower it,
  `--max-usd` sets it), one GPU (`limits.build_max_gpus`), destroyed when the session ends, also after an error. Only
  the generated script, the project settings, the chunk commands, the pack's font files, images the params name and
  the template's assets go up (`render/motion-remote/motion/` becomes `/work/motion`); never footage or keys. The
  machine runs `effectcraft-cli` from the Crewcut GPU image; on the fallback CUDA image this computer sends its own
  binary when it is amd64, else the run stops with one sentence. An insert with a speaker backdrop sends only its
  speaker piece (picture-only ProRes in `render/matte/`, exactly the insert's span) after a spend card that says so in
  plain words; the recording itself never goes up. Params that name footage are refused before anything is rented.

### `render all` without the engine

`render all` runs 2d, motion, 3d, cut. A plan whose motion inserts cannot render here stops with the one sentence,
like `render motion`. A plan that says `"motion_without_engine": "skip"` (the demo does) goes on: the cut leaves those
inserts out (the speaker or background shows instead, their sound events go too) and `<output>.cut.json` names them
in its notes.

## 3D: Blender, here or rented

3D scenes are Blender scripts in `templates/3d/` on a shared stage (`stage.py`): `box`, `stack`, `scale` (keys in
[templates/3d/README.md](../templates/3d/README.md); planned: `object-word`, `row`, `grid3d`, `slide`). The stage,
materials, accent, light, text font and samples come from `brand.json` `stage3d`. The neutral style needs no 3D at
all: 2D carries the numbers, 3D is the exception.

3D in Cycles is the only really slow step. The honest numbers from the author's studio, with its scenes at full size:

| Where | Seconds per frame | A 3-second insert (75 frames) | 840 frames (one long video) |
|---|---|---|---|
| Laptop CPU | about 144 | about 3 h | about 34 h |
| RTX 4090 (rented or own), 128 samples | about 20 to 70 | about 0.5 to 1.5 h on one card | 27 minutes on 8 cards |

A rented card cost about $0.35 to $0.50 per hour in the studio. Nothing else here is measured.

### Three ways

1. **CPU, any machine** (`--local`): Cycles in the container. Always works; slow (see above). Fine over night.
2. **Own NVIDIA card** (`--local`): pass the card into the container (`docker run --gpus all ...` on Linux or
   Windows). Blender then renders as fast as a rented card of the same class. The workbench notices the card
   (`nvidia-smi`) and renders here without asking. `CREWCUT_GPU=1` or `0` decides without asking `nvidia-smi`.
3. **Rented GPUs** (`--rented [--gpus N]`), through `crewcut.compute` ([compute.md](compute.md)).

Mac (planned): Blender directly on the Mac with Apple graphics, started through a small host bridge, because the
container cannot start a Mac program. Not built.

### Who chooses

`crewcut render 3d <plan>` without `--local` or `--rented`:

- a GPU here: render here;
- else it asks `compute.estimate` for both numbers. If renting does not save a lot, it renders here;
- if renting saves a lot, it posts a card with both numbers ("840 frames: about 34 h here, or about 25 min on 4 GPUs
  for about $0.90") and exits with code 3. It never chooses money silently;
- after a yes, the next run rents; after "local is fine" it renders here and does not ask again in this episode.

`--local` always works. `--rented` still goes through the compute module's approval, money cap and session cap.

### How a rented run works

- Only scene code (`templates/3d/*.py`), the insert data, the tokens and font files go up. Never recordings or keys.
- The frames are split into batches of 6. Each machine takes the next batch, so a fast machine takes more. A batch
  that runs longer than 1.5 x the median goes to a second machine. Each batch has a time limit of 3 x the median (at
  the start 150 s per frame + 240 s). A machine stops after three failed batches.
- Every finished batch is fetched right away. When every frame is there, the session ends and destroys every machine,
  also after an error. When the cap is reached mid-run, every machine stops at once and the command exits with code 3.

### Probe first, then the batch

`crewcut render probe <plan> <id>,<id> [--frame N,N] [--local | --rented]` renders still frames at half size (64
samples) into `render/probe/`. Look at them before the big render. A 3D still is measured against the pack
(background colour and brightness, accent share, dark share); `crewcut render measure <png>` does the same for any
still. A check without a target in the pack is reported, not judged.

Draft quality: `--draft` renders with 32 samples and denoising. It is fast but not the final look: soft shadows and
depth of field suffer. Eevee as a draft renderer is planned.

## The cut

`crewcut render cut <plan>`:

1. Picture pieces: the video is split at every cut and every overlay edge. Each piece is one ffmpeg run into
   `<output stem>.pieces/` (speaker with zoom held on `face`, a full-frame insert, a clip, or the generated
   background; overlays laid on top already here). Unchanged pieces are reused next time.
2. Sound in its own run: the voice (or the base's sound), the music bed looped (or up to `sound.music_until`), ducked
   under the voice and with gaps before strong moments, hits, typing and whooshes, the approved effect layer, then a
   limiter.
3. Loudness in two passes to the pack's target (`loudness_lufs`, neutral -14 LUFS). AAC raises the true peak by 0.5 to
   2 dB, so the sound is encoded, the true peak measured, and the limiter lowered until it stays under the pack's
   `true_peak_db`.
4. Picture and sound together (H.264, CRF from the plan, fast start). `<output stem>.cut.json` lists the shots,
   loudness before and after, the true peak, the music source and every note.

Sound effect files are made by code at first use: Crewcut's sound kit (`crewcut/motion/sfx.py`, NumPy only)
writes `whoosh`, `tick`, `typing`, `pop`, `click`, `hit`, `riser`, `reel_tick` and `bell` as 48 kHz WAV files into
`studio/.crewcut/sfx/`, with `kit.json` (kit version, seed, sha256 per file). The repository holds no audio file.
Your own files win: the plan names them (`hit_file`, `typing_file`, `whoosh_file`, relative to the episode) or the
pack does (`edit-style.json` `"sounds": {"hit": "...", "typing": "...", "whoosh": "..."}`, relative to the pack).
Only when neither names a file does the cut take the kit's `hit`, `typing` or `whoosh`, with a note. A file that is
named but missing is skipped with a note. Nobody has listened to the kit yet: [sfx-listening.md](sfx-listening.md).

After the user has seen an output, `crewcut render shown <plan>` writes `<output>.shown`:
`{"at": "2026-11-16T10:00:00Z", "sha256": "<64 hex>"}`. From then on `cut` refuses to overwrite it. Every change is a
new plan version with a new output.

## Shorts: capture, music, proof-top layout

A Short is a portrait plan (`"format": "portrait"`, 1080 x 1920). Three tools exist only for it. Their values come from
the `shorts` block of `edit-style.json`.

### Capture: proof material recorded upright

```
crewcut render capture <episode> --url https://example.com/ --seconds 8 --scroll 0:0,1.5:0,7:end [--hide-overlays]
crewcut render capture <episode> --html results.html --seconds 5 --size stage
crewcut render capture <episode> --terminal session.txt [--type-speed 20] [--line-delay 0.35]
```

- Writes `broll/<name>-vNNN.mp4` in the episode (the next free version, never overwritten) and `broll/<name>-vNNN.json`:
  source address or file, seconds, size, scroll keys, the time of the capture, the page title and its warnings. Name
  it in the Short's sources; the Critic can check it.
- Page: `tools/capture_page.js` opens it in Chromium with a phone-sized viewport (`--zoom 2.5`: 432 x 768 CSS pixels
  at device scale 2.5), so the page lays out like on a phone and every text is 2.5 times bigger. One screenshot per
  video frame: the scroll is exactly even, eased in and out, in whole device pixels. The page's JavaScript clock is
  paused and advanced one frame per screenshot; CSS animations are slowed to the measured capture speed; videos on the
  page are set to each frame's time. Scroll keys are `second:position`, position in CSS pixels, `end` or `40%`.
- Terminal: a plain text transcript. `$ ` starts a command, which is typed; other lines are output and appear at
  once; `[+1.5]` before a line waits 1.5 s. The page uses the pack's colours and mono font (at least `min_text_px`)
  and keeps text out of the right `right_free_frac` (the platform's buttons) and, at full size, out of the top 8 % and
  bottom 20 %.
- `--size stage` records 1080 x 960, the stage of the proof-top layout, so nothing is cut away there.
- Colour range: the screenshots (RGB, white 255) are converted once, explicitly, to limited-range BT.709 yuv420p,
  the range of every other piece of the cut, and the stream is tagged so. Decoded, white stays 255. (A full-range
  browser recording joined with limited-range pieces turned white into 232 in an earlier studio.)

### Music bed: licensed music under the voice

```
crewcut render music-bed audio/voice-v001.wav --music audio/music/track.wav --start 12 --punch 8.4,21.0
```

- Refuses a track without a licence. The licence comes from `<track stem>.source.json` next to the track,
  `--source info.json` or `--licence`: `{"licence": "CC0 1.0", "credit": "Music: ...", "made": "how it was made"}`.
  The music of a long video is no exception: it is used only when its licence is stated.
- The music sits `music_db` (neutral -15 dB) below the voice's measured loudness, ducks under speech (sidechain
  compression keyed by the voice), has a hole of `music_hole_s` (0.5 s) before each `--punch` time and comes back on
  the punchline, fades in and out, and runs `end_tail_s` (1 s) past the voice. A track shorter than the Short loops.
- Loudness: the first pass aims `limiter_headroom_db` (1.4 dB) above `loudness_lufs` (-14), because the limiter takes
  about that much back; then measure, correct and repeat until the result is within 0.5 LU and the true peak is under
  `true_peak_db`.
- Writes `<voice stem>-bed-vNNN.wav` (24 bit, 48 kHz) and `<same>.music.json`: track and its sha256, start second,
  licence, credit line for the description, how the track was made, how the bed was made (levels, holes, passes), and
  a list of places for a person to listen to (holes, loop point, fade). Use the bed as the plan's `voice` without a
  `sound.music`, and put the `.music.json` path into `sound.music_source`.

### Layout "proof-top"

`"layout": "proof-top"` in a portrait plan (or `shorts.layout` in the pack; landscape plans are always `full`):

- A full-frame insert (2D scene, clip, 3D) is the proof on a stage at the top, 1080 x 960; the speaker is cropped
  around `face` into the 960 px below. Without an insert the speaker fills the frame.
- Per insert: `"fit": "cover"` (default: fill the stage, crop the rest; `"anchor": "top"` keeps the top of a tall
  capture) or `"contain"` (the whole picture as a card on `stage_color`, default the pack's `soft`; for the episode's
  landscape 3D render). `"place": "full"` lets one insert cover the whole frame, e.g. an end card in the tail.
- The last `end_face` seconds of the speaker cut (plan, else `shorts.end_face_s`, else 2 s) show the face alone: a
  stage insert that reaches into them stops there, and `<output>.cut.json` says so in its notes.
- Keyword chips in portrait plans default to the left of the free right strip (`right_free_frac`, 0.18): centre at
  0.41 of the width, at most 0.74 wide; in proof-top they sit on the seam between stage and face. `plan` warns about a
  keyword whose centre lies in the strip.
- 2D scenes render at 1080 x 1920 and are cropped to the stage (`cover`) or shown whole as a card (`contain`); a
  stage-sized 2D format does not exist yet.

## The brand preview

`crewcut brand preview [--out file.mp4] [--pack DIR]` builds 10 seconds in the active style pack: a headline card,
a counter and a keyword over a plain background in the pack's colours (no stock footage), cut by the same workbench.
Onboarding shows it on the profile card. It is cached per pack look: the same pack gives the same file without
rendering again. Default output: `studio/.crewcut/preview/preview.mp4`.

## Try it: the demo

`examples/demo/` is a small episode in the neutral style with a generated background, a words file, six 2D inserts
and two motion graphics (`number_roll` full frame and a `keyword_pop` overlay, both with sound; no media files, no
3D). Without `effectcraft-cli` the demo still renders and leaves the two motion graphics out (it says
`"motion_without_engine": "skip"`). Copy it into the studio and render it there (renders never go into the
repository):

```
cp -r examples/demo studio/episodes/000-demo
crewcut render plan studio/episodes/000-demo/edit/plan-v001.json
crewcut render all  studio/episodes/000-demo/edit/plan-v001.json --local
```

## What the container needs

System: `ffmpeg` (with libx264, AAC, qtrle and the ebur128, loudnorm, sidechaincompress, alimiter filters), Node.js 20
or newer, Chromium through `npx playwright@1.50.1 install --with-deps chromium` (or a system Chromium in
`CHROMIUM_PATH`), the Inter font (`fonts-inter`), Blender 5.0.1 on amd64 (`blender` on `PATH`, or `CREWCUT_BLENDER`),
`effectcraft-cli` for motion graphics (`EFFECTCRAFT_CLI` or `PATH`; pinned in `third_party/effectcraft`).
npm: `playwright-core` 1.50.1 in `tools/` (`npm ci` there). Python: Pillow and NumPy (already in `pyproject.toml`).

## Status

Tested: plan parsing, cues, sound references, cache keys, the shown lock, every ffmpeg and Blender argument list, the
batch queue and a rented run against a fake compute session, the rent-or-local card, the preview and the samples
command with fake programs; every 2D scene's script runs through every frame in a DOM without layout; every 3D scene
runs through every frame against a stand-in for Blender. Shorts: the capture's argument lists with a fake browser,
the terminal page through every frame in a DOM, the colour range (white stays 255) and the stacked proof-top pieces
with the real ffmpeg on tiny generated clips, and one real music bed of sine waves (level under the voice, ducking,
hole, loudness).

Motion graphics: the plan (templates, versions, word anchors, cues in seconds, cache key, checks, sound events)
and every engine argument list with a fake engine, the chunks and frame names, the font folder and its variable, the
speaker backdrop's ffmpeg command, and the rented run with a fake compute session. With the real engine, only in the
image: `tests/render/test_motion_engine.py` (a pack font changes the glyphs, a backdrop's first frame equals the
speaker frame, an overlay MOV has alpha) and the motion part of `tests/smoke/render.sh`. No motion graphics speed is
measured yet.

Not tested here: the capture's browser part (`tools/capture_page.js` with Chromium, its clock, CSS-speed and video
handling) runs only in CI or on a real machine; how a real voice and real music sound together needs a person to
listen.

Untested here (by rule, nothing renders on the author's laptop): real Chromium renders, real Blender renders, real
ffmpeg runs, real rented machines. The CI image renders the 2D samples and the preview; the first real 3D probe
decides whether the 3D scripts need fixes for the Blender 5.0 API.

### Blender plates of motion inserts

A motion insert may list `plates` (Blender scripts that render image sequences the comp lays in: a heavy 3D word,
a logo that catches light). `crewcut render plates <plan> [--probe]` renders every missing plate into
`render/plates/<insert>-<plate>-<hash>/0001.png …`: on a computer with its own NVIDIA GPU here, otherwise on one
rented RTX 4090 after a spend card (only the plate scripts, their arguments and the pack's font files go up). A plate
script takes `--out DIR --frames A-B` plus its own arguments, with times in the comp's seconds (frame `f` shows comp
time `t0 + (f - 1) / fps`). The hash covers the script, its arguments, the look tokens and the fonts. The comp reads
the plates from `CC_CTX.plates` (`{id: {"first", "frames", "ready"}}`); `render all` renders plates before the motion
inserts. Code: `crewcut/render/plates.py`.
