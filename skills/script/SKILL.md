---
name: script
description: "Writes the spoken script of an episode in the user's own voice (voice.md), in teleprompter form, after title and proof are fixed: opening that delivers the title's promise, small stories with rising stakes, the critical side, a verdict in its own form, the channel's closing line. skills/script/scripts/script_check.py checks form, sentences, opening, ending, numbers against the proof, and length. Delivered through the web teleprompter (crewcut prompter). Use when: \"write the script\", \"teleprompter text\", \"rewrite the script\", \"shorten the script\", \"make it sound natural\", \"script for the episode\". Not for titles, thumbnails or Shorts under 60 seconds."
---

# Script

The Writer writes what the user says in the video. Goal: the user reads it once and records it. Every sentence carries
or proves the promise of title and thumbnail.

## Before you write

1. Title and thumbnail text are approved (`brief/TITLE-vNNN.md`). No title, no script.
2. The proof is approved (`brief/PROOF-vNNN.md`). Never invent a number, an experience or a quote. If something is
   missing, ask through the chat (`crewcut say`) before writing; the script has no gaps or placeholders.
3. Read `voice.md` (how the user speaks, words to use and to avoid), `brand/rules/script.md`, and the length in
   `edit-style.json` (`length_minutes`) with the speaking rate in `channel.json` (`script.words_per_minute`).
4. Read the endings of the last three scripts, so this verdict takes a new form.

## Structure

Two forms. Use the **test form** for a tool or a claim; use the **story form** when something happened (details in
`references/forms.md`).

1. **Opening, 2 to 6 sentences.** The first seconds carry the promise and its number: sentence 1 names the tool or
   topic and its claim. No greeting, no question, no "in this video". The first 30 seconds confirm the click: the viewer
   sees they got the video the title and thumbnail promised. At most one open loop, resolved at the end.
2. **The problem**, at a case the viewer knows. Explain an unknown tool the first time it comes up.
3. **What it does**, in pictures, only what the viewer does not know yet.
4. **The own test**, with real numbers, rounded the way people speak. Only tests of what the tool is built for.
5. **One subscribe line**, right after the first strong result: what the viewer gets from the channel. If no vendor
   pays for the tests, say so in that line. Never at the start, never as a plea at the end.
6. **Small stories with rising stakes.** Each block between opening and verdict has a goal, an obstacle and a solution;
   from block to block the stakes rise (more data, more money, a harder test). The strongest test comes last, before
   the verdict; the opening may announce it but not give it away.
7. **The critical side.** The vendor's number against the own or an independent measurement; the limits. If the tool
   does not keep its promise, say it, and the title goes back to the title step.
8. **The verdict, in its own form** each time: a task for the viewer, the one number that stays, what it means for the
   user's own work, a callback to the opening image. Not a fixed closing question.
9. **The end.** If `channel.json` has an offer or must-mention (`script.end_mentions`), it comes in the last sentences,
   in the user's words. The last sentence is the channel's `closing_line` when there is one.

**Comparison videos:** at most two blocks with the same build in a row; the third changes form. A new hook at the half.
Each statement once. Cost and time of all candidates once, together on screen, not at the end of every block.

## Words

- The user's words from `voice.md`; never the words on its avoid list.
- Short sentences: median about 10 to 12 words, never more than `script.sentence_max_words`.
- At most three product names in one sentence; longer lists go on screen.
- Out: basic knowledge the audience has, details nobody cares about (test counts, internal switches), file names,
  commands, side topics, private people, why an example was chosen, costs that are not part of the promise.
- No ad or sales tone: say what was tested, promise the viewer nothing. No grand "not this, but that" in the opening.
- Business shows through examples, not by addressing the viewer's business.

## Teleprompter form

The user reads from a phone next to the camera.

- Only spoken text above a line `---`. Notes for the edit (scenes, clips, where each number comes from) go below it.
- A paragraph is one breath: 1 to `script.paragraph_max_sentences` sentences. One empty line is a short pause.
- Three empty lines separate parts: there the edit can cut, there the teleprompter pages, there a clip can run.
- No brackets, stage notes, headings, chapters, timestamps or title line. Dashes only if the pack allows them.
- Mark the one or two key words of a paragraph in **bold**. The teleprompter's points mode shows them instead of the
  full text, for a user who wants to speak freely.

