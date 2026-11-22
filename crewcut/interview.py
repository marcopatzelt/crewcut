"""The interview before the first script draft (`[steps] interview` in config/crewcut.toml, on by default).

A script written only from the brief and the research sounds like anyone could have said it. So after the title is
approved and before the first draft, the Writer asks the creator 5 to 8 open questions in the episode chat, about
what no file can know: how it started for them, their doubts, the real turning point, setbacks with details, how they
work, what it changes for them (`crewcut interview ask`). Then the episode waits: "Interview: waiting for your answers".

Every message the creator sends while it waits is an answer, typed or dictated with the chat microphone; a voice file
dropped into the chat is transcribed on this machine. One message counts as complete. A message that says more is
coming ("more coming", "mehr kommt") keeps the interview open until the creator says "done" ("fertig"). "Skip
interview" (the words or the button) skips it.

The conductor (this code, no tokens) writes the answers verbatim, with light cleanup, to `brief/INTERVIEW-vNNN.md`,
lists the creator's "do not mention" wishes as hard rules, keeps the answers as a voice sample for the Humanizer
(`brand/voice/interviews/`), and starts the Writer on the script in the session that asked the questions.
"""

from __future__ import annotations

import re
import shlex

from . import db, episodes, paths

MIN_QUESTIONS, MAX_QUESTIONS, MAX_WORDS = 5, 8, 30
WAITING = "Interview: waiting for your answers"
ASKING = "Interview: the Writer prepares the questions"
AUDIO = (".m4a", ".mp3", ".wav", ".ogg", ".oga", ".opus", ".aac", ".flac", ".weba", ".amr", ".caf")

QUESTION = re.compile(r"^\s*(?:\*\*)?(\d{1,2})[.)](?:\*\*)?\s+(\S.*)$")
SKIP = re.compile(r"\b(skip(?: the)? interview|no interview|interview (?:überspringen|skippen|weglassen|auslassen)|"
                  r"ohne interview|kein interview)\b", re.I)
DONE = re.compile(r"\b(done|finished|that'?s (?:all|it)|i'?m done|fertig|das war'?s|das wars|ende|alles gesagt)\b", re.I)
MORE = re.compile(r"(more (?:is )?coming|more to come|more later|to be continued|\bpart 1\b|"
                  r"\b(?:mehr|rest) (?:kommt|folgt)|kommt noch|gleich mehr|fortsetzung folgt|\bteil 1\b|"
                  r"ich (?:schreib|sprech)e? (?:gleich )?weiter)", re.I)
# A wish to leave something out of the video, in the creator's words. Such sentences become hard rules.
LEAVE_OUT = re.compile(r"(nicht erw[äa]hn|nicht (?:sagen|nennen|zeigen|ansprechen|rein)|\bweglassen|\blass\w* .{0,40}\bweg\b|"
                       r"\bstreich|\braus\b\W*:|kein wort|nicht das thema|bitte nicht|"
                       r"(?:don'?t|do not|never) (?:mention|say|show|name)|leave .{0,30}\bout\b|keep .{0,30}\bout\b|"
                       r"not the topic)", re.I)
# Filler sounds only; never a word ("um" is a German word, so only "umm" counts).
FILLER = re.compile(r"(?<!\w)(?:äh+m*|öh+m*|ehm|hmm+|uh+m*|umm+|erm)(?!\w)[,.]?\s*", re.I)

