# Script forms and the cue sheet

## Test form (default)

For a tool, a model or a claim. The order is in SKILL.md, section "Structure".

## Story form

For a video where something happened: the user found something, a run went wrong, a result surprised.

1. **Start with a scene and a time** that carries the title's core word or number in sentence 1; a number or the
   announcement of the result comes by 0:20.
2. **Present tense, short statements, concrete details.**
3. **Every part ends open:** one sentence that leaves a question the next part answers. No part starts with "and then".
4. **Puzzle, solution, consequence:** first what the user saw, then what really happened, then what it means for their
   work.
5. **Own ending** (structure step 8): the verdict, then at most one link sentence with the end mention. No goodbye,
   no recap.
6. The subscribe line, the critical side and all word rules still hold.

Lessons for this form: one time stamp is enough; no private side notes; no chat quotes in a cheering tone (tell the
user's way and reason, not their chat messages); keep technical words in the language the audience uses for them; tell
the real reason for a decision in the user's words, never a nicer invented one; place the time when it matters (a model
that just came out).

## Comparison videos

From retention curves of a comparison video with five candidates: the curve stayed flat for three blocks of the same
build and fell at the fourth, with viewers skipping ahead to the verdict. Hence:

1. At most two blocks with the same build in a row. From the third on, change the form: two losers against each other,
   a before and after, a question to the viewer.
2. Do not promise a winner that only comes at the end when four blocks in a fixed order stand before it. Either the
   winner comes early and the rest answers a new question, or every block opens a question the next one closes.
3. At the half, a new hook: one sentence that says what is different now.
4. A block of praise starts with the catch or the price, not with praise and a "but" at the end.
5. Cost and time of all candidates once, together on screen.
6. Every praise and every verdict once. If it was said above, the second place goes or says something new.

## Cue sheet (planned)

The user may want to speak freely with structure instead of reading. The plan: one cue sheet per script,
`brief/SCRIPT-vNNN-CUES.md`, one block per script part, same order:

```
## Part 1
Start: <first sentence of the part, word for word, at most 14 words>
Keywords: <1 to 4 word groups, separated by " · ">
Number: <every number that must be exact>
Fact: <names and details to look up, no sentences, at most 6>
End: <only when a closing sentence must be exact>
```

- The start sentence is also the first sentence of the script part, so both takes can be found in the recording.
- `Verbatim:` instead of `Start:` only for hook, result and ending, at most three parts.
- The cue sheet has at most 40 % of the script's words (facts not counted).
- Recording: per part, first free from the cue sheet, then from the script, both starting with the start sentence.
- After the recording, the edit picks per part: free (all numbers and most keywords said, not much longer), mixed (free,
  plus the sentence with a missing number from the script take), script, or a re-take.

Until then, the teleprompter's "points" mode (`GET /p/{token}/script`, `mode: points`) shows the bold key words of each
paragraph, or its first words when nothing is bold. The cue sheet will show there later.
