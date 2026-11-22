"""A Critic's verdict moves the work on by itself: back starts the builder's next round with the report named, a clear
verdict lets the builder propose its card, and after the last round a card asks the user instead (episode 019: two
reviews said "back to the editor" and nothing happened until someone wrote in the chat)."""

import pytest

from crewcut import approvals, db, engines, episodes, paths
from crewcut.conductor import flow, queue, review

V002 = ("# Critic: plan-v002 (Schnitt v012) — ZURÜCK AN DEN EDITOR, nicht zeigen\n\n## Fehler\n1. s29 Wortrest.\n\n"
        "## Urteil\nOhne Fix von 1–3 geht es nicht an Marco.\n")
V003 = ("# Critic: plan-v003 (Schnitt v013): ZURÜCK AN DEN EDITOR mit zwei kleinen Fixes, noch nicht zeigen\n\n"
        "## Urteil\nNach Fix 1 (Split) geht plan-v004 an Marco ohne weitere Runde. Runde 3 von 3 mit dieser Schleife: "
        "v003 ist Runde 2.\n")
CLEAR = "# Critic: plan-v004 (Schnitt v014): an Marco\n\nNo errors.\n\nVerdict: show\nRound: 3 of 3\n"


@pytest.fixture
def episode(studio, crew):
    ep = episodes.create("Erst Coding, jetzt Videoschnitt")["id"]
    (paths.episode_dir(ep) / "review").mkdir(parents=True, exist_ok=True)
    return ep


def editor_run(ep: str) -> int:
    jid = queue.add(ep, "editor", "edit", "Build preview v002.")
    db.update("jobs", jid, status="done", started=db.now(), ended=db.now(),
              data={"engine": "claude", "session": "sess-editor"})
    return jid


def critic_review(ep: str, parent: int | None, name: str, report: str, words: str = "") -> dict:
    """A Critic run that wrote review/<name> and ended; the conductor's after_job runs as in the queue."""
    jid = queue.add(ep, "critic", "edit", f"check {name}", parent=parent)
    db.update("jobs", jid, status="running", started=db.now())
    (paths.episode_dir(ep) / "review" / name).write_text(report)
    text = words or f"Report in `review/{name}`."
    db.update("jobs", jid, status="done", ended=db.now(), result=text)
    flow.after_job(queue.get(jid), engines.RunResult(ok=True, exit_code=0, text=text))
    return queue.get(jid)


def editor_jobs(ep: str, after: int = 0) -> list[dict]:
    with db.conn() as c:
        return db.rows(c.execute("SELECT * FROM jobs WHERE episode = ? AND identity = 'editor' AND id > ? ORDER BY id",
                                 (ep, after)))


def finish(jid: int) -> None:
    db.update("jobs", jid, status="done", ended=db.now())


def test_verdicts_of_real_reports():
    assert review.verdict(V002) == "back"
    assert review.verdict(V003) == "back"          # "geht an Marco" further down is the plan after the fix
    assert review.verdict(CLEAR) == "show"
    assert review.verdict("plan-v002 ist nicht freigegeben. Es geht an den Editor zurück.") == "back"
    assert review.verdict("# Critic: plan-v005: freigegeben, an Marco\n") == "show"
    assert review.verdict("Verdict: back\n") == "back"
    assert review.verdict("Some notes without a decision.") is None


def test_back_starts_the_next_editor_round_with_the_report(episode):
    parent = editor_run(episode)
    job = critic_review(episode, parent, "critic-plan-v002.md", V002)
    assert job["data"]["review"] == {"verdict": "back", "file": "review/critic-plan-v002.md", "round": 1, "limit": 3,
                                     "builder": "editor"}
    [nxt] = editor_jobs(episode, parent)
    assert nxt["status"] == "queued" and nxt["step"] == "edit"
    assert "review/critic-plan-v002.md" in nxt["task"] and "review round 1 of 3" in nxt["task"]
    assert nxt["data"]["resume"] == {"engine": "claude", "session": "sess-editor"}   # keeps the Editor's context
    assert any("sent it back" in m["text"] for m in flow.messages(episode))


