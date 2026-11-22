---
name: thumbnail
description: "Makes the YouTube thumbnail of an episode and its A/B test variants: picks three different formats from the format library of the style pack (at least one house style and one pro format), gets a real still frame and a real result image, writes one complete new image prompt per variant, generates the images (crewcut thumbnail make, way codex or api), checks size, colours, face and words (thumb_check.py), and prepares the A/B test. Use for: thumbnail, thumbnail prompt, image prompt, still frame of me, thumbnail variants, A/B test thumbnail, test and compare, check the thumbnail, new thumbnail. Not for the title or the thumbnail text (skill title), not for the upload (skill upload)."
---

# Thumbnail

When Full auto is enabled for this episode, propose the usual thumbnail card with
the best variant recommended. The assigned Critic selects it through the scoped
Full-auto review command. Never accept your own card. Prepare up to three final
variants for YouTube Studio, but do not claim a live A/B test has started. Private
videos and Shorts cannot run YouTube's native A/B test. Spending rules still apply.

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
- **Only real things.** The person as in the face references (reference photo, real frames, approved thumbnails). Results as real screenshots from the
  video or the test. Only measured numbers.
- **Never edit text in a generated image by script.** A wrong image gets a new complete prompt.

## Rules

1. **One complete new prompt per variant, never an edit prompt.** Edits drift; a full prompt is repeatable. A disliked
   image gets a changed full prompt in a new run.
2. **Fixed images first, chosen by the variant's format.** `crewcut thumbnail make` attaches them by itself, in this
   order, and puts a numbered list of the images and their roles at the top of the prompt (refer to images by role,
   not by number):
   - **Face references:** the reference photo (`thumbnail.json` `reference_photo`) plus the extra face references of
     the pack (`thumbnail.identity.references`: real frames or approved thumbnails of the person from different
     angles, up to `identity.max_references` in all). Several angles keep the face the person's.
   - **A pro format:** its example image(s) from the format library, as the layout example (composition, placement,
     sizes, kind of graphics; never its person, text, logos or colours). The house thumbnail is not attached.
   - **A house format:** the pack's `style_reference` for style only (the prompt says what it takes: light, type, face
     size). **The control variant:** `thumbnail.control.reference` (or the style reference): its look is followed.
   - Then the episode's result images (`--ref`).
   The format comes from `SET.json` (the variant whose prompt or folder this is) or `--format`; `--control` marks the
   control. Each run is recorded in the variant folder's `REFERENCES.json`. A missing configured reference stops
   generation. A still frame (`still_frame.py`) only when the person needs other clothes or another pose.
3. **The face stays the person.** The image model draws the person from the face references; slightly crisper eyes
   and a little more expression are fine; face shape, eyes, skin, hair and clothes stay. Remove microphones and selfie
   arms. The identity gate (rule 24) decides, not the eye alone.
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
    nothing. A grid only when it reads as ONE focal point at a glance (few large tiles, the winner clearly larger, rule
    15); otherwise the image shows only the winner, large, and the grid goes into the video.
12. **Break the pattern of the niche.** Before a new layout or a new round, put the newest thumbnails of the largest
    channels of the niche (`channel.json` `reference_channels`) next to the user's newest. Write three sentences: what
    almost all do (colour, face, text, layout), and how this variant clearly differs. They go into the round's
    `PLAN.md`. The comparison image is only for looking, never a thumbnail.
13. **Proof instead of reach.** The image shows a proof that makes up for a small channel: a measured result, a ranking,
    an amount from the test. An image without proof does not go to the user.
14. **Thumbnail and the first seconds first.** They get the most care; the quality of the rest is not cut for it.
15. **One or two focal points, the one-second test.** A stranger understands the image in one second: who, what, why
    click. At most two focal points, for example the face and one object or result. Test: look at the 160 px preview for
    one second, look away, say in one sentence what the video is about. If you can't, the image is too full.
16. **No AI look, no clutter.** No collage of several scenes, no whiteboards or screens full of small text, no rows of
    years ("2024 2025 2026"), no glossy stock-photo light. If the finished image looks generated, it does not go to the
    user: write a new complete prompt (rule 1).
17. **One object names the audience and the goal.** One large, instantly recognisable object shows who the video is
    for and what they get, like a YouTube diamond play button held up for creators (audience: creators; goal: a huge
    channel). Ask first: who should click, and what do they want (time, money, control, growth)? The object counts as
    one of the two focal points (rule 15).
