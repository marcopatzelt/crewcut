import json
import subprocess
import sys

import pytest

from crewcut import db, episodes, import_history, studio_import

VIDEO = "synthetic01"
DATE = "2024-01-02T03:04:05Z"


def imported(tmp_path, studio, old=None):
    source = tmp_path / "old" / "001-example"
    source.mkdir(parents=True)
    (source / "project.json").write_text(json.dumps(old or {}))
    studio_import.import_episode(source, studio)
    return studio / "episodes" / source.name


def evidence(distribution="published", **extra):
    return {"provider": "youtube", "video_id": VIDEO,
            "records": [{"id": VIDEO, "distribution": distribution, "checked_at": DATE, **extra}]}


def read(root):
    return json.loads((root / "project.json").read_text())


def save(root, project):
    (root / "project.json").write_text(json.dumps(project))


def test_published_source_beats_stale_stage_without_permissions(tmp_path, studio):
    root = imported(tmp_path, studio, {"created": DATE, "stage": "script",
                                      "publication": {"status": "published", "published_at": DATE}})
    project = read(root)
    assert project["created"] == DATE
    assert project["imported_at"] != DATE
    assert project["history"]["distribution"] == "published"
    assert project["history_conflicts"][0]["stage"] == "script"
    for step in ("record", "edit", "upload"):
        assert project["steps"][step]["status"] == "done"
        assert project["steps"][step]["evidence"]["scope"] == "historical_completion"
        assert "card" not in project["steps"][step]
    for step in ("proof", "script", "thumbnail", "results"):
        assert project["steps"][step]["status"] == "unknown"
    assert not (studio / ".crewcut" / "crewcut.db").exists()
    assert not list((root / "export").iterdir())
    assert import_history.reconcile(root.name)["changed"] is False


def test_legacy_public_visibility_and_youtube_url(tmp_path, studio):
    url = f"https://youtu.be/{VIDEO}"
    root = imported(tmp_path, studio, {"stage": "schnitt", "publication": {
        "youtube": url, "visibility": "public", "published_at": DATE}})
    project = read(root)
    assert project["history"]["distribution"] == "published"
    assert project["history"]["url"] == url
    assert project["history"]["published_at"] == DATE
    assert project["steps"]["upload"]["status"] == "done"


def test_legacy_schedule_text_keeps_upload_evidence_not_publication(tmp_path, studio):
    root = imported(tmp_path, studio, {"stage": "schnitt", "publication": {
        "youtube": f"https://youtu.be/{VIDEO}", "published_at": DATE,
        "visibility": "scheduled (Studio: public on January 2, 2024 at 8:00 AM); until then private"}})
    project = read(root)
    assert project["history"]["distribution"] == "uploaded"
    assert "published_at" not in project["history"]
    assert project["history_conflicts"][0]["visibility"].startswith("scheduled")
    for step in ("record", "edit", "upload"):
        assert project["steps"][step]["status"] == "done"


def test_dry_run_apply_backup_and_idempotent_audit(tmp_path, studio):
    root = imported(tmp_path, studio)
    before = (root / "project.json").read_bytes()
    files_before = sorted(root.rglob("*"))
    report = import_history.reconcile(root.name, evidence())
    assert report["changed"] and not report["applied"]
    assert (root / "project.json").read_bytes() == before
    assert sorted(root.rglob("*")) == files_before
    assert not (studio / ".crewcut" / "crewcut.db").exists()
    report = import_history.reconcile(root.name, evidence(), apply=True)
    assert report["applied"]
    assert (root / report["backup"]).read_bytes() == before
    audits = list((root / "history-audit").iterdir())
    assert len(audits) == 1
    assert json.loads((audits[0] / "report.json").read_text())["changes"]
    assert not import_history.reconcile(root.name, evidence(), apply=True)["changed"]
    assert not import_history.reconcile(root.name, apply=True)["changed"]
    assert list((root / "history-audit").iterdir()) == audits


def test_exact_id_only_no_title_match_and_no_readme_parent(tmp_path, studio):
    root = imported(tmp_path, studio, {"title": "Identical title"})
    (root / "legacy" / "LIESMICH.md").write_text(f"Parent: https://youtu.be/{VIDEO}")
    supplied = evidence()
    supplied["records"][0].update(id="different01", title="Identical title")
    import_history.reconcile(root.name, supplied, apply=True)
    assert read(root)["history"]["distribution"] == "unknown"
    assert "url" not in read(root)["history"]


