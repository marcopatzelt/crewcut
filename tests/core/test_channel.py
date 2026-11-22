import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from crewcut import channel, cli, db, engines, episodes, events, paths
from crewcut.conductor import flow, queue
from crewcut.server.app import create_app


def client():
    return TestClient(create_app(start_worker=False), base_url="http://localhost:4747")


def test_question_history_isolation_and_events(studio, crew):
    api = client()
    message = api.post("/api/channel/messages", json={"text": "What is ready?"}).json()
    assert message["scope"] == "channel"
    assert message["episode"] == "_channel"
    assert queue.get(message["job"])["episode"] is None
    assert queue.get(message["job"])["data"]["conversation_scope"] == "channel"
    assert episodes.list_ids() == []
    assert not (studio / "episodes" / "_channel").exists()
    flow.post(flow.ONBOARDING, "Brand only")
    project = episodes.create("Synthetic episode")
    flow.post(project["id"], "Episode only")
    db._ready.discard(str(paths.db_path()))
    assert client().get("/api/channel/messages").json() == [message]
    assert [item["text"] for item in flow.messages(project["id"])] == ["Episode only"]
    assert [item["text"] for item in flow.messages(flow.ONBOARDING)] == ["Brand only"]
    event = next(item for item in events.since(0) if item["kind"] == "message")
    assert event["episode"] == "_channel"
    assert event["data"]["scope"] == "channel"
    assert api.get(f"/api/channel/messages?after={message['id']}").json() == []
    assert api.post("/api/channel/messages", json={"text": " "}).status_code == 400
    assert api.get("/api/channel/messages?limit=501").status_code == 422


def test_migration_preserves_history(tmp_path):
    database = tmp_path / "old.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(db.SCHEMA)
        connection.execute("INSERT INTO messages (at,episode,author,text,card) VALUES ('now','one','user','old',42)")
        connection.execute("INSERT INTO messages (at,episode,author,text) VALUES ('now','_onboarding','brand','style')")
    with db.conn(database) as connection:
        rows = db.rows(connection.execute("SELECT * FROM messages ORDER BY id"))
    assert rows[0]["scope"] == "episode"
    assert rows[0]["card"] == 42
    assert rows[1]["scope"] == "onboarding"


def test_duplicate_active_and_retry(crew):
    first = channel.user_message("What is ready?")
    with ThreadPoolExecutor(max_workers=4) as pool:
        replies = list(pool.map(channel.user_message, ["What is ready?"] * 4))
    assert all(reply["id"] == first["id"] for reply in replies)
    db.update("jobs", first["job"], status="failed")
    retry = channel.user_message("What is ready?")
    assert retry["job"] != first["job"]


def test_task_root_and_session_scope(studio, crew, monkeypatch):
    monkeypatch.setattr(queue, "plugin_dir", lambda: None)
    first = channel.user_message("Channel question")
    job = queue.get(first["job"])
    engine = engines.get("codex")
    db.update("jobs", job["id"], status="done", data={"conversation_scope": "channel",
                                                     "engine": "codex", "session": "channel-session"})
    other = queue.add(None, "showrunner", None, "Other", data={"engine": "codex", "session": "wrong"})
    db.update("jobs", other, status="done")
    next_job = queue.get(channel.user_message("Another question")["job"])
    task = queue.build_task(next_job, engine, next_job["data"])
    assert task.cwd == studio
    assert task.env["CREWCUT_EPISODE"] == ""
    assert task.env["CREWCUT_CONVERSATION_SCOPE"] == "channel"
    assert task.resume == "channel-session"
    assert channel.resume("showrunner", "claude") is None
    assert channel.resume("editor", "codex") is None
    assert not (studio / "episodes" / "_channel").exists()
    assert "questions alone never start production" in task.system


def test_cli_channel_and_automatic_route(crew, monkeypatch, capsys):
    job = channel.user_message("Question")["job"]
    monkeypatch.setenv("CREWCUT_JOB", str(job))
    monkeypatch.setenv("CREWCUT_CONVERSATION_SCOPE", "channel")
    assert cli.main(["say", "Answer"]) == 0
    assert cli.main(["say", "--channel", "Another answer"]) == 0
    assert cli.main(["chat", "--channel"]) == 0
    assert "Another answer" in capsys.readouterr().out
    assert cli.main(["say", "--channel", "--episode", "other", "Wrong"]) == 2
    flow.after_job(queue.get(job), engines.RunResult(ok=True, exit_code=0, text="Duplicate"))
    assert "Duplicate" not in [item["text"] for item in flow.messages("_channel")]


