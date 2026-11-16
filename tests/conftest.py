"""Every test gets its own empty studio folder, so no test ever writes into the repository."""

import pytest


@pytest.fixture(autouse=True)
def studio(tmp_path, monkeypatch):
    s = tmp_path / "studio"
    s.mkdir()
    monkeypatch.setenv("CREWCUT_STUDIO", str(s))
    for k in ("CREWCUT_IDENTITY", "CREWCUT_JOB", "CREWCUT_EPISODE", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY",
              "VAST_API_KEY", "OPENAI_API_KEY", "YOUTUBE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    return s


@pytest.fixture
def crew(tmp_path, monkeypatch):
    """A tiny crew in a temp team folder (tests must not depend on the real team files)."""
    from crewcut import paths, team
    d = tmp_path / "team"
    d.mkdir()
    for ident, steps, spend, publish in (
        ("showrunner", [], False, False), ("scout", ["idea", "title", "proof"], False, False),
        ("writer", ["script"], False, False), ("editor", ["record", "edit"], True, False),
        ("critic", [], False, False), ("designer", ["thumbnail"], True, False),
        ("publisher", ["upload", "results"], False, True), ("brand", [], False, False),
    ):
        (d / f"{ident}.md").write_text(
            f"---\nid: {ident}\nname: {ident.capitalize()}\nmark: {ident[:2].upper()}\nrole: test role.\n"
            f"steps: {steps}\nmay_spend: {str(spend).lower()}\nmay_publish: {str(publish).lower()}\n---\nI work.\n")
    monkeypatch.setattr(paths, "team_dir", lambda: d)
    team._load_all.cache_clear()
    yield d
    team._load_all.cache_clear()
