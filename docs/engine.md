# Engines: Claude Code and Codex

Every crew member is a run of a coding agent CLI inside the container, on **your own subscription**. Crewcut supports
exactly two engines behind one interface (`crewcut/engines/`):

| Engine | Status | Login | Where the login lives |
|---|---|---|---|
| **Claude Code** (default) | primary | `claude setup-token` once on any computer with a browser; the token goes into `.env` as `CLAUDE_CODE_OAUTH_TOKEN` (`./start.sh` asks once, hidden) | the container's environment only |
| **Codex** | beta, not yet run on a real episode | say "use Codex" in the chat: the sign-in link and a one-time code appear in the chat; you confirm on OpenAI's page | `CODEX_HOME` in the engine volume (`/opt/engine/codex-home`), never the studio folder |

You pick the engine once by saying it (during onboarding or any time later: "use Codex", "back to Claude"). The choice
is stored in the studio and applies to new work. `crewcut engine status` shows both.

## The interface

```python
from crewcut import engines
eng = engines.current()                    # ClaudeCode() or Codex()
task = engines.Task(prompt=..., system=..., cwd=episode_dir, model=..., resume=session_id_or_None)
result = eng.run(task, on_event=callback, stop=threading_event)
# events: step (plan item), tool (one readable line per tool call), text, usage, session, error, result
# result: ok, text, usage, session (for resume), API-equivalent cost where reported, error, timed_out
```

- **Start** a task with the prompt, the identity's house rules and the skill of its step, in the episode folder.
- **Stream** events into the Crew column ("who is working on what") and a readable, secret-free log per job.
- **Stop** a task (the job queue kills the whole process group).
- **Resume** a session: when you answer a card, the crew member who asked continues its own session with your answer,
  so it keeps its context.

| | Claude Code | Codex |
|---|---|---|
| Command | `claude -p … --output-format stream-json --verbose --append-system-prompt … --dangerously-skip-permissions [--resume ID] [--model M]` | `codex exec --json --skip-git-repo-check --sandbox danger-full-access -c approval_policy="never" [-m M] [resume ID] "<rules + task>"` |
| Events | `system/init` (session), `assistant` (text, tool_use), `result` (cost, turns, usage) | `thread.started` (session), `item.*` (messages, commands, file changes, plans), `turn.completed` (token usage) |
| Cost shown | API equivalent in USD (not money you pay on a subscription) | token usage |
| Models | `engine.claude.plan_model` = opus, `work_model` = sonnet | empty = the model Codex picks for your plan |

The container is the sandbox: agents run as a normal user and only see the app and the studio folder, which is why the
engines' own permission prompts are off inside it.

## Doctor and the first start

At every start the entrypoint installs the chosen engine if it is missing (from its official npm package into the
engine volume; Claude Code is never shipped inside the image because its licence is not open) and runs
`crewcut doctor --probe`: one tiny real call proves that the login works. The result is in the Crew column and in
`studio/.crewcut/logs/doctor.log`.

## Known problems

- Claude Code: some containers reject a token with "401 Invalid bearer token". Make a new one with `claude setup-token`.
- Claude Code: an old `~/.claude/.credentials.json` can hide the token. Do not mount an old `~/.claude`; doctor warns.
- Codex: device-code login is a beta feature of Codex and must be switched on in your ChatGPT security settings.
  Resuming an exec session and attaching images (thumbnail way A) are untested inside the container.
- An `ANTHROPIC_API_KEY` works for Claude Code too, paid per token; Crewcut is built for the subscription.
- Whether a subscription may drive an open-source app like this is governed by each provider's terms. Crewcut starts
  your own CLI with your own login, the same way you would in a terminal.