## Steps

1. Fill the structure with the proven numbers.
2. Cut: every sentence carries or proves the promise.
3. Bring it into the user's voice. Read every sentence in your head: would the user say this into the camera?
4. Write the draft to `work/script-draft-vNNN.md` with the next free number; never overwrite a version.
5. **Humanizer pass** (see below). Write the result to `brief/SCRIPT-vNNN.md` (same number), then record it:
   `crewcut humanize record --draft work/script-draft-vNNN.md --final brief/SCRIPT-vNNN.md --why "<the patterns that
   applied>"`.
6. Check until 0 errors:
   `python3 skills/script/scripts/script_check.py brief/SCRIPT-vNNN.md --title "<title>" --name "<tool>"
   --proof brief/PROOF-vNNN.md`. Read every warning and hint; a hint you keep gets one sentence of reason below `---`.
   If you change the script to pass the check, record the pass again: the card needs the record of the exact file.
7. Card: `crewcut card propose --episode <id> --step script --kind script --title "Script, version N" --file
   brief/SCRIPT-vNNN.md --body "<words>, about <min> min, check: 0 errors"`, then `crewcut card wait`. The card shows
   "Humanized" with what changed; without the record it is refused and says what to run.
8. After the yes: `crewcut prompter <id>` prints the phone link and a QR code. Tell the user in one message: the link,
   how many parts, about how long. The teleprompter shows only the text above `---`.

## Humanizer pass

Every script draft goes through **Humanizer** ([blader/humanizer](https://github.com/blader/humanizer), MIT) before
the user sees it: long videos and Shorts alike. Crewcut downloads its newest version at start; in Claude Code it is
the skill `humanizer:humanizer` (run it like any skill), with Codex its text is in your prompt. `crewcut skills status`
shows the version.

- **Mode "Embedded", with the user's voice.** Read every file in `brand/voice/` first: the user's own spoken words from
  their videos. Give them to Humanizer as the voice sample. No samples: plain mode; the card says so.
- **What to look for most:** "not X but Y" contrasts; closing lines that add nothing new; sayings that sound deep; a
  staged run-up before the point ("here's the thing"); lists of three; inflated meaning and advertising language.
- **What stays:** the user's own words and turns of phrase (those in `brand/voice/` and `voice.md`) even when Humanizer
  would smooth them; every number, name, claim and the promise of the title. The pass changes how it sounds, never
  what it says.
- **What is out of scope:** making text pass AI detectors. Humanizer edits for people, and so do we.

## What the check cannot see

Whether an example grows too broad, whether a part leaves the thread, whether a test fits the promise, whether the voice
sounds like the user. That is reading work in steps 2 and 3.

## Planned

- Cue sheet and two takes per part (first free from a cue sheet, then from the script; the edit takes the better take):
  format in `references/forms.md`; the checker and the take mix (`zettel.py` in the studio) are not ported yet.
- Script against recording: compare the approved script with the transcript to learn the user's real words (these
  transcripts can become new voice samples).
- A check list of phrases per language (filler words, sales phrases) as data in `voice.md`.

## Sources

- Humanizer by blader, https://github.com/blader/humanizer (MIT), built on Wikipedia's "Signs of AI writing". Used as a
  skill, downloaded at start; its text is not part of this repository.

- Vexian in Grant Owen's podcast, "The Crazy Genius Who Solved The Youtube Algorithm":
  https://www.youtube.com/watch?v=41HMFGbENj4. Taken: the hook is the first seconds, every block is a small story, the
  strongest test comes last, the subscribe line with independence, the offer late in the video.
- MrBeast's production handbook (public since 2024), summary: https://simonwillison.net/2024/Sep/15/how-to-succeed-in-mrbeast-production/
  Taken: the first minute delivers what title and thumbnail promised.
- Storytelling in short founder videos: Farza (https://www.youtube.com/@farzatv), Chris Raroque
  (https://www.youtube.com/@raroque), Roy Lee (https://www.youtube.com/@im_roy_lee), Riley Brown
  (https://www.youtube.com/@rileybrownai), Varun Mayya (https://www.youtube.com/@VarunMayya), Codie Sanchez
  (https://www.youtube.com/@CodieSanchezCT). Taken: first person, the turn, uneven real numbers.
