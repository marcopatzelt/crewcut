# From the recording to the speaker cut

In the desktop app, the crew can browse computer media and connected cards with
`crewcut media sources`, then copy selected takes before ingesting them. Additional
folders connect through **Media folders** in Episodes. See [computer media](desktop-media.md).

This page covers step 5 (`record`) and the first half of step 6 (`edit`): what to do before you record, how Crewcut
saves and checks the files, how it finds what you said, and how it builds the speaker cut that the edit plan stands on.
The agent rules for the same steps are in `skills/edit/references/record-to-cut.md`.

All paths are relative to the episode folder `studio/episodes/<id>/`. Every command prints plain text, or JSON with
`--json`. Exact arguments: `crewcut cut <tool> --help`.

## Before you record

- **Teleprompter.** `crewcut prompter <episode>` prints a link and a QR code. Open it on your phone. It shows the
  script as full text or as points only, in numbered speaking blocks (one paragraph each; a line marks a new section).
  A second phone or the desktop can be the remote. Tap a block, or use **Previous**, **Repeat** and **Next**, and every
  screen jumps to the start of that block at once. Say a block as often as you like: the editor cuts between blocks
  and picks the take (the last complete one, unless you say otherwise).
  Every jump, repeat, play and pause is written with its UTC time to `brief/prompter-log-<date>.jsonl`, so the editor
  can find where each block's takes start.
- **Focus.** Fix the focus on your face (manual focus or face tracking). Record ten seconds and look at them sharp on a
  big screen before the real take.
- **Microphone.** A clip-on radio microphone into the camera is the safe default. Most receivers put the voice on one
  channel; Crewcut finds that channel and puts it on both sides. Switch on the transmitter's own backup recording if it
  has one. Record ten seconds and run `crewcut cut audio <file>`: it must not say "camera microphone".
- **Never record the voice only over Bluetooth.** A Bluetooth headset sends phone-call quality (no energy above about
  7.5 kHz). No equaliser can repair that.
- **Say a sentence again until it sits.** Crewcut takes the last full attempt of every sentence. You can talk to the
  editor while recording; these phrases are understood (English and German built in, more in `config/speech.toml`):

  | You say | What happens |
  |---|---|
  | "scratch that", "once more" | the attempt just before is thrown away |
  | "take the first version" | the first full attempt of that sentence is used, not the last |
  | "leave that out", "take this part out" | the sentence just before is left out of the video |
  | "keep that", "that part was good" | the attempt just before is used |
  | "I'll just read on" | nothing; the script goes on |

  The instruction itself never goes into the video.

## Ingest

```
crewcut ingest <episode> <file> [<file> ...]      files from a mounted card or folder
crewcut ingest <episode>                          everything dropped into the browser (studio/inbox/<episode>/)
```

- Each file goes to `originals/<first 12 characters of its sha256>-<name>`. Nothing is ever overwritten. Running ingest
  twice on the same file says "already saved".
- A mounted card or folder is only read. Files from the inbox are moved (on the same disk this is instant), so a 4 GB
  file does not take the disk twice.
- The copy is verified: the file is hashed while copying, and the copy is hashed again.
- `brief/ingest-<time>.json` holds, per file: the sha256, size, length, recording time, the probe, and the results of
  the checks below. Its `warnings` list is what needs action now.

### What the checks mean

**Microphone check** (two minutes from 30 s in, both channels):

| Result | Meaning |
|---|---|
| External microphone on the left/right channel | Normal for a radio microphone. Plan and build use that channel on both sides. |
| WARNING: both channels alike and quiet | Probably only the camera's own microphone recorded. Check receiver, transmitter and the transmitter's backup before you record more. |
| Sound on both channels | A stereo source; nothing to do. |

**Sound to the end** (level of the louder channel in 10 s windows over the whole file): "sound until X s of Y s, then
Z s of silence". A few seconds of silence after the last sentence are normal. **More than 30 s is a WARNING.** It
happened in a real episode: the radio microphone stopped 110 s before the end of a file while the speaker went on; nobody
noticed until the cut. On this warning, look at a frame after X s at once. If someone still speaks there, the sound is
missing and that part has to be recorded again. Before you say so, check the ways out: is the sentence in another file,
or does the other channel carry the camera microphone (raise it by 40 dB: if the level does not move with speech, it is
only noise)?

**Split recordings.** Cameras split a long recording at about 4 GB. Two files with consecutive numbers are one
recording when the first file stops at about 4 GB and the second starts within 3 s of the first one's end (GoPro
chapters always are). Ingest lists them under `recordings`. Then there is no "better take" to choose between them.

**HDR.** An HDR recording is noted. The cut refuses it until the colour conversion is decided; nothing is converted on
its own.

## What was said

