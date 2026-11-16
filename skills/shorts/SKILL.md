---
name: shorts
description: "Makes YouTube Shorts in two modes: Clip (cut from a finished episode: candidates from the transcript and retention, a 9:16 rough cut from the original recording around the face, portrait graphics, music with clear rights, the Critic's own Short check) and Original (a Short recorded for itself: three ideas with a proof from the user's real work, the user talks freely, the Writer shortens, only the speaker is recorded, the crew brings the B-roll). Publishing: one card per Short, or the user's own standing approval for Shorts; at most two a day. Use when: \"make shorts\", \"make a short about …\", \"clip this episode\", \"short from episode N\", \"publish shorts without asking\", \"how are my shorts doing\". Not for long videos (skills/episode, skills/edit)."
---

# Shorts

A Short is its own small episode in portrait (1080x1920) with fewer steps. **Clip** comes from a finished episode and
costs the user nothing but one yes. **Original** is recorded for itself, to test quickly what lands. Data suggest, the
user decides: a strong idea that makes no sense to the user right now is dropped without discussion.

## Which mode (Showrunner)

| Situation | Do |
|---|---|
| An episode is cut | The Scout looks for clip candidates on its own; the card comes with or right after the preview |
| An episode has been online for two days and retention data exist | The Scout checks for a strong passage that is no Short yet; one card if so |
| "make a short about …" | Original |
| "make shorts", nothing more | One card: up to three clip candidates of the last episode and three original ideas |
| No video for a long time, none in work | Original ideas, at most once a week, unless the user switched that off |
| An original idea the user already said in an episode | Say so: "You already said this in episode 12. A clip takes no recording." |

Clip first when material exists. New Short: `crewcut episode new "<title>" --short clip --from <episode>` or
`--short original`. The step strip then shows only its steps (clip 6, original 9).

## Clip

1. **Candidates (Scout).** `crewcut cut candidates --episode <source>` lists stand-alone passages with times. A candidate
   needs: a first sentence that stands without the video before it and holds a claim or a result; a proof in the
   picture (a number, a comparison, a result), not only a talking head; a real end, never a sentence cut off in the
   middle; 20 to 55 s from at most about twelve whole sentences (they may come from different places). With retention
   data, prefer passages where the curve rises. Without data, say that you worked from the text only. Check that the
   originals and a clean voice exist before you propose a candidate.
2. **One card**, the best three: title, first sentence, length, a still each, strength 1 to 10 and effort (small,
   medium, large: is the footage there in portrait, or must screens be recorded again?). Button "Make these three".
3. **Rough cut (Editor).** `crewcut cut short` with the pieces by start and end word (or fixed seconds when word times
   are off): back to the original recording, 9:16 around the face, the episode's clean voice, new word times. A piece
   never crosses a cut boundary. If the original is too small for a sharp portrait crop (1080p landscape), say so
   before building, not after.
4. **Portrait graphics.** 2D scenes rendered again in portrait with the style pack. Screens and web pages recorded again
   in portrait (`crewcut render capture`), never the landscape picture cropped. 3D of the episode comes back as a card
   or a layer; new portrait 3D costs rent and needs a card. At most `shorts.text_cards_max` text cards; every picture
   understood within two seconds; symbols before text; calm motion (nothing that grows pixel by pixel).
5. **Music.** Only music with clear rights and a source file (`crewcut render music-bed`): under the voice at
   `shorts.music_db`, ducking, a short hole before the punchline. Never the long video's music unless its licence says so.
6. **Check (Critic).** `crewcut cut short-check`: the Short rule set (face in frame, no text over the face or the right
   edge where YouTube's buttons are, brightness, length and pace from the style pack, loudness with the limiter headroom,
   piece boundaries at the audio level). Look at the contact sheet; write the "please listen" list with time stamps for
   the user: nobody but the user hears the sound. 0 errors before the preview card.

## Original

