"""CC0 3D assets without the network: specs, the cache, Poly Haven checksums, ambientCG zips, the allow-list of hosts,
and the plate bootstrap that gives Blender the module and the cache."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

from crewcut.render import assets3d, plate_quality, plates

ca = assets3d.lib()


@pytest.fixture
def cache(tmp_path, monkeypatch):
    d = tmp_path / "cache"
    monkeypatch.setenv("CREWCUT_ASSET_CACHE", str(d))
    return d


def fake_net(monkeypatch, files: dict[str, bytes]):
    calls = []

    def get(url, timeout=60.0):
        assert ca._host_ok(url), url
        calls.append(url)
        if url not in files:
            raise ca.AssetError(f"404 {url}")
        return files[url]
    monkeypatch.setattr(ca, "_get", get)
    return calls


def test_specs_and_resolutions():
    assert ca.parse("polyhaven:hdri/studio_small_09") == ("polyhaven", "hdri", "studio_small_09")
    assert ca.parse("ambientcg:Paper005") == ("ambientcg", "material", "Paper005")
    assert ca.resolution("2K", "polyhaven") == "2k" and ca.resolution("1k", "ambientcg") == "1K"
    for bad in ("polyhaven:studio", "polyhaven:hdri/../x", "sketchfab:x", "ambientcg:a/b", "nothing"):
        with pytest.raises(ca.AssetError):
            ca.parse(bad)
    assert not ca._host_ok("http://api.polyhaven.com/x") and not ca._host_ok("https://evil.example/x")
    assert ca._host_ok("https://dl.polyhaven.org/file/x.hdr")


def test_polyhaven_hdri_is_checked_and_cached(cache, monkeypatch):
    data = b"#?RADIANCE fake"
    url = "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/studio_small_09_1k.hdr"
    files = {"https://api.polyhaven.com/files/studio_small_09": json.dumps(
        {"hdri": {"1k": {"hdr": {"url": url, "md5": hashlib.md5(data).hexdigest(), "size": len(data)}}}}).encode(),
        url: data}
    calls = fake_net(monkeypatch, files)
    p = ca.hdri("studio_small_09", "1k")
    assert p.endswith("studio_small_09_1k.hdr") and open(p, "rb").read() == data
    rec = json.loads((cache / "polyhaven" / "hdri" / "studio_small_09_1k" / "asset.json").read_text())
    assert rec["licence"] == "CC0-1.0" and rec["source"] == "https://polyhaven.com/a/studio_small_09"
    n = len(calls)
    assert ca.hdri("studio_small_09", "1k") == p and len(calls) == n, "the cache answers the second time"
    assert [r["spec"] for r in assets3d.cached()] == ["polyhaven:hdri/studio_small_09"]


def test_a_wrong_checksum_is_refused(cache, monkeypatch):
    url = "https://dl.polyhaven.org/file/x_1k.hdr"
    fake_net(monkeypatch, {"https://api.polyhaven.com/files/x": json.dumps(
        {"hdri": {"1k": {"hdr": {"url": url, "md5": "0" * 32}}}}).encode(), url: b"data"})
    with pytest.raises(ca.AssetError, match="checksum"):
        ca.hdri("x", "1k")


def test_ambientcg_material_maps(cache, monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for m in ("Color", "Roughness", "NormalGL", "NormalDX", "Displacement"):
            z.writestr(f"Paper005_1K-JPG_{m}.jpg", m.encode())
        z.writestr("../evil.jpg", b"x")
    api = "https://ambientcg.com/api/v2/full_json?id=Paper005&include=downloadData"
    link = "https://ambientcg.com/get?file=Paper005_1K-JPG.zip"
    fake_net(monkeypatch, {api: json.dumps({"foundAssets": [{"downloadFolders": {"default": {
        "downloadFiletypeCategories": {"zip": {"downloads": [{"attribute": "1K-JPG", "downloadLink": link}]}}}}}]})
        .encode(), link: buf.getvalue()})
    maps = ca.material("Paper005", "1K")
    assert set(maps) == {"color", "roughness", "normal", "displacement"}
    assert maps["normal"].endswith("_NormalGL.jpg")
    folder = cache / "ambientcg" / "material" / "Paper005_1K"
    assert not list(folder.glob("*.zip")) and not (cache / "evil.jpg").exists()


def test_cli_fetch_and_list(cache, monkeypatch, capsys):
    from crewcut.render import cli
    monkeypatch.setattr(assets3d, "fetch", lambda spec, res="2k", fmt=None: {
        "spec": spec, "resolution": res, "paths": {"hdri": "/x.hdr"}})
    assert cli.main(["assets", "fetch", "polyhaven:hdri/a", "--res", "1k"]) == 0
    assert "polyhaven:hdri/a 1k: hdri /x.hdr" in capsys.readouterr().out
    assert cli.main(["assets", "list"]) == 0
    assert cli.main(["assets", "fetch"]) == 1


def test_plate_bootstrap_puts_the_module_on_the_path():
    code = plate_quality.bootstrap({"version": 1, "size": [160, 90], "samples": 8}, "/out", False, False,
                                   lib="/app/crewcut/render/blender_lib", cache="/studio/.crewcut/cache/assets3d")
    inner = eval(code[len("exec("):-1])                      # the bootstrap is exec(<repr of the code>)
    assert "_cc_lib = '/app/crewcut/render/blender_lib'" in inner
    assert "CREWCUT_ASSET_CACHE" in inner and "/studio/.crewcut/cache/assets3d" in inner
    cmd = plates.blender_cmd("blender", "p.py", "/out", "1-1", {}, quality={"version": 1, "size": [16, 9],
                             "samples": 1}, lib=str(assets3d.LIB_DIR), cache="/c")
    assert cmd[:3] == ["blender", "-b", "--factory-startup"] and "--python-expr" in cmd


def test_rented_plates_take_the_module_and_fetch_there():
    script = plates.remote_script(plates.Plate("m1", "gpu", assets3d.LIB_DIR / "crewcut_assets.py", {}, 4, "h",
                                               assets3d.LIB_DIR, {"version": 1, "size": [16, 9], "samples": 1}),
                                  probe=False)
    assert plates.REMOTE_LIB in script and plates.REMOTE_ASSETS in script
