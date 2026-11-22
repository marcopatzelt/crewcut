# One story, not a list

A script fails when every point from the brief, the chat or the interview becomes its own paragraph, in the order it
came in. The video then sounds like a checklist: each paragraph opens a new topic, nothing causes anything, and the
viewer has no reason to wait for the next part. This page is the method against that. `script_check.py` and the
script card check the parts a program can see (`crewcut/spoken.py`); the Critic reads the rest.

## Story first, then the draft

Before the first sentence of the draft, write the plan into the script notes, below the `---` line:

```
Premise: <one sentence: what the whole video is about, the through-line every paragraph pushes>
Arc: hook <...>, tension <...>, turn <...>, payoff <...>, close <...>
Beats:
- <beat 1>
- <beat 2>
- <beat 3>
```

- **Premise:** one sentence. If a paragraph does not push it, the paragraph goes.
- **Arc:** hook, tension or problem, turning point, payoff, close. German labels work too (Prämisse, Bogen: Einstieg,
  Problem, Wende, Auflösung, Schluss).
- **Beats:** 3 to 5. Each beat is a step of the arc, not a topic from the brief.

Brief items, chat notes and interview answers are a **material pool**. Pick what serves the arc and drop the rest, even
when it is true and the user said it. An example the user gives ("something like the time I burned money on an
expensive GPU") is a hint at the kind of moment wanted, not a line to insert word for word. Use it only where it moves
the story.

## Transitions

Each beat ties to the one before with cause or contrast: "so", "but", "and then", "that is why" (German: "deshalb",
"aber", "und dann", "darum"). A new topic needs a bridge sentence that says why it comes now. A paragraph that could
swap places with its neighbour without anyone noticing is a list item.

## Spoken text only

The user reads the script from a teleprompter. Above the `---` line there are only words to say: no colon, semicolon,
bracket, slash, arrow, list mark, heading or bracket cue. Shot ideas go below the line, under "Shots" ("Bildideen").
The teleprompter never shows what stands below the line, and it also stops at a shots or notes heading that slipped
above it. A script card is refused while such a mark is left.

## The story pass (Critic)

Before the script card, the Critic reads the draft once only for the story and rewrites it or sends it back:

1. Does every paragraph push the premise?
2. List smell: paragraphs that change topic without a bridge (`script_check.py` names them).
3. An idea told twice, a staged run-up ("now comes the part that changes everything", "here's where it gets
   interesting"), a subscribe line inside a beat or at the very end.

The Humanizer pass still runs after the draft. In a dramatic hook a deliberate device, such as a short opening triad,
may stay; everywhere else the Humanizer rules apply.

## Example pair

The same facts, twice. The first is a list: true sentences, each its own topic. The second tells one story.

**List (do not write this):**

```
I let a local AI transcribe 40 hours of my old podcast.

It took one evening on my laptop.

The tool is free and runs offline.

A transcription service charges 90 dollars per hour of audio.

My machine has 32 gigabytes of memory.

Names are the hardest part for any model.

Subscribe if you like tests like this.

The export comes as plain text files.

Search engines read text, not audio.

Many podcasters still skip transcripts.

Here's the thing. Accuracy was 96 percent.

Thanks for watching.
```

**One story:**

```
Forty hours of my old podcast were sitting on a drive, and nobody could search a single word of them.

Transcripts would fix that. But a service wanted 90 dollars for every hour of audio.

So I tried a free local model instead, on the laptop I already had.

That evening I started it on all forty hours and went to bed.

By the morning all forty hours were text. The laptop had not even run hot.

But was the text right? I checked ten random minutes against the audio, word by word.

Ninety-six words in a hundred were correct. The mistakes were almost all names.

That is the one catch. A model has never heard the name of your guest, so it guesses.

So I gave it a list of every guest name and ran the worst episode again.

Now it spelled every one of them right.

If you want more tests like this, subscribe. No company pays for them.

And the drive? Every word on it is searchable now, for zero dollars.

Thanks for watching.

---
Premise: A free local model turned forty hours of unsearchable audio into text overnight, once it knew the names.
Arc: hook the drive nobody can search, tension the 90 dollar price, turn the free model on my own laptop, payoff 96 in
100 and the name fix, close the searchable drive
Beats:
- the price of a service
- one night on my own laptop
- the check, and the names it got wrong
- the name list fixes it
Shots: the drive, the price page, the progress bar overnight, the error list.
```