18. **A power word that makes people ask "how?".** Among the few words (`max_words`) there is one power word that
    raises the question "how?": solved, cracked, replaced, built, without code, in 1 hour. The video must carry it.
19. **Image and title as a crossover, never the same line.** The image and the title are two halves: one sets an
    expectation, the other turns it or adds what is missing. They never repeat each other. A key word of the title may
    appear in the image, but not the same statement. Test: read the image text and the title side by side; if one makes
    the other redundant, rewrite the image text.
20. **Many candidates, then finalists.** A round makes 6 to 10 prompt variants that really differ (motif, object, power
    word, crossover, face position), and up to 4 images per prompt (`--variants 4`), so 20 or more candidates. The Critic
    checks every candidate and picks the best 2 or 3 as finalists for the A/B test (YouTube allows at most 3). The
    reasons go into `PLAN.md`, one line per candidate.

21. **A test set is three formats, not three versions.** Every A/B set (`thumbnail.formats.per_set`, default 3, the
    YouTube maximum) uses a different format from the format library (`crewcut thumbnail formats`) for each variant:
    at least `min_house` in the channel's own style (kind `house`) and at least `min_pro` outside formats (kind
    `pro`, the user's collected references). Each variant changes the hook, not details: its own focal object, text
    idea, emotion, composition and colour. Four images that differ only in the result card measure nothing.
22. **The set check decides, not taste.** `crewcut thumbnail set check <round>` reads `SET.json` (formats and hooks)
    and compares every pair of finished images: a perceptual hash, the layout (where bright, dark and busy parts sit)
    and the colours. A pair that is nearly the same picture, the same composition or the same colours fails, and the
    check names the variant to make again. Make it again with a new complete prompt in another format (rule 1). Only a
    set that passes goes on a card (`crewcut thumbnail set card <round>`), and the card shows the format under each
    image.
23. **Palette, brand marker and colour limits** (`thumbnail.palette`, `thumbnail.backgrounds`). The pack names the main
    colour, the allowed grounds, optionally one small constant brand marker (for example a short underline in the brand
    colour) and `palette.limits`: colours to keep out, each with a `max_share`. The check reports the main colour's
    share, fails a missing marker or a marker colour that takes over the image, and warns when a limited colour covers
    more than its share. The control variant (rule 26) is exempt.

24. **The identity gate.** `crewcut thumbnail set check` measures the main face of every variant with a person against
    the pack's face references (face embedding, cosine similarity; `crewcut thumbnail face check <image>` for one
    image). Below `thumbnail.identity.min_similarity` the variant fails as a look-alike: make it again with a new
    complete prompt and stronger face references (more angles, a frame close to the wanted pose and expression). The
    threshold is calibrated on the user's real thumbnails and rejected look-alikes
    (`crewcut thumbnail face calibrate --positive … --negative … --write`). When the check cannot run (OpenCV or the
    models missing) it fails the set; it never passes silently. Variants without a person set `"face": false`.
    `crewcut thumbnail make` checks every new image at once and tries again up to `identity.tries` times; an image with
    the wrong face is kept as `…-wrong-face.png`, and raw attempts never show in the app (only a round whose set check
    passed does). The gate catches look-alikes, not every fine drift: a face that an embedding still calls the same
    person can look wider or have another nose. So the set check also writes `SET-FACES.jpg`, each variant's face next to
    the first face references at the same size: look at it before the card.
    **How to keep the face:** face references are tight head-and-shoulder crops of approved thumbnails and sharp real
    frames (frontal and a slight 3/4; no selfies, no screenshots; `identity.use_reference_photo: false` drops a weak
    reference photo). Better still, edit an image that already has the right face (`crewcut thumbnail make --edit
    <image>`: the person stays, background, layout, text and pose change) instead of drawing the face anew. Make the face
    large (about 40 % of the image height or more), take a real expression from a frame instead of an invented smile, and
    keep words about facial features in the prompt few: the references do that work.
25. **Real-photo fallback.** Only when a variant keeps failing the gate: put a real frame of the person into the
    design. `crewcut thumbnail face frames <videos> --out <dir>` finds sharp, large frames of the person (look at
    `sheet.jpg`; pick expression and pose for the format, or adapt the layout to the closest frame),
    `face save` takes the full frame, `face cutout` cuts the person out (rembg), `face compose` places the cutout over
    the designed background and graphics with light retouch only (colour match, rim light, slight sharpen; no change
    of geometry) and records the source in `<image>.face.json`.
