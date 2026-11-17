# Engines: Claude Code and Codex, never held back

Crewcut is a conductor, not a wrapper. Whatever Claude Code can do, it can do in Crewcut, and a new Claude Code release
is live in Crewcut at the next start. Crewcut decides only three things: who works on what, where a person says yes,
and what costs money.

Two engines, both on **your own subscription**, behind one interface (`crewcut/engines/`):

| Engine | Status | Login | Where the login lives |
|---|---|---|---|
| **Claude Code** (default) | primary | "Connect Claude": Crewcut runs `claude setup-token` in the container with `BROWSER=true`, opens the sign-in link it prints (only links to claude.ai, claude.com, console.anthropic.com or platform.claude.com), and writes the code Claude's page shows to the CLI, which prints a one-year token. On a server without a screen `./start.sh` also takes a token by hand (hidden input, `.env`) | as `CLAUDE_CODE_OAUTH_TOKEN` in the environment: from the system keychain (desktop app), from `.env`, or from `/opt/engine/secrets/claude-oauth-token` in the engine volume (web UI, mode 0600, never the studio folder); the environment wins |
| **Codex** | beta, not yet run on a real episode | say "use Codex": the sign-in link and a one-time code appear in the chat | `CODEX_HOME` in the engine volume, never the studio folder |

You pick the engine once by saying it ("use Codex", "back to Claude"). `crewcut engine status` shows both.

## Always the newest version, with a way back

```
start
 ├─ newest version on the channel?      one npm query, skipped when offline
 │     yes → install it NEXT TO the current one (/opt/engine/versions/<engine>/<version>/)
 ├─ smoke test the new one              it starts, knows the flags Crewcut needs, and with a login answers one tiny
 │                                      stream-json call with a session id
 │     pass → switch the link /opt/engine/current/<engine>, remember it as last good
 │     fail → mark it broken, keep the current one
 └─ run
```

- **When:** at every container start (the first start waits, later ones update in the background) and once a day while
  no job runs (`engine.update_every_hours`). Never in the middle of an episode: Claude Code's own self-update stays off
  (`DISABLE_AUTOUPDATER=1`), Crewcut swaps versions between jobs.
- **Channel:** `engine.claude.channel` is `latest` (default), `stable`, or a fixed version. Say "stay on stable" and the
  Showrunner writes it.
- **Way back:** if two jobs in a row fail with an engine error (an unknown flag, a crash, a missing module; not a content
  or login problem) right after a switch, Crewcut goes back to the previous good version and says so in the chat:
  "Claude Code 2.1.330 failed twice. Back on 2.1.325. I will try a newer one again tomorrow." A broken version is never
  used again; the next newer one is tried.
- `crewcut engine update [claude|codex] [--channel …]`, `crewcut engine rollback`, `crewcut doctor` (shows the active
  version, the channel and the last good one).

## Every flag goes through

The command line has three layers:

1. **What Crewcut needs to read the run** (fixed): `-p`, `--output-format stream-json`, `--verbose`, `--resume`.
2. **What Crewcut sets for the job:** `--plugin-dir` (the Crewcut plugin), `--agent crewcut:<crew member>`, `--model`,
   `--effort`, `--add-dir`, `--name "Editor · 003 · edit"`, `--append-system-prompt` (only what changes per job: the
   house rules and the episode state).
3. **What you add:** `extra_args` in `config/crewcut.toml` (every run) and in a crew member's file (`team/<id>.md`), passed
   through unchanged, including flags Crewcut does not know yet: `--mcp-config`, `--settings`, `--fallback-model`,
   `--permission-mode`, `--max-budget-usd`, `--json-schema`, `--include-hook-events` and whatever comes next. A flag from
   layer 3 that layer 2 also sets wins; layer 1 cannot be overridden (Crewcut says so in the job log).

```toml
[engine.claude]
channel = "latest"
crew = "runs"            # or "subagents"
plan_model = ""          # empty = the model Claude Code picks for your plan; any name Claude Code knows works
work_model = ""
extra_args = ["--fallback-model", "sonnet"]
env = {}
```

