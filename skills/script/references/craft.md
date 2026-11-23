# Script craft: hook, depth, rhythm, ending

How good long explainers are written, as rules the Writer follows and the Critic checks. Measured on 119 long videos
(about 600,000 words of transcript) of three successful English-language education channels in November 2026: one
monologue channel and two tutorial channels. Read this page before every draft. `script_check.py` measures what a
program can see (`crewcut/craft.py`); the Critic reads the rest (the list at the end).

The rules work in every language. The check has word lists for English and German; the function counts, not the
words, so never copy a phrase from another channel one to one.

## Length follows the brief

The length comes from the episode's brief, not from one fixed number. A short test may need 3 to 5 minutes; an
explainer with depth needs 11 to 14 minutes (about 1,900 to 2,400 spoken words at 165 to 185 words per minute).
Pass the brief's range to the check with `--minutes 11-14`; without it the check uses `edit-style.json`
`length_minutes`. Depth needs words: one of the measured channels needs about 1,900 words for six steps.

## 1. Hook in 30 seconds

The first 30 seconds (about the first 90 to 110 words) carry all of this:

1. **A result or a claim first.** No greeting before the hook. None of the measured hits starts with a greeting.
2. **Why it matters**, in one sentence ("If you edit alone, editing eats whole weekends."). Seven of ten hits of one
   tutorial channel say it by second 30; its other videos only 13 of 30.
3. **One measured number.** The monologue channel names a number by second 30 in 31 of 40 videos.
4. **A roadmap with a count**: one sentence that counts the parts ("the four jobs"). The viewer knows how long the trip
   is. The count must match what the video shows.
5. **An open loop**: one promise the end resolves. The total cost of the work is a good one.
6. **One honest limit by 0:45**: "Is it perfect? No." and one sentence on what does not work yet. It makes everything
   after it credible.
7. **The first demo of the real thing by 1:30.** The tutorial channels show their own tool at a median of 0:40.

The start is dense, not rushed: short sentences (4 to 10 words), two numbers, result pictures. All three channels keep
the same speaking rate over the whole video (within 5 %); the first minute only holds twice as many numbers.

## 2. Depth pattern

Each idea takes **40 to 60 seconds**, the median of all three channels. Each idea has the same order:

1. **Question**: what is the problem? A real question that gets its answer at once.
2. **Why**: the mechanism in one sentence ("The reason is ...").
3. **How**, on screen, with the real tool. The shot idea goes below `---`.
4. **Failure or limit**: what went wrong, with a number or a picture. Failures stay in.
5. **Number**: one measured number of this idea.
6. **Try this**: one small task the viewer can do today without the product. One sentence.

In every idea:

