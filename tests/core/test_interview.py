"""The interview before the first script draft (crewcut/interview.py): asked once, waited for, saved verbatim."""

import pytest

from crewcut import db, episodes, interview, paths, voice
from crewcut.conductor import flow, queue

QUESTIONS = """Ein paar Fragen, damit das Skript nach dir klingt.
1. Wie hat das für dich angefangen?
2. Was hat dich am Anfang skeptisch gemacht?
3. Wann war der Moment, in dem es klick gemacht hat?
4. Was ist schiefgegangen, mit einem konkreten Beispiel?
5. Wie arbeitest du heute damit?
6. Was ändert das für dich?
"""

ANSWER = ("Ich habe früher nie Videos gemacht, ähm, nur Content konsumiert. Mit älteren Modellen ging das gar nicht, "
          "total viele Schnittfehler. Der Klick-Moment waren die gemieteten GPUs, weil Claude dann mit sich selbst in "
          "eine Feedback-Schleife kam. (Nicht erwähnen, dass ich schon immer Content machen wollte.) Heute baue ich "
          "Schritt für Schritt: erst Schnitte, dann Einblendungen, dann 3D, dann Motion Graphics.")


@pytest.fixture
def jobs(monkeypatch):
    added = []

    def add(episode, identity, step, task, kind="agent", heavy=False, parent=None, data=None):
        added.append({"episode": episode, "identity": identity, "step": step, "task": task, "kind": kind, "data": data})
        return len(added)

    monkeypatch.setattr(queue, "add", add)
    monkeypatch.setattr(queue, "cancel", lambda jid: None)
    return added


def _at_script(title="Erst Coding, jetzt Videoschnitt"):
    eid = episodes.create(title)["id"]
    for s in ("idea", "title"):
        episodes.set_step(eid, s, "done")
    return eid


def test_title_yes_starts_the_interview_not_the_draft(crew, studio, jobs):
    eid = episodes.create("Example")["id"]
    episodes.set_step(eid, "idea", "done")
    flow.on_card_decided({"id": 1, "episode": eid, "kind": "title", "status": "accepted", "title": "Pick a title",
                          "options": ["A title"], "choice": 0})
    assert [j["step"] for j in jobs] == ["script"]
    assert jobs[0]["data"] == {"interview": "ask"} and "Do not write the script yet" in jobs[0]["task"]
    p = episodes.read(eid)
    assert p["interview"]["status"] == "asking" and p["interview"]["job"] == 1
    assert episodes.summary(eid)["interview"]["label"] == interview.ASKING


def test_switched_off_drafts_from_the_brief(crew, studio, jobs):
    (studio / "config").mkdir()
    (studio / "config" / "crewcut.toml").write_text("[steps]\ninterview = false\n")
    eid = _at_script()
    flow.start_step(eid, "script")
    assert "interview" not in episodes.read(eid) and "Do not write the script yet" not in jobs[0]["task"]


def test_no_interview_when_a_script_exists_or_it_was_done(crew, studio, jobs):
    eid = _at_script()
    (paths.episode_dir(eid) / "brief" / "SCRIPT-v004.md").write_text("Text\n")
    assert not interview.needed(eid)
    other = _at_script("Other")
    p = episodes.read(other)
    p["interview"] = {"status": "done", "note": "done by hand in the chat"}
    episodes.write(other, p)
    assert not interview.needed(other)
    short = episodes.create("Short", kind="short", mode="original")["id"]
    assert not interview.needed(short)