def test_fallback_failure_and_restart(crew):
    first = queue.get(channel.user_message("Question")["job"])
    flow.after_job(first, engines.RunResult(ok=True, exit_code=0, text="Fallback answer"))
    assert flow.messages("_channel")[-1]["text"] == "Fallback answer"
    flow.after_job(first, engines.RunResult(ok=False, exit_code=1, error="Offline"))
    assert "Offline" in flow.messages("_channel")[-1]["text"]
    db.update("jobs", first["id"], status="running")
    queue.Worker().recover()
    assert "restart" in flow.messages("_channel")[-1]["text"]
    assert queue.get(first["id"])["status"] == "failed"


@pytest.mark.parametrize("explicit", [True, False])
def test_cli_channel_preserves_facts(crew, monkeypatch, explicit):
    job = channel.user_message("Question")["job"]
    monkeypatch.setenv("CREWCUT_JOB", str(job))
    monkeypatch.setenv("CREWCUT_CONVERSATION_SCOPE", "channel")
    command = ["say", "--channel"] if explicit else ["say"]
    command += ["--fact", "episode=001-first", "--fact", " episode = 002-second ",
                "--fact", "note=one=two", "--fact", "ignored", "These episodes are ready."]
    assert cli.main(command) == 0
    expected = [{"label": "episode", "value": "001-first"}, {"label": "episode", "value": "002-second"},
                {"label": "note", "value": "one=two"}]
    assert flow.messages("_channel")[-1]["facts"] == expected
    assert client().get("/api/channel/messages").json()[-1]["facts"] == expected
    assert events.since(0)[-1]["data"]["facts"] == expected
    assert '--fact "episode=ID"' in queue.get(job)["task"]


def test_cli_channel_child_command_syntax(crew, monkeypatch, capsys):
    import shlex
    parent = channel.user_message("Explicit work")["job"]
    episode = episodes.create("Synthetic target")["id"]
    monkeypatch.setenv("CREWCUT_JOB", str(parent))
    monkeypatch.setenv("CREWCUT_CONVERSATION_SCOPE", "channel")
    command = f'job add --episode {episode} --identity writer --step script "Write the script"'
    assert cli.main(shlex.split(command)) == 0
    output = capsys.readouterr().out.strip()
    assert output.startswith("job #") and output.endswith(" queued for writer")
    child = queue.get(int(output.split()[1].removeprefix("#")))
    assert child["episode"] == episode
    assert child["parent"] == parent
    assert child["identity"] == "writer"
    assert child["step"] == "script"
    assert child["task"] == "Write the script"
    assert child["status"] == "queued"


def test_child_dispatch_and_results(crew):
    parent = channel.user_message("Work on the named episode")["job"]
    episode = episodes.create("Synthetic target")["id"]
    child = queue.add(episode, "writer", "script", "Write", parent=parent)
    assert queue.add(episode, "writer", "script", "Write again", parent=parent) == child
    with pytest.raises(ValueError, match="explicit episode"):
        queue.add(None, "writer", "script", "Write", parent=parent)
    result = engines.RunResult(ok=True, exit_code=0, text="Script ready")
    flow.post(episode, "Script ready", author="writer", job=child)
    flow.after_job(queue.get(child), result)
    flow.after_job(queue.get(child), result)
    replies = [item for item in flow.messages("_channel") if item["job"] == child]
    assert len(replies) == 1
    assert episode in replies[0]["text"]
    assert len(flow.messages(episode)) == 1
    db.update("jobs", child, status="done")
    episodes.set_step(episode, "script", "waiting")
    with pytest.raises(ValueError, match="waiting for approval"):
        queue.add(episode, "writer", "script", "Retry", parent=parent)


def test_a_new_episode_from_the_channel_gets_its_first_job(crew):
    # `crewcut episode new` marks the idea step working before any job exists; the channel may still start it once
    parent = channel.user_message("New episode, start with the idea")["job"]
    episode = episodes.create("Synthetic new episode")["id"]
    assert episodes.read(episode)["steps"]["idea"]["status"] == "working"
    child = queue.add(episode, "scout", "idea", "Find the idea", parent=parent)
    assert queue.get(child)["status"] == "queued"
    assert queue.add(episode, "scout", "idea", "Again", parent=parent) == child   # the running one, never a second


def test_context_is_bounded_without_file_contents(crew):
    project = episodes.create("Synthetic target")
    project["history"] = {"distribution": "published"}
    episodes.write(project["id"], project)
    script = paths.episode_dir(project["id"]) / "brief" / "SCRIPT.md"
    script.write_text("Do not include this script")
    summary = client().get("/api/channel/context").json()
    assert summary["episodes"][0]["distribution"]["status"] == "published"
    assert "Do not include" not in str(summary)
    assert "costs" in summary and "approvals" in summary and "jobs" in summary


