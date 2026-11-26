# Script craft: opening, counted units, rhythm, ending

How good long explainers are written, as rules the Writer follows and the Critic checks. Since 26 Nov 2026 the rules
follow a study of Alex Hormozi's long videos (54 best against 33 typical ones, 443 openings, 542 endings) and the
retention curves of one channel that applied it. Where that study contradicted the earlier rules (measured on 119 long
videos of three English-language education channels in November 2026), the earlier rule is gone: no recap list and no
goodbye at the end, no honest limit before the first content, no "try this" in every part, no number forced into the
first sentences. Read this page before every draft. `script_check.py` measures what a program can see
(`crewcut/craft.py`); the Critic reads the rest (the list at the end). A studio with its own style checker (the style
gate, `docs/architecture.md`) adds a hard gate on top; its rules win where they are stricter.

The rules work in every language. The check has word lists for English and German; the function counts, not the
words, so never copy a phrase from another channel one to one.

## Length follows the brief

The length comes from the episode's brief, not from one fixed number. A short test may need 3 to 5 minutes; an
explainer with depth needs 11 to 14 minutes (about 1,900 to 2,400 spoken words at 165 to 185 words per minute).
Pass the brief's range to the check with `--minutes 11-14`; without it the check uses `edit-style.json`
`length_minutes`. Depth needs words: one of the measured channels needs about 1,900 words for six steps.

## 1. Opening: the first 30 seconds

1. **Sentence 1 is a claim or a result of the own test** that proves the title's promise, with the title's core word or
   number. No greeting, no run-up, no tool promise ("X promises you ..."), no "not X, but Y". An assumption plus the
   own result works ("Local AI counts as the safe option. I tested two models, and nine runs tried to send data out").
2. **By 0:15 the real result with its exact number**; at **0:10 to 0:20 a number or the announcement** of what the
   viewer has at the end. Our own curves lose 15 to 19 points exactly there when it carries background instead.
3. **Why it matters**, as the viewer's situation in one "If you ..." sentence.
4. **A plan with a count by 0:30**: one sentence that counts the parts ("the four jobs"). The count must match what the
   video shows.
5. **At most one open loop**: one promise the end resolves with exactly the promised thing.
6. **Before point one only** proof, number, announcement, the viewer's situation, the plan or the one loop: no
   background ("Kurz zu dem Problem"), no limit or caveat, no greeting, no ask. The first content is marked below `---`
   with `[[first content | "the spoken words"]]`.

The start is dense, not rushed: short sentences, two numbers, result pictures.

## 2. Counted units

The middle is a **counted list on the outside, the test on the inside**: 3 to 5 units of **45 to 75 seconds**, each a
step of the test or an action with its own evidence (a number, a screen, an incident, a sum).

- **Before every lesson a test, a picture or a story from this video**; every claim gets its evidence at once. Two
  units in a row never use the same kind of evidence.