Two ways; use both.

```
crewcut transcribe originals/<file>                         fast: every word with its time, whole file
crewcut cut islands <episode> originals/<file> --words work/words-<name>.json --fill
crewcut cut islands <episode> originals/<file> [--from S --to S]    exact: every speech island read on its own
```

- `crewcut transcribe` uses faster-whisper with word times and writes `work/words-<name>.json` in the edit plan's words
  format `[{"w": "...", "s": 1.23, "e": 1.5}]`. For the voice track of cut version NNN (`audio/voice-vNNN.wav`) the file
  is `work/words-vNNN.json`, which the edit plan reads. Model, device and language come from `config/speech.toml`; the
  language defaults to the style pack's `channel.language`. A very quiet file (under -25 dB) gets 14 dB of gain first.
- Pauses come from the microphone channel at 16 kHz (`work/raw/<stem>-16k.wav`, pause list `work/raw/<stem>-silence.txt`).
  The speech between two pauses is an **island**. `work/<stem>-islands.json` holds `{"source", "islands": [{"start",
  "end", "text", "source"}]}`.
- **Trap:** whole-file recognition leaves out whole sentences and invents others ("thanks for watching"). `islands`
  lists every island over 1 s without words; `--fill` reads exactly those one by one. `transcribe` flags known invented
  phrases with their time.
- **Cut edges always come from islands or measured dips, never from word times.** Word times drift; they are for
  finding things.

## The speaker cut

```
crewcut cut takes <episode> [--script brief/SCRIPT-vNNN.md] [--take originals/<file> ...]
crewcut cut dips <episode> originals/<file> START END       (also: crewcut cut islands dips ...)
crewcut cut probe <episode> originals/<file> START-END ...  (also: crewcut cut islands probe ...)
crewcut cut doubles edit/selects-vNNN.json                  exit 2 = a doubled sentence start
crewcut cut plan edit/selects-vNNN.json
crewcut cut build edit/cut-plan-vNNN.json [--reuse vOLD | --resume]
crewcut cut verify work/edit-decisions-vNNN.json            exit 2 = edges, joins or channels to fix
crewcut cut grade check|apply <episode> work/speaker-vNNN.mov ...
crewcut transcribe audio/voice-vNNN.wav                     words of the finished cut
crewcut cut srt work/edit-decisions-vNNN.json               subtitles for the final
```

1. **Takes.** `cut takes` lines up every attempt of every script sentence across all takes (in recording order) and
   picks one: the last full attempt, unless you said otherwise while recording. It writes a draft
   `edit/selects-vNNN.json` and `review/takes-vNNN.json`, and prints per sentence: time, text and verdict of every
   attempt (full, broken, scratched), what was chosen and why, where you said something different from the script (what
   you said wins; the select keeps the script's spelling where both agree), the spoken instructions found, and the
   **pickup list**: sentences without any full attempt. Sentences you said in one go stay one select. The agent checks
   the draft before building; the selects file is the place to correct it.
2. **Edges inside an island.** A select marked `"check": ["start"]` or `["end"]` begins or ends between two words
   without a pause. Measure the dip there (`cut dips`: usable is under -40 dB for at least 0.06 s) and read the edge
   (`cut probe`: the text must hold the whole first and last word). Never start in the middle of a flow of speech; take
   a whole sentence from another take instead.
3. **Doubled starts.** `cut doubles` reads every short piece (under 2 s) that another piece follows inside the same
   select and compares the first two words. Recognition over the whole cut misses this ("so I built ... so I built"),
   so run it before every build. Fix: start the select at the time it names. `--fast` uses the words files only.
4. **Plan.** `cut plan` applies the cut rules: edges reach 0.12 s / 0.16 s into real silence and never into the next
   word; until the first content (`first_content`, else the first 25 s) inner pauses over 0.7 s shrink to about
   0.26 s, after it natural pauses up to 1.0 s stay, also between two selects that follow each other in one take
   (before 26 Nov 2026: every inner pause over 0.30 s shrank); one select may ask for a deliberate pause of 1.5 to 3 s
   before it (`pause_before`); every second cut inside one take punches in to hide the jump;
   a one-sided microphone goes on both ears; locked ranges and music length are checked (exit 2 with the problems).
   Selects can set `hard_end` (no pause after the last word), `tail` (picture after the last word, voice faded out),
   and per take `face`, `lock`, `zoom_factor` (a pickup filmed from further away) and `audio` (a separate recorder).
5. **Build.** `cut build` writes `work/cut-vNNN/NN-<id>.mov` (one clip per cut), `work/speaker-vNNN.mov` (the speaker
   picture: the edit plan's `base`), `audio/voice-vNNN.wav` (cleaned and levelled voice: the edit plan's `voice`) and
   `work/edit-decisions-vNNN.json`. It stops on HDR, a wrong aspect ratio, a cut past the end of its source, or a
   one-sided voice. `--reuse vOLD` hard-links the clips that did not change from an older version; `--resume`
   continues an interrupted build.
6. **Verify.** `cut verify` reads every clip on its own and writes `work/cut-verification-vNNN.json`:
   `issues` (missing, extra or changed words against the expected script; "replace" is often only spelling),
   `edge_issues` (first or last word of a select differs), `joins` and `bad_joins` (the pause at each cut must be
   0.17-0.45 s; shorter sounds chopped, longer sounds like a gap; a join that continues its take and the deliberate
   pause are measured against their planned length), and the channel levels. A pause too short: give the
   select before a `tail` of about 0.24 or move its end into the silence. Too long: start the next select at the real
   start of speech. Each fix is a new version: collect all findings first, then build once.
7. **Grade.** `cut grade check` makes before/after stills, one sheet and numbers per still in `review/grade/`, with a
   verdict per target (neutral wall, skin luma 140-190 and in order R > G > B, no crushed blacks, no clipped highlights).
   `cut grade apply` bakes the filter into `work/speaker-graded-vNNN.mov`. Every episode gets its own measured grade.
8. **Subtitles.** `cut srt` takes the text from the selects (right spelling) and the times from the decisions; with
   `work/words-vNNN.json` the block borders sit on word times. Build them on exactly the speaker cut the final uses,
   then check three blocks (start, middle, end) against the sound of the finished video.

Nothing is overwritten: plans, builds, decisions and subtitles refuse an existing file. Every change is a new version.

Taste values of the cut live in the style pack (`edit-style.json`, key `cut`): `speed` (default 1.0), `zoom_base`
(1.0 = full frame), `zoom_punch` (1.12), `face_y` (0.40), `join_min`/`join_max`, `pad_in`/`pad_out`,
`pause_gap_open` (0.7), `pause_gap` (1.0), `pause_keep` (0.13), `open_seconds` (25), `beat_pause_min`/`beat_pause_max`
(1.5/3.0), `voice_filter`. The grade's base filter is `grade_filter`. A selects file can override each.

## Speed: CPU or rented GPU

Honest numbers. They were measured with the earlier studio this code was ported from, on the author's laptop (no NVIDIA
card). Crewcut itself has not been timed yet.

