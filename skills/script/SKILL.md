---
name: script
description: "Writes the spoken script of an episode in the user's own voice (voice.md), in teleprompter form, after the title is fixed: a story plan first (premise, arc, beats), the script craft (references/craft.md: hook in 30 seconds, depth pattern, spoken rhythm, an ending with exactly one call to action), opening that delivers the title's promise, small stories with rising stakes, the critical side, a verdict in its own form, the channel's closing line. skills/script/scripts/script_check.py checks form (every mark reads aloud), story (plan, list smell, run-ups), sentences, opening, ending, numbers against the gathered facts, length, and the craft (--craft for the craft alone). Delivered through the web teleprompter (crewcut prompter). Use when: \"write the script\", \"teleprompter text\", \"rewrite the script\", \"shorten the script\", \"make it sound natural\", \"script for the episode\". Not for titles or thumbnails. Short scripts: the `--short` mode of the check and skills/shorts."
---

# Script

The Writer writes what the user says in the video. Goal: the user reads it once and records it. Every sentence carries
or proves the promise of title and thumbnail.

## Before you write

1. Title and thumbnail text are approved (`brief/TITLE-vNNN.md`). No title, no script.
2. **Gather the material that serves the story**, for yourself only: no card, no report, no chat summary. Facts,
   numbers, clips and scenes from the episode folder, the user's earlier episodes and the chat go into
   `work/material-vNNN.md`, each fact and number with its source (a file path or a link). Pick what makes the story
   stronger, not everything that is true. Only concrete factual claims and numbers need a source; emotional, style and
   title words ("Krass!", "genial") are the user's voice, never claims to measure. A proof file
   (`brief/PROOF-vNNN.md`, only when the studio switched step 3 on) is an internal fact check, not script content; what
   the user said in the chat about the content wins. Never invent a number, an experience or a quote. If something is
   missing, ask through the chat (`crewcut say`) before writing; the script has no gaps or placeholders.
