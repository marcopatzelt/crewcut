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

## C. Rented GPUs

Tools: `crewcut compute estimate|rent|run|fetch|destroy|guard|ledger`. `crewcut render 3d --rented` and `probe` use
them. Only an identity with `may_spend: true` rents, and only after a spend card was accepted.

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
