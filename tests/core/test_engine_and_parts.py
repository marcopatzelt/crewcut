from crewcut import engines, prompter
from crewcut.engines import claude_code, codex
from crewcut.onboarding import fetch
from crewcut.youtube import upload


def test_scrub_removes_secrets(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-abcdefghijklmnopqrstuvwxyz")
    s = engines.scrub("token sk-ant-oat01-abcdefghijklmnopqrstuvwxyz and VAST_API_KEY=abc123 and "
                      'Authorization: Bearer xyz and {"access_token": "tok-123"}')
    assert "abcdefghij" not in s and "abc123" not in s and "xyz" not in s and "tok-123" not in s


def test_claude_command_and_events(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-secretsecretsecret")
    eng = engines.get("claude")
    task = engines.Task(prompt="do it", system="you are the writer", cwd=".", model="sonnet", resume="sess-1")
    cmd = eng.command(task)
    assert "stream-json" in cmd and "--append-system-prompt" in cmd and cmd[cmd.index("--resume") + 1] == "sess-1"
    assert not any("secretsecret" in c for c in cmd)
    state = {"texts": [], "usage": {}, "session": None, "result": None, "cost": 0.0, "turns": 0, "error": ""}
    evs = eng.parse({"type": "system", "subtype": "init", "session_id": "abc"}, state)
    evs += eng.parse({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "Starting."},
        {"type": "tool_use", "name": "Bash", "input": {"command": "ls", "description": "List files"}},
        {"type": "tool_use", "name": "TodoWrite", "input": {"todos": [{"status": "in_progress",
                                                                      "activeForm": "Writing version 2"}]}}]}}, state)
    evs += eng.parse({"type": "result", "subtype": "success", "result": "done", "total_cost_usd": 0.41,
                      "num_turns": 7, "usage": {"input_tokens": 10, "output_tokens": 5}}, state)
    kinds = [(e.kind, e.text) for e in evs]
    assert ("session", "") in kinds and ("tool", "List files") in kinds and ("step", "Writing version 2") in kinds
    assert state["session"] == "abc" and state["result"] == "done" and state["cost"] == 0.41


def test_codex_command_and_events():
    eng = engines.get("codex")
    assert eng.beta and eng.env()["CODEX_HOME"].endswith("codex-home")
    cmd = eng.command(engines.Task(prompt="do it", system="house rules", cwd=".", resume="thr-9"))
    assert cmd[:3] == [cmd[0], "exec", "--json"] and "resume" in cmd and cmd[-1].startswith("house rules")
    assert "--full-auto" not in cmd
    state = {"texts": [], "usage": {}, "session": None, "result": None, "cost": 0.0, "turns": 0, "error": ""}
    evs = eng.parse({"type": "thread.started", "thread_id": "thr-1"}, state)
    evs += eng.parse({"type": "item.completed", "item": {"id": "1", "type": "command_execution",
                                                         "command": "crewcut doing x"}}, state)
    evs += eng.parse({"type": "item.completed", "item": {"id": "2", "type": "agent_message", "text": "Done."}}, state)
    evs += eng.parse({"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 20}}, state)
    evs += eng.parse({"type": "turn.completed", "usage": {"input_tokens": 50, "output_tokens": 5}}, state)
    assert state["session"] == "thr-1" and state["texts"] == ["Done."]
    assert state["usage"] == {"input_tokens": 150, "output_tokens": 25}
    assert any(e.kind == "tool" and e.text.startswith("$ crewcut") for e in evs)
    eng.parse({"type": "turn.failed", "error": {"message": "usage limit reached"}}, state)
    assert state["error"] == "usage limit reached"


def test_engine_choice_is_stored():
    assert engines.current_name() == "claude"
    engines.use("Codex")
    assert engines.current_name() == "codex"
    import pytest
    with pytest.raises(ValueError):
        engines.use("gemini")
    assert claude_code.describe_tool({"name": "Read", "input": {"file_path": "/a/b/c.md"}}) == "Read c.md"
    assert codex.describe_item({"type": "web_search", "query": "q"}) == ("tool", "WebSearch q")


def test_prompter_script_parsing():
    blocks = prompter.parse_script("# Intro\n\nI tested **five models** on a laptop.\n\n- point one\n")
    assert blocks[0]["heading"] and blocks[1]["points"] == ["five models"]
    assert "**" not in blocks[1]["text"]


HTML = """<html lang="de"><head><title>Acme Studio</title><meta name="description" content="We build tools.">
<meta name="theme-color" content="#0F766E"><link rel="icon" href="/favicon.png">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500">
<style>:root{--brand-primary:#E4572E;--ink:#111}body{font-family:"Space Grotesk",sans-serif;color:#111111}
.btn{background:#E4572E}.x{color:rgb(228,87,46)}h1{font-family:'Acme Display',serif}</style></head>
<body><svg class="site-logo"><path d="M0 0h10v10z"/></svg><h1>Tools for makers</h1><img src="/img/logo.png" alt="Acme logo">
<script>var a="#FF0000";</script></body></html>"""


def test_website_facts():
    w = fetch.parse_website("https://acme.example/", HTML, [])
    assert w["title"] == "Acme Studio" and w["language"] == "de"
    assert w["colors"]["accent_candidates"][0]["hex"] == "#E4572E"
    assert w["colors"]["named"]["brand-primary"] == "#E4572E"
    fams = {f["family"]: f["licence"] for f in w["fonts"]}
    assert fams["Space Grotesk"].startswith("free") and fams["Acme Display"].startswith("unknown")
    assert w["logo"]["images"] == ["https://acme.example/img/logo.png"] and w["logo"]["inline_svg"]
    assert "Tools for makers" in w["text_sample"]


def test_youtube_parsing():
    assert fetch.kind_of("https://www.youtube.com/@someone") == "youtube"
    assert fetch.kind_of("https://x.com/someone") == "social"
    assert fetch.youtube_channel_id('"externalId":"UCabcdefghijklmnopqrstuv"') == "UCabcdefghijklmnopqrstuv"
    feed = ("<feed><entry><yt:videoId>abc</yt:videoId><title>First</title><published>2026-11-01</published>"
            '<media:statistics views="42"/></entry></feed>')
    assert fetch.parse_feed(feed) == [{"id": "abc", "title": "First", "published": "2026-11-01", "views": 42,
                                       "thumbnail": "https://i.ytimg.com/vi/abc/hqdefault.jpg"}]


def test_upload_package_rules(crew):
    from crewcut import episodes
    eid = episodes.create("x")["id"]
    errs = upload.validate(eid, {"title": "t" * 101, "description": "<b>", "video": "export/missing.mp4",
                                 "privacy": "secret", "publish_at": "tomorrow"})
    joined = " ".join(errs)
    for word in ("100", "<", "not found", "privacy", "ISO"):
        assert word in joined
    body = upload.body_of({"title": "T", "description": "D", "tags": ["a"], "privacy": "public"},
                          publish_at="2026-11-20T16:00:00Z")
    assert body["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                              "publishAt": "2026-11-20T16:00:00Z"}
