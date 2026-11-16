# Crew talk

Crew members can message each other directly, in three narrow cases. **Off by default** until the measurement below
has run on the demo episode. Switch it on with one sentence ("crew chat on"; the Showrunner runs
`crewcut crew talk on`) or in `config/crewcut.toml` (`[crew.talk] enabled = true`); "no crew chat" switches it off.

## Why only three cases

The episode runs in ten fixed steps, and results are files: a file costs nothing, can be checked and stays. A message
costs a model turn every time. A free conversation of the whole crew does not pay off. Direct messages pay off where a
round trip through the Showrunner would cost more:

| Case | From, to | Gain |
|---|---|---|
| `fix` | the Critic to the builder, all findings of one version bundled | the builder continues its own session and still knows its cut; the Showrunner is not the messenger |
| `question` | anyone to the author of a file in use | a question before the work is cheaper than a correction after it |
| `notice` | the author of a changed file to those who read it | collected, handed over at the next start; nobody is woken up for it |

Never by message: the user's decisions (cards), assignments (the Showrunner gives work), results (files), money.

## How it runs

- `crewcut say --to <crew member> --about <file> --kind fix|question|notice "…"`. When the recipient runs right now,
  Claude Code's own cross-session messaging reaches it (every run has a session name such as `editor-003-local-llms`
  and accepts messages from other sessions while crew talk is on); otherwise its last session in this episode continues
  with the message (`--resume`). A recipient's row in the crew column says why it works: "Editor · Fixing 3 findings
  from the Critic".
- A finished exchange is one collapsed line in the chat ("Critic and Editor · fix about review/cut-check-v001.json ·
  2 messages"); opened, it shows the messages.
- The limits are counted by Crewcut (and by the plugin's hook for Claude Code's own SendMessage): 2 rounds per topic,
  3 fix rounds per piece of work, 20 messages per episode, a file named in every message. The numbers live in
  `[crew.talk]`; the user can change them or switch the hook off. Crewcut never denies Claude Code's own messaging when
  crew talk is off; it just does not use it.
- Codex: crew talk says "not available with Codex yet" (its resume is untested).
- Every message is in the episode's log (`GET /api/episodes/<id>/crew`): who, to whom, why, which file, the route.

## The measurement before it can become the default (prepared, not run)

`tools/ci/measure_crew_talk.py` runs the demo episode six times on one engine version: three runs without crew talk,
three with it. Before each run it plants a known weakness so the Critic has something to report: a graphic six frames
after its moment. The plan's other two (a pause 0.8 s too long, a half word at a join) need a demo with recorded speech;
the repository ships none, so they are planted only when such a demo is supplied. It records per run: API-equivalent
cost and tokens per crew member, time from the title to a preview ready for a card, Showrunner turns, cut versions
until the check is clean, weaknesses found and fixed, crew messages, rounds per topic and limits reached.

It needs an engine login and spends subscription usage (about six short episodes), so it runs only with the user's yes,
on a rented machine or in CI with a login secret, never on the user's own computer:

```bash
python3 tools/ci/measure_crew_talk.py --runs 3 --out crew-talk.json
```

**When it becomes the default:** with crew talk, quality is equal or better (as many or more weaknesses fixed, not more
versions) and cost at most 10 % higher or time clearly lower. If the gain comes only from `fix`, only `fix` becomes the
default. If cost rises clearly and quality stays the same, it stays off. The result table goes here, with the real
numbers, also if they speak against crew talk.

| | without crew talk | with crew talk |
|---|---|---|
| results | not measured yet | not measured yet |
