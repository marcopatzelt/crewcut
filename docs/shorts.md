# Shorts

A Short is its own small episode in portrait (1080 x 1920) with fewer steps. Two modes:

| | **Clip**: from a finished episode | **Original**: recorded for itself |
|---|---|---|
| Material | an episode you already recorded | what you really did, told in 30 to 50 seconds |
| What you do | one yes | pick an idea, talk freely, record yourself |
| What for | bring viewers to the long video | test quickly what lands, reach on your own |
| Steps | Idea, Title, Edit, Thumbnail, Upload, Results (6) | Idea, Title, Proof (optional, off by default), Script, Record, Edit, Thumbnail, Upload, Results (9) |

Start one by saying it ("make shorts", "make a short about …", "clip episode 3"), or:

```bash
crewcut episode new "Five models, one laptop" --short clip --from 003-local-llms
crewcut episode new "Claude built my site" --short original
```

The crew's know-how is in [`skills/shorts/SKILL.md`](../skills/shorts/SKILL.md); the values are in your style pack
(`edit-style.json` → `shorts`).

## Clip

1. **Candidates.** The Scout reads the finished episode's transcript and graphics plan (and the retention curve, when
   the video is online and YouTube is connected) with `crewcut cut candidates`, and proposes the best three on one card:
   title, first sentence, length, a still, strength and effort.
2. **Rough cut.** The Editor writes the pieces to `edit/pieces-vNNN.json` (`source_episode`, then `pieces` by start and
   end word or phrase, or by `from`/`to` seconds on the finished cut) and runs `crewcut cut short edit/pieces-vNNN.json`.
   It maps every piece back to the original recording through the episode's edit decisions (never the scaled video),
   crops 9:16 around your face, takes the episode's clean voice, levels it to the Short loudness, and makes new word
   times (`--words carry` keeps the old ones). A piece over a cut boundary stops the run with its name. A crop too
   small for a sharp portrait (608 px from a 1080p original) stops before anything is built, unless `--accept-soft`.
   Outputs: `work/speaker-vNNN.mov`, `audio/voice-vNNN.wav`, `work/words-vNNN.json`, `work/short-cut-vNNN.json`.
3. **Graphics and music.** 2D scenes again in portrait; screens and web pages recorded again in portrait
   (`crewcut render capture`); 3D of the episode as a card or layer. Music only with clear rights and a source file
   (`crewcut render music-bed`), ducked under your voice with a short hole before the punchline. Or, when your rules say
   so, a dry Short: `"sound": {"bed": "dry"}`, voice and room only, at most two quiet pops from the approved effect
   layer.
4. **Check.** The Critic runs the Short rule set (`crewcut cut short-check <video>`): face in frame, no text over the
   face or the right edge where YouTube's buttons are, brightness, length and pace, loudness with limiter headroom,
   piece boundaries at the audio level. It writes `review/short-check-<name>.json`, a 24-frame contact sheet and a
   "please listen" list with time stamps for you. 0 errors is what the standing approval needs.

## Original

1. **Ideas.** Three, each with a first sentence, the proof that will be in the picture, the form and the evidence from
   data. No proof from your real work, no idea. Data suggest; you decide.
2. **You talk, the Writer shortens.** Two to three minutes into the composer's microphone, along four questions (what
   you did, what you thought before, what went wrong or surprised you, which number you have). The Writer keeps your
   words, checks them with `script_check.py --short`, runs the Humanizer pass, and the card's button is "This really
   happened".
3. **Record only yourself.** The crew brings the B-roll: the real proof, 2D scenes, 3D only if your pack has it.
   Layout `shorts.layout`: `full`, or `proof-top` (proof above, face below).

## Publishing

- **One card per Short**, like every video. Or your own **standing approval** for Shorts: the quiet second button on a
  Short's publish card ("Publish this and all future Shorts without asking"). It is never on by default and covers only
  Shorts, only after the Short check found 0 errors, never with someone else's material or a person, and not the
  first Short after your style pack changed. The profile shows "Shorts are published without asking, since …"; say "ask
  me again for Shorts" to switch it off. A crew member cannot switch it on: it can only propose the card.
- **Private first.** Every Short is uploaded private, read back (title and description), and only then made public or
  scheduled. If anything differs, it stays private and the chat says what.
- **When.** At most `shorts.per_day_max` (2) a day at `shorts.publish_times` (12:00 and 18:00 in your channel's time
  zone), never two Shorts with the same message on one day (`crewcut shorts slot`). "All at once" is one sentence.
- **Link to the long video.** Through the API Crewcut puts it into the description and a comment. YouTube's "Related
  video" field and pinning a comment have no API: the chat tells you to set them in YouTube Studio.

## Results

After 48 hours `crewcut shorts results` adds a row to `studio/shorts.tsv`: mode, form, length, captions, first sentence,
views, average view percentage, subscribers (YouTube Analytics API). From ten Shorts on, the Scout may propose a rule
from your own numbers as a card. Before ten it says nothing about patterns.

## Style pack values (`edit-style.json` → `shorts`)

| Key | Default | What |
|---|---|---|
| `length_s` | [30, 50] | length in seconds |
| `words` | [110, 170] | words of an original script |
| `layout` | `full` | `full` or `proof-top` |
| `captions` | `keywords` | `keywords` or `words` (a test, not a rule) |
| `max_still_s` | 2.5 | longest picture without a change |
| `text_cards_max` | 3 | text cards per Short |
| `loudness_lufs`, `limiter_headroom_db` | -14, 1.4 | target and the headroom the limiter takes |
| `music_db`, `music_hole_s` | -15, 0.5 | music under the voice, the hole before the punchline |
| `end_tail_s` | 1.0 | tail after the last word |
| `right_free_frac` | 0.18 | right edge kept free for YouTube's buttons |
| `min_mean_luma` | 40 | darker footage fails the check |
| `per_day_max`, `publish_times` | 2, 12:00 and 18:00 | publishing slots |
| `end_face_s` | 2.0 | `proof-top`: the end on the face alone |

## Honest limits

- Built and unit-tested; no Short has gone through Crewcut end to end yet. Portrait capture and the browser parts run
  in CI only so far.
- A fixed crop needs you near the middle of the picture; a crop that follows a moving speaker is planned.
- The face box, the text boxes, still and cut thresholds and the candidate score are heuristics; the Critic's listening
  list exists because only you can judge the sound.
- Screen captures convert to limited range (BT.709) like every other piece of the cut, so white stays white.
- The starting values come from the author's thirteen clips and one large US channel. Your own table moves them.