def test_existing_episode_work_reports_to_channel(crew):
    episode = episodes.create("Existing work")["id"]
    child = queue.add(episode, "editor", "edit", "Existing work")
    parent = channel.user_message("Check this work")["job"]
    assert queue.add(episode, "editor", "edit", "Same step", parent=parent) == child
    flow.after_job(queue.get(child), engines.RunResult(ok=True, exit_code=0, text="Finished"))
    assert flow.messages("_channel")[-1]["facts"] == [{"label": "episode", "value": episode}]
    assert flow.messages(episode)[-1]["text"] == "Finished"


def test_crash_redacts_messages_activity_and_logs(crew, monkeypatch):
    secret = "synthetic-secret-for-test-only"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    job = queue.get(channel.user_message("Question")["job"])

    def crash(job):
        raise RuntimeError(f"Connection failed: {secret}")

    monkeypatch.setattr(queue, "_run_agent", crash)
    queue._start(job)
    assert queue.get(job["id"])["status"] == "failed"
    assert secret not in str(flow.messages("_channel"))
    assert secret not in str(events.since(0))
    assert secret not in (paths.logs_dir() / f"job-{job['id']}.log").read_text()
    assert "[removed]" in flow.messages("_channel")[-1]["text"]


def test_channel_jobs_run_one_at_a_time(crew, monkeypatch):
    first = channel.user_message("First")["job"]
    second = channel.user_message("Second")["job"]
    worker = queue.Worker()
    monkeypatch.setattr(worker, "maybe_update_engine", lambda: None)

    class IdleThread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            pass

        def is_alive(self):
            return True

    monkeypatch.setattr(queue.threading, "Thread", IdleThread)
    worker.tick()
    assert queue.get(first)["status"] == "running"
    assert queue.get(second)["status"] == "queued"
    worker.tick()
    assert queue.get(second)["status"] == "queued"


def test_channel_cli_requires_child_target(crew, monkeypatch, capsys):
    parent = channel.user_message("Question")["job"]
    monkeypatch.setenv("CREWCUT_JOB", str(parent))
    monkeypatch.setenv("CREWCUT_CONVERSATION_SCOPE", "channel")
    monkeypatch.delenv("CREWCUT_EPISODE", raising=False)
    assert cli.main(["job", "add", "--identity", "writer", "--step", "script", "Work"]) == 3
    assert "explicit episode" in capsys.readouterr().err


def test_recent_channel_history_is_not_first_page(crew):
    with db.conn() as connection:
        connection.executemany(
            "INSERT INTO messages (at,episode,scope,author,text) VALUES (?, '', 'channel', 'user', ?)",
            [(db.now(), str(number)) for number in range(505)])
    assert [message["text"] for message in channel.recent(2)] == ["503", "504"]


def test_channel_job_completion_with_fake_engine(crew, monkeypatch):
    from crewcut.engines import versions
    job = queue.get(channel.user_message("Read-only question")["job"])
    engine = engines.get("codex")
    monkeypatch.setattr(engines, "current", lambda: engine)
    monkeypatch.setattr(versions, "note_job", lambda *args: None)

    def run(task, **kwargs):
        assert task.env["CREWCUT_CONVERSATION_SCOPE"] == "channel"
        return engines.RunResult(ok=True, exit_code=0, text="Nothing is running.", session="synthetic-session")

    monkeypatch.setattr(engine, "run", run)
    queue._run_agent(job)
    assert queue.get(job["id"])["status"] == "done"
    assert channel.resume("showrunner", "codex") == "synthetic-session"
    assert flow.messages("_channel")[-1]["text"] == "Nothing is running."
    assert episodes.list_ids() == []


@pytest.mark.parametrize("status,ok,text", [("failed", False, "stopped"), ("waiting", True, "waiting for approval")])
def test_child_failure_and_waiting_reports(crew, status, ok, text):
    parent = channel.user_message("Explicit work")["job"]
    episode = episodes.create("Synthetic work")["id"]
    child = queue.add(episode, "writer", "script", "Write", parent=parent)
    db.update("jobs", child, status=status)
    flow.after_job(queue.get(child), engines.RunResult(ok=ok, exit_code=0 if ok else 1, error="Synthetic failure"))
    assert text in flow.messages("_channel")[-1]["text"]
    assert episode in flow.messages("_channel")[-1]["text"]
