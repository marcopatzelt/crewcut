"""Older intermediate renders go when a new version is written: the newest two of each series stay, and a file the
current cut plan or edit plan names stays whatever its version (episode 019 kept ten 5.5 GB speaker cuts)."""

import json

from crewcut import db, engines, episodes, paths
from crewcut.conductor import flow, queue
from crewcut.cut import prune


def episode_with_renders(studio) -> tuple[str, object]:
    ep = episodes.create("Erst Coding, jetzt Videoschnitt")["id"]
    d = paths.episode_dir(ep)
    work, edit = d / "work", d / "edit"
    work.mkdir(parents=True, exist_ok=True)
    edit.mkdir(parents=True, exist_ok=True)
    for v in range(3, 14):
        (work / f"speaker-v{v:03d}.mov").write_bytes(b"x")
        (work / f"cut-v{v:03d}").mkdir()
        (work / f"cut-v{v:03d}" / "01-s01.mov").write_bytes(b"x")
        (work / f"edit-decisions-v{v:03d}.json").write_text("{}")
    for v in range(9, 14):
        (work / f"speaker-graded-v{v:03d}.mov").write_bytes(b"x")
    (work / "speaker-v009-notes.mov").write_bytes(b"x")      # not a series member: never touched
    (work / "cut-render-v003.log").write_text("log")
    # the current edit plan still builds on graded v010; an older plan named v009
    (edit / "plan-v003.json").write_text(json.dumps({"base": "work/speaker-graded-v009.mov"}))
    (edit / "plan-v004.json").write_text(json.dumps({"base": "work/speaker-graded-v010.mov",
                                                     "inserts": [{"file": "work/cut-v005/01-s01.mov"}]}))
    (edit / "cut-plan-v013.json").write_text(json.dumps({"cuts": [{"source": "raw/C0806.MP4"}],
                                                         "selects": "edit/selects-v013.json"}))
    return ep, d


def names(d, pattern: str) -> list[str]:
    return sorted(p.name for p in (d / "work").glob(pattern))


def test_keeps_the_newest_two_and_what_the_current_plans_name(studio):
    _, d = episode_with_renders(studio)
    gone = prune.work(d)
    assert names(d, "speaker-v*.mov") == ["speaker-v009-notes.mov", "speaker-v012.mov", "speaker-v013.mov"]
    assert names(d, "speaker-graded-v*.mov") == ["speaker-graded-v010.mov", "speaker-graded-v012.mov",
                                                 "speaker-graded-v013.mov"]   # v010: the current plan's base
    assert names(d, "cut-v*") == ["cut-v005", "cut-v012", "cut-v013"]   # v005: the current plan names a clip in it
    assert (d / "work" / "cut-render-v003.log").is_file()
    assert "work/speaker-graded-v009.mov" in gone                            # only an older plan named it
    assert len(names(d, "edit-decisions-v*.json")) == 11                      # small records stay
    assert prune.work(d) == []                                                # nothing more to do


def test_a_new_speaker_cut_removes_the_oldest_kept_one(studio):
    _, d = episode_with_renders(studio)
    prune.work(d)
    (d / "work" / "speaker-v014.mov").write_bytes(b"x")
    assert prune.after_write(d) == ["work/speaker-v012.mov"]


def test_an_unreadable_plan_deletes_nothing(studio):
    _, d = episode_with_renders(studio)
    (d / "edit" / "plan-v005.json").write_text("{ broken")
    assert prune.after_write(d) == []
    assert len(names(d, "speaker-v0??.mov")) == 11


def test_links_are_never_followed(studio, tmp_path):
    _, d = episode_with_renders(studio)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "keep.mov").write_bytes(b"x")
    (d / "work" / "cut-v001").symlink_to(outside, target_is_directory=True)
    prune.work(d)
    assert (outside / "keep.mov").is_file() and (d / "work" / "cut-v001").is_symlink()


def test_an_editor_run_ending_prunes_its_episode(studio, crew):
    ep, d = episode_with_renders(studio)
    jid = queue.add(ep, "editor", "edit", "Cut v013.")
    db.update("jobs", jid, status="done", started=db.now(), ended=db.now())
    flow.after_job(queue.get(jid), engines.RunResult(ok=True, exit_code=0, text="done"))
    assert names(d, "speaker-v0??.mov") == ["speaker-v012.mov", "speaker-v013.mov"]