| Work | Measured |
|---|---|
| Whole-file recognition (fast way) | about 2 minutes per 9 minutes of sound |
| Reading islands one by one (exact way) | 250 speech pieces took over half an hour |
| Build of a 3.5-minute cut | about 5 minutes; with unchanged clips reused, about 1 minute |
| Verify | about 6 minutes |
| Grade | about 3 minutes |

On a Mac, the container cannot use the Apple graphics chip, so recognition runs on the processor. That speed is
untested.

**Rented GPU** (`crewcut transcribe <file> --rented`, untested against a real provider): recognition runs on a rented
NVIDIA card with the same image. Crewcut's privacy rule sends scene code and fonts to rented machines, and media only after a card that names
the exact file (the voice here, a picture-only shot for the person matte), so this path
first asks for a yes on its own card: it extracts only the voice (16 kHz mono FLAC, no picture, no metadata) to
`work/upload/`, and the card shows exactly that file. Without a yes, nothing is sent (exit 3). Renting itself needs the
usual spend card and stays under the month cap. The machine is destroyed after the run. Without renting, everything
works on the processor; it only takes longer.

## Exit codes

`0` ok, `1` error, `2` usage, or a check that found something to fix (`plan`, `doubles`, `verify`, `loudness`),
`3` waiting for your yes or refused, `4` missing key (rented path).
# Register earlier recordings

Select a specific imported reading text with `crewcut episode recording-script <id> <file> [--partial]`.
The prompter follows that file rather than guessing by filename; a different approved script cannot be replaced
without review. `--partial` shows a visible warning on both the reading screen and remote. Selecting a file never
approves the script, marks steps done or starts work. Missing selected files fail instead of silently switching drafts.

After an offline studio import, `crewcut ingest <episode> --imported` registers recordings listed under
`01-originals/` or `originals/` in `legacy-import.json`. It verifies every file's size and SHA-256 and probes its
media information. Missing, changed or linked files stop registration without writing a report.

The resulting `brief/ingest-legacy.json` uses the native ingest schema and recording groups. Its file paths point
to the verified copies under `legacy/`; no second media copy is needed. Crewcut's cut commands can use these
episode-relative paths. A second registration refuses to overwrite the report.

Registration starts no jobs, transcription or audio checks and grants no approval. Microphone/full-track audio
checks and historical take-selection conversion remain necessary before editing. The original studio is untouched.