def test_scheduled_past_date_is_not_published(tmp_path, studio):
    root = imported(tmp_path, studio)
    import_history.reconcile(root.name, evidence("scheduled", scheduled_at=DATE), apply=True)
    project = read(root)
    assert project["history"]["distribution"] == "scheduled"
    assert project["history"]["scheduled_at"] == DATE
    assert "published_at" not in project["history"]
    summary = episodes.summary(root.name)
    assert summary["history"] == project["history"]
    assert summary["historical_status"] == "scheduled"
    assert summary["created"] is None
    assert summary["imported_at"] == project["imported_at"]


def test_preserves_later_edits_across_repeated_apply(tmp_path, studio):
    root = imported(tmp_path, studio)
    project = read(root)
    project.update(title="User's title", next_action="User's instruction", created=DATE, lifecycle="parked")
    project["steps"]["edit"] = {"status": "waiting", "card": 42, "at": DATE}
    save(root, project)
    report = import_history.reconcile(root.name, evidence(), apply=True)
    assert set(report["preserved"]) == {"created", "next_action", "steps.edit"}
    for key in ("title", "next_action", "created", "lifecycle"):
        assert read(root)[key] == project[key]
    assert read(root)["steps"]["edit"] == project["steps"]["edit"]
    assert not import_history.reconcile(root.name, apply=True)["changed"]


@pytest.mark.parametrize("status", ["queued", "running", "waiting"])
@pytest.mark.parametrize("apply", [False, True])
def test_rejects_busy_jobs(tmp_path, studio, status, apply):
    root = imported(tmp_path, studio)
    db.insert("jobs", episode=root.name, status=status, created=DATE)
    before = (root / "project.json").read_bytes()
    with pytest.raises(ValueError, match="jobs"):
        import_history.reconcile(root.name, evidence(), apply=apply)
    assert (root / "project.json").read_bytes() == before
    assert not (root / "history-audit").exists()


def test_no_jobs_cards_or_costs_created(tmp_path, studio):
    root = imported(tmp_path, studio)
    with db.conn():
        pass
    import_history.reconcile(root.name, evidence(), apply=True)
    with db.conn() as connection:
        for table in ("jobs", "cards", "costs", "rentals"):
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_provider_priority_keeps_conflicting_sources(tmp_path, studio):
    root = imported(tmp_path, studio, {"publication": {"status": "scheduled", "video_id": "different01"}})
    import_history.reconcile(root.name, evidence(), apply=True)
    project = read(root)
    assert project["history"]["source"] == f"youtube:{VIDEO}"
    assert project["history"]["distribution"] == "published"
    assert len(project["history_conflicts"]) == 2


def test_missing_listing_does_not_disprove_local_publication(tmp_path, studio):
    root = imported(tmp_path, studio, {"publication": {"status": "published"}})
    supplied = evidence()
    supplied["records"] = []
    import_history.reconcile(root.name, supplied, apply=True)
    assert read(root)["history"]["distribution"] == "published"


@pytest.mark.parametrize("records", [[], [{"id": VIDEO, "distribution": "unknown", "checked_at": DATE}]])
def test_missing_or_unknown_provider_observation_keeps_previous_evidence(tmp_path, studio, records):
    root = imported(tmp_path, studio)
    import_history.reconcile(root.name, evidence(), apply=True)
    supplied = evidence()
    supplied["records"] = records
    assert not import_history.reconcile(root.name, supplied, apply=True)["changed"]
    assert read(root)["history"]["distribution"] == "published"


@pytest.mark.parametrize("mutation", [
    {"video_id": "bad"}, {"provider": "other"}, {"records": ["bad"]},
    {"records": [{"id": VIDEO, "distribution": "published"}]},
])
def test_invalid_evidence_never_writes(tmp_path, studio, mutation):
    root = imported(tmp_path, studio)
    supplied = {**evidence(), **mutation}
    before = (root / "project.json").read_bytes()
    with pytest.raises(ValueError):
        import_history.reconcile(root.name, supplied, apply=True)
    assert (root / "project.json").read_bytes() == before


