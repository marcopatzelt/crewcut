"""Reconcile imported history without starting work or granting approvals.

Run ``python -m crewcut.import_history EPISODE --evidence evidence.json`` to
preview changes; add ``--apply`` to save a backup and audit beside the project.
Add ``--keep-progress`` to leave step, next_action and all steps unchanged.
Evidence is an explicit binding: {"provider": "youtube", "video_id": "ID",
"records": [{"id": "ID", "distribution": "published", "checked_at": "ISO",
"published_at": "ISO"}]}. Only the exact ID is used. Empty listings prove nothing.
No network calls, title matching, README links, or source-file writes occur.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from . import db, paths

DISTRIBUTIONS = {"published", "scheduled", "uploaded", "unknown"}
MANAGED = ("created", "imported_at", "history", "history_conflicts", "production", "step", "next_action")
REVIEW = "Review imported history. No work starts and no publication permission is granted."


def safe_file(root: Path, relative: str) -> Path | None:
    from .studio_import import permitted

    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts or not permitted(relative_path):
        return None
    current = root
    if current.is_symlink():
        return None
    for part in relative_path.parts:
        current = current / part
        if current.is_symlink():
            return None
    return current if current.is_file() and current.resolve().is_relative_to(root.resolve()) else None


def timestamp(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value


def snapshot(project: dict) -> dict:
    return copy.deepcopy({**{key: project.get(key) for key in MANAGED}, "steps": project.get("steps", {})})


def _publication(record: dict, source: str, checked_at: str) -> dict:
    state = record.get("distribution", record.get("status", "unknown"))
    state = state if state in DISTRIBUTIONS else "unknown"
    url = record.get("url", record.get("youtube"))
    visibility = str(record.get("visibility", "")).strip().lower()
    if state == "unknown" and source.startswith("legacy/"):
        if visibility == "public":
            state = "published"
        elif isinstance(url, str) and url.startswith("https://") and (
            visibility in ("private", "unlisted") or visibility.startswith("scheduled")
        ):
            state = "uploaded"
    result = {"distribution": state, "source": source, "checked_at": checked_at}
    for key in ("published_at", "scheduled_at"):
        if timestamp(record.get(key)) and (key != "published_at" or state == "published"):
            result[key] = record[key]
    if isinstance(url, str) and url.startswith("https://"):
        result["url"] = url
    return result


def distribution(old: dict, evidence: dict | None, observed_at: str) -> tuple[dict, list[dict]]:
    publication = old.get("publication")
    publication = publication if isinstance(publication, dict) else {}
    historical = _publication(publication, "legacy/project.json:publication", observed_at)
    result = historical
    conflicts = []
    if str(publication.get("visibility", "")).lower().startswith("scheduled"):
        conflicts.append({"source": "legacy/project.json:publication", "visibility": publication["visibility"],
                          "note": "Historical schedule text is not a current provider observation."})
    if evidence:
        video_id = evidence.get("video_id")
        if evidence.get("provider") != "youtube" or not isinstance(video_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{11}", video_id
        ):
            raise ValueError("Evidence requires provider youtube and an exact 11-character video_id.")
        records = evidence.get("records")
        if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
            raise ValueError("Evidence records must be a list of provider records.")
        matches = [record for record in records if record.get("id") == video_id]
        if len(matches) > 1:
            raise ValueError("Supply only one observation for the exact video ID.")
        if matches:
            record = matches[0]
            if record.get("distribution") not in DISTRIBUTIONS or not timestamp(record.get("checked_at")):
                raise ValueError("Provider evidence requires distribution and checked_at.")
            observation = _publication(record, f"youtube:{video_id}", record["checked_at"])
            observation["url"] = f"https://www.youtube.com/watch?v={video_id}"
            if observation["distribution"] != "unknown":
                result = observation
            if historical["distribution"] != "unknown" and historical["distribution"] != observation["distribution"]:
                conflicts.append({"preferred": result, "other": historical if result == observation else observation})
            old_id = publication.get("video_id", publication.get("id"))
            if old_id and old_id != video_id:
                conflicts.append({"source": "legacy/project.json:publication", "video_id": old_id,
                                  "supplied_video_id": video_id})
    stage = old.get("stage")
    if stage and stage != result["distribution"]:
        conflicts.append({"source": "legacy/project.json:stage", "stage": stage,
                          "distribution": result["distribution"], "hint_only": True})
    return result, conflicts


def _registered_recording(root: Path, observed_at: str) -> dict | None:
    brief = root / "brief"
    if brief.is_symlink():
        return None
    for report_path in sorted(brief.glob("ingest-*.json")):
        relative_report = report_path.relative_to(root).as_posix()
        if not safe_file(root, relative_report):
            continue
        try:
            report = json.loads(report_path.read_text())
        except (ValueError, OSError):
            continue
        if not isinstance(report, dict):
            continue
        for entry in report.get("files", []):
            if not isinstance(entry, dict) or entry.get("kind") not in ("video", "audio"):
                continue
            relative = entry.get("file")
            if not isinstance(relative, str):
                continue
            candidate = safe_file(root, relative)
            if candidate and candidate.stat().st_size > 0 and candidate.stat().st_size == entry.get("bytes"):
                return {"source": relative, "scope": "registered_recording", "checked_at": observed_at,
                        "registration": relative_report, "bytes": entry["bytes"],
                        "registered_sha256": entry.get("sha256")}
    return None


def _exports(root: Path, observed_at: str) -> dict:
    directory = root / "export"
    if directory.is_symlink() or not directory.is_dir():
        return {}
    found = {}
    for candidate in sorted(directory.iterdir()):
        if candidate.suffix.lower() not in (".mp4", ".mov", ".mkv", ".webm"):
            continue
        relative = candidate.relative_to(root).as_posix()
        if not safe_file(root, relative) or candidate.stat().st_size == 0:
            continue
        name = candidate.name.lower()
        kind = "preview" if "preview" in name else "final" if "final" in name else "export"
        found[kind] = {"source": relative, "scope": "final_file" if kind == "final" else kind,
                       "checked_at": observed_at, "bytes": candidate.stat().st_size}
    return found


def historical_fields(root: Path, old: dict, imported_at: str | None, evidence: dict | None = None,
                      checked_at: str | None = None) -> dict:
    """Build historical observations; a file proves presence, not a current approval."""
    from .episodes import STEP_IDS

    observed_at = checked_at or imported_at or db.now()
    history, conflicts = distribution(old, evidence, observed_at)
    steps = {step: {"status": "unknown"} for step in STEP_IDS}
    steps["blog"] = {"status": "skipped", "note": "Blog is disabled."}
    production = _exports(root, observed_at)
    recording = _registered_recording(root, observed_at)
    if recording:
        production["recording"] = recording
        steps["record"] = {"status": "done", "evidence": recording}
    delivery = old.get("delivery")
    delivery = delivery if isinstance(delivery, dict) else {}
    candidates = [("script", "brief/SCRIPT-v001.md", "draft")]
    for name, scope in (("recording", "recording"), ("preview", "preview"),
                        ("final", "final_file"), ("cover", "cover")):
        value = delivery.get(name)
        if isinstance(value, dict):
            if name == "final" and value.get("accepted") is True and timestamp(value.get("accepted_at")):
                scope = "historical_accepted_final"
            value = value.get("path")
        if isinstance(value, str):
            candidates.append((name, "legacy/" + value.split(" (", 1)[0], scope))
    for name, relative, scope in candidates:
        candidate = safe_file(root, relative)
        if candidate:
            with candidate.open("rb") as incoming:
                digest = hashlib.file_digest(incoming, "sha256").hexdigest()
            production[name] = {"source": relative, "scope": scope, "checked_at": observed_at, "sha256": digest}
            if scope in ("recording", "historical_accepted_final"):
                step = "record" if scope == "recording" else "edit"
                steps[step] = {"status": "done", "evidence": production[name]}
    if history["distribution"] in {"published", "scheduled", "uploaded"}:
        for step in ("record", "edit", "upload"):
            steps[step] = {"status": "done", "evidence": {**history, "scope": "historical_completion"}}
    return {"created": timestamp(old.get("created")) or timestamp(old.get("created_at")),
            "imported_at": imported_at, "history": history, "history_conflicts": conflicts,
            "production": production, "steps": steps,
            "step": None if history["distribution"] != "unknown" else "script", "next_action": REVIEW}


def initialize(project: dict, root: Path, old: dict) -> dict:
    fields = historical_fields(root, old, project["imported_at"])
    for step, value in project["steps"].items():
        if value.get("absent"):
            fields["steps"][step] = {"status": "skipped", "absent": True}
    project.update(fields)
    project["import_history"] = {"version": 1, "baseline": snapshot(project), "provider_evidence": None,
                                 "observed_at": project["imported_at"]}
    return project


def _legacy_baseline(project: dict) -> dict:
    baseline = {}
    for step in project.get("steps", {}):
        value = {"status": "open"}
        if step in ("idea", "title"):
            value = {"status": "done", "note": "Imported; not newly approved."}
        if step in ("upload", "blog", "results"):
            value = {"status": "skipped", "note": "Import never publishes or starts work."}
        if project.get("kind") == "short" and step == "blog":
            value["absent"] = True
        baseline[step] = value
    return baseline


@contextmanager
def _idle(episode: str, apply: bool):
    database = paths.studio_root() / ".crewcut" / "crewcut.db"
    if not database.exists():
        yield
        return
    if database.is_symlink():
        raise ValueError("The studio database must not be a link.")
    connection = sqlite3.connect(database.as_uri() + ("?mode=rw" if apply else "?mode=ro"), uri=True)
    try:
        if apply:
            connection.execute("BEGIN IMMEDIATE")
        busy = connection.execute(
            "SELECT 1 FROM jobs WHERE episode = ? AND status IN ('queued','running','waiting')", (episode,)
        ).fetchone()
        if busy:
            raise ValueError("Finish or cancel this episode's jobs before reconciling history.")
        yield
    finally:
        connection.close()


def reconcile(episode: str, evidence: dict | None = None, *, apply: bool = False,
              preserve_progress: bool = False) -> dict:
    """Preview by default. Save only unchanged import-owned fields when applying."""
    if Path(episode).name != episode or episode in ("", ".", ".."):
        raise ValueError("Invalid episode ID.")
    root = paths.studio_root() / "episodes" / episode
    if root.parent.is_symlink() or root.is_symlink():
        raise ValueError("Episode folders must not be links.")
    project_file = safe_file(root, "project.json")
    manifest_file = safe_file(root, "legacy-import.json")
    if not project_file or not manifest_file:
        raise ValueError("Reconciliation requires an imported episode and its manifest.")
    with _idle(episode, apply):
        original = project_file.read_bytes()
        project = json.loads(original)
        source = safe_file(root, "legacy/project.json")
        old = json.loads(source.read_text()) if source else {}
        state = project.get("import_history", {})
        baseline = state.get("baseline")
        manifest = json.loads(manifest_file.read_text())
        imported_at = project.get("imported_at") or manifest.get("imported_at") or project.get("created")
        supplied = evidence if evidence is not None else state.get("provider_evidence")
        observed_at = state.get("observed_at") or db.now()
        desired = historical_fields(root, old, imported_at, supplied, observed_at)
        if supplied and state.get("provider_evidence") and not any(
            record.get("id") == supplied["video_id"] and record.get("distribution") != "unknown"
            for record in supplied["records"]
        ):
            supplied = state["provider_evidence"]
            desired = historical_fields(root, old, imported_at, supplied, observed_at)
        result = copy.deepcopy(project)
        preserved = []
        for key in MANAGED:
            if preserve_progress and key in ("step", "next_action"):
                preserved.append(key)
                continue
            if baseline is not None:
                owned = project.get(key) == baseline.get(key)
            else:
                owned = key not in project or key in ("created",)
                if key == "next_action":
                    owned = project.get(key) == (
                        "Import prüfen. Keine Aufgabe startet automatisch. Veröffentlichungen bleiben ausgeschaltet.")
                if key == "step":
                    owned = project.get(key) in ("record", "script") and project.get("next_action", "").startswith(
                        "Import prüfen.")
            if owned:
                result[key] = desired[key]
            elif project.get(key) != desired[key]:
                preserved.append(key)
        expected_steps = baseline.get("steps", {}) if baseline is not None else _legacy_baseline(project)
        if preserve_progress:
            preserved.append("steps")
        for step, value in desired["steps"].items():
            if preserve_progress:
                break
            current = project.get("steps", {}).get(step)
            expected = expected_steps.get(step)
            owned = current == expected
            if baseline is None and current == {
                "status": "waiting", "note": "Review imported material before continuing."
            } and step in ("script", "record"):
                owned = True
            if current and current.get("absent"):
                continue
            if owned:
                result.setdefault("steps", {})[step] = value
            elif current != value:
                preserved.append(f"steps.{step}")
        changes = {key: {"before": project.get(key), "after": result.get(key)}
                   for key in (*MANAGED, "steps") if project.get(key) != result.get(key)}
        new_baseline = snapshot(result)
        for key in preserved:
            if key == "steps":
                new_baseline[key] = copy.deepcopy(expected_steps)
            elif key.startswith("steps."):
                step = key.split(".")[1]
                new_baseline["steps"][step] = expected_steps.get(step)
            else:
                new_baseline[key] = baseline.get(key) if baseline else None
        result["import_history"] = {"version": 1, "baseline": new_baseline, "provider_evidence": supplied,
                                    "observed_at": observed_at}
        changed = result != project
        report = {"episode": episode, "applied": False, "changed": changed, "changes": changes,
                  "preserved": preserved, "preserve_progress": preserve_progress,
                  "conflicts": desired["history_conflicts"]}
        if not apply or not changed:
            return report
        audit_root = root / "history-audit"
        if audit_root.is_symlink():
            raise ValueError("History audit folder must not be a link.")
        audit_root.mkdir(exist_ok=True)
        audit = Path(tempfile.mkdtemp(prefix="reconcile-", dir=audit_root))
        (audit / "project.before.json").write_bytes(original)
        report.update(at=db.now(), backup=str((audit / "project.before.json").relative_to(root)))
        (audit / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        (audit / "project.after.json").write_text(serialized)
        pending = audit / "project.pending.json"
        pending.write_text(serialized)
        if project_file.read_bytes() != original:
            raise RuntimeError("Project changed during reconciliation; no metadata was replaced.")
        pending.replace(project_file)
        report["applied"] = True
        (audit / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--keep-progress", action="store_true", help="Preserve step, next_action and all steps.")
    args = parser.parse_args()
    try:
        evidence = json.loads(args.evidence.read_text()) if args.evidence else None
        if evidence is not None and not isinstance(evidence, dict):
            raise ValueError("Evidence must be a JSON object.")
        print(json.dumps(reconcile(args.episode, evidence, apply=args.apply, preserve_progress=args.keep_progress),
                         ensure_ascii=False, indent=2))
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