HOW = {
    "de": "Antworte in deinen eigenen Worten, getippt oder gesprochen (Mikrofon im Chat oder eine Sprachdatei). Eine "
          "Nachricht nehme ich als vollständig. Willst du in mehreren Nachrichten antworten, schreib „mehr kommt“ dazu "
          "und am Ende „fertig“. Oder: „Interview überspringen“.",
    "en": "Answer in your own words, typed or spoken (the chat microphone or a voice file). I take one message as "
          "complete. To answer in several messages, add “more coming” and say “done” at the end. Or say “skip "
          "interview”.",
}
LINES = {
    "de": {"more": "Okay, ich sammle weiter. Sag „fertig“, wenn du durch bist.",
           "empty": "Noch keine Antworten. Antworte auf die Fragen oder sag „Interview überspringen“.",
           "done": "Danke, das Interview ist gespeichert ({file}). Der Writer schreibt das Skript jetzt aus deinen Sätzen.",
           "skipped": "Interview übersprungen. Der Writer schreibt das Skript aus dem Brief.",
           "voice": "Deine Sprachdatei ist da. Ich schreibe sie auf diesem Rechner ab und nehme sie als Antwort.",
           "again": "Der Writer bereitet die Interviewfragen noch einmal vor.",
           "none": "Der Writer hat keine Interviewfragen gestellt. Er schreibt das Skript aus dem Brief."},
    "en": {"more": "Okay, I keep collecting. Say “done” when you have finished.",
           "empty": "No answers yet. Answer the questions, or say “skip interview”.",
           "done": "Thanks, the interview is saved ({file}). The Writer writes the script from your sentences now.",
           "skipped": "Interview skipped. The Writer writes the script from the brief.",
           "voice": "Your voice file is here. I transcribe it on this machine and take it as your answer.",
           "again": "The Writer prepares the interview questions again.",
           "none": "The Writer asked no interview questions. It writes the script from the brief."},
}

ASK_TASK = (
    "Interview before the first script draft (this studio has `[steps] interview` on). Do not write the script yet. "
    "Read the approved title, brief/PACKAGING-vNNN.md, brief/BRIEF.md, the research in brief/ and work/, and the recent "
    "chat (`crewcut chat --episode {episode} --last 20`). Then write {lo} to {hi} open questions for the creator, "
    "specific to this topic, about what the files cannot know: how it started for them personally, their doubts or "
    "skepticism, the real turning point, setbacks with concrete details (when, what broke, what it cost), how they "
    "work now, what it changes for them, their own opinion. One short sentence per question (at most {words} words), "
    "easy to answer by voice, in the channel's language, never a yes/no question, never one the files already answer. "
    "Write them to work/interview-questions.md: at most one short first line, then one numbered question per line "
    "(`1. …`). Post them in one message: `crewcut interview ask {episode} --file work/interview-questions.md` (it adds "
    "how to answer and sets the episode to wait). Then stop. The conductor wakes you with the answers."
)
USE_TASK = (
    "\n\nThe creator answered the interview: {file} (verbatim, light cleanup). It carries this script. Use the "
    "creator's own sentences as much as possible, almost word for word; smooth a sentence only where it cannot be "
    "spoken, and never add an experience, a feeling or a detail they did not say. Every wish to leave something out "
    "(the 'Do not mention' list and any such wish in the answers) is a hard rule: it never appears in the script, not "
    "even paraphrased. Below the `---` line, mark which spoken lines come from the interview, one mark per line: "
    '`[[interview: 3 | "the spoken words"]]` (the question number, the words as they stand in the script). Run the '
    "script check with `--interview {file}`. The answers are also a voice sample (brand/voice/interviews/): the "
    "Humanizer keeps the creator's words."
)


def enabled() -> bool:
    return episodes.step_enabled("interview")


def state(project: dict) -> dict:
    return project.get("interview") if isinstance(project.get("interview"), dict) else {}


def _language() -> str:
    from . import brand
    try:
        lang = str(brand.load().value("channel.language", "en") or "en").lower()[:2]
    except Exception:  # noqa: BLE001 - a broken pack must not stop the conductor
        lang = "en"
    return lang if lang in HOW else "en"


def _line(key: str, **kw) -> str:
    return LINES[_language()][key].format(**kw)


def needed(episode: str, project: dict | None = None) -> bool:
    """True when the script step should start with the interview: switched on, a long video, never asked before, and
    no script draft yet (an episode that already has a script, or did its interview by hand, is not asked again)."""
    p = project or episodes.read(episode)
    if not enabled() or p.get("kind", "episode") != "episode" or state(p).get("status"):
        return False
    brief = paths.episode_dir(episode) / "brief"
    return not any(brief.glob("SCRIPT*.md"))


def waiting(episode: str) -> bool:
    try:
        return state(episodes.read(episode)).get("status") == "waiting"
    except (FileNotFoundError, ValueError):
        return False


