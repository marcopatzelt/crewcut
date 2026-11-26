# Sound, music and rented GPUs

## A. Music

Nobody in this flow can hear. Every choice comes from measurements, and every result ends with a listening list for
the user.

The pack decides the kind of music (`edit-style.json`, `music`: `none`, `generated` or `own`). With `own`, the user's
files sit in the episode or the brand folder, with their licence. Never use a piece without cleared rights.

Generated music (the studio did this by hand with an open music model on a rented GPU; in Crewcut it is **planned**
as a compute job):

1. **Parts along the story:** 4 to 6 parts (opening, build-up, lift at the reveal, quiet reflection, resolution),
   several seeds each, each a bit longer than its section. **All parts at the same tempo and in related keys**, or no
   transition works. Prompts name instruments and mood, never an artist, a film, a game or a studio. Every prompt adds:
   instrumental, no vocals, dry, leaves room for a speaker.
2. **Choose by measurement:** no recognisable words, low vocal share, the planned tempo, a calm level, little energy in
   the speech band (300 to 3400 Hz). A pulse is welcome in work and lift parts, not in quiet ones.
3. **Join the parts at sentence pauses** (word anchors), with an equal-power crossfade of about 1.5 s and the beats of all
   pieces on one grid.
4. **Write the source note** (`audio/music-source.md`): model and its licence, prompts, the candidates with their
   values, the choice, and the listening list with times (start, every transition ±2 s, the music gap, the end). Point
   `sound.music_source` in the plan at it. Without it the style check reports `music-rights` as an ERROR.
5. A piece from the shown game or app under its scene: only at the same tempo and a related key, and the bed goes down
   by about 10 dB there. Put it on the listening list.

## B. Levels in the cut

- `sound.music_db` and `sound.duck` default to the pack (`music_db`, `duck`). Ducking lowers the music by a few dB
  while someone speaks.
- Target loudness `loudness_lufs`, true peak at most `true_peak_db`. AAC encoding raises the true peak by 0.5 to 2 dB:
  the assembly encodes the sound first, measures the peak, and limits lower if needed.
- A hit only at strong spots, typing under counters, a short gap in the music before the most important number
  (`sound.gaps`, `sound.hits`, `sound.typing`, `sound.whooshes`).
- Sound effect files are made by code: when neither the plan (`hit_file`, `typing_file`, `whoosh_file`) nor the
  pack (`edit-style.json` `sounds`) names a file, the cut uses Crewcut's sound kit (`studio/.crewcut/sfx/`, made at
  first use; no audio file in the repo). Nobody has heard the kit yet: put its sounds on the listening list
  (`docs/sfx-listening.md`). No riser in a talk segment, and no effect on top of a speech peak.

## B2. Switches a channel's rules can ask for (per plan)

The channel's rules (`brand/rules/cut.md`, `edit.md`) say when to use them; without them the cut keeps the old way.

- **Music only in the opening** (`sound.music_until`): the bed stops at that moment instead of running to the end.
  Give it as a word anchor on the first words of the first content (`{"word": "...", "offset": -0.3}`; the Writer marks
  them below the script's `---` as `[[first content | "..."]]`), as an insert reference (`"ch1"`: the chapter card)
  or in seconds. `sound.music_out` says how it stops: `"fade"` (default, `sound.music_fade` seconds, 1 to 2) or
  `"whoosh"` (a hard stop with a whoosh on that moment, best on a chapter card). Ducking and gaps still work before the
  stop. A later quiet bed under a picture-only stretch is a second plan entry only when the rules allow it.
- **A dry Short** (`sound.bed: "dry"`): voice and room only. No music bed step, no `sound.music`, no
  `music_source`; the cut leaves out hits, typing and whooshes and says so. With the approved effect layer it gets at
  most two quiet pops on a number or the result.
- **The effect layer on picture events** (`sound.events: "auto"`, module `crewcut/render/sfx_events.py`): a quiet
  effect only where something appears: a pop for text and for a number (on its landing cue), the same whoosh-and-pop
  pair on every part change (`"sfx": "part"` on the insert that shows the chapter card when it is not a
  `chapter_card` template), a swoosh on a B-roll change. At most 6 a minute, at least 1 s apart, moved up to 0.2 s off
  a loud syllable or left out, never a riser or a hit. `"sfx": false` silences one insert. While the layer is on, the
  inserts' own template sounds are left out (no double effects); the plan's own `hits`, `typing` and `whooshes` stay.
  It runs only when the user approved the exact effect set (`crewcut render sfx-sheet`, `docs/sfx-listening.md`);
  until then the cut runs without it and its notes say so. Never approve it yourself.

## C. Rented GPUs

Tools: `crewcut compute estimate|rent|run|fetch|destroy|guard|ledger`. `crewcut render 3d --rented` and `probe` use
them. Only an identity with `may_spend: true` rents, and only after a spend card was accepted.

**Build cheap, render expensive.** Build the scene, previews and tests on this machine or on ONE rented RTX 4090. Rent
several GPUs only for the final render of an approved scene (`crewcut render 3d --rented` does this with `--final`
inside; by hand `crewcut compute rent --gpus N --final`), and let them go right after. A machine that runs nothing for
a few minutes is deleted: do not rent first and think later. Never ask for an RTX 5090 or bigger yourself; only when the
user names one (`--gpu "RTX 5090"`). The price cap per GPU-hour ($0.60 by default) is hard. Put the estimate's
`idle_note` on the spend card: it says honestly what waiting would cost.

The cost card: run `crewcut compute estimate --kind blender --frames N`, write one sentence with the amount and what it
buys ("Rent 3 GPUs for about 25 minutes, about 1.20 USD, for 840 frames of 3D"), propose it with
`crewcut card propose --kind spend`, wait with `crewcut card wait`. Declined (exit 3): render locally, render fewer
frames, or drop the scene.

Pitfalls the studio met, and what to do:

| Pitfall | Sign | What the tools do / what you do |
|---|---|---|
| Machines in the account that are not ours | the list shows machines you did not rent | every machine carries our label; `destroy --all-ours` deletes only those. Never delete without a label or id |
| Host breaks large uploads | "connection reset" | test every new machine with a small real upload first; on failure destroy it and take another host |
| Image still loading | not reachable after a few minutes, status "loading" | wait for the status, do not rent a second one at once |
| Broken GPU driver | CUDA errors, no GPU visible | check the GPU before any large download |
| Slow host | probe frames take several times longer | fetch every probe frame at once; take the next offer; remember the host as bad |
| Package hangs | no new frame for three times the median | time limit per package; the package goes to another machine |
| Two of our machines on one host | | one offer per host |

- Order: start the machines, then keep working locally (plan, 2D, cut). Never wait idle.
- Every few minutes look at the log and `crewcut compute guard --once`. A machine without load and without progress
  costs money: find out why or destroy it.
- Only scene code, fonts and prompts go to a machine. Never footage, the recorded voice or keys.
- **Bookkeeping:** `crewcut compute ledger --episode ID` before and after; the difference goes into the report.
- **Proof at the end:** `crewcut compute destroy --all-ours`, then the guard shows no machine of ours. The output goes
  into the report, also after a failure.
- Rough values from the studio (not measured in Crewcut): a probe frame at half size takes seconds on a large consumer
  GPU, a full frame up to about half a minute; several GPUs share a long scene well.
