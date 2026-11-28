# Cue sheets: fix only the lines that must be exact

A cue sheet is a script that does not make the speaker read. It fixes the opening, and per unit the first line (the
hook) and the last line (the punch line); everything between them is bullets the speaker says in their own words. A
long video is a chain of units, and each unit is built like a Short (hook, retain, reward); whether it also works alone
as a Short is only a hint, and `Short: yes` marks the units that do.

Crewcut reads cue sheets in the teleprompter (pages instead of running text), in the style gate (the plan before the
recording, and what was said after it) and on script cards. The parser is `crewcut/cuesheet.py`.

## The file

`brief/CUES-vNNN.md` (or `brief/DREHZETTEL-vNNN.md`, the German name), numbered like scripts. Above the first line that
is only `---` stands the sheet; below it, notes for the edit. English and German markers are built in.

```
## Opening                                   (## Einstieg)
LINE1: The cheapest setting built my best clip. [Picture: the ranking]
PROOF: I tested four settings on eight clips.
PLAN: Here is why, in three points.

## Unit 1 | Proof: Screen | Short: yes      (## Einheit 1 | Beleg: Bildschirm | Short: ja)
HOOK: Point one. My best clip took 40 minutes, the worst one 90.
• Proof: [both clocks side by side] 40 minutes against 90 · same prompt
• Example: [the run log] three helpers · street, flat, edit
PUNCH: Helpers beat thinking time.
ASK: If you like tests like this, subscribe.            (BITTE:)
BRIDGE: So where did the time go?                (optional)                       (BRÜCKE:)

## Unit 2 | Proof: Number | Short: no
…

## Close                                     (## Schluss)
VERDICT: I keep the cheap setting for big jobs.         (URTEIL:)
LINK: If you want this system, the link is in the description.
```

- Every line starts with a marker or is a bullet (`•` or `-`). A fixed line is said word for word; a picture cue in
  square brackets is not spoken.
- A bullet names what is on screen first (`[both clocks side by side]`), then cue words separated by ` · `. It is not
  a sentence: the speaker makes the sentences.
- Opening markers: `LINE1`, `PROOF`, `SITUATION`, `PROMISE`, `LOOP`, `PLAN` (German `SATZ1`, `BEWEIS`, `LAGE`, `ANSAGE`,
  `SCHLEIFE`, `PLAN`). Unit: `HOOK` first, bullets, `PUNCH`, then only `ASK` and `BRIDGE`. A bridge is optional: a real
  question that comes out of the unit, or nothing (the next hook's count word is enough). Hook and punch line may also
  be cue words; a full short sentence is the default. An optional `## Payoff` (`EINLÖSUNG`) between the last unit and the close keeps a promise from the opening.
  The close has a `VERDICT` and, as its last line, one `LINK`.
- The unit heading carries the kind of proof and whether the unit can go out as a Short on its own.

## In the style gate

With a studio checker that knows cue sheets (the own skill's checker; see [own skills](own-skills.md)), the gate works
like this:

1. **The plan.** After every Writer run the gate runs the checker on the newest cue sheet. Hard are only the things a
   machine can decide: the sheet parses, the fixed ask is there word for word, the link line is last. Counts (a number
   in the hook, the length of the punch line, the estimated duration, explanation clauses, short questions) come back
   as hints (`kind: "hinweis"`) for the Critic, never as failures.
2. **The Critic.** A check may name an `instructions` file. The gate gives the Critic that file: it reads every
   sentence and every unit, asks the questions the file lists, cites its sources, and writes a rewrite for every line
   that gives the viewer nothing. Its verdict carries a checksum of the text, so it is only valid for the version it read.
3. **The fresh review.** A check may set `fresh_context` (with an `answer_key`): once the Critic approves, a second
   Critic reads the script again in a new session, without chat and crew notes, told not to read the notes below `---`
   or earlier reviews. Only when both approve does the gate go on.
4. **The loop.** With `loop = "until_pass"` the Writer and the Critic take turns until the Critic approves. If the same
   point stays open, unchanged, for two rounds in a row, the gate stops and puts exactly that point on a card
   ("Not approved: …"). `safety_rounds` is only an emergency stop. A script that does not pass never goes to the user
   as approved.
5. **The second opinion.** When everything else passes and the checker asks for one (`second_opinion: true`), the gate
   asks a second model through the host helper (`crewcut/second_opinion.py`, job `second-opinion` in
   `host/crewcut-host.sh`). Set `CREWCUT_SECOND_OPINION_CMD` on the host; the command reads its prompt from
   `$INPUT_FILE` and prints a JSON answer (`{"agree": …, "points": […]}`). It runs in its own folder
   (`CREWCUT_SECOND_OPINION_DIR`), at most `CREWCUT_SECOND_OPINION_PARALLEL` (default 2) at a time. Without the helper
   or the command, the answer is "unavailable" with the reason, and the card shows it. A disagreeing second opinion
   sends its points to the Writer.
   Who starts the helper: `./start.sh`, or the **desktop app** (macOS and Linux), which runs it as its own child
   process next to the stack and stops it on Quit. The app makes the key once (`CREWCUT_HOST_TOKEN` in `stack/.env`
   in its data folder, owner-only) and gives it to the container; a container that was started before has no key
   until the next start (quit the app and open it again). The app takes the command from the environment
   (`CREWCUT_SECOND_OPINION_CMD`, `_DIR`, `_PARALLEL`) or, since an app started from the menu has no terminal
   environment, from its `settings.json` (never from a page, since the command runs on your computer):

   ```json
   "secondOpinion": { "command": "/path/to/your-wrapper", "parallel": 2 }
   ```

   Its work folder is `second-opinion/` in the app's data folder unless you name another (never your home folder);
   with `./start.sh` it is `.host/second-opinion/` in the repository. Both lie outside the studio, so a command with
   tools finds no files the crew put there. Feed the script to the model as text and do not let it run tools without
   asking: the script was written by the crew. `crewcut doctor` names who runs the helper and how many runs it allows
   (`second opinion: the host helper (desktop app) can ask a second model, at most 2 at a time`). A refused request
   (another key, an old prompt, no command) gets its answer at once, with the reason.
6. **The card.** Only a sheet that passes all of this gets a script card.

## After the recording

When the words of a finished voice cut are in (`crewcut transcribe audio/voice-vNNN.wav` writes `work/words-vNNN.json`),
the gate asks the Critic to review what was actually said against the cue sheet. The checker finds the fixed lines in
the transcript, so it knows where each unit begins and ends. The Critic marks every spoken sentence without value; the
checker turns the marks into `edit/cutlist-vNNN.json` (sentence, start, end, reason) for the Editor. Nothing is
blocked: the Editor listens to each place and cuts at islands, never at word times.

## Recording

See [recording](recording.md#recording-from-a-cue-sheet): one take per unit is enough, the hook and the punch line as
written, the bullets in the speaker's own words; a unit can be recorded again on its own, because every cut between
units lies in the pause before the next hook.
