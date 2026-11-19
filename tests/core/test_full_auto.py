import json

import pytest

from crewcut import approvals, db, episodes, full_auto, paths
from crewcut.conductor import queue


@pytest.fixture
def episode(crew):
    return episodes.create("Synthetic automatic production")["id"]


def card(episode, kind="preview", step="edit", options=None):
    name = f"review/{kind}.txt"
    paths.inside(paths.episode_dir(episode), name).write_text("synthetic artifact")
    return approvals.propose(episode, step, kind, "Review", file=name, identity="editor", options=options)


def evidence(episode, c, verdict="pass"):
    name = "review/auto-test.json"
    paths.inside(paths.episode_dir(episode), name).write_text(json.dumps({
        "card_sha256": c["sha256"], "verdict": verdict, "checks": [{"name": "Synthetic fixture", "passed": True}],
        "reason": "Synthetic result"}))
    return name


def assigned(monkeypatch, episode, c):
    jid = queue.add(episode, "critic", c["step"], "Review", data={"auto_card": c["id"],
        "auto_revision": full_auto.policy(episode)["revision"]})
    monkeypatch.setenv("CREWCUT_IDENTITY", "critic")
    monkeypatch.setenv("CREWCUT_JOB", str(jid))


def test_off_by_default_and_does_not_touch_existing_jobs(episode):
    jid = queue.add(episode, "editor", "edit", "Existing work")
    before = queue.get(jid)
    assert not full_auto.active(episode)
    full_auto.configure(episode, "private")
    assert queue.get(jid) == before
    full_auto.configure(episode, "off")
    assert queue.get(jid) == before


def test_only_assigned_critic_can_approve_and_disabling_revokes(episode, monkeypatch):
    full_auto.configure(episode, "private")
    c = card(episode)
    report = evidence(episode, c)
    with pytest.raises(PermissionError):
        full_auto.review(c["id"], report)
    assigned(monkeypatch, episode, c)
    full_auto.configure(episode, "off")
    with pytest.raises(PermissionError):
        full_auto.review(c["id"], report)
    assert approvals.get(c["id"])["status"] == "open"


def test_review_is_file_bound_and_continues_after_pass(episode, monkeypatch):
    full_auto.configure(episode, "private")
    c = card(episode)
    assigned(monkeypatch, episode, c)
    report = evidence(episode, c)
    result = full_auto.review(c["id"], report)
    assert result["status"] == "accepted"
    assert result["data"]["auto_report_sha256"]
    with db.conn() as con:
        assert con.execute("SELECT COUNT(*) FROM jobs WHERE identity='editor' AND step='edit'").fetchone()[0] == 1


def test_changed_file_or_unselected_option_is_not_approved(episode, monkeypatch):
    full_auto.configure(episode, "private")
    c = card(episode, options=["A", "B"])
    assigned(monkeypatch, episode, c)
    report = evidence(episode, c)
    with pytest.raises(ValueError, match="option"):
        full_auto.review(c["id"], report)
    paths.inside(paths.episode_dir(episode), c["file"]).write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        full_auto.review(c["id"], report, choice=0)


def test_scheduler_dispatches_once_without_starting_recording(episode):
    full_auto.configure(episode, "private")
    full_auto.tick()
    with db.conn() as con:
        assert con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
    c = card(episode)
    full_auto.tick()
    full_auto.tick()
    with db.conn() as con:
        assert con.execute("SELECT COUNT(*) FROM jobs WHERE identity='critic'").fetchone()[0] == 1
    assert approvals.get(c["id"])["status"] == "open"


def test_ready_reviews_upload_package_without_approving_upload(episode):
    full_auto.configure(episode, "ready")
    c = card(episode, kind="publish", step="upload")
    full_auto.tick()
    assert not full_auto.policy(episode).get("complete")
    assert approvals.get(c["id"])["status"] == "open"
    with db.conn() as con:
        assert con.execute("SELECT COUNT(*) FROM jobs WHERE identity='critic'").fetchone()[0] == 1


def test_private_scope_rejects_public_or_scheduled_package(episode):
    full_auto.configure(episode, "private")
    root = paths.episode_dir(episode)
    (root / "render/final.mp4").write_bytes(b"synthetic")
    pkg = {"video": "render/final.mp4", "title": "Test", "description": "Test", "privacy": "public"}
    (root / "export/upload.json").write_text(json.dumps(pkg))
    c = approvals.propose(episode, "upload", "publish", "Test", file="export/upload.json")
    with pytest.raises(ValueError, match="private"):
        full_auto.publish_allowed(c)
    pkg["privacy"] = "private"
    (root / "export/upload.json").write_text(json.dumps(pkg))
    with pytest.raises(ValueError, match="reviewed final"):
        full_auto.publish_allowed(c)


def test_ready_completion_keeps_upload_manual(episode, monkeypatch):
    full_auto.configure(episode, 'ready')
    c = card(episode, kind='publish', step='upload')
    assigned(monkeypatch, episode, c)
    monkeypatch.setattr(full_auto, 'publish_allowed', lambda *a, **kw: None)
    result = full_auto.review(c['id'], evidence(episode, c))
    assert result['status'] == 'ready'
    assert full_auto.policy(episode)['complete']
    saved = approvals.get(c['id'])
    assert saved['status'] == 'open'
    assert 'auto_revision' not in saved['data']
    with db.conn() as con:
        assert con.execute("SELECT COUNT(*) FROM jobs WHERE identity='publisher'").fetchone()[0] == 0


def test_unrelated_import_rule_does_not_block_edit_and_spend_is_not_declined(episode):
    full_auto.configure(episode, 'ready')
    paths.inside(paths.episode_dir(episode), 'originals/take.mp4').write_bytes(b'synthetic')
    rule = approvals.propose(episode, 'script', 'rule', 'Old script rule')
    full_auto.tick()
    assert approvals.get(rule['id'])['status'] == 'open'
    with db.conn() as con:
        assert con.execute("SELECT COUNT(*) FROM jobs WHERE identity='editor'").fetchone()[0] == 1
    spend = approvals.propose(episode, 'edit', 'spend', 'Quality budget', data={'budget_usd': 2})
    full_auto.tick()
    assert approvals.get(spend['id'])['status'] == 'open'