def summary(project: dict) -> dict | None:
    """What the episode card and the episode view show (Episode.interview)."""
    st = state(project)
    if not st.get("status"):
        return None
    label = {"waiting": WAITING, "asking": ASKING, "done": "Interview: done",
             "skipped": "Interview: skipped"}.get(st["status"], "Interview")
    return {"status": st["status"], "label": label, "answers": len(st.get("answers") or []),
            "questions": len(st.get("questions") or []), "file": st.get("file")}


def _writer() -> str:
    from .conductor import prompts
    return (prompts.owner("script") or {}).get("id", "writer")


def _update(episode: str, **fields) -> dict:
    p = episodes.read(episode)
    p["interview"] = {**state(p), **fields}
    episodes.write(episode, p)
    return p


def _active_jobs(episode: str) -> list[dict]:
    with db.conn() as c:
        rows = c.execute("SELECT * FROM jobs WHERE episode = ? AND status IN ('queued','running','waiting')",
                         (episode,)).fetchall()
    return [db.row(r) for r in rows]


def start(episode: str) -> int:
    """The script step begins with the interview: the Writer writes the questions (one short agent run)."""
    from .conductor import queue
    episodes.set_step(episode, "script", "working", next_action=ASKING)
    _update(episode, status="asking", at=db.now())
    jid = queue.add(episode, _writer(), "script",
                    ASK_TASK.format(episode=episode, lo=MIN_QUESTIONS, hi=MAX_QUESTIONS, words=MAX_WORDS),
                    data={"interview": "ask"})
    _update(episode, job=jid)
    return jid


def parse_questions(text: str) -> tuple[str, list[str]]:
    """(the first line before the questions, the numbered questions in order)."""
    intro, questions = [], []
    for line in text.strip().splitlines():
        m = QUESTION.match(line)
        if m:
            questions.append(" ".join(m.group(2).replace("**", "").split()))
        elif not questions and line.strip():
            intro.append(line.strip())
        elif questions and line.strip():
            questions[-1] += " " + " ".join(line.split())      # a question that wraps onto the next line
    return " ".join(intro), questions


def ask(episode: str, text: str, author: str = "writer", job: int | None = None) -> int:
    """Post the questions as one message and let the episode wait for the answers. Returns the message id."""
    from .conductor import flow
    p = episodes.read(episode)
    status = state(p).get("status")
    if status in ("done", "skipped"):
        raise ValueError(f"The interview of {episode} is {status}; write the script.")
    if status == "waiting":
        raise ValueError(f"The questions of {episode} are asked; the episode waits for the answers.")
    intro, questions = parse_questions(text)
    if not MIN_QUESTIONS <= len(questions) <= MAX_QUESTIONS:
        raise ValueError(f"{len(questions)} numbered questions; ask {MIN_QUESTIONS} to {MAX_QUESTIONS}, one per line "
                         "as '1. …'.")
    long = [i + 1 for i, q in enumerate(questions) if len(q.split()) > MAX_WORDS]
    if long:
        raise ValueError(f"question {', '.join(map(str, long))} is longer than {MAX_WORDS} words; ask it shorter, so it "
                         "is easy to answer by voice.")
    if len(intro.split()) > 40:
        raise ValueError("the first line is too long; one short sentence before the questions is enough.")
    body = (intro + "\n\n" if intro else "") + "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))
    mid = flow.post(episode, body + "\n\n" + HOW[_language()], author=author, job=job, step="script")
    episodes.set_step(episode, "script", "waiting", next_action=WAITING)
    _update(episode, status="waiting", asked_at=db.now(), message=mid, intro=intro, questions=questions, answers=[],
            collecting=False)
    return mid


def classify(text: str) -> str:
    """skip, done (only a short 'done'), more (an answer, and more is coming) or answer."""
    words = len(text.split())
    if words <= 12 and SKIP.search(text):
        return "skip"
    if words <= 6 and DONE.search(text):
        return "done"
    if MORE.search(text):
        return "more"
    return "answer"


