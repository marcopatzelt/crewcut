"""Estimate maths and the rules for the rent suggestion and the referral link."""

from __future__ import annotations

import json
import math

import pytest

from crewcut.compute import cli, local, settings, state, vast
from crewcut.compute.estimate import estimate, fmt_duration, local_is_fine

INTERFACE_KEYS = {"kind", "frames", "local_seconds", "local_measured", "rented_seconds", "rented_usd",
                  "rented_usd_worst", "gpus", "price_per_hour", "suggest_rent", "sentence", "referral"}


def test_estimate_without_key_uses_config_numbers(studio):
    e = estimate("blender", 840)
    assert INTERFACE_KEYS <= set(e)
    k = settings.kind("blender")
    assert e["local_seconds"] == pytest.approx(840 * k["local_sec_per_frame"])
    assert e["local_measured"] is False
    overhead = settings.num("estimate.overhead_minutes") * 60
    target = settings.num("estimate.target_minutes") * 60 - overhead
    gpus = min(int(settings.num("limits.max_gpus")), math.ceil(840 * k["gpu_sec_per_frame"] / target))
    assert e["gpus"] == gpus
    per = math.ceil(840 / gpus)
    assert e["rented_seconds"] == pytest.approx(per * k["gpu_sec_per_frame"] + overhead)
    price = settings.num("estimate.price_per_hour")
    assert e["price_per_hour"] == pytest.approx(price)
    assert e["price_source"] == "config"
    assert e["rented_usd"] == pytest.approx(gpus * price * e["rented_seconds"] / 3600, abs=0.01)
    worst_s = per * k["gpu_sec_per_frame_worst"] + overhead
    assert e["rented_usd_worst"] == pytest.approx(gpus * price * worst_s / 3600, abs=0.01)
    assert e["suggest_rent"] is True
    assert e["referral"] == {"url": settings.get("vast_referral"), "note": vast.REFERRAL_NOTE}
    assert "840 frames" in e["sentence"] and "not measured on this machine yet" in e["sentence"]
    assert f"{gpus} rented GPUs" in e["sentence"]


def test_explicit_numbers_and_gpus(studio):
    e = estimate("blender", 100, local_sec_per_frame=10, gpus=2, gpu_sec_per_frame=5)
    assert e["local_measured"] is True
    assert e["local_seconds"] == 1000
    assert e["rented_seconds"] == pytest.approx(50 * 5 + settings.num("estimate.overhead_minutes") * 60)
    assert e["gpus"] == 2


def test_measured_probe_replaces_default(studio):
    local.record("blender", 90)
    local.record("blender", 110)
    local.record("blender", 100)
    e = estimate("blender", 840)
    assert e["local_measured"] is True
    assert e["local_seconds"] == pytest.approx(840 * 100)


def test_measured_rented_probe_is_used(studio):
    local.record("blender", 30, where="rented", gpu="RTX 4090")
    e = estimate("blender", 80, gpus=1)
    assert e["gpu_sec_per_frame"] == 30


def test_small_job_is_not_suggested(studio):
    e = estimate("blender", 10, gpus=1)  # 24 min here vs about 16 min rented: saves less than 15 min
    assert e["suggest_rent"] is False
    assert e["referral"] is None
    assert "saves only" in e["reason"]


def test_not_faster_enough_is_not_suggested(studio):
    # a local GPU as fast as one rented GPU: renting one is not faster
    e = estimate("blender", 2000, local_sec_per_frame=45, gpus=1)
    assert e["suggest_rent"] is False
    assert e["reason"] == "renting is not faster"


def test_own_gpu_works_locally(studio, monkeypatch):
    monkeypatch.setenv("CREWCUT_LOCAL_GPU", "1")
    e = estimate("blender", 840)
    assert e["suggest_rent"] is False and e["referral"] is None
    assert "own GPU" in e["reason"]
    assert e["local_seconds"] == pytest.approx(840 * settings.kind("blender")["gpu_sec_per_frame"])


def test_suggestion_once_per_job(studio):
    first = estimate("blender", 840, job=17)
    second = estimate("blender", 840, job=17)
    other = estimate("blender", 840, job=18)
    assert first["suggest_rent"] is True
    assert second["suggest_rent"] is False and "already" in second["reason"]
    assert second["referral"] is None
    assert other["suggest_rent"] is True


def test_job_from_environment(studio, monkeypatch):
    monkeypatch.setenv("CREWCUT_JOB", "41")
    assert estimate("blender", 840)["suggest_rent"] is True
    assert estimate("blender", 840)["suggest_rent"] is False


def test_local_is_fine_silences_the_episode(studio):
    local_is_fine("001-a")
    e = estimate("blender", 840, episode="001-a", job=1)
    assert e["suggest_rent"] is False and "local is fine" in e["reason"]
    assert estimate("blender", 840, episode="002-b", job=2)["suggest_rent"] is True
    assert not state.was_suggested(1)


def test_no_referral_when_user_has_a_key(fake):
    e = estimate("blender", 840)
    assert e["suggest_rent"] is True
    assert e["referral"] is None
    assert e["price_source"] == "live offers"
    # one offer per host IP (the cheaper of the two on host-1.test), preferred GPU first, then price; never more
    # GPUs than offers
    assert e["gpus"] == 4
    assert e["price_per_hour"] == pytest.approx((0.39 + 0.42 + 0.45 + 0.50) / 4, abs=1e-4)
    assert estimate("blender", 840, gpus=6)["price_per_hour"] == pytest.approx((0.39 + 0.42 + 0.45 + 0.50 * 3) / 6,
                                                                              abs=1e-4)


def test_empty_referral_link_means_no_link(studio, studio_config):
    studio_config("compute", 'vast_referral = ""\n')
    e = estimate("blender", 840)
    assert e["suggest_rent"] is True
    assert e["referral"] is None


def test_unknown_kind_needs_numbers(studio):
    with pytest.raises(ValueError):
        estimate("music", 60)
    e = estimate("music", 60, local_sec_per_frame=20, gpu_sec_per_frame=2, gpus=1)
    assert e["local_seconds"] == 1200


def test_cli_estimate_json_and_local_fine(studio, capsys):
    assert cli.main(["estimate", "--kind", "blender", "--frames", "840", "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert INTERFACE_KEYS <= set(d)
    assert cli.main(["estimate", "--frames", "840", "--episode", "003-x", "--local-fine", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["suggest_rent"] is False
    assert cli.main(["estimate", "--frames", "840", "--local-fine"]) == 1
    assert cli.main(["estimate"]) == 2


def test_fmt_duration():
    assert fmt_duration(30) == "about 30 s"
    assert fmt_duration(25 * 60) == "about 25 min"
    assert fmt_duration(3 * 3600) == "about 3 h"
    assert fmt_duration(3.4 * 3600) == "about 3.4 h"
    assert fmt_duration(34 * 3600) == "about 34 h"
    assert fmt_duration(72 * 3600) == "about 3 days"