```yaml
# team/critic.md (front matter)
model: plan          # a role, not a model name
effort: max          # passed as --effort; empty = the engine's default
extra_args: []       # per crew member
```

You do not have to edit these files: say it ("use the highest effort for the Critic") and the Showrunner writes the
line.

**Nothing is swallowed.** Events Crewcut does not know yet are kept in the job log with their type. Subagent text,
hook events and every tool (MCP tools appear as "server: tool") get a readable line.

## The real things, not copies

- **Crewcut is a Claude Code plugin.** At start it builds `<studio>/.crewcut/plugin/crewcut/` from `skills/` and
  `team/`: the skills, the crew as agents (`crewcut:showrunner`, `crewcut:editor`, …), and a guard hook. Every run loads it
  with `--plugin-dir`. You can load the same folder in your own Claude Code outside the container
  (`claude --plugin-dir …`). `crewcut plugin --out <dir>` writes it anywhere; CI checks it with `claude plugin validate`.
- **The crew are real agents.** A job for the Editor starts with `--agent crewcut:editor`; the crew member's "how I
  work" is the agent's own system prompt, not appended text.
- **Two crew modes**, one setting (`engine.claude.crew`):

  | | `runs` (default) | `subagents` |
  |---|---|---|
  | Who hands out work | the conductor: every crew member is its own run and session | the Showrunner runs and hands the work to the crew member as its subagent (`--forward-subagent-text` makes the subagent's work visible) |
  | Gains | one run, one row, one session to resume | everything Claude Code improves in subagents arrives at once; less own code |
  | Rights | the identity of the run (`CREWCUT_IDENTITY`) | the guard hook checks the subagent (`agent_type`); Crewcut's code checks cards and caps |
  | Status | default | built; to be measured against `runs` on the demo episode before it can become the default |

- **Your Claude Code settings keep working.** `<studio>/.claude/` is Claude Code's own folder inside the container:
  `settings.json`, `CLAUDE.md`, `skills/`, `agents/`, `commands/`, MCP servers. Put things there (or say what you want and
  the Showrunner does it). To bring your host's `~/.claude`, uncomment the read-only line in `compose.yaml`; it is copied
  in once, never the login file. `doctor` lists hooks of yours that call programs the container does not have.
- **Order when two set the same thing:** Crewcut's defaults, then the Crewcut plugin, then your `<studio>/.claude/`,
  then the crew member, then the job. You win against Crewcut.

## What stays hard, in code

Three rules are not settings and cannot be switched off by a flag, a hook or a plugin: publishing needs your accepted
publish card for the exact file (checksum); money needs a spend card or an approved budget and stays under the monthly
cap; secrets never go into arguments, files or logs. The guard hook adds a check per crew member on top; it is not the
only lock, because a hook is a setting that a user or another plugin can change.

## Codex

The same principles: newest version with smoke test and way back (`@openai/codex`), `extra_args` and `-c key=value`
pairs passed through (`engine.codex.config`), `effort` as `model_reasoning_effort`, unknown events kept. Codex has no
agents flag in `exec`, so the crew member's "how I work" goes first in the prompt. Resuming an exec session is untested.
Codex stays beta until a whole episode has run with it.

## Every night: the newest engines

`.github/workflows/engine-nightly.yml` installs the newest Claude Code and Codex through Crewcut's own version manager,
validates the Crewcut plugin with `claude plugin validate`, and compares the engines' flags with the snapshots in
`engine/help/`. New or removed flags and failures become one issue per version. The login smoke test and a tiny real run
switch on when the repository has the secret `CREWCUT_CI_CLAUDE_TOKEN` (an API key with a small monthly limit is
recommended); until then only the parts without a login run.

## Known problems

- Some containers reject a token with "401 Invalid bearer token". Make a new one with `claude setup-token`.
- An old `.credentials.json` can hide the token; the host copy never brings it in, and `doctor` warns when it sees one.
- Codex device-code login is a beta feature of Codex and must be switched on in your ChatGPT security settings.
- Whether a subscription may drive an open-source app like this is governed by each provider's terms. Crewcut starts
  your own CLI with your own login, the same way you would in a terminal.