3. **The interview** (`[steps] interview`, on by default, long videos only). Before the first draft the conductor wakes
   you to ask the user 5 to 8 open questions: what the files cannot know. How it started for them personally, their
   doubts or skepticism, the real turning point, setbacks with concrete details (when, what broke, what it cost), how
   they work now, what it changes for them, their opinion. One short sentence each, easy to answer by voice, in the
   channel's language, never yes/no, never one the brief answers. Write them to `work/interview-questions.md`, post
   them with `crewcut interview ask <id> --file work/interview-questions.md` and stop. The answers come back as
   `brief/INTERVIEW-vNNN.md` (verbatim). Then they carry the script: the user's own sentences, almost word for word,
   smoothed only where a sentence cannot be spoken; nothing they did not say. Every wish to leave something out (the
   file's "Do not mention" list, and any such wish in the answers) is a hard rule, also when paraphrased. Below `---`
   mark each spoken line that comes from the interview: `[[interview: 3 | "the spoken words"]]`, and run the check
   with `--interview brief/INTERVIEW-vNNN.md`. Never answer or skip the interview for the user.
4. Read `voice.md` (how the user speaks, words to use and to avoid), `brand/rules/script.md`, and the length: the
   episode's brief wins (a long explainer with depth runs 11 to 14 minutes, a short test 3 to 5), otherwise
   `edit-style.json` (`length_minutes`), with the speaking rate in `channel.json` (`script.words_per_minute`).
   Depth needs words: never cut an explainer to a short length the brief did not ask for.
5. Read the endings of the last three scripts, so this verdict takes a new form.
6. **Read `references/craft.md` in full, every time**, also for a rewrite: the hook in 30 seconds, the depth pattern
   for every idea, the spoken rhythm and the ending. Every draft follows it, and the check measures it.
7. **Story first** (`references/story.md`). Before the first sentence of the draft, write the story plan into the
   script notes below `---`: one premise sentence (the through-line), the arc (hook, tension or problem, turning point,
   payoff, close) and the 3 to 5 beats that serve it. Brief items, chat notes and interview answers are a material
   pool: take what serves the arc and drop the rest. An example the user gives is a hint at the kind of moment, never
   a line to insert word for word. The card is refused for a long script without this plan.

## Structure

Two forms. Use the **test form** for a tool or a claim; use the **story form** when something happened (details in
`references/forms.md`).

1. **Opening: the hook in 30 seconds** (`references/craft.md`, group 1). The first seconds carry the promise and its
   number: sentence 1 names the tool or topic and its claim. No greeting, no question, no "in this video". By second
   30: the result or claim, why it matters, one measured number, a roadmap with a count, and one open loop that the end
   resolves. One honest limit by 0:45, the first demo of the real thing by 1:30. The first 30 seconds confirm the
   click: the viewer sees they got the video the title and thumbnail promised.
2. **The problem**, at a case the viewer knows. Explain an unknown tool the first time it comes up.
3. **What it does**, in pictures, only what the viewer does not know yet.
4. **The own test**, with real numbers, rounded the way people speak. Only tests of what the tool is built for.
5. **One subscribe line**, right after the first strong result: what the viewer gets from the channel. If no vendor
   pays for the tests, say so in that line. Never at the start, never as a plea at the end.
6. **Small stories with rising stakes, each idea in the depth pattern** (`references/craft.md`, group 2). Each block
   between opening and verdict has a goal, an obstacle and a solution; from block to block the stakes rise (more data,
   more money, a harder test). Each idea runs 40 to 60 seconds: question, why, how on screen, failure or limit, number,
   and "try this" (a small task the viewer can do without the product). Every technical word gets one plain sentence
   the first time; examples, sums said aloud and contrast pairs make it concrete; the parts are counted aloud. The strongest test comes last, before
   the verdict; the opening may announce it but not give it away.
7. **The critical side.** The vendor's number against the own or an independent measurement. A limit goes in only
   where leaving it out would mislead the viewer, in one sentence, never as a list of caveats. If the tool does not
   keep its promise, say it, and the title goes back to the title step.
8. **The verdict, in its own form** each time: a task for the viewer, the one number that stays, what it means for the
   user's own work, a callback to the opening image. Not a fixed closing question.
9. **The end, in at most 60 seconds** (`references/craft.md`, group 4): the parts as one list, what the human still
   does, the verdict with its limit, and exactly one call to action. The hook's open loop is resolved before it. If
   `channel.json` has an offer or must-mention (`script.end_mentions`), it comes in the last sentences, in the user's
   words, without a second plea. The last sentence is the channel's `closing_line` when there is one.

**Transitions.** Each beat ties to the one before with cause or contrast ("deshalb", "aber", "und dann"; "so", "but",
"and then"), never with a new topic. A new topic needs a bridge sentence. A paragraph that could swap places with its
neighbour is a list item: tie it in or cut it. No staged run-ups ("Jetzt kommt der Teil, der alles ändert", "here's
where it gets interesting") and no idea told twice.

**Comparison videos:** at most two blocks with the same build in a row; the third changes form. A new hook at the half.
Each statement once. Cost and time of all candidates once, together on screen, not at the end of every block.

## Words

- The user's words from `voice.md`; never the words on its avoid list.
- **The spoken rhythm** (`references/craft.md`, group 3): connected sentences ("and so", "the reason is", "which
  means"), then a short punch line; about one sentence in four is short. Questions as joints, asked and answered at
  once (about 3 to 5 per 1,000 words). The viewer's objection said aloud. The key number repeated once. More "you"
  than "I" where it explains; "I" for the story and the failures. Written to be spoken, not read.
- Short sentences: median about 10 to 12 words, never more than `script.sentence_max_words` (22 in the neutral pack,
  so a teleprompter line stays readable).
- At most three product names in one sentence; longer lists go on screen.
- Out: basic knowledge the audience has, details nobody cares about (test counts, internal switches), file names,
  commands, side topics, private people, why an example was chosen, costs that are not part of the promise.
- No ad or sales tone: say what was tested, promise the viewer nothing. No grand "not this, but that" in the opening.
- Business shows through examples, not by addressing the viewer's business.

## Teleprompter form

The user reads from a phone next to the camera.

- Only spoken text above a line `---`. Notes for the edit (the story plan, scenes, clips, where each number comes
  from) go below it; shot ideas under "Shots" ("Bildideen"). The teleprompter shows nothing below the line.
- **Every mark reads aloud.** No colon, semicolon, bracket, slash, arrow or list mark in the spoken text: say it in
  words ("rund 35 Cent", not "Ergebnis: 35 Cent"). This is a hard check: `script_check.py` reports it as an error and
  the script card is refused while one is left.
- A paragraph is one breath: 1 to `script.paragraph_max_sentences` sentences. One empty line is a short pause.
- Three empty lines separate parts: there the edit can cut, there the teleprompter pages, there a clip can run.
- No brackets, stage notes, headings, chapters, timestamps or title line. Dashes only if the pack allows them.
- Mark the one or two key words of a paragraph in **bold**. The teleprompter's points mode shows them instead of the
  full text, for a user who wants to speak freely.
- **Motion marks** (optional, below `---`): up to five beats where a picture would say more than the face, as
  `[[motion: number | "30 cents per million tokens"]]`: the kind of picture, then the words as they are spoken. They
  are wishes for the Editor's motion pass (skill `motion`), which may drop any of them. The check counts them; a mark
  above `---` or a sixth mark is an error.

## Steps

The order: draft, check, the Critic's passes, **the Humanizer pass as the last step before the card**, the check once
more, card.

1. Fill the structure with the gathered facts and numbers, following `references/craft.md`.
2. Cut: every sentence carries or proves the promise. Cutting removes repeats and side topics, never the depth the
   brief asked for: examples, sums said aloud and "try this" lines stay.
3. Bring it into the user's voice. Read every sentence in your head: would the user say this into the camera?
4. Write the draft to `work/script-draft-vNNN.md` with the next free number; never overwrite a version.
5. Check the draft until 0 errors:
   `python3 skills/script/scripts/script_check.py work/script-draft-vNNN.md --title "<title>" --name "<tool>"
   --facts work/material-vNNN.md` (add `--minutes 11-14` when the brief sets the length). Read every warning and hint,
   the craft line (words per part, questions, "you" against "I", "try this" per depth part, the ending) and the "by
   hand" list; a hint you keep gets one sentence of reason below `---`.
   A studio skill with its own check: run that one, and also `python3 $CREWCUT_APP/skills/script/scripts/script_check.py
   <file> --spoken` (only the speak and story checks) and, unless the studio's check measures the craft, `--craft`.
6. **Story pass, craft pass and quiet claim check.** Have the Critic (subagent `crewcut:critic`) read the draft three
   times. First for the story (`references/story.md`, "The story pass"): does every paragraph push the premise, is
   there a list smell (the check names the paragraphs without a bridge), an idea told twice, a staged run-up, a
   subscribe line inside a beat or at the end? Then for the craft (`references/craft.md`, "What the Critic reads"):
   the hook's five parts and the limit by 0:45, every idea in the depth pattern, a plain sentence for every technical
   word, questions at joints, the ending with exactly one call to action and the loop resolved. The Critic rewrites
   those parts or sends the draft back; a draft like that never reaches the user. Then against
   `work/material-vNNN.md`: it marks only claims that are false or would mislead the viewer, never a word of feeling or
   style. Fix those in the wording itself and run step 5 again; never add a caveat because of a note. Nothing of this
   goes to the user.
7. **Humanizer pass, the last step before the card** (see below). Write the result to `brief/SCRIPT-vNNN.md` (same
   number), then record it: `crewcut humanize record --draft work/script-draft-vNNN.md --final brief/SCRIPT-vNNN.md
   --why "<the patterns that applied>"`.
8. Run the check of step 5 once more, on `brief/SCRIPT-vNNN.md`, until 0 errors. If you change the script to pass it,
   record the pass again: the card needs the record of the exact file.
9. Card: `crewcut card propose --episode <id> --step script --kind script --title "Script, version N" --file
   brief/SCRIPT-vNNN.md --body "<words>, about <min> min, check: 0 errors"`, then `crewcut card wait`. The card shows
   "Humanized" with what changed; without the record it is refused and says what to run. It is also refused while
   the spoken text has a mark that does not read aloud, or a long script has no story plan or a strong list smell.
10. After the yes: `crewcut prompter <id>` prints the phone link and a QR code. Tell the user in one message: the link,
    how many parts, about how long. The teleprompter shows only the text above `---`.

## Humanizer pass

Every script draft goes through **Humanizer** ([blader/humanizer](https://github.com/blader/humanizer), MIT) before
the user sees it: long videos and Shorts alike. Crewcut downloads its newest version at start; in Claude Code it is
the skill `humanizer:humanizer` (run it like any skill), with Codex its text is in your prompt. `crewcut skills status`
shows the version.

- **Mode "Embedded", with the user's voice.** Read every file in `brand/voice/` first: the user's own spoken words from
  their videos, and in `brand/voice/interviews/` their interview answers (this episode's too). Give them to Humanizer
  as the voice sample. No samples: plain mode; the card says so.
- **What to look for most:** "not X but Y" contrasts; closing lines that add nothing new; sayings that sound deep; a
  staged run-up before the point ("here's the thing"); lists of three; inflated meaning and advertising language.
- **What stays:** the user's own words and turns of phrase (those in `brand/voice/`, the interview and `voice.md`) even when Humanizer
  would smooth them; every number, name, claim and the promise of the title. The pass changes how it sounds, never
  what it says. The craft devices stay too: questions with their answers, objections said aloud, the one repeat of
  the key number, the examples, "try this", the roadmap and the ending's list. A contrast pair with two concrete
  sides ("seven hours against 35 minutes") is not the "not X but Y" pattern.
- **What is out of scope:** making text pass AI detectors. Humanizer edits for people, and so do we.
- **The hook may keep a device.** In a dramatic opening a deliberate device, such as a short triad of parallel
  sentences, may stay. Everywhere else the rules above apply.

## What the check cannot see

The craft check counts words; the Critic reads what it cannot see (the "by hand" list of the check and
`references/craft.md`): whether the demo comes by 1:30, whether every technical word gets its plain sentence, whether a
question is a real joint and a "try this" works without the product.

The list-smell check only finds paragraphs without a connector or a shared word; it cannot tell whether a beat pushes
the premise. Whether an example grows too broad, whether a part leaves the thread, whether a test fits the promise, whether the voice
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
