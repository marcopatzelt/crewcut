# From the recording to the speaker cut

Read all of it before you touch the first file. Each step has the command, the rule, the trap. Paths are relative to
the episode folder. Exact arguments of every tool: `crewcut cut <tool> --help`.

## 1. Ingest, and check the sound to the end at once

`crewcut ingest <episode> <file> [<file> …]` copies the files to `originals/` and writes `brief/ingest-<sha>.json`.

- Never write to or delete from the user's card or folder. Ingest only reads there.
- Ingest reports two things: which channel carries the clip-on microphone, and **sound to the end**: "sound until X s
  of Y s, then Z s silent". More than 30 s of silence at the end is a WARNING.
- On that warning, act at once. Look at a still from the silent part. If the speaker talks there, the sound is missing.
  Tell the user before you cut, with exactly which script sentences are missing.
- Before you report it, check the ways out and name the result: (1) Is the sentence in another file with sound?
  (2) Does the file have a second track, or does the other channel carry the camera microphone? Test: raise the other
  channel by 40 dB and look at the level per second. If it does not move with the speech, it is only noise.

## 2. One recording or several?

- Cameras split a long recording at about 4 GB. **Two files with consecutive numbers and times are usually one
  recording, not two takes.**
- Test: the text of the first file stops in the middle of the script and the second starts exactly there. Then it is
  one recording, and there is no "better take per section" to choose.

## 3. What was said? Two ways, use both

- Fast: word times for the whole file (`crewcut transcribe <file>`).
- Exact but slow: speech islands from the pause list (`crewcut cut islands …`), only for ranges the fast way skipped.
- **Trap:** the fast way skips whole sentences and invents some ("thanks for watching", "subtitles by …"). Check: the
  pause list shows speech islands (longer than 1 s) with no words. Fetch those ranges with the exact way.
- **Trap:** a very quiet file (under -25 dB) is not heard. Raise it first.
- Cut edges always come from the pause list (island borders), never from transcript times. Transcript times are only
  for finding.

## 4. Choosing: the rules

1. **The last complete take wins.** People repeat a sentence until it sits. Take the last complete attempt.
2. **Follow spoken instructions.** Speakers talk to the editor while recording: "the first version was fine" (take the
   first, not the last), "cut this part", "scratch that" (drop everything since the last complete sentence), "I'll just
   read on". These sentences never go into the video.
3. **What the speaker said beats the script.** Cut what was said. Keep a list of the differences for the report.
4. **A select starts and ends at an island border.** If the edge falls inside an island (two sentences without a
   pause), measure the dip (`crewcut cut islands … dips`). Usable: a dip under -40 dB for at least 0.06 s.
5. **Never start in the middle of the speech flow**, even when the content fits. A start with only a shallow dip
   leaves a word rest. Better: a whole sentence from the main recording as a bridge.
6. **Probe every edge.** The text must match with the whole first and the whole last word.

## 5. Double sentence starts (required before building)

`crewcut cut doubles <selects>` finds a short piece (under 2 s) at the start of a select followed by the same sentence
start again. Required, because the transcript and the cut verification do not report it (transcribers drop
repeats). Fix: let the select start at the second attempt.

## 6. Build, verify, grade, words

1. `crewcut cut plan <selects>` and `crewcut cut build <cut plan>`.
2. `crewcut cut verify <edit decisions>`: `bad_joins` must be empty (the pause at each join is inside the allowed
   range). Too short: give the select before it a tail, or move its end a little into the silence. Too long: start
   the next select at the real speech onset (measure with dips). `edge_issues` must be empty, unless it is only spelling.
3. Issues of type "replace" are almost always spelling. "insert" with several words is a double start: back to step 5.
4. Speaker values from the pack: `speech_speed`, `zoom_base`, `zoom_punch`; format and fps from `edit-style.json`.
   Measure the face centre per take on a grid still and write it as shares of the frame (plan key `face`).
5. **Grade.** Every episode gets its own measured grade (`crewcut cut grade`, measure first, then apply). Never copy grade
   values from an old episode. The measurement goes to `review/`; the style check looks for it.
6. Words of the finished cut: `crewcut transcribe audio/voice-vNNN.wav` → `work/words-vNNN.json`.
7. Every correction is a new version (v002, v003 …). Collect all findings of verify and doubles first, then build ONE
   new version. Only one heavy job runs at a time (the job queue does that).

## 7. Re-shoot

- **With camera and clip-on microphone, never sound alone over Bluetooth.** Bluetooth headsets cut the high
  frequencies; an equaliser does not bring them back.
- A re-shoot is its own take in the selects, with its own `face` and a zoom factor that matches the other camera
  distance (measure the head height in both takes; the ratio is the factor).
- Check the light: measure the same wall area in both takes. Under 5 steps difference: the same grade is enough.
- **The seam between main recording and re-shoot never sits visibly on the speaker.** Put an insert over the last
  sentence before the seam or the first after it.
- If the re-shoot lacks a clean attempt for a sentence, check in this order: (a) is the sentence with sound in the
  main recording? (b) can it go without losing what "this" or "that" refers to? (c) only then a start after the slip,
  and only at a real pause.
- Before building, send the user the list: time, text, verdict per attempt (complete / slip / broken off), and what
  you take.

## 8. An order that saves time

1. Ingest (checks the sound to the end). 2. Fast words, exact gaps. 3. Selects. 4. Doubles. 5. Plan and build.
6. While verify runs: measure the grade. 7. Collect findings, one new version. 8. When verify is clean: apply the grade,
get the words of the finished cut, write the edit plan (`SKILL.md`).

## 9. Showing, approval, final

1. **A build is unchecked until both checks show 0 ERROR** (skill `cut-check`). Nobody sees the build output. Tell
   whoever coordinates: "built, unchecked, do not show".
2. **Only after 0 ERROR:** the preview goes to `export/<id>-vNNN-preview.mp4`. Only files in `export/` go to the user.
3. **Lock right after showing:** `crewcut render shown <plan>` writes `<output>.shown` with time and sha256. The
   workbench then refuses to overwrite it. The approval card stores the same checksum.
4. **Every change after showing is a new plan version**, even for two frames. Never rebuild in place.
5. **Approved is exactly the file the user saw** (compare sha256). It becomes `export/<id>-vNNN-final.mp4` without
   overwriting anything. If a later build fixed a real fault, the user decides which file counts; name the difference
   exactly (frames, length, loudness, which inserts moved).
6. **Captions for the final** (`crewcut cut srt …`): built on exactly the speaker cut that this final uses, with the
   spelling of the selects. Check three captions (start, middle, end) against what is said at those times.
7. `project.json`: the final file, its length and sha256, the user's words with the date, the measured loudness, and
   what is NOT final.