@pytest.mark.parametrize("relative", ["project.json", "legacy-import.json"])
def test_rejects_linked_metadata(tmp_path, studio, relative):
    root = imported(tmp_path, studio)
    outside = tmp_path / "outside.json"
    (root / relative).rename(outside)
    (root / relative).symlink_to(outside)
    with pytest.raises(ValueError):
        import_history.reconcile(root.name, apply=True)


def test_file_evidence_cannot_follow_linked_parent(tmp_path, studio):
    root = imported(tmp_path, studio, {"delivery": {"final": "external/final.mp4"}})
    outside = tmp_path / "external"
    outside.mkdir()
    (outside / "final.mp4").write_bytes(b"synthetic media")
    (root / "legacy" / "external").symlink_to(outside, target_is_directory=True)
    import_history.reconcile(root.name, apply=True)
    assert read(root)["production"] == {}
    assert read(root)["steps"]["edit"]["status"] == "unknown"


def test_old_import_repair_preserves_modified_steps(tmp_path, studio):
    root = imported(tmp_path, studio, {"created": DATE, "publication": {"status": "published"}})
    project = read(root)
    for key in (*import_history.MANAGED, "import_history"):
        project.pop(key, None)
    project.update(created="2026-01-01T00:00:00Z", step="record",
                   next_action="Import prüfen. Keine Aufgabe startet automatisch. Veröffentlichungen bleiben ausgeschaltet.")
    project["steps"] = import_history._legacy_baseline(project)
    project["steps"]["record"] = {"status": "waiting", "note": "Review imported material before continuing."}
    project["steps"]["proof"] = {"status": "done", "card": 11}
    save(root, project)
    import_history.reconcile(root.name, apply=True)
    repaired = read(root)
    assert repaired["created"] == DATE
    assert repaired["steps"]["upload"]["status"] == "done"
    assert repaired["steps"]["proof"] == project["steps"]["proof"]
    assert not import_history.reconcile(root.name, apply=True)["changed"]


def test_preview_is_not_final_approval(tmp_path, studio):
    root = imported(tmp_path, studio, {"delivery": {"preview": "preview.mp4"}})
    (root / "legacy" / "preview.mp4").write_bytes(b"synthetic preview")
    import_history.reconcile(root.name, apply=True)
    assert read(root)["production"]["preview"]["scope"] == "preview"
    assert read(root)["steps"]["edit"]["status"] == "unknown"


def test_native_exports_are_evidence_not_approval(tmp_path, studio):
    root = imported(tmp_path, studio)
    (root / "export" / "example-preview.mp4").write_bytes(b"synthetic preview")
    (root / "export" / "example-final.mp4").write_bytes(b"synthetic final")
    import_history.reconcile(root.name, apply=True)
    project = read(root)
    assert project["production"]["preview"]["scope"] == "preview"
    assert project["production"]["final"]["scope"] == "final_file"
    assert project["steps"]["edit"]["status"] == "unknown"


@pytest.mark.parametrize("relative", ["originals/recording.mov", "legacy/01-originals/camera/day/recording.mov"])
def test_registered_recordings_prove_record_step(tmp_path, studio, relative):
    root = imported(tmp_path, studio)
    recording = root / relative
    recording.parent.mkdir(parents=True, exist_ok=True)
    recording.write_bytes(b"synthetic recording")
    (root / "brief" / "ingest-legacy.json").write_text(json.dumps({"files": [{
        "file": relative, "kind": "video", "bytes": recording.stat().st_size}]}))
    import_history.reconcile(root.name, apply=True)
    project = read(root)
    assert project["steps"]["record"]["status"] == "done"
    assert project["steps"]["record"]["evidence"]["source"] == relative
    assert project["steps"]["edit"]["status"] == "unknown"


def test_distributed_history_has_no_current_work_step(tmp_path, studio):
    root = imported(tmp_path, studio)
    import_history.reconcile(root.name, evidence(), apply=True)
    assert read(root)["step"] is None
    assert not any(step["status"] in ("working", "waiting") for step in read(root)["steps"].values())


