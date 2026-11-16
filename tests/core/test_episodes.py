from crewcut import episodes


def test_create_and_steps(crew, studio):
    p = episodes.create("Does a $20 plan build a website?")
    eid = p["id"]
    assert eid.startswith("001-")
    d = studio / "episodes" / eid
    assert (d / "project.json").is_file() and (d / "brief" / "BRIEF.md").is_file()
    s = episodes.summary(eid)
    assert [x["id"] for x in s["steps"]][:3] == ["idea", "title", "proof"]
    assert next(x for x in s["steps"] if x["id"] == "blog")["status"] == "skipped"
    episodes.set_step(eid, "idea", "done")
    assert episodes.read(eid)["step"] == "title"
    assert episodes.create("second")["id"].startswith("002-")


def test_slug_and_bad_ids():
    assert episodes.slug("Héllo, Wörld! 100%") == "hello-world-100"
    import pytest

    from crewcut import paths
    with pytest.raises(ValueError):
        paths.episode_dir("../x")
