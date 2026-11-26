---
name: title
description: "Writes and checks the YouTube title and the thumbnail text of an episode, before the script. Delivers ten candidates from at least four title formulas, each with its formula and a reason, one recommendation, and three variants for the A/B test; skills/title/scripts/title_check.py is the gate every candidate passes (pass or fail, not a score). Use when: \"title\", \"video title\", \"YouTube title\", \"what should the video be called\", \"check this title\", \"shorten the title\", \"better title\", \"thumbnail text\". Not for the blog's search title and not for the thumbnail image."
---

# Title

The title comes before the script. Title and thumbnail set what the viewer expects; the video must deliver exactly
that. The Scout writes the title after the idea step and before the script.

Not here: the thumbnail image (`skills/thumbnail/`), the first sentence of the video (`skills/script/`).

## Title and thumbnail first

For Shorts, use the title method and the gate below. Show the candidates with their formulas on the card. Skip thumbnail tasks and Designer handoffs during title selection. Any later Short cover is vertical (9:16).

For long videos, before the script or recording, develop the title and a concrete thumbnail draft together with the Designer.
Read the thumbnail skill. Save brief/PACKAGING-vNNN.md: title promise, exact image text, visual idea, draft path,
audience, evidence plan and the independent Critic review at 160 px. A title keyword plus a verdict can appear
in the image; the image must add a different statement, not repeat the title. Numbers are optional.
Before measurements, label outcomes provisional and never fabricate proof. Recheck the package after the test.
A number goes into a title only when it is measured. Emotional and style words ("Krass!", "genial") are a hook,
not a claim: they need no measurement and no caveat, and nobody marks them as unmeasured.
Do not defer the first visual concept until the edit is done. The later thumbnail step finalizes real evidence.

## Method

1. **Read the input.** From the idea step: topic, tool, planned test, the numbers it will measure, proof videos. Read
   `brand/rules/title.md` and the title limits in `channel.json` (`crewcut brand show`). If a number is not measured
   yet, write `[N]` and mark the title as provisional.