26. **One control variant.** A set may hold one control (`"role": "control"` in `SET.json`): the channel's current,
    proven style, so the test shows whether the new formats beat it. It is exempt from the palette and colour rules
    (rule 23); face, words, readability and the near-duplicate check still apply. The card marks it
    (`thumbnail.control.name`).
27. **Finalists and reserve.** YouTube tests `per_set` (3) at a time. A set may hold up to `max_candidates` (default 5)
    variants; `SET.json` `finalists` names the 3 for the test (normally including the control), the rest is the reserve
    for a second round. The card shows the suggestion and marks the reserve.

When you apply rules 12 to 20 you may cite them in one line:
`crewcut say --episode $CREWCUT_EPISODE --cite "pattern break and proof after Vexian's packaging advice" "…"`.

## Format library

`crewcut thumbnail formats [--strong] [--kind house|pro]` lists the formats; `crewcut thumbnail formats show <id>` prints
one card (recipe, when it fits, example images). The library lives in the style pack (`references/formats/formats.json`,
one entry per format: id, name, kind, recipe, fits, strong, card, images). The neutral pack has a small generic library
in Crewcut's own words; the user builds their own from references they collected (outlier thumbnails of their niche,
their best own thumbnails). Collected images are references only: they stay in the user's studio, never go into a
public repository, and are never passed to the image model as something to copy. Pick formats whose "fits" matches
the topic; prefer formats marked strong.

## Layout templates

The pack lists the allowed layouts in `thumbnail.json` `layouts`; the house formats of the library describe them as
recipes. Prompt blocks for each: `references/prompt-blocks.md`.

| Layout | What it shows | When |
|---|---|---|
| `face-result` | the person large in the left or right third, turned to a large real result and pointing at it; 1 to 3 words; at most one number in an accent box; a product logo | default, image 1 |
| `result-vs-result` | split in the middle, two equal halves, each a real result with its logo; the one number on the winner's side; no "vs" between the halves | the video really compares two results |
| `before-after` | the state before and after, side by side, the after larger | the video changes one thing |
| `progress` | 3 or 4 real stages from left to right, each a bit larger, short labels, the last in the accent box | the video shows rounds or steps; a test variant only |

## Start with the title, before the script

Build the first concrete concept and draft during the title step, with the Scout and Designer.
For each candidate write the title, exact image text, visual idea, audience question and evidence plan in
brief/PACKAGING-vNNN.md. Have the Critic judge the pair at 160 px before the Writer starts.
A title keyword may recur with a verdict; the image adds meaning instead of repeating the title.
Numbers are optional: never force a measurement into every layout. Before the test, use provisional concepts,
not invented results. After the test insert real evidence and check again. The late thumbnail step is finalization.

## Steps

1. **Read the input:** `brief/TITLE-vNNN.md` (title, promise, thumbnail text), the results of the episode
   (`brief/PROOF-vNNN.md`, `review/`), the final video.
2. **Pick the formats and write `SET.json`** in the round folder (rule 21): three variants, each with its label,
   format id, image path and hook (focal object, text, emotion, composition, colour). Check the plan before any image:
   `crewcut thumbnail set check graphics/thumbnail/vN-x --plan-only`. For more candidates (rule 20), make several
   images per variant; the finalists that go into `SET.json` are one per format.
3. **Images of the person:** `crewcut thumbnail make` attaches the pack's face references by itself (rule 2). For a
   pose the references do not show, add a fitting real frame as a face reference. Only when needed, a still frame:
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
7. **Generate:** `crewcut thumbnail make --episode $CREWCUT_EPISODE --prompt <round>/A-x/prompt.txt --out <round>/A-x --ref <round>/A-x/3-result.png --way codex --variants 4`, once per prompt variant (rule 20).
   The face references and the format's example or style reference come automatically (rule 2); check the printed
   "References:" line. Way `api` only after an accepted spend card.
8. **Check:**
   ```
   python3 skills/thumbnail/scripts/thumb_check.py A-x/thumbnail-v001.png B-y/thumbnail-v001.png \
       --title "<title>" --text "<text A>" --text "<text B>" --convert --compare <best own thumbnail>
   ```
   It measures size, colours, face position, size and count, words and numbers, writes upload copies (1280x720 JPG) and
   previews at 320 and 160 px. Look at the previews, then go through the checklist below.