def test_ask_checks_the_questions_and_waits(crew, studio, jobs):
    eid = _at_script()
    interview.start(eid)
    with pytest.raises(ValueError, match="numbered questions"):
        interview.ask(eid, "1. Only one question?")
    with pytest.raises(ValueError, match="longer than"):
        interview.ask(eid, QUESTIONS.replace("Wie arbeitest du heute damit?", " ".join(["Wort"] * 31) + "?"))
    mid = interview.ask(eid, QUESTIONS)
    msg = flow.message(mid)
    assert msg["author"] == "writer" and "6. Was ändert das für dich?" in msg["text"]
    assert "skip interview" in msg["text"]  # the neutral pack speaks English: how to answer and how to skip
    p = episodes.read(eid)
    assert p["steps"]["script"]["status"] == "waiting" and p["next_action"] == interview.WAITING
    s = episodes.summary(eid)["interview"]
    assert s == {"status": "waiting", "label": interview.WAITING, "answers": 0, "questions": 6, "file": None}
    with pytest.raises(ValueError, match="waits for the answers"):
        interview.ask(eid, QUESTIONS)


def test_one_message_is_complete_and_saved_verbatim(crew, studio, jobs):
    eid = _at_script()
    interview.start(eid)
    interview.ask(eid, QUESTIONS)
    flow.user_message(eid, ANSWER)
    p = episodes.read(eid)
    assert p["interview"]["status"] == "done" and p["interview"]["file"] == "brief/INTERVIEW-v001.md"
    text = (paths.episode_dir(eid) / "brief" / "INTERVIEW-v001.md").read_text()
    assert "Ich habe früher nie Videos gemacht, nur Content konsumiert." in text      # filler sound out, words kept
    assert "3. Wann war der Moment, in dem es klick gemacht hat?" in text
    rules = text.split("## Do not mention (hard rules)")[1]
    assert "Nicht erwähnen, dass ich schon immer Content machen wollte." in rules
    script = jobs[-1]
    assert script["step"] == "script" and "brief/INTERVIEW-v001.md" in script["task"]
    assert "[[interview:" in script["task"] and "hard rule" in script["task"]
    # the answers are a voice sample for the Humanizer, next to the video samples
    assert any("interviews" in str(s) for s in voice.samples())
    assert p["steps"]["script"]["status"] == "working"


def test_several_messages_until_done(crew, studio, jobs):
    eid = _at_script()
    interview.start(eid)
    interview.ask(eid, QUESTIONS)
    n = len(jobs)
    flow.user_message(eid, "Zu 1 und 2: Ich habe nur Content konsumiert. Mehr kommt gleich.")
    flow.user_message(eid, "Zu 3: Die GPUs waren der Klick-Moment.")
    assert len(jobs) == n and episodes.read(eid)["interview"]["status"] == "waiting"
    flow.user_message(eid, "fertig")
    p = episodes.read(eid)
    assert p["interview"]["status"] == "done" and len(p["interview"]["answers"]) == 2
    text = (paths.episode_dir(eid) / p["interview"]["file"]).read_text()
    assert "Die GPUs waren der Klick-Moment." in text and "### Answer 2" in text and "fertig" not in text.lower()
    assert len(jobs) == n + 1


def test_done_without_answers_keeps_waiting(crew, studio, jobs):
    eid = _at_script()
    interview.start(eid)
    interview.ask(eid, QUESTIONS)
    flow.user_message(eid, "done")
    assert episodes.read(eid)["interview"]["status"] == "waiting"


def test_skip_in_words_or_by_button(crew, studio, jobs):
    eid = _at_script()
    interview.start(eid)
    interview.ask(eid, QUESTIONS)
    flow.user_message(eid, "Interview überspringen bitte")
    p = episodes.read(eid)
    assert p["interview"]["status"] == "skipped" and "INTERVIEW-v001" not in jobs[-1]["task"]
    assert jobs[-1]["step"] == "script" and p["steps"]["script"]["status"] == "working"
    other = _at_script("Other")
    interview.start(other)                      # the Writer still prepares the questions
    interview.skip(other, "the creator pressed Skip interview")
    with pytest.raises(ValueError, match="skipped"):
        interview.ask(other, QUESTIONS)


def test_messages_after_the_interview_go_to_the_showrunner(crew, studio, jobs):
    eid = _at_script()
    interview.start(eid)
    interview.ask(eid, QUESTIONS)
    flow.user_message(eid, ANSWER)
    flow.user_message(eid, "Mach den Anfang kürzer.")
    assert jobs[-1]["identity"] == "showrunner"