1. **Ideas (Scout).** Sources: Shorts of the channels the user named, by views against the channel's median; what the
   user really did (recent episodes, tests, what they told in the chat). Never invent an experience. Forms that carry
   (Nate Herk's analysis of 50 Shorts, a US channel with over a million subscribers; a direction, not a promise):
   the Short is the proof ("Claude built this"), first choice; first-person story with a wow, second; someone else's
   story, possible; tool presentation and news, avoid; street polls, avoid. One card with three ideas: first sentence,
   the proof that will be in the picture, the form, the evidence from the data. No proof, no idea.
2. **The user talks first, then the Writer shortens.** Ask in one message for two to three minutes of free talk (the
   microphone in the composer), along four questions: What did you do? What did you think before? What went wrong or
   surprised you? Which number do you have? Keep the user's words and order them:
   I, event, number (the first sentence holds the whole conflict); a time anchor or a number in a series; what I
   thought; the turn, with the proof in the picture (a demo runs within five seconds); what I do differently now; a
   loose end. Length from `shorts.words` (default 110 to 170 words, 30 to 50 s).
3. **Check and humanize.** `python3 skills/script/scripts/script_check.py <file> --short` until 0 errors, then the
   Humanizer pass (skills/script). The script card's button is "This really happened": the user confirms the story
   is true (`--data '{"button": "This really happened"}'`).
4. **Record: only the speaker**, portrait or landscape with room to crop, from the teleprompter or from key points.
   Nothing else: no screen, no hands, no second angle.
5. **B-roll (Editor):** the real proof from the user's work (a portrait screen recording, a render, a number as a
   scene), 2D scenes in the style pack, 3D only if the pack has it (with the usual estimate). Nothing staged, no
   invented quote. Layout from `shorts.layout`: "full", or "proof-top" (proof on top, face below, the end on the face).
6. Check as in Clip step 6.

## Title, thumbnail, link to the long video

- **Title** with the usual title checks, shorter. The first sentence and the title say the same.
- **Thumbnail (Designer):** portrait with a free lower edge.
- **Link:** the package gets `related_url` (the long video) for clips; the upload adds it to the description and as a
  comment. "Related video" and pinning have no API: tell the user in one line to set them in YouTube Studio.

## Publishing

- One publish card per Short, unless the user switched on the **standing approval** for Shorts: the quiet second
  button on a Short's publish card, or `crewcut shorts standing on` (as a crew member this proposes the card; only the
  user's yes switches it on). It covers only Shorts, only after `short-check` found 0 errors, never with someone
  else's material or a person (`"third_party": true` in the package), and not the first Short after the style pack
  changed. Every Short goes up private, is read back, and only then becomes public or scheduled. Off: "ask me again
  for Shorts" → `crewcut shorts standing off`. With the standing approval the API is the right way: no hand on the file.
- **When:** `crewcut shorts slot --episode <short>` gives the next free time (at most `shorts.per_day_max` a day at
  `shorts.publish_times`, never two Shorts with the same core message on one day, pairs one after the other). "All at
  once" is one sentence from the user.

## Results

After 48 hours: `crewcut shorts results --episode <short>` adds a row to `studio/shorts.tsv` (mode, form, length,
captions, first sentence, views, average view percentage, subscribers). From ten Shorts on, the Scout may propose a
rule from the table as a card ("Your Shorts under 40 s keep 20 % more viewers. Make 40 s the limit?"). Before ten,
say nothing about patterns.

## Honest limits

- Built and unit-tested; no Short has been made end to end with Crewcut yet.
- A fixed crop needs the speaker near the middle; a crop that follows a moving speaker is planned.
- Retention data need the YouTube Analytics API (connected with YouTube).

## Sources

- Nate Herk (https://www.youtube.com/@nateherk): Shorts as proof; the form ranking above is our summary of an analysis
  of his 50 Shorts.
- Reel storytelling of Farza, Chris Raroque, Roy Lee, Riley Brown, Varun Mayya and Codie Sanchez (links in README):
  first person, the turn, uneven real numbers; the user talks, the agent shortens.
