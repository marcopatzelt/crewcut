"""CC0 assets for Blender: HDRIs and textures from Poly Haven, materials from ambientCG, by their public APIs, cached.

Standard library only, so it runs inside Blender's own Python (on the rented GPU and in the Crewcut image) as well
as in Crewcut. A plate script uses it like this (the plate bootstrap puts this folder on ``sys.path``):

    import crewcut_assets as ca
    ca.world_hdri(ca.hdri("studio_small_09", "2k"), strength=0.9, rotation=200)      # light and reflections
    mat = ca.material_from(ca.material("ambientcg:Paper005", "2K"), name="paper")      # a PBR material

Specs: ``polyhaven:hdri/<id>``, ``polyhaven:tex/<id>`` (a texture set), ``ambientcg:<id>`` (a material). Resolutions:
Poly Haven ``1k`` ``2k`` ``4k`` ``8k``, ambientCG ``1K`` ``2K`` ``4K`` ``8K`` (either spelling works).

Cache: env ``CREWCUT_ASSET_CACHE``, else ``/work/assets`` when that folder exists (rented machines: setup.sh makes
it), else ``~/.cache/crewcut/assets3d``. Every file is kept with ``asset.json`` beside it: the spec, source URL,
licence (CC0 1.0), size, checksum and date. A file already in the cache is never fetched again; Poly Haven files are
checked against the MD5 the API gives, ambientCG zips must open. Only the hosts in ``HOSTS`` are contacted, with a
neutral User-Agent (Poly Haven asks for one), never with personal data.

Licences: Poly Haven https://polyhaven.com/license and ambientCG https://docs.ambientcg.com/license/ are CC0 1.0:
free, also commercially, no credit needed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

USER_AGENT = "crewcut-assets/1.0"
HOSTS = ("api.polyhaven.com", "dl.polyhaven.org", "ambientcg.com", "acg-download.struffelproductions.com")
LICENCE = "CC0-1.0"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")
_RES = re.compile(r"^([1248])[kK]$")
MAX_BYTES = 400_000_000
MAPS = {  # role -> names of the maps in Poly Haven (keys of /files) and in ambientCG zips (file name endings)
    "color": (("Diffuse", "diff"), ("_Color",)),
    "roughness": (("Rough", "rough"), ("_Roughness",)),
    "normal": (("nor_gl", "nor_gl"), ("_NormalGL",)),
    "displacement": (("Displacement", "disp"), ("_Displacement",)),
    "ao": (("AO", "ao"), ("_AmbientOcclusion",)),
    "metalness": (("Metal", "metal"), ("_Metalness",)),
}


class AssetError(RuntimeError):
    """An asset cannot be fetched or read. The message says which and why."""


# ---- names and the cache --------------------------------------------------------------------------------------------
def cache_dir() -> Path:
    env = os.environ.get("CREWCUT_ASSET_CACHE")
    if env:
        return Path(env)
    if Path("/work/assets").is_dir():
        return Path("/work/assets")
    return Path.home() / ".cache" / "crewcut" / "assets3d"


def parse(spec: str) -> tuple[str, str, str]:
    """``polyhaven:hdri/<id>`` -> ("polyhaven", "hdri", id); ``polyhaven:tex/<id>``; ``ambientcg:<id>``."""
    if not isinstance(spec, str) or ":" not in spec:
        raise AssetError(f"asset {spec!r}: write polyhaven:hdri/<id>, polyhaven:tex/<id> or ambientcg:<id>")
    src, _, rest = spec.partition(":")
    src = src.lower()
    if src == "polyhaven":
        kind, _, aid = rest.partition("/")
        if kind not in ("hdri", "tex") or not _ID.match(aid):
            raise AssetError(f"asset {spec!r}: polyhaven:hdri/<id> or polyhaven:tex/<id>")
        return src, kind, aid
    if src == "ambientcg":
        if not _ID.match(rest):
            raise AssetError(f"asset {spec!r}: ambientcg:<id>, e.g. ambientcg:Paper005")
        return src, "material", rest
    raise AssetError(f"asset {spec!r}: only polyhaven and ambientcg (both CC0)")


def resolution(res: str, src: str) -> str:
    m = _RES.match(str(res or "2k"))
    if not m:
        raise AssetError(f"resolution {res!r}: 1k, 2k, 4k or 8k")
    return f"{m.group(1)}k" if src == "polyhaven" else f"{m.group(1)}K"


def _folder(src: str, kind: str, aid: str, res: str) -> Path:
    return cache_dir() / src / kind / f"{aid}_{res}"


def _host_ok(url: str) -> bool:
    u = urllib.parse.urlparse(url)
    return u.scheme == "https" and u.hostname in HOSTS


# ---- HTTP -------------------------------------------------------------------------------------------------------------
def _get(url: str, timeout: float = 60.0) -> bytes:
    if not _host_ok(url):
        raise AssetError(f"refusing {url}: only {', '.join(HOSTS)} over https")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:      # noqa: S310 - https and allow-listed hosts
                if not _host_ok(r.geturl()):
                    raise AssetError(f"{url} redirected to {r.geturl()}, which is not allowed")
                data = r.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise AssetError(f"{url} is larger than {MAX_BYTES // 1_000_000} MB")
                return data
        except AssetError:
            raise
        except Exception as e:  # noqa: BLE001 - network: retry, then try curl (Blender's Python may lack CA files)
            last = e
            time.sleep(1.5 * (attempt + 1))
    if shutil.which("curl"):
        p = subprocess.run(["curl", "-fsSL", "--proto", "=https", "--max-time", str(int(timeout * 5)), "-A", USER_AGENT,
                            "--max-filesize", str(MAX_BYTES), url], capture_output=True)
        if p.returncode == 0:
            return p.stdout
        last = AssetError(p.stderr.decode("utf-8", "replace").strip()[-200:])
    raise AssetError(f"cannot fetch {url}: {last}")


def _json(url: str) -> dict:
    try:
        d = json.loads(_get(url, timeout=30).decode("utf-8"))
    except ValueError as e:
        raise AssetError(f"{url} gave no JSON: {e}") from e
    if not isinstance(d, dict):
        raise AssetError(f"{url} gave an unexpected answer")
    return d


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


def _record(folder: Path, info: dict) -> dict:
    info = {**info, "licence": LICENCE, "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (folder / "asset.json").write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    return info


def _cached(folder: Path) -> dict | None:
    try:
        info = json.loads((folder / "asset.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    files = info.get("files") or {}
    if files and all((folder / f).is_file() for f in files.values()):
        return info
    return None


# ---- Poly Haven -----------------------------------------------------------------------------------------------------
def _polyhaven_file(entry: dict, folder: Path) -> str:
    url, md5 = entry.get("url"), entry.get("md5")
    if not isinstance(url, str):
        raise AssetError("Poly Haven gave no file link")
    name = Path(urllib.parse.urlparse(url).path).name
    if not _ID.match(name):
        raise AssetError(f"unexpected file name {name!r}")
    data = _get(url, timeout=120)
    if md5 and hashlib.md5(data).hexdigest() != md5:                   # noqa: S324 - the API's own checksum
        raise AssetError(f"{name}: checksum does not match Poly Haven's")
    _write(folder / name, data)
    return name


def _polyhaven(kind: str, aid: str, res: str, fmt: str | None) -> dict:
    folder = _folder("polyhaven", kind, aid, res)
    have = _cached(folder)
    if have:
        return have
    files = _json(f"https://api.polyhaven.com/files/{urllib.parse.quote(aid)}")
    out: dict[str, str] = {}
    if kind == "hdri":
        by_res = (files.get("hdri") or {}).get(res) or {}
        pick = fmt or ("hdr" if "hdr" in by_res else "exr")
        entry = by_res.get(pick)
        if not isinstance(entry, dict):
            raise AssetError(f"Poly Haven has no HDRI {aid} at {res} as {pick} (has {', '.join(sorted(by_res))})")
        out["hdri"] = _polyhaven_file(entry, folder)
    else:
        pick = fmt or "jpg"
        for role, (ph, _acg) in MAPS.items():
            entry = ((files.get(ph[0]) or {}).get(res) or {}).get(pick if role != "displacement" else "png") \
                or ((files.get(ph[0]) or {}).get(res) or {}).get(pick)
            if isinstance(entry, dict):
                out[role] = _polyhaven_file(entry, folder)
        if "color" not in out:
            raise AssetError(f"Poly Haven has no texture set {aid} at {res}")
    return _record(folder, {"spec": f"polyhaven:{kind}/{aid}", "id": aid, "kind": kind, "resolution": res,
                            "source": f"https://polyhaven.com/a/{aid}", "files": out})


# ---- ambientCG --------------------------------------------------------------------------------------------------------
def _ambientcg(aid: str, res: str, fmt: str | None) -> dict:
    folder = _folder("ambientcg", "material", aid, res)
    have = _cached(folder)
    if have:
        return have
    attr = f"{res}-{(fmt or 'jpg').upper()}"
    d = _json("https://ambientcg.com/api/v2/full_json?" + urllib.parse.urlencode({"id": aid, "include": "downloadData"}))
    found = d.get("foundAssets") or []
    if not found:
        raise AssetError(f"ambientCG has no material {aid}")
    cats = (((found[0].get("downloadFolders") or {}).get("default") or {}).get("downloadFiletypeCategories") or {})
    dl = next((x for x in (cats.get("zip") or {}).get("downloads") or [] if x.get("attribute") == attr), None)
    if not dl:
        raise AssetError(f"ambientCG has no {aid} as {attr}")
    data = _get(dl["downloadLink"], timeout=300)
    folder.mkdir(parents=True, exist_ok=True)
    zpath = folder / f"{aid}_{attr}.zip"
    _write(zpath, data)
    out: dict[str, str] = {}
    try:
        with zipfile.ZipFile(zpath) as z:
            for member in z.namelist():
                base = Path(member).name
                if not base or not _ID.match(base) or member.endswith("/"):
                    continue
                for role, (_ph, acg) in MAPS.items():
                    if any(Path(base).stem.endswith(end) for end in acg) and role not in out:
                        with z.open(member) as src:
                            _write(folder / base, src.read())
                        out[role] = base
    except zipfile.BadZipFile as e:
        raise AssetError(f"ambientCG zip for {aid} is damaged: {e}") from e
    finally:
        zpath.unlink(missing_ok=True)
    if "color" not in out:
        raise AssetError(f"ambientCG {aid}: no colour map in the zip")
    return _record(folder, {"spec": f"ambientcg:{aid}", "id": aid, "kind": "material", "resolution": res,
                            "source": f"https://ambientcg.com/view?id={aid}", "files": out})


# ---- the public functions ---------------------------------------------------------------------------------------------
def fetch(spec: str, res: str = "2k", fmt: str | None = None) -> dict:
    """Fetch (or find in the cache) one asset. Returns its record with ``folder`` and absolute ``paths``."""
    src, kind, aid = parse(spec)
    r = resolution(res, src)
    info = _polyhaven(kind, aid, r, fmt) if src == "polyhaven" else _ambientcg(aid, r, fmt)
    folder = _folder(src, kind, aid, r)
    return {**info, "folder": str(folder), "paths": {k: str(folder / v) for k, v in (info.get("files") or {}).items()}}


def hdri(name: str, res: str = "2k") -> str:
    """The path of a Poly Haven HDRI (``studio_small_09``, or a full spec)."""
    spec = name if ":" in name else f"polyhaven:hdri/{name}"
    return fetch(spec, res)["paths"]["hdri"]


def material(name: str, res: str = "2K") -> dict[str, str]:
    """Map role -> path of a material (``ambientcg:Paper005``, ``polyhaven:tex/<id>``; a bare id is ambientCG)."""
    spec = name if ":" in name else f"ambientcg:{name}"
    return fetch(spec, res)["paths"]


def cached() -> list[dict]:
    """Every asset in the cache (its record)."""
    root = cache_dir()
    out = []
    if not root.is_dir():
        return out
    for f in sorted(root.glob("*/*/*/asset.json")):
        try:
            info = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({**info, "folder": str(f.parent)})
    return out


# ---- inside Blender -------------------------------------------------------------------------------------------------
def world_hdri(path: str, strength: float = 1.0, rotation: float = 0.0, scene=None):
    """Light the scene with an HDRI (environment texture with a Z rotation in degrees). Returns the world."""
    import math

    import bpy
    scene = scene or bpy.context.scene
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(rotation))
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(path, check_existing=True)
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = float(strength)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return world


def material_from(maps: dict[str, str], name: str = "crewcut-material", scale: float = 1.0, tint: str | None = None):
    """A Principled BSDF material from a map set (color, roughness, normal; displacement as bump). ``tint`` (#RRGGBB)
    multiplies the colour map, e.g. toward the brand accent. Returns the material."""
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (scale, scale, scale)
    nt.links.new(coord.outputs["UV"], mapping.inputs["Vector"])

    def tex(role: str, colour: bool):
        if role not in maps:
            return None
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(maps[role], check_existing=True)
        if not colour:
            node.image.colorspace_settings.name = "Non-Color"
        nt.links.new(mapping.outputs["Vector"], node.inputs["Vector"])
        return node

    col = tex("color", True)
    if col is not None:
        if tint:
            h = tint.lstrip("#")
            rgb = [((int(h[i:i + 2], 16) / 255) / 12.92 if int(h[i:i + 2], 16) / 255 <= 0.04045 else
                    (((int(h[i:i + 2], 16) / 255) + 0.055) / 1.055) ** 2.4) for i in (0, 2, 4)]
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs[0].default_value = 1.0
            nt.links.new(col.outputs["Color"], mix.inputs[6])
            mix.inputs[7].default_value = (*rgb, 1.0)
            nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        else:
            nt.links.new(col.outputs["Color"], bsdf.inputs["Base Color"])
    rough = tex("roughness", False)
    if rough is not None:
        nt.links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])
    nor = tex("normal", False)
    if nor is not None:
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(nor.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return mat