2. **Write ten candidates from at least four formulas** (`channel.json` `title.candidates` and
   `title.formulas_min`). A formula is the shape of the promise; ten variants of one formula are one candidate. The
   formulas (`title_check.py`, `FORMULAS`; the channel's `rules/title.md` says which come first):
   - `situation`: the viewer's situation ("If you ...").
   - `howto`: how to do it ("How to ...").
   - `contrast`: a cost or risk contrast (cheap against expensive, safe against risky).
   - `flip`: the expectation flips (what the viewer believes turns out wrong).
   - `plan`: my plan ("How I'd ...").
   - `condition-plan`: condition plus my plan ("If I ..., I'd ...").
   - `condensed`: knowledge condensed ("N years in M minutes").
   - `year`: a year that frames a plan.
   - `time`: the viewer's time to the result ("in one evening"), never the tool's working time.
   - `case`: a case (who, a number, the problem), a quote or an I-sentence; mostly for Shorts.
   Inside every formula the craft stays the same. The click words that work in the user's language are in `voice.md`
   (`## Title hooks`) when the Brand identity found them; otherwise judge by the proof videos.
   - **The best-known name early.** The thing the title is about is the best-known thing of its class (the famous
     product, not the category word), and it starts within the first characters (`title.name_within`). Phones cut long
     titles.
   - **A number only when it is real.** It comes from the own test and matches what the video shows.
   - **A price ladder** ("for 1, 10 and 100") or **a contrast** ("cheap beats expensive") only when the video measures
     every step or shows the contrast. If the measurement turns out differently, the title changes before the upload.
   - **Plain words and a promise.** No category jargon, no business words in the title: the title speaks to everyone,
     the business case sits inside the video. A long video's title is a statement or a plan, not an open question.
3. **The gate.** Write the candidates to `work/title-candidates-vNNN.tsv`, one per line: `<formula><TAB><title>`. Run
   `python3 skills/title/scripts/title_check.py --set work/title-candidates-vNNN.tsv --name "<tool>"`. It passes when
   there are enough different candidates from enough formulas and every title passes on its own (length, name early,
   the pack's forbidden words and signs). A candidate that fails is rewritten or dropped; it never goes to the user.
   The check is a gate, not a goal: there are no points to raise, and a passing title is not better because it has
   more hooks. Choose the recommendation by the promise the video keeps, the formula the channel's rules put first and
   the proof videos, and say why in one sentence.
4. **Thumbnail text.** At most `thumbnail.max_words` words: one key word of the title and the verdict. Never the whole
   title. Check it with `--thumbnail "<text>"`.
5. **Three variants for the A/B test** (`channel.json` `title.variants`): place 1 the recommended title; place 2 the
   same title with exactly one change (the hypothesis: without the number, or with one click word); place 3 a calmer
   variant, or for an old video its current title as control. Check all three.
6. **Write `brief/TITLE-vNNN.md`:** chosen title, characters, its formula, the promise, the hook, the number and where
   it comes from, the thumbnail text, the three test variants, all ten candidates with their formulas, rejected ones
   with the reason, and the gate line of the check. Never overwrite a version.
7. **Humanizer pass on the words.** Before the card, run the Humanizer skill over the candidates and the thumbnail
   text (write them first to `work/titles-draft-vNNN.md`), the same way as the script (skills/script, "Humanizer
   pass"): look for advertising language, inflated meaning and staged run-ups; the click words of `voice.md`
   (`## Title hooks`) and every number stay. Record it: `crewcut humanize record --draft work/titles-draft-vNNN.md
   --final brief/TITLE-vNNN.md`. The card then shows what changed.
8. **Card.** `crewcut card propose --episode <id> --step title --kind title --title "Pick a title" --file
   brief/TITLE-vNNN.md --body "Recommendation: option 1. <one sentence why>" --option "<1>" … --option "<5>"` (the
   five strongest candidates as options, from different formulas; all ten are in the file), then
   `crewcut card wait`.
9. **Hand over.** To the script (and to the proof step, when the studio switched it on): the promise, the tool and
   the number to measure. To the Designer: title, thumbnail text, verdict, the three variants.
10. **After the test, check again.** Does the number still hold? If not, write a new version and a new card
   before the script starts.

A title change after the upload needs a card and goes through `skills/upload/`.

## What the gate cannot see

Whether the number is real, whether the video keeps the hook, which name is better known, whether every step of a
ladder is measured. That is reading work in steps 2 and 9.

## Card format

```
Title (recommendation first)
1. <title>  (<N> characters) · formula: <situation> · reason: <proof video or rule>   <- recommendation
2. …
Thumbnail: <key word + verdict>
Gate passed: 10 candidates from 5 formulas (title_check.py --set).
```

## Planned

- A results table from the 48-hour checks (`review/results-48h.json` of past episodes) that the title step reads to
  weigh hooks by the user's own data.
- Language data packs: hook words with measured effects per language, built from public title studies (the studio had a
  German one; its raw data is not part of Crewcut).

## Sources

- Vexian in Grant Owen's podcast, "The Crazy Genius Who Solved The Youtube Algorithm":
  https://www.youtube.com/watch?v=41HMFGbENj4. Taken: the best-known thing of its class, click words that work in any
  niche, the price ladder, the contrast that the video must prove.
- MrBeast's production handbook (public since 2024), summary: https://simonwillison.net/2024/Sep/15/how-to-succeed-in-mrbeast-production/
  Taken: title and thumbnail are fixed before the shoot, and the video must deliver them.
- Alex Hormozi's channel (public titles and views, measured 26 Nov 2026), https://www.youtube.com/@AlexHormozi: our own
  outlier study of 3,424 long videos. Taken: write candidates from several formulas instead of raising one checker's
  score; the viewer's situation, my plan under a condition, the viewer's time to the result and a year carried the
  most; open questions and series names carried the least.
