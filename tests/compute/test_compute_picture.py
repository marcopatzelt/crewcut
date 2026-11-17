"""The one privacy exception: the picture of a shot for the matting job (graphics behind the speaker).

Against the fake Vast API and the fake SSH runner: the spend card says in plain words that the picture goes up and is
deleted with the machine; only the files that card names go up; everything else stays refused."""

from __future__ import annotations

import hashlib

import pytest

from crewcut import approvals, db
from crewcut.compute import Refused, privacy
from crewcut.compute import session as session_fn
from crewcut.compute.errors import NeedsApproval
from crewcut.compute.session import Session

EP = "001-test"


def accept(card_id: int) -> None:
    db.update("cards", card_id, status="accepted", decided_at=db.now())


@pytest.fixture
def clips(studio):
    """Two picture-only shot clips in render/matte/ and a raw original; ffprobe is faked (no sound in the clips)."""
    md = studio / "episodes" / EP / "render" / "matte"
    md.mkdir(parents=True)
    out = {}
    for name in ("s03", "s04"):
        p = md / f"{name}.mp4"
        p.write_bytes(f"picture of shot {name}".encode())
        out[name] = p
    orig = studio / "episodes" / EP / "originals" / "take.mp4"
    orig.parent.mkdir(parents=True)
    orig.write_bytes(b"camera original with sound")
    out["original"] = orig
    privacy.use_probe(lambda argv: (0, "video\n" if "render/matte" in argv[-1] else "video\naudio\n"))
    yield out
    privacy.use_probe(None)


def picture(*paths) -> dict:
    return {"files": [{"shot": p.stem, "file": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                       "seconds": 4.2} for p in paths]}


def matte_session(pic: dict, cap_usd: float = 1.0):
    return session_fn(episode=EP, step="edit", purpose="graphics behind the speaker", cap_usd=cap_usd, monitor=False,
                      picture=pic, blender=False).open()


def test_the_card_says_the_picture_goes_up_and_only_named_files_go(fake, fssh, clips):
    s = matte_session(picture(clips["s03"]))
    with pytest.raises(NeedsApproval) as e:
        s.rent(gpus=1, gpu="RTX 4090")
    card = approvals.get(e.value.card_id)
    assert ("The picture of shot s03, 4.2 s, without sound, goes to the rented machine to separate the speaker from "
            "the background; it is deleted with the machine. Nothing else from the recording goes up.") in card["body"]
    assert "Only code and fonts" not in card["body"]
    assert card["data"]["picture"]["files"][0]["sha256"] == picture(clips["s03"])["files"][0]["sha256"]
    assert not fake.instances, "nothing is rented before the yes"
    assert s.picture_ok() == frozenset(), "no yes yet: no picture may go up"
    accept(card["id"])

    (m,) = s.rent(gpus=1, gpu="RTX 4090")
    setup = [c[-1] for c in fssh.calls if c[0] == "ssh" and "crewcut-setup.sh" in c[-1]]
    assert setup and setup[0].endswith("--blender none"), "the matting job needs no Blender"
    assert m.put([clips["s03"]], "/work/matte/in/") == 1
    assert any(str(clips["s03"]) in src for src, _ in fssh.uploads)
    with pytest.raises(Refused, match="does not name this exact file"):
        m.put([clips["s04"]], "/work/matte/in/")
    with pytest.raises(Refused, match="render/matte"):
        m.put([clips["original"]], "/work/matte/in/")
    s.close()
    assert not fake.by_label(s.label), "leaving the session deletes the machine and the picture on it"
    assert s.picture_ok() == frozenset(), "a closed session sends nothing"


def test_inside_an_approved_budget_the_picture_still_needs_its_own_yes(fake, fssh, clips):
    budget = approvals.propose(EP, "edit", "spend", "Rent a GPU", data={"amount_usd": 1.0, "budget_usd": 5.0})
    accept(budget["id"])
    before = approvals.budget_for(EP)
    s = matte_session(picture(clips["s03"], clips["s04"]))
    with pytest.raises(NeedsApproval) as e:
        s.rent(gpus=1)
    card = approvals.get(e.value.card_id)
    assert card["title"] == "Send the picture of 2 shots to a rented GPU"
    assert "The picture of 2 shots (s03, s04), 8.4 s, without sound" in card["body"]
    assert card["data"]["budget_usd"] == 0.0
    accept(card["id"])
    assert approvals.budget_for(EP) == before, "the picture card adds no money"
    (m,) = s.rent(gpus=1)
    assert m.put([clips["s03"], clips["s04"]], "/work/matte/in/") == 2
    s.close()


def test_a_card_for_other_files_or_a_session_without_picture_sends_nothing(fake, fssh, clips):
    other = approvals.propose(EP, "edit", "spend", "Earlier matte run", data={
        "amount_usd": 1.0, "budget_usd": 5.0, "picture": picture(clips["s04"])})
    accept(other["id"])
    s = matte_session(picture(clips["s03"]))
    with pytest.raises(NeedsApproval) as e:
        s.rent(gpus=1)
    assert e.value.card_id != other["id"], "a yes for another shot is not a yes for this one"
    silent = approvals.propose(EP, "edit", "spend", "Rent a GPU", body="Rent one GPU.", data={
        "amount_usd": 1.0, "budget_usd": 0.0, "picture": {**picture(clips["s03"]), "sentence": "The picture ..."}})
    accept(silent["id"])
    assert s._picture_card() is None, "a card that does not say it in plain words is no yes for the picture"
    db.update("cards", e.value.card_id, status="declined", decided_at=db.now())
    s.close()

    plain = session_fn(episode=EP, step="edit", purpose="3D scenes", cap_usd=1.0, monitor=False).open()
    (m,) = plain.rent(gpus=1)           # inside the budget of the earlier card
    with pytest.raises(Refused, match="never go to marketplace GPUs"):
        m.put([clips["s04"]], "/work/")
    plain.close()


def test_the_picture_rule_survives_attach_and_needs_an_episode(fake, fssh, clips):
    s = matte_session(picture(clips["s03"]))
    with pytest.raises(NeedsApproval) as e:
        s.rent(gpus=1)
    accept(e.value.card_id)
    s.rent(gpus=1)
    again = Session.attach(s.id)
    assert again.picture == s.picture and again.blender is False
    assert again.picture_ok() == s.picture_ok() != frozenset()
    s.close()
    lone = session_fn(episode=None, purpose="x", cap_usd=1.0, monitor=False, picture=picture(clips["s03"])).open()
    with pytest.raises(Refused, match="inside an episode"):
        lone.rent(gpus=1)
    with pytest.raises(ValueError):
        session_fn(episode=EP, purpose="x", cap_usd=1.0, monitor=False, picture={"files": [{"shot": "s03"}]})
