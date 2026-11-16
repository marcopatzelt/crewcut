---
name: thumbnail
description: "Makes the YouTube thumbnail of an episode and its A/B test variants: picks a layout template from the style pack, gets a real still frame and a real result image, writes one complete new image prompt per variant, generates the images (crewcut thumbnail make, way codex or api), checks size, colours, face and words (thumb_check.py), and prepares the A/B test. Use for: thumbnail, thumbnail prompt, image prompt, still frame of me, thumbnail variants, A/B test thumbnail, test and compare, check the thumbnail, new thumbnail. Not for the title or the thumbnail text (skill title), not for the upload (skill upload)."
---

# Thumbnail

The Designer makes the image. The title step delivers the title and the thumbnail text (`brief/TITLE-vNNN.md`); the
upload step uploads. Layouts, colours, face rules, word limits and the reference photo come from the style pack
(`thumbnail.json`, colours from `brand.json`). Taste lives in `brand/rules/thumbnail.md`.

## Hard limits

- **Nothing changes on a live video without a card.** A new thumbnail, an A/B test or a title change touches the live
  video: every time a card, even when the user said yes before.
- **No money without a card.** Way `codex` uses the user's own Codex login. Way `api` is a paid image API: propose a
  spend card with the amount first and wait for it. Default to `codex`.
- **Never overwrite.** Every round gets a new folder `graphics/thumbnail/vN-<purpose>/`, one subfolder per variant
  (`A-<motif>/`, `B-<motif>/`). The scripts stop when a target file exists.
- **Only real things.** The person from the reference photo or a real still frame. Results as real screenshots from the
  video or the test. Only measured numbers.
- **Never edit text in a generated image by script.** A wrong image gets a new complete prompt.

## Rules

1. **One complete new prompt per variant, never an edit prompt.** Edits drift; a full prompt is repeatable. A disliked
   image gets a changed full prompt in a new run.
