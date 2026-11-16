import pytest

from crewcut import crewtalk, db, episodes, plugin
from crewcut.conductor import flow, queue


@pytest.fixture
def ep(crew, monkeypatch):
    added = []

    def fake_add(episode, identity, step, task, kind="agent", heavy=False, parent=None, data=None):
        jid = db.insert("jobs", episode=episode, step=step, identity=identity, kind=kind, task=task, heavy=int(heavy),
                        status="queued", created=db.now(), data=data or {})
        added.append((identity, task, data))
        return jid

    monkeypatch.setattr(queue, "add", fake_add)
    e = episodes.create("Crew talk test")["id"]
    return e, added


def test_off_by_default(ep):
    e, _ = ep
    assert crewtalk.settings()["enabled"] is False
    with pytest.raises(crewtalk.Refused, match="off"):
        crewtalk.send(e, "critic", "editor", "fix", "review/cut-check-v001.json", "3 findings")


def test_fix_resumes_the_builder_and_a_reply_closes_the_exchange(ep):
    e, added = ep
    crewtalk.set_enabled(True)
    db.insert("jobs", episode=e, step="edit", identity="editor", kind="agent", task="cut", status="done",
              created=db.now(), data={"engine": "claude", "session": "sess-editor"})
    m = crewtalk.send(e, "critic", "editor", "fix", "review/cut-check-v001.json",
                      "- pause at 2:31 too long\n- graphic 4 late\n- half word at 1:02")
    assert m["route"] == "resume" and m["status"] == "delivered"
    who, task, data = added[-1]
    assert who == "editor" and data["resume"] == {"engine": "claude", "session": "sess-editor"}
    assert data["reason"] == "Fixing 3 findings from the Critic" and "not an approval" in task
    assert db.get("jobs", m["job"])["doing"] == "Fixing 3 findings from the Critic"
    r = crewtalk.send(e, "editor", "critic", "fix", "review/cut-check-v001.json", "Fixed in cut v2.",
                      expects="none", reply_to=m["id"])
    assert r["topic"] == m["topic"]
    line = [x for x in flow.messages(e) if x.get("exchange")][-1]
    assert line["text"].startswith("Critic and Editor") and len(line["exchange"]["messages"]) == 2


def test_limits_and_rules(ep):
    e, _ = ep
    crewtalk.set_enabled(True)
    with pytest.raises(crewtalk.Refused, match="names the file"):
        crewtalk.send(e, "writer", "scout", "question", "", "what?")
    with pytest.raises(crewtalk.Refused, match="no other crew member"):
        crewtalk.send(e, "writer", "writer", "question", "brief/TITLE-v001.md", "?")
    for i in range(4):
        crewtalk.send(e, "writer", "scout", "question", "brief/TITLE-v001.md", f"q{i}")
    with pytest.raises(crewtalk.Refused, match="rounds"):
        crewtalk.send(e, "writer", "scout", "question", "brief/TITLE-v002.md", "q5")  # same topic, other version


def test_notice_waits_for_the_next_start(ep):
    e, added = ep
    crewtalk.set_enabled(True)
    n = crewtalk.send(e, "scout", "designer", "notice", "brief/TITLE-v003.md", "Title changed.", expects="none")
    assert n["route"] == "collected" and not added
    assert [x["text"] for x in crewtalk.collected_for(e, "designer")] == ["Title changed."]
    assert crewtalk.collected_for(e, "designer") == []


def test_episode_budget(ep, monkeypatch):
    e, _ = ep
    crewtalk.set_enabled(True)
    from crewcut import config
    real = config.get
    monkeypatch.setattr(config, "get", lambda n, d, default=None: {"enabled": True, "max_rounds": 9,
                                                                   "max_fix_rounds": 9, "max_per_episode": 2}
                        if (n, d) == ("crewcut", "crew.talk") else real(n, d, default))
    crewtalk.send(e, "writer", "scout", "question", "a.md", "1")
    crewtalk.send(e, "writer", "designer", "question", "b.md", "2")
    with pytest.raises(crewtalk.Refused, match="budget"):
        crewtalk.send(e, "writer", "editor", "question", "c.md", "3")


def test_hook_logs_and_limits_claude_sendmessage(ep, monkeypatch):
    e, _ = ep
    payload = {"tool_name": "SendMessage", "tool_input": {"to": "editor-" + e, "message": "see review/x-v1.json"},
               "agent_type": "crewcut:critic"}
    monkeypatch.setenv("CREWCUT_EPISODE", e)
    assert plugin.guard_decision(payload, "critic") == (True, "")      # off: Claude Code's own messaging untouched
    assert crewtalk.messages(e) == []
    crewtalk.set_enabled(True)
    assert plugin.guard_decision(payload, "critic")[0]
    assert crewtalk.messages(e)[0]["route"] == "live"
    bad = {"tool_name": "SendMessage", "tool_input": {"to": "editor", "message": "hi"}, "agent_type": "crewcut:critic"}
    assert not plugin.guard_decision(bad, "critic")[0]


def test_runs_get_session_names_and_inbound_messages_when_on(crew, monkeypatch, studio):
    from crewcut import engines
    monkeypatch.setattr(queue, "plugin_dir", lambda: "/p")
    e = episodes.create("x")["id"]
    job = {"id": 3, "episode": e, "step": "edit", "identity": "editor", "task": "cut", "data": {}}
    t = queue.build_task(job, engines.get("claude"), {})
    assert t.name == f"editor-{e}" and "settings" not in t.engine_options
    crewtalk.set_enabled(True)
    t = queue.build_task(job, engines.get("claude"), {})
    cmd = engines.get("claude").command(t)
    assert '{"crossSessionInbound": "accept"}' in cmd and "Crew talk is on" in t.system