def answer(episode: str, text: str, source: str) -> str:
    """One answer from the creator while the interview waits. Returns what happened: skipped, collecting, waiting
    (a 'done' without answers) or done."""
    from .conductor import flow
    kind = classify(text)
    if kind == "skip":
        skip(episode, "the creator said so in the chat")
        return "skipped"
    p = episodes.read(episode)
    st = state(p)
    answers = list(st.get("answers") or [])
    if kind != "done":
        answers.append({"source": source, "at": db.now(), "text": text})
    if kind == "done" and not answers:
        flow.post(episode, _line("empty"), step="script")
        return "waiting"
    if st.get("collecting") and kind == "answer" and DONE.search(text[-40:]):
        kind = "done"            # a last long answer that ends with "done"
    if kind == "more" or (kind == "answer" and st.get("collecting")):
        first = not st.get("collecting")
        _update(episode, answers=answers, collecting=True)
        if first:
            flow.post(episode, _line("more"), step="script")
        return "collecting"
    _update(episode, answers=answers)
    complete(episode)
    return "done"


def tidy(text: str) -> str:
    """Light cleanup, never new or fewer words: filler sounds out, spaces and empty lines tidy."""
    out = []
    for para in re.split(r"\n\s*\n", text.strip()):
        lines = []
        for line in para.splitlines():
            s = FILLER.sub("", line)
            s = re.sub(r"[ \t]+", " ", s).strip()
            s = re.sub(r"\s+([,.!?;:])", r"\1", s)
            if s:
                lines.append(s)
        if lines:
            out.append("\n".join(lines))
    return "\n\n".join(out)


def leave_out(texts: list[str]) -> list[str]:
    """The creator's wishes to leave something out, as they said them (sentences, bullet lines, brackets)."""
    found: list[str] = []
    for text in texts:
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z„\"(*Ä-Ü])|\n+", text):
            s = part.strip(" -*•\t")
            if s and LEAVE_OUT.search(s) and s not in found:
                found.append(s)
    return found


def _next_file(episode: str) -> str:
    brief = paths.episode_dir(episode) / "brief"
    n = 0
    for f in brief.glob("INTERVIEW-v*.md"):
        m = re.match(r"INTERVIEW-v(\d+)\.md$", f.name)
        if m:
            n = max(n, int(m.group(1)))
    return f"brief/INTERVIEW-v{n + 1:03d}.md"


def write_file(episode: str, project: dict) -> str:
    st = state(project)
    rel = _next_file(episode)
    answers = [{**a, "text": tidy(a["text"])} for a in st.get("answers") or []]
    rules = leave_out([a["text"] for a in answers])
    lines = [f"# Interview: {project.get('title', episode)}", "",
             f"- episode: {episode}",
             f"- asked: {st.get('asked_at', '?')} by the Writer (chat message {st.get('message', '?')})",
             f"- answered: {db.now()}, {len(answers)} answer(s): " + ", ".join(a["source"] for a in answers),
             "- use: the creator's own sentences as much as possible; the 'Do not mention' list is a hard rule",
             "- cleanup: filler sounds and spaces only; every word is the creator's", "",
             "## Questions", ""]
    if st.get("intro"):
        lines += [st["intro"], ""]
    lines += [f"{i}. {q}" for i, q in enumerate(st.get("questions") or [], 1)] + ["", "## Answers", ""]
    for i, a in enumerate(answers, 1):
        lines += [f"### Answer {i} ({a['source']}, {a['at']})", "", a["text"], ""]
    lines += ["## Do not mention (hard rules)", ""]
    lines += [f"- {r}" for r in rules] or ["- none found by the conductor; read the answers for more wishes like this"]
    target = paths.inside(paths.episode_dir(episode), rel)
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return rel


def complete(episode: str) -> str:
    """The answers are in: write the interview file, keep the voice sample, start the Writer on the script."""
    from . import voice
    from .conductor import flow, prompts, queue
    p = episodes.read(episode)
    st = state(p)
    rel = write_file(episode, p)
    sample = None
    try:
        sample = str(voice.write_interview(episode, p.get("title", episode),
                                           "\n\n".join(tidy(a["text"]) for a in st.get("answers") or []))
                     .relative_to(paths.studio_root()))
    except (voice.VoiceError, OSError, ValueError):
        sample = None
    _update(episode, status="done", done_at=db.now(), file=rel, voice=sample, collecting=False)
    episodes.set_step(episode, "script", "working", next_action="The Writer writes the script from your interview.")
    flow.post(episode, _line("done", file=rel), step="script")
    ask_job = db.get("jobs", st["job"]) if st.get("job") else None
    data = (ask_job or {}).get("data") or {}
    resume = ({"resume": {"engine": data["engine"], "session": data["session"]}}
              if data.get("session") and data.get("engine") else None)
    queue.add(episode, _writer(), "script", prompts.step_task("script", episode) + USE_TASK.format(file=rel),
              data=resume)
    return rel