2. **Fixed images first.** Image 1 is the reference photo of the person (`thumbnail.json` `reference_photo`, a file in
   `brand/`). If the pack has a `style_reference` (the user's best own thumbnail), it is image 2 for style only: the
   prompt says what it takes (colours, light, type, face size) and that it does NOT take its layout. Then the results.
   A still frame (`still_frame.py`) only when the person needs other clothes or another pose.
3. **The face stays the person.** Slightly crisper eyes and a little more expression are fine; face shape, hair and
   clothes stay. Remove microphones and selfie arms.
4. **Colours from the pack** (`thumbnail.colors`, `background`; avoid `avoid_colors`). No strong glow or halo unless the
   pack's rules say otherwise.
5. **At most `max_numbers` numbers**, measured, belonging to exactly the result in the image. Money as an amount with
   its currency when the video is about cost.
6. **At most `max_words` words.** A key word of the title may appear in the image (the title step decides).
   An exaggeration only when the video carries it.
7. **One product logo**, large enough to read at 160 px. Arrow or circle only when the person does not already point.
8. **A comparison shows both real results of the same test**, never a product against a product it was not tested
   against.
9. **Bottom-right corner free.** YouTube puts the video length there: no text or number in the last 15 % of the width
   and 12 % of the height.
10. **Face** (`face`, `face_position`, `face_min_area`, `max_faces`): one face, large, where the pack says.
11. **The result shows the topic.** If the video tests several tools, the image shows all tested results with the
    winner marked, built as a real image (screenshots, labels, a frame around the winner), so the image model invents
    nothing.
12. **Break the pattern of the niche.** Before a new layout or a new round, put the newest thumbnails of the largest
    channels of the niche (`channel.json` `reference_channels`) next to the user's newest. Write three sentences: what
    almost all do (colour, face, text, layout), and how this variant clearly differs. They go into the round's
    `PLAN.md`. The comparison image is only for looking, never a thumbnail.
13. **Proof instead of reach.** The image shows a proof that makes up for a small channel: a measured result, a ranking,
    an amount from the test. An image without proof does not go to the user.
14. **Thumbnail and the first seconds first.** They get the most care; the quality of the rest is not cut for it.

When you apply rules 12 to 14 you may cite them in one line:
`crewcut say --episode $CREWCUT_EPISODE --cite "pattern break and proof after Vexian's packaging advice" "…"`.

## Layout templates

The pack lists the allowed layouts in `thumbnail.json` `layouts`; the first one is image 1, the others are test
variants. Prompt blocks for each: `references/prompt-blocks.md`.

| Layout | What it shows | When |
|---|---|---|
| `face-result` | the person large in the left or right third, turned to a large real result and pointing at it; 1 to 3 words; at most one number in an accent box; a product logo | default, image 1 |
| `result-vs-result` | split in the middle, two equal halves, each a real result with its logo; the one number on the winner's side; no "vs" between the halves | the video really compares two results |
| `before-after` | the state before and after, side by side, the after larger | the video changes one thing |
| `progress` | 3 or 4 real stages from left to right, each a bit larger, short labels, the last in the accent box | the video shows rounds or steps; a test variant only |

## Steps

1. **Read the input:** `brief/TITLE-vNNN.md` (title, promise, thumbnail text), the results of the episode
   (`brief/PROOF-vNNN.md`, `review/`), the final video.
2. **Pick the layouts:** image 1 from the first layout of the pack, 1 or 2 test variants that differ from it in ONE
   feature (the motif, the number, the face side). Same text, box, logo and title otherwise.
3. **Images of the person:** copy the reference photo into each variant folder. Only when needed, a still frame:
   ```
   python3 skills/thumbnail/scripts/still_frame.py sheet export/<id>-vNNN-final.mp4 --out graphics/thumbnail/vN-x/stills --range 0: --max 30 --face 0.5,0.38
   python3 skills/thumbnail/scripts/still_frame.py save export/<id>-vNNN-final.mp4 88.0 graphics/thumbnail/vN-x/A-x/1-still-88.0s.png
   ```
   Look at `sheet.png`, then at the chosen frame in full (inserts at the edge are not visible in the face crop).
4. **Result image:** a real screenshot in full size from the test or the episode folders, or a still from the video at
   the moment the graphic is fully built (`still_frame.py save … --face …` works for any time). Write its source into
   `PLAN.md`.
5. **Write the prompt** per variant from `references/prompt-blocks.md`: `A-x/prompt.txt`. It names every uploaded image
   in order, the layout with sizes in percent, the exact text, the colours and what must be absent.
6. **Write `PLAN.md`** in the round folder: images in which order, which prompt, why these variants, the pattern-break
   sentences (rule 12), then check and test.
7. **Generate:** `crewcut thumbnail make --episode $CREWCUT_EPISODE --prompt A-x/prompt.txt --ref A-x/1-photo.jpg --ref A-x/3-result.png --way codex --variants 2`.
   Way `api` only after an accepted spend card.
8. **Check:**
   ```
   python3 skills/thumbnail/scripts/thumb_check.py A-x/thumbnail-v001.png B-y/thumbnail-v001.png \
       --title "<title>" --text "<text A>" --text "<text B>" --convert --compare <best own thumbnail>
   ```
   It measures size, colours, face position, size and count, words and numbers, writes upload copies (1280x720 JPG) and
   previews at 320 and 160 px. Look at the previews, then go through the checklist below.
9. **Card:** `crewcut card propose --episode $CREWCUT_EPISODE --step thumbnail --kind thumbnail --title "Thumbnail A, test B" --file <preview-320.png>`.
   The user says which one, or what to change, in a sentence.
10. **A/B test** (section below), only with a card.

## A/B test on YouTube ("Test & compare")

From YouTube Help as the studio read it on 8 and 9 Nov 2026 (read it again before relying on it):
- Up to 3 variants per test. Modes: title only, thumbnail only, title and thumbnail.
- Desktop YouTube Studio only; needs the channel's advanced features. Not for Shorts, videos made for kids, private
  videos or scheduled live streams.
- A test runs for days, at most 2 weeks. The winner is the variant with the most watch time, not the highest click rate.
  Results: winner, performed the same, inconclusive; without a clear winner all get the first variant.
- An image under 1280x720 makes YouTube scale every image of the test down to 854x480.
- Changing the title or thumbnail during a test ends it. One test per video at a time.

As far as we know there is no public API to start a test. The Publisher prepares the variants (upload copies from
`--convert`) and a card for the user, who starts the test in Studio. Recording tests and their results is planned
(`ab_tests.py`). A result becomes a rule only after several finished tests that point the same way, and only with a
card (`crewcut rule propose --step thumbnail …`).

## Checklist

Check by hand on the finished image and the 160 px preview. `thumb_check.py` prints this list.
1. The face is clearly the person of the reference photo, only lightly refined; no microphone in the hand.
2. Face position and size as the pack says; only one face.
3. Colours from the pack only, plus the real colours of the photo and the result; nothing from `avoid_colors`.
4. At most `max_numbers` numbers, measured, with proof in the episode, belonging to the shown result.
5. At most `max_words` words; the video carries every exaggeration.
6. One product logo; an arrow or circle only when the person does not point.
7. A comparison shows both real results of the same test.
8. The result image is real and unchanged: the image model invented no tasks, numbers or text.
9. The bottom-right corner is free; text is spelled right, with the number format of the channel's language.
10. At 160 px one sees who, what result, and the verdict (words or number).

## Scripts

| Script | Call | What it does |
|---|---|---|
| `scripts/thumb_check.py` | `IMAGE [IMAGE2 IMAGE3] [--title T] [--text X …] [--convert] [--compare IMG …] [--out DIR]` | format, 16:9, at least 1280x720, upload file 1280x720 under 2 MB, avoided colours, edge against the pack background, accent share, face (with OpenCV and the YuNet model), words, numbers, money, title words; previews at 320 and 160 px; the checklist and the pack rules |
| `scripts/still_frame.py` | `sheet VIDEO --out DIR [--range A:B …] [--step 0.5] [--spacing 1] [--max 24] [--face X,Y] [--crop face\|full]` and `save VIDEO TIME TARGET.png` | candidates every 0.5 s, sharpness in the face window, skin share drops graphics, numbered contact sheet; saves the chosen frame at full size, never overwrites |

The face check needs `opencv-python-headless` and the YuNet face detector model from the OpenCV model zoo (MIT,
https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) at
`skills/thumbnail/models/face_detection_yunet_2023mar.onnx` or in `CREWCUT_YUNET`. Without them the check says so and
the face is checked by hand.

## Planned

- The browser way as a fallback for image generation (an image tool driven in a browser), only if ways codex and api fail.
- `ab_tests.py`: record every variant of every test (features, watch-time share, impressions, click rate) and evaluate
  per feature.
- A niche comparison sheet for rule 12 from the YouTube Data API.
- A result picker that finds the calmest frame around a time (the fully built graphic).

## Sources

No connection to or endorsement by these people; we took ideas and wrote our own summary.

- Vexian, in Grant Owen's podcast "The Crazy Genius Who Solved The Youtube Algorithm",
  https://www.youtube.com/watch?v=41HMFGbENj4: break the pattern of the niche, proof instead of reach, packaging
  (thumbnail and the first seconds) first, and split tests of thumbnails.
- fern (YouTube channel), https://www.youtube.com/@fern-tv: inspiration for the clay look of 3D result images only.