- **Every technical word gets one plain sentence the first time** ("A sub-agent is a helper: another copy of the model
  with one narrow job."). At most one new word every 20 seconds.
- **Concrete, not abstract**: an example ("Let's say you run a gym ..."), at least one sum worked out aloud that ends in
  the viewer's time or money ("300 frames times 85 seconds, that's about seven hours"), and contrast pairs with two
  concrete sides ("seven hours on the laptop against 35 minutes on a rented machine"). A contrast pair is not the grand
  "not X, but Y": that stays out.
- **Count the parts aloud** ("step three", "the fourth job"), and give each unit one ordering sentence ("The reason is
  ..."). No staged run-ups and no hype lines ("here's where it gets crazy").
- **The advice belongs in the sentence** ("If you edit alone, let a second chat check the cut"). At most one added
  "try this" line in the whole video.
- At most one theory stretch of 30 to 60 seconds, none longer. Three empty lines between two units.

## 3. Spoken rhythm

- **Connected sentences, then a punch line.** Explaining sentences joined with "and so", "the reason is", "which
  means"; then one short sentence that lands the point: "None." "Exactly one." Long sentences up to the pack's limit
  (`script.sentence_max_words`) only as a chain, never nested.
- **Questions as joints**, 1.5 to 4 a minute, each answered in the next sentence, and the answer never starts with
  "because": "And if one try takes seven hours, how many tries do you make? One."
- **The viewer's objection said aloud**: "Now you might think: why not one big prompt?" Then the answer. One or two in
  a video.
- **The key number repeated once**, on purpose: "I'll say it again: seven hours against 35 minutes."
- **"You" at least as often as "I".** "I" is for the test, the finding and the verdict; "you" explains ("if you ...,
  then ...", "you see ...").
- **Written to be spoken, not read**: natural spoken word order, the verb early, no nested clauses.
- **Pace**: calm and sure, not fast. A script cannot measure pace; it is a note for the recording and the edit.

Leave out: wealth and status talk, provoking the viewer, superlatives without proof, private life stories, fear of
being replaced, the same ad in every video, and set phrases copied from other channels.

## 4. Ending, and the automatic check

- **One fixed ask in the middle**, word for word the same in every video, between 15 and 60 % of the script, right
  after the first strong result; never in the ending and never inside a unit.
- **The ending is a verdict that picks up sentence 1** (a word or the number), then **at most one link sentence**
  (the offer the channel always names, `script.end_mentions`), then the cut. At most 25 seconds; mark the verdict below
  `---` with `[[urteil | "the spoken words"]]`.
- **No goodbye, no thanks, no recap, no list of the parts and no question** in the last 60 seconds. Every goodbye cost
  the measured channel 10 to 14 points of its audience, and only 11 of 542 strong endings recap.
- **The hook's open loop is resolved** before the ending ("And now the cost I promised at the start.").
- **Nothing the episode does not prove.** Every number comes from the episode's files or an earlier measurement; say
  so when a number is projected.

## What `script_check.py` measures

The long mode and `--craft` run these checks before the Writer makes the card. Errors must go; read every warning and
hint and give a hint you keep one sentence of reason below `---`. Levels and limits are in `channel.json`
`script.craft` (docs/style-packs.md); a text under 150 words gets only the greeting check.

| Group | Measure | Default level |
| --- | --- | --- |
| Opening | greeting in the first two sentences | error |
| Opening | sentence 1 carries a core word or number of the title (`script.checks.title_word_sentence_1`) | warn |
| Opening | a number in words 33 to 67 (`script.number_window_words`, `script.checks.number_window`) | warn |
| Opening | a plan with a count ("four jobs") in the first 30 s | warn |
| Opening | an open loop in the first 30 s | hint |
| Opening | why it matters ("if you", "costs", "lose") in the first 30 s | hint |
| Opening | a limit or caveat before the first content (the mark, else the first counted part) | warn |
| Units | each unit (a part of 80 words or more between opening and ending) 45 to 75 s | warn |
| Units | more than one "try this" line | warn |
| Units | examples, sums aloud, contrast pairs, signposts | hint at none |
| Rhythm | sentences over `sentence_max_words` (32) | error |
| Rhythm | share of short sentences (up to 5 words), 15 to 40 % | hint |
| Rhythm | questions per 1,000 words, 7.5 to 20 | warn |
| Rhythm | a question without an answer in the next sentence, an answer that starts with "because" | warn |
| Rhythm | objections said aloud, the key number repeated | hint at none |
| Rhythm | "you" against "I" in the whole script | warn when "I" wins |
| Ending | the ending (from the verdict mark, else the last part) over 25 s (+10 %) | warn |
| Ending | a request other than one link sentence in the ending; no fixed ask, or one outside 15 to 60 % | warn |
| Ending | more than one subscribe line in the script | warn |
| Ending | goodbye or thanks in the last 60 s | error |
| Ending | recap or the list of the parts in the last 60 s | error |
| Ending | the hook's open loop resolved in the last 40 % | warn |

## What the Critic reads (the check cannot see it)

After the story pass (`references/story.md`) the Critic does the craft pass and rewrites or sends back:

1. Sentence 1: a claim or an own result that proves the title's promise, not a run-up?
2. By 0:15 the real result with its exact number? At 0:10 to 0:20 a number or the announcement?
3. The title's topic before any other; before point one only proof, number, announcement, situation, plan or one loop?
4. Every unit: an action or a test step with its own evidence; never the same kind of evidence twice in a row?
5. Before every lesson a test, a picture or a story from this video?
6. The end of each unit opens the question the next answers?
7. Every name and reference clear to someone who never saw the creator?
8. Every open loop resolved with exactly the promised thing?
9. The end is a verdict that picks up sentence 1, not a summary; no goodbye?
10. Does it sound spoken? Read it aloud. A sentence the user would not say goes back.

With the style gate on, the Critic answers the checker's own yes/no questions in `<script>.kritik.json` next to the
script; in doubt the answer is no.

## Order until the card

Draft, check (0 errors; with the style gate the checker's `--nur-auto` run passes), the Critic's story and craft pass
(with the gate: its answers in `<script>.kritik.json`), **the Humanizer pass as the last step before the card**, the
check once more (0 errors; with the gate the full run passes; if it changes the text, record the Humanizer pass
again), card. The Humanizer keeps the craft devices: counted words, ordering sentences, objections, the one sum, the
one repeat of the key number, the fixed ask word for word, and the verdict with the word from sentence 1.