def test_rounds_count_up_and_the_last_one_asks_the_user(episode):
    parent = editor_run(episode)
    critic_review(episode, parent, "critic-plan-v002.md", V002)
    [r2] = editor_jobs(episode, parent)
    finish(r2["id"])
    critic_review(episode, r2["id"], "critic-plan-v003.md", V003)
    [r3] = editor_jobs(episode, r2["id"])
    assert "review round 2 of 3" in r3["task"] and "critic-plan-v003.md" in r3["task"]
    finish(r3["id"])
    last = critic_review(episode, r3["id"], "critic-plan-v004.md", V002.replace("v002", "v004"))
    assert last["data"]["review"]["round"] == 3
    assert editor_jobs(episode, r3["id"]) == []                   # no fourth round
    [card] = [c for c in approvals.list_cards(episode=episode) if c["status"] == "open"]
    assert card["kind"] == "other" and card["identity"] == "critic" and card["file"] == "review/critic-plan-v004.md"
    assert card["data"]["critic_limit"]["builder"] == "editor"
    approvals.decide(card["id"], False, reason="Noch eine Runde: Split ruhiger.")
    [again] = editor_jobs(episode, r3["id"])
    assert "Split ruhiger" in again["task"] and "critic-plan-v004.md" in again["task"]
    assert not [j for j in queue.active(episode) if j["identity"] == "critic"]   # the card's no is not a Critic job


def test_limit_card_yes_lets_the_editor_show_the_current_version(episode):
    parent = editor_run(episode)
    for i in range(3):
        critic_review(episode, parent, f"critic-plan-v00{i + 2}.md", V002)
        for j in editor_jobs(episode, parent):
            finish(j["id"])
    [card] = [c for c in approvals.list_cards(episode=episode) if c["status"] == "open"]
    approvals.decide(card["id"], True)
    newest = editor_jobs(episode, parent)[-1]
    assert newest["status"] == "queued" and "Do not change it" in newest["task"] and "kind preview" in newest["task"]


def test_a_clear_verdict_lets_the_builder_propose_its_card(episode):
    parent = editor_run(episode)
    critic_review(episode, parent, "critic-plan-v004.md", CLEAR)
    [nxt] = editor_jobs(episode, parent)
    assert "cleared it for the user" in nxt["task"] and "card of kind preview" in nxt["task"]


def test_round_limit_comes_from_the_critics_round_line(episode):
    parent = editor_run(episode)
    job = critic_review(episode, parent, "critic-plan-v002.md", V002 + "\nRound: 1 of 1\n")
    assert job["data"]["review"]["limit"] == 1
    assert editor_jobs(episode, parent) == []
    assert any(c["data"].get("critic_limit") for c in approvals.list_cards(episode=episode))


def test_nothing_twice_when_someone_already_woke_the_editor(episode):
    parent = editor_run(episode)
    jid = queue.add(episode, "critic", "edit", "check plan-v003", parent=parent)
    db.update("jobs", jid, status="running", started=db.now())
    woken = queue.add(episode, "editor", "edit", "Marco: letzte Runde nach review/critic-plan-v003.md")  # the chat
    (paths.episode_dir(episode) / "review" / "critic-plan-v003.md").write_text(V003)
    db.update("jobs", jid, status="done", ended=db.now(), result="done")
    flow.after_job(queue.get(jid), engines.RunResult(ok=True, exit_code=0, text="done"))
    assert [j["id"] for j in editor_jobs(episode, parent)] == [woken]


def test_a_running_editor_gets_the_verdict_as_a_relay(episode):
    parent = queue.add(episode, "editor", "edit", "Build preview v002.")
    db.update("jobs", parent, status="running", started="2026-11-22T21:00:00Z")
    critic_review(episode, parent, "critic-plan-v002.md", V002)
    assert [j["id"] for j in editor_jobs(episode)] == [parent]          # no second Editor next to the running one
    relay = [m for m in flow.messages(episode) if m.get("for") == ["editor"]]
    assert relay and "critic-plan-v002.md" in relay[-1]["text"]


def test_other_critic_runs_are_left_alone(episode):
    parent = editor_run(episode)
    jid = queue.add(episode, "critic", "edit", "answer", parent=parent, data={"crew_message": 4})
    db.update("jobs", jid, status="done", started=db.now(), ended=db.now())
    (paths.episode_dir(episode) / "review" / "critic-plan-v002.md").write_text(V002)
    flow.after_job(queue.get(jid), engines.RunResult(ok=True, exit_code=0, text="answered"))
    assert editor_jobs(episode, parent) == []