9. **Set check, then card:** `crewcut thumbnail set check graphics/thumbnail/vN-x` (rules 22 to 27: variety, palette,
   identity gate, references used, control, finalists). Redo every variant it names with a new complete prompt, then
   check again. When it passes:
   `crewcut thumbnail set card graphics/thumbnail/vN-x --preview <preview-320.png>`. The card shows each variant with its
   format name. The user says which one, or what to change, in a sentence.
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

**Repackage when a video is flat.** After 7 days and after 30 days the Publisher compares every video with the median of
the user's other videos at the same age (views). If it is clearly below, the Designer makes a new package: a new
thumbnail by rules 15 to 18 and, if needed, a new title from the title step. It runs as a "title and thumbnail" test
against the old package, and only with a card, because it changes the live video. A video that lay flat for 70 days can
take off after new packaging (Steven Baterina's example, see Sources).
The archive too: every 90 days the Publisher checks older videos. Candidates are videos with good watch time per view
but few impressions or a low click rate. They get a new package as a test, again only with a card. A video can still
take off "two years down the line" with a new thumbnail and title (Zack Honarvar, see Sources).

As far as we know there is no public API to start a test. The Publisher prepares the variants (upload copies from
`--convert`) and a card for the user, who starts the test in Studio. Recording tests and their results is planned
(`ab_tests.py`). A result becomes a rule only after several finished tests that point the same way, and only with a
card (`crewcut rule propose --step thumbnail …`).

## Checklist

Check by hand on the finished image and the 160 px preview. `thumb_check.py` prints this list.
1. The face is clearly the person of the reference photo, only lightly refined, and passed the identity gate; no
   microphone in the hand.
2. Face position and size as the pack says; only one face.
3. Colours from the pack only (main colour, allowed grounds, the small brand marker), plus the real colours of the photo
   and the result; nothing from `avoid_colors`.
4. At most `max_numbers` numbers, measured, with proof in the episode, belonging to the shown result.
5. At most `max_words` words; the video carries every exaggeration.
6. One product logo; an arrow or circle only when the person does not point.
7. A comparison shows both real results of the same test.
8. The result image is real and unchanged: the image model invented no tasks, numbers or text.
9. The bottom-right corner is free; text is spelled right, with the number format of the channel's language.
10. At 160 px one sees who, what result, and the verdict (words or number).
11. At most two focal points; after one second at 160 px you can say in one sentence what the video is about.
12. No AI look: no collage, no small text, no whiteboards, no stock-photo light.
13. One large object shows the audience and the goal.
14. One power word that makes people ask "how?", and the video carries it.
15. Image text and title do not say the same thing: one sets an expectation, the other turns it.
16. The set uses different formats (one house, one pro at least, at most one control), each with its own hook, every
    pro variant made from its format example, and passed `set check`.

## Scripts

| Script | Call | What it does |
|---|---|---|
| `scripts/thumb_check.py` | `IMAGE [IMAGE2 IMAGE3] [--title T] [--text X …] [--convert] [--compare IMG …] [--out DIR]` | format, 16:9, at least 1280x720, upload file 1280x720 under 2 MB, avoided colours, edge against the pack background, accent share, face (with OpenCV and the YuNet model), words, numbers, money, title words; previews at 320 and 160 px; the checklist and the pack rules |
| `crewcut thumbnail face` | `check IMG …`, `calibrate --positive … --negative … [--write]`, `frames VIDEO … --out DIR`, `save VIDEO TIME OUT`, `cutout IMG OUT`, `compose --background BG --person CUT --height H --x X [--overlay FG] [--rim #hex] OUT` | the identity gate for single images, its calibration, and the real-photo fallback (rules 24, 25); needs `crewcut[faces]` (OpenCV; the YuNet and SFace models download once) |
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
- Steven Baterina (Creo Social), Instagram reel comparing two thumbnails of one video,
  https://www.instagram.com/reel/DfvkIktPyQH/: one or two focal points, no AI-looking clutter, one object that names the
  audience and the goal, a power word that raises "how?", and new packaging for a video that lies flat (rules 15 to 18
  and "Repackage when a video is flat").
- Zack Honarvar in the Ourselves podcast, Instagram reel, https://www.instagram.com/reel/Df0AeCOz6qF/: title and thumbnail
  as a crossover instead of the same line, many thumbnail candidates with only the finalists in the A/B test (Airrack tests
  20 to 50), and new packaging for old videos (rules 19 and 20, archive repackaging).