def test_accepted_delivery_is_history_not_current_card(tmp_path, studio):
    root = imported(tmp_path, studio, {"delivery": {"final": {
        "path": "final.mp4", "accepted": True, "accepted_at": DATE}}})
    (root / "legacy" / "final.mp4").write_bytes(b"synthetic final")
    import_history.reconcile(root.name, apply=True)
    step = read(root)["steps"]["edit"]
    assert step["status"] == "done"
    assert step["evidence"]["scope"] == "historical_accepted_final"
    assert "card" not in step
    assert read(root)["steps"]["upload"]["status"] == "unknown"


def test_cli_defaults_to_preview(tmp_path, studio):
    root = imported(tmp_path, studio)
    supplied = tmp_path / "evidence.json"
    supplied.write_text(json.dumps(evidence()))
    before = (root / "project.json").read_bytes()
    result = subprocess.run([sys.executable, "-m", "crewcut.import_history", root.name,
                             "--evidence", str(supplied)], capture_output=True, text=True, check=True)
    assert not json.loads(result.stdout)["applied"]
    assert (root / "project.json").read_bytes() == before


@pytest.mark.parametrize("has_baseline", [False, True])
def test_keep_progress_updates_history_and_dates_only(tmp_path, studio, has_baseline):
    root = imported(tmp_path, studio, {"created": DATE})
    project = read(root)
    project.update(step="record", next_action="Keep this instruction.")
    project["steps"] = import_history._legacy_baseline(project)
    project["steps"]["script"] = {"status": "waiting", "card": 42, "at": DATE}
    project["steps"]["custom"] = {"status": "done", "note": "Keep this too."}
    project["created"] = project["imported_at"]
    project.pop("imported_at")
    if has_baseline:
        project["import_history"]["baseline"] = import_history.snapshot(project)
    else:
        project.pop("import_history")
        for key in ("history", "history_conflicts", "production"):
            project.pop(key, None)
    save(root, project)
    before = (root / "project.json").read_bytes()
    preview = import_history.reconcile(root.name, evidence(), preserve_progress=True)
    assert (root / "project.json").read_bytes() == before
    assert not {"step", "next_action", "steps"}.intersection(preview["changes"])
    assert {"step", "next_action", "steps"}.issubset(preview["preserved"])
    applied = import_history.reconcile(root.name, evidence(), apply=True, preserve_progress=True)
    result = read(root)
    for key in ("step", "next_action", "steps"):
        assert result[key] == project[key]
    assert result["created"] == DATE
    assert result["imported_at"] == project["created"]
    assert result["history"]["distribution"] == "published"
    assert (root / applied["backup"]).read_bytes() == before
    assert not import_history.reconcile(root.name, apply=True, preserve_progress=True)["changed"]


def test_cli_keep_progress(tmp_path, studio):
    root = imported(tmp_path, studio)
    supplied = tmp_path / "evidence.json"
    supplied.write_text(json.dumps(evidence()))
    before = read(root)
    result = subprocess.run([sys.executable, "-m", "crewcut.import_history", root.name,
                             "--evidence", str(supplied), "--keep-progress", "--apply"],
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["preserve_progress"] is True
    for key in ("step", "next_action", "steps"):
        assert read(root)[key] == before[key]
    assert read(root)["history"]["distribution"] == "published"


def test_blog_stays_disabled_on_import_and_reconciliation(tmp_path, studio):
    root = imported(tmp_path, studio)
    assert read(root)["steps"]["blog"] == {"status": "skipped", "note": "Blog is disabled."}
    import_history.reconcile(root.name, evidence(), apply=True)
    assert read(root)["steps"]["blog"] == {"status": "skipped", "note": "Blog is disabled."}


def test_standard_script_is_safe_draft_evidence_not_done(tmp_path, studio):
    root = imported(tmp_path, studio)
    script = root / "brief" / "SCRIPT-v001.md"
    script.write_text("Synthetic draft awaiting review.")
    assert import_history.safe_file(root, "brief/SCRIPT-v001.md") == script
    import_history.reconcile(root.name, apply=True)
    project = read(root)
    assert project["production"]["script"]["source"] == "brief/SCRIPT-v001.md"
    assert project["production"]["script"]["scope"] == "draft"
    assert project["steps"]["script"]["status"] == "unknown"