- **Every technical word gets one plain sentence the first time** ("A sub-agent is a helper: another copy of the model
  with one narrow job."). At most one new word every 20 seconds. One tutorial channel uses the one-sentence
  definition more than any other device (105 times in 40 videos).
- **Concrete, not abstract**: an example ("Let's say you run a gym ..."), a sum worked out aloud with round numbers
  ("300 frames times 85 seconds, that's about seven hours"), and contrast pairs with two concrete sides ("seven hours on
  the laptop against 35 minutes on a rented machine"). The monologue channel uses 200 examples, 110 comparisons and 54
  sums aloud in 40 videos. A contrast pair is not the grand "not X, but Y": that stays out.
- **Count the parts aloud** ("step three", "the fourth job"). Signposts carry the structure: more than half of all
  transitions in the tutorial channels. A signpost still needs its bridge to what came before ("That brings us to job
  three").
- Three empty lines between two ideas. A part longer than about three minutes holds several ideas: split it.

## 3. Spoken rhythm

- **Connected sentences, then a punch line.** Explaining sentences joined with "and so", "the reason is", "which
  means"; then one short sentence that lands the point: "None." "Exactly one." About one sentence in four is short (up to
  six words). In the depth parts, 11 to 14 words per sentence on average.
- **Questions as joints**, asked and answered at once: "And if one try takes seven hours, how many tries do you make?
  One." About 3 to 5 per 1,000 words, so 7 to 11 in a long script.
- **The viewer's objection said aloud**: "Now you might think: why not one big prompt?" Then the answer.
- **The key number repeated once**, on purpose: "I'll say it again: seven hours against 35 minutes."
- **More "you" than "I" where it explains.** "I" is for the story and the failures. All three channels say "you" more
  often than "I" (for example 41 against 32 per 1,000 words).
- **Written to be spoken, not read**: natural spoken word order, the verb early, contractions where the speaker uses
  them, no nested clauses.
- **At most 22 words per sentence** (teleprompter). The pack sets it (`script.sentence_max_words`).
- **Pace**: calm and sure, not fast. From minute two about 165 to 185 words per minute. A script cannot measure pace;
  it is a note for the recording and the edit.

Leave out: wealth and status talk, provoking the viewer, superlatives without proof, private life stories, fear of
being replaced, the same ad in every video, and set phrases copied from other channels.

## 4. Ending, and the automatic check

- **At most 60 seconds**, set apart with three empty lines, in four steps:
  1. the parts as one list in one sentence,
  2. what the human still does (record, say yes, taste),
  3. a verdict with its limit,
  4. **exactly one call to action**.
  Then the channel's closing line. An offer the channel always names (`script.end_mentions`) is no second call to
  action as long as it asks for nothing.
- **The hook's open loop is resolved** before the ending ("And now the cost I promised at the start.").
- **One subscribe line** in the whole video, right after the first strong result, never in the ending.
- **Nothing the episode does not prove.** Every number comes from the episode's files or an earlier measurement; say
  so when a number is projected.

## What `script_check.py` measures

The long mode and `--craft` run these checks before the Writer makes the card. Errors must go; read every warning and
hint and give a hint you keep one sentence of reason below `---`. Levels and limits are in `channel.json`
`script.craft` (docs/style-packs.md); a text under 150 words gets only the greeting check.

| Group | Measure | Default level |
| --- | --- | --- |
| Hook | greeting in the first two sentences | error |
| Hook | a number in the first 30 s of words (rate from `words_per_minute`, the start 20 % faster) | warn |
| Hook | a roadmap with a count ("four jobs") in the first 30 s | warn |
| Hook | an open loop ("at the end", "later in this video") in the first 30 s | warn |
| Hook | why it matters ("if you", "costs", "lose") in the first 30 s | hint |
| Hook | an honest limit ("not perfect", "not yet", "can't") in the first 45 s | warn |
| Depth | words and seconds per part (parts are separated by three empty lines); a part over 180 s | hint |
| Depth | "try this" per depth part (a part of 80 words or more between hook and ending) | warn at none, hint naming the parts without one |
| Depth | examples, sums aloud, contrast pairs, signposts | hint at none |
| Rhythm | sentences over `sentence_max_words` (22) | error |
| Rhythm | share of short sentences, 15 to 40 % | hint |
| Rhythm | questions per 1,000 words, 2.5 to 6 | warn at none, hint outside |
| Rhythm | a question without an answer in the next two sentences of its part | hint |
| Rhythm | objections said aloud, the key number repeated | hint at none |
| Rhythm | "you" against "I" in the depth parts | hint when "I" wins |
| Ending | length of the last part, at most 60 s (+10 %) | warn |
| Ending | calls to action in the ending (link or form, subscribe, comment, next video, like, follow) | warn unless exactly one |
| Ending | more than one subscribe line in the script | warn |
| Ending | the list of parts, the human's part, a verdict with its limit | hint |
| Ending | the hook's open loop resolved in the last 40 % | warn |

## What the Critic reads (the check cannot see it)

After the story pass (`references/story.md`) the Critic does the craft pass and rewrites or sends back:

1. Hook: are the five parts really there, or only their words? Is the number measured? Does the demo come by 1:30?
2. Every idea: question, why, how, failure or limit, number, try this. Does the task work without the product?
3. Every technical word: one plain sentence the first time?
4. Questions: at joints, or filler? More than 11 in a long script are too many.
5. Objections: do they sound like a real viewer's doubt?
6. Ending: four steps, exactly one call to action, the loop resolved, the verdict with its limit.
7. Does it sound spoken? Read it aloud. A sentence the user would not say goes back.

## Order until the card

Draft, check (0 errors), the Critic's story and craft pass, **the Humanizer pass as the last step before the card**,
the check once more (0 errors; if it changes the text, record the Humanizer pass again), card. The Humanizer keeps the
craft devices: questions with their answers, objections said aloud, the one repeat of the key number, the examples,
"try this", the roadmap and the ending's list.