def test_writer_that_asked_nothing_falls_back_to_the_draft(crew, studio, jobs):
    eid = _at_script()
    jid = interview.start(eid)
    interview.after_ask_job({"id": jid, "episode": eid}, ok=True)
    assert episodes.read(eid)["interview"]["status"] == "skipped" and jobs[-1]["step"] == "script"


def test_message_after_a_stopped_writer_asks_again(crew, studio, jobs):
    eid = _at_script()
    interview.start(eid)
    flow.user_message(eid, "try again")
    assert [j["data"] for j in jobs] == [{"interview": "ask"}, {"interview": "ask"}]


def test_voice_file_is_an_answer_while_it_waits(crew, studio, jobs, monkeypatch):
    eid = _at_script()
    interview.start(eid)
    interview.ask(eid, QUESTIONS)
    flow.on_upload(eid, [f"inbox/{eid}/antwort.m4a"])
    tool = jobs[-1]
    assert tool["kind"] == "tool" and tool["task"].startswith(f"interview answer {eid} --audio")
    inbox = studio / "inbox" / eid
    inbox.mkdir(parents=True)
    (inbox / "antwort.m4a").write_bytes(b"x")
    monkeypatch.setattr(voice, "transcribe", lambda src: ANSWER)
    assert interview.answer_audio(eid, [f"inbox/{eid}/antwort.m4a"]) == "done"
    with pytest.raises(ValueError, match="inbox"):
        interview.answer_audio(eid, ["brand/x.m4a"])


def test_video_upload_still_goes_to_the_editor(crew, studio, jobs):
    eid = _at_script()
    interview.start(eid)
    interview.ask(eid, QUESTIONS)
    flow.on_upload(eid, [f"inbox/{eid}/take.mp4"])
    assert jobs[-1]["identity"] == "editor"


def test_classify_and_tidy():
    assert interview.classify("Skip interview") == "skip"
    assert interview.classify("Fertig!") == "done"
    assert interview.classify("Teil 1: so fing es an.") == "more"
    assert interview.classify("Als das Studio fertig war, habe ich lange gezögert und dann doch weitergemacht.") == "answer"
    assert interview.tidy("Ich bin  um 8 Uhr, ähm, los.\n\n\nÄh dann kam es.") == "Ich bin um 8 Uhr, los.\n\ndann kam es."
    assert interview.leave_out(["Raus: die Frage nach Videoeditoren. Der Rest bleibt."]) == [
        "Raus: die Frage nach Videoeditoren."]


def test_server_interview_buttons(crew, studio, jobs):
    from fastapi.testclient import TestClient

    from crewcut.server.app import create_app
    eid = _at_script()
    interview.start(eid)
    interview.ask(eid, QUESTIONS)
    client = TestClient(create_app(start_worker=False), base_url="http://localhost:4747")
    assert client.post(f"/api/episodes/{eid}/interview", json={"action": "done"}).status_code == 200
    assert episodes.read(eid)["interview"]["status"] == "waiting"      # done without answers keeps waiting
    r = client.post(f"/api/episodes/{eid}/interview", json={"action": "skip"})
    assert r.status_code == 200 and r.json()["status"] == "skipped"
    assert client.post(f"/api/episodes/{eid}/interview", json={"action": "skip"}).status_code == 400
    assert client.post(f"/api/episodes/{eid}/interview", json={"action": "nope"}).status_code == 400


def test_agents_cannot_answer_or_skip_for_the_creator(crew, studio, jobs, monkeypatch, capsys):
    from crewcut import cli
    eid = _at_script()
    interview.start(eid)
    interview.ask(eid, QUESTIONS)
    jid = db.insert("jobs", episode=eid, step="script", identity="writer", kind="agent", task="x", heavy=0,
                    created=db.now(), status="running")
    monkeypatch.setenv("CREWCUT_JOB", str(jid))
    assert cli.main(["interview", "skip", eid]) == 3
    assert cli.main(["interview", "done", eid]) == 3
    assert episodes.read(eid)["interview"]["status"] == "waiting"