def skip(episode: str, why: str) -> None:
    """No interview for this episode: the Writer writes the script from the brief."""
    from .conductor import flow, prompts, queue
    p = episodes.read(episode)
    st = state(p)
    if st.get("status") in ("done", "skipped"):
        return
    if not st.get("status"):          # before the script step: it simply never asks
        _update(episode, status="skipped", note=why, at=db.now())
        return
    for j in _active_jobs(episode):
        if (j.get("data") or {}).get("interview") == "ask":
            queue.cancel(j["id"])
    _update(episode, status="skipped", note=why, at=db.now(), collecting=False)
    episodes.set_step(episode, "script", "working", next_action="The Writer writes the script.")
    flow.post(episode, _line("skipped"), step="script")
    queue.add(episode, _writer(), "script", prompts.step_task("script", episode))


def finish(episode: str) -> str:
    """The creator says the answers are complete (the button, or `crewcut interview done`)."""
    return answer(episode, "done", "button")


def on_message(episode: str, text: str, mid: int) -> bool:
    """A chat message of the creator. True when the interview took it: an answer while it waits, "skip interview"
    while the questions are prepared, or any message after the Writer stopped before asking (it asks again)."""
    try:
        status = state(episodes.read(episode)).get("status")
    except (FileNotFoundError, ValueError):
        return False
    if status == "waiting":
        answer(episode, text, f"message {mid}")
        return True
    if status != "asking":
        return False
    if classify(text) == "skip":
        skip(episode, "the creator said so in the chat")
        return True
    if any((j.get("data") or {}).get("interview") == "ask" for j in _active_jobs(episode)):
        return False
    from .conductor import flow
    flow.post(episode, _line("again"), step="script")
    start(episode)
    return True


def after_ask_job(job: dict, ok: bool) -> None:
    """The Writer's question run ended. If it posted no questions although it finished, go on without an interview."""
    episode = job.get("episode")
    if not episode or not ok:
        return
    try:
        p = episodes.read(episode)
    except (FileNotFoundError, ValueError):
        return
    st = state(p)
    if st.get("status") == "asking" and st.get("job") == job["id"]:
        from .conductor import flow
        flow.post(episode, _line("none"), step="script")
        skip(episode, "the Writer asked no questions")


def voice_files(episode: str, files: list[str]) -> int:
    """Voice files dropped into the chat while the interview waits: transcribe them on this machine (a tool job)."""
    from .conductor import flow, queue
    flow.post(episode, _line("voice"), step="script")
    task = "interview answer " + shlex.quote(episode) + "".join(f" --audio {shlex.quote(f)}" for f in files)
    return queue.add(episode, _writer(), "script", task, kind="tool")


def is_voice(files: list[str]) -> bool:
    return bool(files) and all(f.lower().endswith(AUDIO) for f in files)


def answer_audio(episode: str, files: list[str]) -> str:
    """Transcribe voice files from the studio inbox of this episode and take them as one answer."""
    from . import voice
    root = paths.studio_root()
    inbox = (root / "inbox" / episode).resolve()
    texts = []
    for f in files:
        src = (root / f).resolve()
        if not src.is_relative_to(inbox) or not src.is_file():
            raise ValueError(f"{f}: voice answers come from the inbox of this episode (inbox/{episode}/).")
        texts.append(voice.transcribe(src))
    text = "\n\n".join(t for t in texts if t.strip())
    if not text.strip():
        raise ValueError("the voice file has no words that could be transcribed")
    return answer(episode, text, "voice file " + ", ".join(files))


__all__ = ["answer", "answer_audio", "ask", "classify", "complete", "enabled", "finish", "leave_out", "needed",
           "on_message", "skip", "start", "summary", "tidy", "waiting", "WAITING"]
