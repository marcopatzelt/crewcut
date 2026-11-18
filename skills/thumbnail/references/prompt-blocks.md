# Prompt blocks

Every prompt is built from these blocks, in this order. Replace `<angle brackets>` with values from the style pack
(`thumbnail.json`, `brand.json`) and the episode. When the user corrects a prompt, the change becomes a rule
(`crewcut rule propose --step thumbnail …`) and, if it is general, a change of the block here.

Why: the image model only knows what the prompt says. A complete prompt describes the whole image, names every uploaded
image by number and says exactly which text stands on it. Everything not in the prompt the model invents.

## 1. Head (always)

```
Create a brand-new YouTube thumbnail from scratch, landscape 16:9, 1280x720 px. This is a complete new design, not an edit of any image I upload.
```

## 2. Images (always, in upload order)

```
I upload <N> images, in this order:
Image 1: a photo of me (the person). Use it for my face, hair, skin and clothes.
Image 2: my own earlier thumbnail, as the style reference only: <what it gives: background, light on me, type, accent box, badges>. Do NOT copy its layout.
Image 3: a real screenshot from my <video/test>: <what it shows, one sentence> (the result).
```

Image 2 only when the pack has a `style_reference`. Follow the pack's rules about reusing its layout.
Layouts without a person start with the style reference (if any),
then the results in the order they appear (left to right, early to late). Upload a logo only when the model draws it
wrong.

## 3. Layout (always, one of)

- `face-result`: `LAYOUT: Me in the <right/left> third, large and close to the camera. One big result in the <left/right> two thirds. Nothing else.`
  The side follows the result image and `thumbnail.face_position`.
- `result-vs-result`: `LAYOUT: the image is split exactly in the middle into two equal halves, with a thin vertical gap of background between them. No person. Left half = <A>, right half = <B>.`
- `before-after`: `LAYOUT: two real states side by side, left = before (smaller), right = after (larger). No person.`
- `progress`: `LAYOUT: <3 or 4> real stages in one row from left to right, each slightly larger than the one before, the last one the largest. No person.`

## 4. Person (layouts with a person)

```
PERSON (image 1): the person from image 1, in the <right/left> third, chest-up and very large: the face from forehead to chin is about <share> of the image height, the top of the hair almost touches the top edge, the shoulders are cut off by the bottom edge. <pose>. Keep the person exactly recognisable: same face shape, eyes, eyebrows, nose, mouth, hair and the same clothes as in image 1. <light>. You may subtly refine the face for a thumbnail: slightly crisper eyes, even skin, a touch more expression. No beauty filter, no younger or different person. Remove any microphone, the outstretched selfie arm and the room behind.
```

- Size: the face box should cover at least `thumbnail.face_min_area` of the image. Say the target as a share of the
  image height; "head about 40 % of the height" is only a few percent of the area. `thumb_check.py` measures it.
- Pose for `face-result`: `body turned slightly towards the result, pointing at it with the nearer hand, index finger extended, relaxed and natural, looking straight into the camera, mouth closed or a small smile`.
- Without pointing: `looking straight into the camera with a calm, confident look and a slight closed-mouth smile`.
- With a still frame instead of the photo: image 1 is `a still frame of me from my video`; the rest stays.

## 5. Result (always)

```
RESULT (image 3): <crop, size in percent, position in percent>. Use the real screenshot from image 3 as it is: do not redraw, restyle, translate or invent content in it, and leave out <foreign text: labels, corner text, watermarks>. You may crop it, scale it, round its corners and give it a soft dark shadow.
```

Logo: `LOGO: a large <colour> <name> app badge, about <share> of the image height, <position>. It must not touch the text or the number box.` Small badges at the edge of the result are too small at 160 px.

## 6. Text (always)

```
TEXT: exactly these, nothing else on the whole image:
1. "<1 to max_words words>" in huge <text colour> letters, <lines>, <position>. <display font family from brand.json, or "a heavy geometric sans-serif">, height about <share> of the image.
2. "<one number>" in huge <text colour> figures on one solid <accent colour as hex> rounded box, <position>. Write it exactly "<number>".
Keep the bottom-right corner (the last 15 % of the width and 12 % of the height) free of text; YouTube puts the video length there.
```

- Words: at most `max_words`; a key word of the title is allowed; an exaggeration only when the video carries it.
- Number: at most `max_numbers`; money as an amount with its currency; percent rather than "x times".
- Without a number, the verdict word can stand in the accent box.
- Spelling and number format follow the channel language (`channel.json` `language`).

## 7. Colours (always)

```
COLOURS: <background colour as hex> background<, a very faint accent gradient behind the result>. Only <the colours of thumbnail.colors as hex>, plus the natural colours of the photo and the result. Clean, minimal, generous space.
```

## 8. Avoid (always)

```
AVOID: <avoid_colors by name>; underlines or hand-drawn marks; <a second number / any number>; a second person or any other face; a small or distant face; <a centred person, when face_position is a side>; any other words, captions, labels, logos, watermarks or channel names; strong glow, halo or lens flares; emojis; <elements of other layouts: a split screen / a person / a second picture>.
```

An arrow is allowed when the person does not point: `one simple thick <text colour> arrow from <start> to <target>`;
then "arrows" is not in AVOID.

## 9. End (always)

```
Very sharp, high contrast, readable at 160 px width. Output one 16:9 image.
```

## Lessons

- A style reference with "copy its layout" gave every video the same layout. Say what the reference gives and that the
  layout is not copied.
- Fixed poses in the prompt (the same hand gesture every time) make every thumbnail alike. The pose comes from the layout.
- Edit prompts ("edit image 1 …") drift and lose quality. Always block 1.
