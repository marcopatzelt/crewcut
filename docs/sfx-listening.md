# The sound kit: listening sheet

Crewcut's sound kit is made by code (`crewcut/motion/sfx.py`, NumPy only) the first time a cut needs it, into
`studio/.crewcut/sfx/` (48 kHz, 24-bit WAV, peak -1.5 dBFS each, `kit.json` with the kit version, the seed and the
sha256 of every file). The repository holds no audio file.

**Nobody has listened to these sounds yet.** They were checked by measurement only: length, peak level, and the
energy per frequency band and over time compared with the launch film's recipes they were ported from
(`examples/launch-film/sfx.py`). A person must listen to every sound below, on headphones and on a phone speaker,
before anyone calls them good. Write the result into the last column.

| Sound | File | Length | What it is for | Where it is used | Heard (who, date, verdict) |
|---|---|---|---|---|---|
| `whoosh` | `whoosh.wav`, stereo | 0.45 s | a keyword or lower third moving in, a camera move | the cut's `sound.whooshes` when no `whoosh_file` / pack `sounds.whoosh` is set (at -16 dB, 120 ms pre-roll) | |
| `tick` | `tick.wav`, mono | 0.07 s | one keystroke, or one step of a counter | not used by the cut yet; `crewcut.motion.sfx.kit_path("tick")` | |
| `typing` | `typing.wav`, mono | 1.2 s | a run of ticks 50 to 75 ms apart: typing under text, a counter rolling | the cut's `sound.typing` when no `typing_file` / pack `sounds.typing` is set (at -14 dB, trimmed to the entry) | |
| `pop` | `pop.wav`, mono | 0.11 s | something small appearing: an icon, a card | not used by the cut yet | |
| `click` | `click.wav`, mono | 0.13 s | a mouse click on screen (press and release) | not used by the cut yet | |
| `hit` | `hit.wav`, mono | 0.5 s | a soft low hit for a strong moment in a talk video, such as a number landing (not the film's big impact) | the cut's `sound.hits` when no `hit_file` / pack `sounds.hit` is set (at -9 dB, 40 ms pre-roll) | |
| `riser` | `riser.wav`, stereo | 1.0 s | the build-up into a reveal; ends hard. Not for talk segments | not used by the cut yet | |
| `reel_tick` | `reel_tick.wav`, mono | 0.05 s | a word reel or digit wheel arriving on its next item | not used by the cut yet | |
| `bell` | `bell.wav`, mono | 1.2 s | a "done" moment (D6 bell) | not used by the cut yet | |
| `pop_soft` | `pop_soft.wav`, mono | 0.09 s | text or a number appears (quiet, no click on top) | the effect layer (`sound.events`), -18 dB | |
| `whoosh_soft` | `whoosh_soft.wav`, stereo | 0.36 s | a part change, followed 0.22 s later by `pop_soft` | the effect layer, -20 dB | |
| `swoosh` | `swoosh.wav`, stereo | 0.24 s | a B-roll or picture change | the effect layer, -22 dB | |

What to listen for: clicks or pops at the start and the end of each file, a whoosh that hisses more than it moves, a
hit that disappears on a phone speaker, a typing run that sounds like a machine gun, any sound that covers speech at
the cut's levels (the voice at -14 LUFS, effects 10 to 14 dB under it).

## The effect layer's set: listen first, then say yes

The effect layer on picture events (`sound.events` in a plan, [rendering.md](rendering.md)) uses only `pop_soft`,
`whoosh_soft` and `swoosh`, at the levels of `edit-style.json` `sfx.levels_db`. It stays off until the user has
listened to exactly this set:

```
crewcut render sfx-sheet --voice episodes/<id>/audio/voice-v001.wav --start 30
```

writes `<studio>/library/sfx-sets/<set id>/` with each sound at its mix level, a demo under the voice with the six kinds of
moments, `index.html` to listen in a browser, and `set.json`. It prints the set id (`sfx-` and 12 hex characters, made
from the files and the levels). After listening, the user approves it:

```
crewcut render sfx-approve sfx-<id> --source "<name>, <date>, after listening"
```

which writes `sfx.approved_set` into the studio's `brand/edit-style.json`. A crew job cannot run it. A changed sound,
level or pair gap is a new set with a new id, and the layer is off again until the next yes.

To change a sound: edit its recipe in `crewcut/motion/sfx.py` and raise `KIT_VERSION`; every studio makes the kit again
at its next cut. A pack's own files (`edit-style.json` `sounds`) and the plan's (`hit_file`, `typing_file`,
`whoosh_file`) always win over the kit.
