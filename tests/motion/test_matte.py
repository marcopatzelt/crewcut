"""Graphics behind the speaker: the edge gate on synthetic head-and-shoulders pictures, the decision, the privacy
exception, the remote commands, the composite graph and the rented flow with a fake compute session.

No real footage and no model: every picture here is drawn with numpy (a head with a soft, noisy hair edge and shoulders
that run out of the bottom of the frame, on a light wall)."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from crewcut.compute import privacy
from crewcut.compute.errors import NeedsApproval, Refused
from crewcut.motion import matte, matte_cli

FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")
needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="ffmpeg is not installed")
EP = "001-test"

# ---- synthetic pictures --------------------------------------------------------------------------------------------
W, H = 240, 180
WALL = (0.88, 0.88, 0.86)
WHITE = (0.97, 0.97, 0.97)
HAIR = (0.15, 0.10, 0.08)
SKIN = (0.80, 0.62, 0.52)
SHIRT = (0.20, 0.30, 0.55)
FACE = (96, 40, 48, 58)        # x, y, w, h of the face box


def _smooth_noise(rng, n, scale):
    k = np.hanning(2 * scale + 1)
    return np.convolve(rng.normal(size=n + 2 * scale), k / k.sum(), mode="same")[scale:scale + n]


def person(width=W + 8, height=H, seed=1):
    """Signed distance to the person (negative inside), the person's colours, and the hair weight."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:height, 0:width].astype(np.float64)
    cx, cy, rx, ry = 120.0, 64.0, 30.0, 38.0
    dx = x - cx
    ang = np.degrees(np.arctan2(y - cy, dx))
    bump = (_smooth_noise(rng, 360, 6) * 9.0)[((ang + 360) % 360).astype(int)] * (y < cy)   # uneven hair outline
    d_head = (np.sqrt((dx / rx) ** 2 + ((y - cy) / ry) ** 2) - 1) * min(rx, ry) - bump
    d_neck = np.maximum.reduce([np.abs(dx) - (11 + 0.12 * (y - 92)), 92 - y, y - 132])
    d_top = (116 + 0.008 * dx ** 2 - y) / np.sqrt(1 + (0.016 * dx) ** 2)     # sloping shoulders
    d_side = (np.abs(dx) - (78 + (y - 140) * 0.5)) / np.sqrt(1.25)
    d_body = np.maximum(d_top, d_side)                                       # runs out of the bottom of the frame
    d = np.minimum.reduce([d_head, d_neck, d_body])
    hair = np.clip((cy - 6 - y) / 10, 0, 1) * (d_head <= np.minimum(d_neck, d_body))
    col = np.empty((height, width, 3))
    col[:] = SHIRT
    head_like = (d_head <= d_body) | (d_neck <= d_body)
    col[head_like] = SKIN
    col[head_like & (y < cy - 8)] = HAIR
    return d, col, hair


def alpha_from(d, hair, rng, ramp=1.6, hair_ramp=5.0, strands=0.18):
    """A soft matte: about 1.6 px ramp on skin and clothes, a wide noisy ramp (strands) in the hair."""
    a_body = np.clip(0.5 - d / ramp, 0, 1)
    a_hair = np.clip(0.5 - d / hair_ramp + strands * rng.normal(size=d.shape) * (np.abs(d) < hair_ramp), 0, 1)
    return a_hair * hair + a_body * (1 - hair)


def scene(kind="good", frames=4, moving=True, seed=1):
    """Pictures and mattes. good: a correct soft matte; halo: grown 3 px over a white wall; hard: binary;
    cutout: ends in a straight line 20 px above the bottom; flicker: every other frame 2.5 px smaller, picture still."""
    rng = np.random.default_rng(seed)
    d, col, hair = person(seed=seed)
    a_true = alpha_from(d, hair, np.random.default_rng(seed + 1))
    bg = np.array(WHITE if kind == "halo" else WALL) * np.linspace(0.97, 1.0, d.shape[1])[None, :, None]
    pic = a_true[..., None] * col + (1 - a_true[..., None]) * bg
    a = a_true
    if kind == "halo":
        a = alpha_from(d - 3.0, hair, np.random.default_rng(seed + 1))
    elif kind == "hard":
        a = (a_true >= 0.5).astype(np.float64)
    elif kind == "cutout":
        a = a_true.copy()
        a[H - 20:] = 0.0
    imgs, alphas = [], []
    for k in range(frames):
        off = k if moving and kind != "flicker" else 0
        img = pic[:, off:off + W] + rng.normal(scale=0.004, size=(H, W, 3))
        ak = a[:, off:off + W]
        if kind == "flicker" and k % 2:
            ak = alpha_from(d + 2.5, hair, np.random.default_rng(seed + 1 + k))[:, :W]
        imgs.append(np.clip(img, 0, 1))
        alphas.append(np.clip(ak, 0, 1))
    return imgs, alphas


def write_case(root: Path, kind: str, frames=4, moving=True, sixteen_bit=False) -> tuple[Path, Path]:
    """frames/000000.png ... (the picture) and pha/0000.png ... (the matte, as RVM names it)."""
    imgs, alphas = scene(kind, frames, moving)
    fd, ad = root / kind / "frames", root / kind / "pha"
    fd.mkdir(parents=True)
    ad.mkdir(parents=True)
    for k, (img, a) in enumerate(zip(imgs, alphas, strict=True)):
        Image.fromarray((img * 255 + 0.5).astype(np.uint8)).save(fd / f"{k:06d}.png")
        if sixteen_bit:
            Image.fromarray((a * 65535 + 0.5).astype(np.uint16)).save(ad / f"{k:04d}.png")
        else:
            Image.fromarray((a * 255 + 0.5).astype(np.uint8), "L").save(ad / f"{k:04d}.png")
    return fd, ad


def failed(r: dict) -> set[str]:
    return {k for k, c in r["checks"].items() if not c["passed"]}


# ---- 3. the gate ---------------------------------------------------------------------------------------------------
def test_gate_passes_a_good_soft_matte_on_a_moving_speaker(tmp_path):
    fd, ad = write_case(tmp_path, "good", frames=4, moving=True)
    r = matte.edge_check(fd, ad, tmp_path / "out", FACE, every=2)
    assert r["passed"], r["reasons"]
    assert r["frames_checked"] == 2 and len(r["pairs"]) == 2
    c = r["checks"]
    assert c["halo"]["worst"] <= 0.02 and c["hard_edge"]["worst"] < 0.05 and c["hard_edge"]["worst_hair"] < 0.05
    assert c["flicker"]["mean"] < 0.01, "a matte that follows the picture does not flicker"
    assert all(p["motion"] > 0.02 for p in r["pairs"]), "the picture really moved"
    assert not c["frame_edges"]["border_gaps"] and 0.2 < c["coverage"]["min"] < 0.35
    assert matte.decide(r) == "behind"


@pytest.mark.parametrize("kind, check, words", [
    ("halo", "halo", "bright rim"),
    ("hard", "hard_edge", "binary"),
    ("cutout", "frame_edges", "before the bottom edge"),
    ("flicker", "flicker", "where the picture stands still"),
])
def test_gate_fails_each_defect_with_the_right_reason(tmp_path, kind, check, words):
    fd, ad = write_case(tmp_path, kind, frames=4, moving=False)
    r = matte.edge_check(fd, ad, tmp_path / "out", FACE, every=2)
    assert not r["passed"]
    assert failed(r) == {check}, r["reasons"]
    assert any(words in x for x in r["reasons"]), r["reasons"]
    d = matte.decide(r)
    assert d == "beside" and words in d.reason
    assert d.side == "right", "the face sits in the middle; then the graphic goes right"


def test_gate_numbers_for_each_defect(tmp_path):
    """The numbers behind the reasons, so a change to the gate shows up here."""
    out = {}
    for kind in ("halo", "hard", "cutout"):
        fd, ad = write_case(tmp_path, kind, frames=2, moving=False)
        out[kind] = matte.edge_check(fd, ad, tmp_path / f"out-{kind}", FACE, every=2)["checks"]
    assert out["halo"]["halo"]["worst"] > 0.3, "a matte grown over a white wall: most of the rim is old background"
    assert out["hard"]["hard_edge"]["worst"] == 1.0 and out["hard"]["hard_edge"]["worst_hair"] == 1.0
    fe = out["cutout"]["frame_edges"]
    assert fe["border_gaps"][0][1:] == ["bottom", 20]
    assert fe["straight_h_px"] > 100 > fe["limit_h_px"]


def test_hard_edge_without_a_face_box_finds_the_hair_from_the_top(tmp_path):
    fd, ad = write_case(tmp_path, "hard", frames=2, moving=False)
    r = matte.edge_check(fd, ad, tmp_path / "out", None, every=2)
    assert "hard_edge" in failed(r) and r["checks"]["hard_edge"]["worst_hair"] == 1.0
    fd2, ad2 = write_case(tmp_path / "g", "good", frames=2, moving=False)
    assert matte.edge_check(fd2, ad2, tmp_path / "out2", None, every=2)["passed"]


def test_gate_writes_crops_at_200_percent_and_a_sheet(tmp_path):
    fd, ad = write_case(tmp_path, "good", frames=2, moving=False)
    out = tmp_path / "out"
    r = matte.edge_check(fd, ad, out, FACE, every=2)
    saved = json.loads((out / "edge-check.json").read_text())
    assert saved["passed"] is True and saved["thresholds"]["halo_share"] == matte.THRESHOLDS["halo_share"]
    for key in ("halo", "halo_dark", "halo_colour", "hard_share", "hard_share_hair", "straight_h_px", "straight_v_px",
                "coverage", "border_gaps"):
        assert key in saved["frames"][0], key
    assert {"flicker", "still_px", "motion", "ratio"} <= set(saved["pairs"][0])
    assert sorted(r["crops"]) == sorted(f"{n}-{g}" for n in ("hair", "left", "right") for g in ("grey", "colour"))
    side = r["boxes"]["hair"][2]
    for p in r["crops"].values():
        with Image.open(p) as im:
            assert im.size == (2 * side, 2 * side)
            px = np.asarray(im)
        assert (px[0::2, 0::2] == px[1::2, 1::2]).all(), "nearest neighbour: every source pixel is a 2x2 block"
    with Image.open(r["sheet"]) as sheet:
        assert sheet.size[0] > 6 * side and Path(r["sheet"]).name == "edges-200.jpg"
    hx, hy, _, _ = r["boxes"]["hair"]
    assert hy < FACE[1] and FACE[0] - side < hx < FACE[0] + FACE[2], "the hair crop sits on the top of the head"
    assert r["boxes"]["left"][0] < FACE[0] < FACE[0] + FACE[2] < r["boxes"]["right"][0]


def test_gate_reads_16_bit_alpha(tmp_path):
    fd, ad = write_case(tmp_path, "good", frames=2, moving=False, sixteen_bit=True)
    with Image.open(next(ad.glob("*.png"))) as im:
        assert im.mode.startswith("I")
    assert matte.edge_check(fd, ad, tmp_path / "out", FACE, every=2)["passed"]


def test_size_mismatch_empty_and_full_mattes_fail(tmp_path):
    fd, ad = write_case(tmp_path, "good", frames=2, moving=False)
    Image.new("L", (W // 2, H // 2), 255).save(ad / "0000.png")
    r = matte.edge_check(fd, ad, tmp_path / "o1", FACE, every=2)
    assert not r["passed"] and "size" in r["reasons"][0]
    for value, word in ((0, "an empty"), (255, "a full-frame")):
        Image.new("L", (W, H), value).save(ad / "0000.png")
        r = matte.edge_check(fd, ad, tmp_path / f"o{value}", FACE, every=2)
        assert "coverage" in failed(r) and word in r["checks"]["coverage"]["reason"]
    empty = tmp_path / "none"
    empty.mkdir()
    r = matte.edge_check(fd, empty, tmp_path / "o3", FACE)
    assert not r["passed"] and "no frames" in r["reasons"][0]


def test_thresholds_have_a_comment_each():
    src = Path(matte.__file__).read_text()
    block = src[src.index("THRESHOLDS: dict = {"):src.index("}\nDARK_GROUND")]
    keys = re.findall(r'^\s+"(\w+)":', block, re.M)
    assert keys == list(matte.THRESHOLDS)
    for line in block.splitlines()[1:]:
        if re.match(r'^\s+"\w+":', line):
            assert "#" in line, line


# ---- 5. the decision -----------------------------------------------------------------------------------------------
def test_decision_records_the_reason_and_the_free_side(tmp_path):
    ok = matte.decide({"passed": True})
    assert ok == "behind" and isinstance(ok, str) and ok.side is None
    check = {"passed": False, "reasons": ["halo: 40% ...", "temporal flicker: ..."], "size": [1920, 1080],
             "face": [1100, 200, 300, 380], "checks": {"halo": {"passed": False, "worst": 0.4, "reason": "x"}}}
    d = matte.decide(check)
    assert d == "beside" and d.side == "left" and d.reason == "halo: 40% ...; temporal flicker: ..."
    assert matte.decide({"passed": False, "size": [1920, 1080], "person_x": 500.0}).side == "right"
    rec = matte.write_decision(tmp_path / "s03", check)
    saved = json.loads((tmp_path / "s03" / "decision.json").read_text())
    assert saved == rec and saved["place"] == "beside" and saved["checks"]["halo"] == {"passed": False, "worst": 0.4}


# ---- 1. export -----------------------------------------------------------------------------------------------------
class FakeMedia:
    """Plays ffmpeg and ffprobe: records argv, writes the output file, answers probes with `streams`."""

    def __init__(self, streams=("video",)):
        self.calls: list[list[str]] = []
        self.streams = list(streams)
        self.frames: dict[str, Path] = {}       # shot id -> numbered picture PNGs (what "decoding" the clip gives)
        self.total = 0

    def __call__(self, cmd, timeout=600, cwd=None):
        cmd = [str(c) for c in cmd]
        self.calls.append(cmd)
        if "-show_entries" in cmd:
            st = [{"codec_type": t, "width": W, "height": H, "r_frame_rate": "25/1", "nb_frames": "40"}
                  if t == "video" else {"codec_type": t} for t in self.streams]
            return 0, json.dumps({"streams": st})
        out = Path(cmd[-1])
        if "%" in out.name:          # frame extraction: 0, 1, N, N+1, ...
            every = int(re.search(r"mod\(n\\,(\d+)\)", " ".join(cmd)).group(1))
            frames = self.frames[Path(cmd[cmd.index("-i") + 1]).stem]
            for k in range(self.total):
                if k % every in (0, 1):
                    src = frames / f"{k:06d}.png"
                    shutil.copy(src, out.parent / f"{len(list(out.parent.glob('*.png'))) + 1:06d}.png")
            return 0, ""
        out.write_bytes(b"\0fake mp4 " + " ".join(cmd).encode())
        return 0, ""


def test_export_cuts_picture_only_with_margin(studio):
    ep = studio / "episodes" / EP
    run = FakeMedia()
    clip = matte.export_shot(Path("/rec/take.mov"), 12.0, 16.5, ep / "render" / "matte" / "s03.mp4", run, fps=25)
    assert clip == ep / "render" / "matte" / "s03.mp4" and clip.is_file()
    cmd = run.calls[0]
    assert cmd[cmd.index("-ss") + 1] == "11.520" and cmd[cmd.index("-t") + 1] == "5.460", "12 whole frames each side"
    assert {"-an", "-sn", "-dn"} <= set(cmd) and cmd[cmd.index("-map") + 1] == "0:v:0"
    assert cmd[cmd.index("-crf") + 1] == "10" and cmd[cmd.index("-map_metadata") + 1] == "-1"
    assert cmd[cmd.index("-vf") + 1] == "fps=25"
    meta = matte.read_meta(clip)
    assert meta["clip_start_s"] == 11.52 and meta["start_s"] == 12.0 and meta["width"] == W
    assert round((meta["start_s"] - meta["clip_start_s"]) * 25, 6) == 12
    first = matte.export_shot(Path("/rec/take.mov"), 0.2, 1.0, ep / "render" / "matte" / "s01.mp4", run)
    assert matte.read_meta(first)["clip_start_s"] == 0.0, "the margin stops at the start of the recording"


def test_export_refuses_wrong_places_spans_and_sound(studio):
    ep = studio / "episodes" / EP
    for bad in (ep / "render" / "s03.mp4", ep / "broll" / "matte" / "s03.mp4", ep / "render" / "matte" / "s03.mov",
                ep / "render" / "matte" / "a b.mp4"):
        with pytest.raises(ValueError):
            matte.export_shot(Path("/rec/take.mov"), 1, 2, bad, FakeMedia())
    with pytest.raises(ValueError):
        matte.export_shot(Path("/rec/take.mov"), 5, 4, ep / "render" / "matte" / "s03.mp4", FakeMedia())
    with pytest.raises(ValueError, match="longer"):
        matte.export_shot(Path("/rec/take.mov"), 0, 500, ep / "render" / "matte" / "s03.mp4", FakeMedia())
    with pytest.raises(matte.MatteError, match="not picture-only"):
        matte.export_shot(Path("/rec/take.mov"), 1, 2, ep / "render" / "matte" / "s03.mp4",
                          FakeMedia(("video", "audio")))
    assert not list((ep / "render" / "matte").glob("*.mp4")), "nothing with sound is kept"


# ---- the privacy exception -----------------------------------------------------------------------------------------
def fake_probe(streams_by_name: dict[str, list[str]]):
    def probe(argv):
        return 0, "\n".join(streams_by_name.get(Path(argv[-1]).name, ["video", "audio"])) + "\n"
    return probe


@pytest.fixture
def probe_fake():
    yield lambda m: privacy.use_probe(fake_probe(m))
    privacy.use_probe(None)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_privacy_allows_only_the_named_picture_only_clip(studio, probe_fake):
    md = studio / "episodes" / EP / "render" / "matte"
    md.mkdir(parents=True)
    clip = md / "s03.mp4"
    clip.write_bytes(b"picture of shot s03")
    with_sound = md / "s04.mp4"
    with_sound.write_bytes(b"picture and sound of shot s04")
    elsewhere = studio / "episodes" / EP / "render" / "other" / "s03.mp4"
    elsewhere.parent.mkdir(parents=True)
    elsewhere.write_bytes(clip.read_bytes())
    original = studio / "episodes" / EP / "originals" / "take.mp4"
    original.parent.mkdir(parents=True)
    original.write_bytes(clip.read_bytes())      # even the same bytes: an original never goes up
    probe_fake({"s03.mp4": ["video"], "s04.mp4": ["video", "audio"], "take.mp4": ["video"]})
    allowed = {sha(clip), sha(with_sound), sha(original)}

    assert privacy.check_upload([clip], allowed) == 1                      # allowed clip passes
    with pytest.raises(Refused, match="audio"):
        privacy.check_upload([with_sound], allowed)                        # the same kind of clip with sound
    with pytest.raises(Refused, match="render/matte"):
        privacy.check_upload([elsewhere], allowed)                         # outside render/matte/
    with pytest.raises(Refused, match="render/matte"):
        privacy.check_upload([original], allowed)                          # a raw original, inside the session
    with pytest.raises(Refused, match="never go to marketplace GPUs"):
        privacy.check_upload([clip])                                       # no session card: no picture at all
    with pytest.raises(Refused, match="does not name this exact file"):
        privacy.check_upload([clip], {"0" * 64})
    wav = md / "s03.wav"
    wav.write_bytes(b"RIFF")
    probe_fake({"s03.wav": ["audio"]})
    with pytest.raises(Refused):
        privacy.check_upload([wav], {sha(wav)})


@needs_ffmpeg
def test_privacy_with_real_clips_cut_by_export(studio):
    src = studio / "take.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=64x48:r=25:d=2", "-f",
                    "lavfi", "-i", "sine=f=440:d=2", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(src)],
                   check=True)
    md = studio / "episodes" / EP / "render" / "matte"
    clip = matte.export_shot(src, 0.6, 1.2, md / "s03.mp4", fps=25)
    assert privacy.stream_types(clip) == ["video"], "export drops the sound"
    assert privacy.check_upload([clip], {sha(clip)}) == 1
    noisy = md / "s04.mp4"
    shutil.copy(src, noisy)
    assert privacy.stream_types(noisy) == ["video", "audio"]
    with pytest.raises(Refused, match="audio"):
        privacy.check_upload([noisy], {sha(noisy)})
    info = matte.probe(clip)
    assert info["types"] == ["video"] and (info["width"], info["height"]) == (64, 48)
    assert info["frames"] in (39, 40, 41), "0.6 s + 0.5 s margin each side at 25 fps"


# ---- 2. the remote commands ----------------------------------------------------------------------------------------
def script(cmd: str) -> str:
    parts = shlex.split(cmd)
    assert parts[:2] == ["bash", "-c"] and len(parts) == 3
    return parts[2]


def test_remote_commands_pin_rvm_and_run_it_as_a_separate_program():
    c = matte.remote_commands([{"id": "s03", "ratio": 0.25}, {"id": "s07", "ratio": 0.375}])
    setup = script(c["setup"])
    assert f"git clone -q {matte.RVM_REPO}" in setup and f"checkout -q --detach {matte.RVM_COMMIT}" in setup
    assert re.fullmatch(r"[0-9a-f]{40}", matte.RVM_COMMIT) and re.fullmatch(r"[0-9a-f]{64}", matte.RVM_CHECKPOINT_SHA256)
    assert matte.RVM_CHECKPOINT_URL in setup and f"{matte.RVM_CHECKPOINT_SHA256}  " in setup and "sha256sum -c" in setup
    assert "--index-url https://download.pytorch.org/whl/cu124 torch==2.5.1 torchvision==0.20.1" in setup
    assert "torch.cuda.is_available()" in setup and setup.rstrip().endswith("echo MATTE_SETUP_OK")
    run = script(c["matte"]["s07"])
    flags = dict(re.findall(r"--([a-z-]+) (\S+)", run.split("inference.py", 1)[1]))
    assert flags["variant"] == "resnet50" and flags["checkpoint"] == "/opt/rvm/rvm_resnet50.pth"
    assert flags["device"] == "cuda" and flags["input-source"] == '"$F"' and flags["downsample-ratio"] == "0.375"
    assert flags["output-type"] == "png_sequence" and flags["seq-chunk"] == "12"
    assert flags["output-alpha"] == '"$O/pha"' and flags["output-foreground"] == '"$O/fgr"'
    assert "/opt/rvm/venv/bin/python inference.py" in run, "RVM's own script, in its own Python, on the machine"
    assert "trap 'rm -rf \"$F\" \"$IN\"' EXIT" in run, "the picture is deleted there right after use"
    assert "IN=/work/matte/in/s07.mp4" in run and 'echo "MATTE_OK s07 $N"' in run
    assert script(c["clean"]["s03"]).strip() == "rm -rf /work/matte/out/s03 /work/matte/in/s03.mp4 /work/matte/frames/s03"
    assert script(c["wipe"]).strip() == "rm -rf /work/matte"
    for cmd in [c["setup"], c["wipe"], *c["matte"].values(), *c["clean"].values()]:
        assert subprocess.run(["bash", "-n", "-c", script(cmd)], capture_output=True).returncode == 0
        assert not re.search(r"(?i)api[_-]?key|token|secret|password", script(cmd))


def test_remote_commands_refuse_unsafe_ids_and_ratios():
    for bad in ("a b", "x;rm -rf /", "../up", "-n", ""):
        with pytest.raises(ValueError):
            matte.remote_commands([{"id": bad, "ratio": 0.25}])
    with pytest.raises(ValueError):
        matte.remote_commands([{"id": "s1", "ratio": 1.5}])


def test_downsample_ratio_follows_rvm_portrait_guide():
    assert matte.downsample_ratio(1920, 1080) == 0.4
    assert matte.downsample_ratio(1080, 1920) == 0.4
    assert matte.downsample_ratio(1280, 720) == 0.6
    assert matte.downsample_ratio(3840, 2160) == 0.2
    assert matte.downsample_ratio(400, 300) == 1.0


# ---- 4. the composite ----------------------------------------------------------------------------------------------
def test_composite_graph_order_and_exact_size():
    g = matte.composite_graph(matte.Place(1920, 1080), 25)
    steps = g.split(";")
    assert steps[0].startswith("[0:v]") and steps[0].endswith("[spk]")
    assert "[spk][gfx]overlay=0:0" in g, "the graphic goes over the speaker picture"
    assert "[fg][al]alphamerge[person]" in g
    assert g.index("[spk][gfx]overlay") < g.index("[mid][person]overlay=0:0"), "the person goes over the graphic"
    chains = re.findall(r"scale=(\d+:\d+):flags=\w+", g)
    assert chains == ["1920:1080"] * 3, "speaker, foreground and alpha get the same size: never shrunk"
    assert "[3:v]setpts=PTS-STARTPTS,format=gray," in g and g.endswith("format=yuv420p[v]")


def test_composite_graph_with_a_crop_and_a_placed_speaker():
    place = matte.Place(1080, 960, x=0, y=960, crop=(1215, 1080, 352, 0), canvas=(1080, 1920))
    g = matte.composite_graph(place, 30)
    assert g.count("crop=1215:1080:352:0,scale=1080:960") == 3
    assert "color=c=black:s=1080x1920:r=30[bg]" in g and "[bg][spk]overlay=0:960" in g
    assert "[mid][person]overlay=0:960" in g, "the person sits exactly where the speaker sits"
    with pytest.raises(ValueError, match="proportions"):
        matte.Place(1080, 960, crop=(1000, 1080, 0, 0)).chain()
    with pytest.raises(ValueError, match="canvas"):
        matte.composite_graph(matte.Place(1920, 1080, x=10), 25)


def test_composite_args_line_up_the_matte_frames(tmp_path):
    argv = matte.composite_args(Path("speaker.mp4"), Path("word.mov"), tmp_path / "s03", start_s=12.0, end_s=14.0,
                                clip_start_s=11.5, fps=30, place=matte.Place(1920, 1080), out=tmp_path / "o.mp4")
    i = [k for k, v in enumerate(argv) if v == "-i"]
    assert [argv[k + 1] for k in i] == ["speaker.mp4", "word.mov", str(tmp_path / "s03" / "fgr" / "%04d.png"),
                                        str(tmp_path / "s03" / "pha" / "%04d.png")]
    assert argv[argv.index("-ss") + 1] == "12.000" and argv[argv.index("-t") + 1] == "2.000"
    assert [argv[k + 1] for k, v in enumerate(argv) if v == "-start_number"] == ["15", "15"], "0.5 s at 30 fps"
    assert "-an" in argv and argv[argv.index("-filter_complex") + 1] == matte.composite_graph(matte.Place(1920, 1080), 30)
    still = matte.composite_args(Path("s.mp4"), Path("word.png"), tmp_path, start_s=1, end_s=2, clip_start_s=0.5,
                                 fps=25, place=matte.Place(64, 48), out=tmp_path / "o.mp4")
    assert still[still.index("word.png") - 5:still.index("word.png")] == ["-loop", "1", "-framerate", "25", "-i"]
    with pytest.raises(ValueError):
        matte.composite_args(Path("s.mp4"), Path("w.mov"), tmp_path, start_s=1, end_s=2, clip_start_s=1.5, fps=25,
                             place=matte.Place(64, 48), out=tmp_path / "o.mp4")


@needs_ffmpeg
def test_composite_runs_in_ffmpeg_and_keeps_the_person_in_front(tmp_path):
    """A tiny real run: a grey speaker picture, a red graphic over the whole frame, a white 'person' square with alpha.
    The square must stay white (in front), the rest red (the graphic over the speaker)."""
    w, h, fps = 64, 48, 25
    speaker = tmp_path / "speaker.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s={w}x{h}:r={fps}:d=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(speaker)], check=True)
    graphic = tmp_path / "word.png"
    Image.new("RGBA", (w, h), (255, 0, 0, 255)).save(graphic)
    md = tmp_path / "s03"
    (md / "fgr").mkdir(parents=True)
    (md / "pha").mkdir()
    a = np.zeros((h, w), np.uint8)
    a[12:36, 20:44] = 255
    for k in range(50):
        Image.new("RGB", (w, h), (255, 255, 255)).save(md / "fgr" / f"{k:04d}.png")
        Image.fromarray(a, "L").save(md / "pha" / f"{k:04d}.png")
    out = tmp_path / "out.mp4"
    argv = matte.composite_args(speaker, graphic, md, start_s=0.5, end_s=1.0, clip_start_s=0.0, fps=fps,
                                place=matte.Place(w, h), out=out)
    r = subprocess.run(argv, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    frame = tmp_path / "f.png"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(out), "-frames:v", "1", str(frame)], check=True)
    px = np.asarray(Image.open(frame).convert("RGB")).astype(int)
    assert (px[24, 32] > 220).all(), "the person is in front of the graphic"
    assert px[4, 4, 0] > 200 and px[4, 4, 1] < 60, "the graphic covers the speaker picture around the person"
    assert matte.probe(out)["types"] == ["video"]


# ---- 2. the rented flow with a fake compute session ----------------------------------------------------------------
class FakeMachine:
    def __init__(self, case_dir: Path, fail_shot: str | None = None):
        self.case_dir, self.fail_shot = case_dir, fail_shot
        self.puts, self.runs, self.gets = [], [], []

    def put(self, paths, dest):
        self.puts.append(([Path(p) for p in paths], dest))

    def run(self, cmd, timeout=600, doing=None):
        self.runs.append((cmd, doing))
        if "MATTE_SETUP_OK" in cmd:
            return 0, "torch 2.5.1 cuda 12.4 NVIDIA GeForce RTX 4090\nrvm: imports ok\nMATTE_SETUP_OK\n"
        m = re.search(r'echo "MATTE_OK (\S+) \$N"', script(cmd))
        if m:
            sid = m.group(1)
            if sid == self.fail_shot:
                return 1, "RuntimeError: CUDA out of memory"
            return 0, f"MATTE_OK {sid} {len(list((self.case_dir / sid / 'pha').glob('*.png')))}\n"
        return 0, ""

    def get(self, remote, local):
        sid = remote.rstrip("/").rsplit("/", 1)[1]
        self.gets.append((remote, Path(local)))
        for sub in ("pha", "fgr"):
            shutil.copytree(self.case_dir / sid / sub, Path(local) / sub, dirs_exist_ok=True)
        return {"files": 0}


class FakeCompute:
    NeedsApproval = NeedsApproval
    Refused = Refused

    def __init__(self, machine=None, block=None):
        self.machine, self.block = machine, block
        self.sessions: list[dict] = []

    def session(self, **kw):
        compute = self

        class S:
            closed = False

            def __enter__(self):
                compute.sessions.append({"kw": kw, "s": self})
                return self

            def rent(self, gpus=1, max_minutes=None, **kw2):
                self.rented = {"gpus": gpus, "max_minutes": max_minutes, **kw2}
                if compute.block:
                    raise compute.block
                return [compute.machine]

            def __exit__(self, *exc):
                self.closed = True       # the machine is deleted here
                return False
        return S()


def rented_case(studio: Path, kinds: dict[str, str]) -> tuple[list[matte.Shot], Path, FakeMedia]:
    """Shots with clips in render/matte/, and what the 'machine' will return for each (alpha + foreground)."""
    ep = studio / "episodes" / EP
    remote = studio / "remote"
    media_fake = FakeMedia()
    shots = []
    for sid, kind in kinds.items():
        clip = ep / "render" / "matte" / f"{sid}.mp4"
        clip.parent.mkdir(parents=True, exist_ok=True)
        clip.write_bytes(f"picture of {sid}".encode())
        matte.meta_path(clip).write_text(json.dumps({"seconds": 0.16, "fps": 25, "start_s": 0.0, "end_s": 0.16}))
        fd, ad = write_case(remote / "src", kind, frames=4, moving=kind == "good")
        (remote / sid).mkdir(parents=True)
        shutil.copytree(ad, remote / sid / "pha")
        shutil.copytree(fd, remote / sid / "fgr")
        media_fake.frames[sid], media_fake.total = fd, 4
        shots.append(matte.Shot(sid, ep, face=FACE))
    return shots, remote, media_fake


def test_rented_flow_mattes_fetches_checks_and_decides(studio):
    shots, remote, media_fake = rented_case(studio, {"s03": "good"})
    compute = FakeCompute(FakeMachine(remote))
    lines: list[str] = []
    (res,) = matte.matte_rented(shots, compute, cap_usd=1.0, log=lines.append, runner=media_fake, every=2)
    kw = compute.sessions[0]["kw"]
    s = compute.sessions[0]["s"]
    assert kw["episode"] == EP and kw["cap_usd"] == 1.0 and kw["blender"] is False
    files = kw["picture"]["files"]
    assert files == [{"shot": "s03", "file": str(shots[0].clip), "sha256": sha(shots[0].clip), "seconds": 0.16}]
    assert s.rented == {"gpus": 1, "max_minutes": 45, "gpu": "RTX 4090"} and s.closed
    m = compute.machine
    assert m.puts == [([shots[0].clip], "/work/matte/in/")]
    assert [d for _, d in m.runs] == ["installing the matting model", "matting shot s03", "deleting shot s03 there",
                                      "deleting the work folder"]
    assert m.gets == [("/work/matte/out/s03/", shots[0].out_dir)]
    assert res.ok and res.frames == 4 and res.decision["place"] == "behind"
    assert (shots[0].out_dir / "decision.json").is_file()
    assert (shots[0].out_dir / "check" / "edges-200.jpg").is_file()
    assert not (shots[0].out_dir / "frames").exists(), "the decoded frames are removed after the check"
    assert any("released" in x for x in lines)


def test_rented_flow_falls_back_beside_and_records_why(studio):
    shots, remote, media_fake = rented_case(studio, {"s03": "halo", "s04": "good"})
    compute = FakeCompute(FakeMachine(remote, fail_shot="s04"))
    res = matte.matte_rented(shots, compute, cap_usd=1.0, log=lambda *_: None, runner=media_fake, every=2)
    assert [r.ok for r in res] == [True, False]
    assert res[0].decision["place"] == "beside" and "halo" in res[0].decision["reason"]
    assert res[0].decision["side"] == "right"
    assert res[1].decision["place"] == "beside" and "CUDA out of memory" in res[1].decision["reason"]
    saved = json.loads((shots[0].out_dir / "decision.json").read_text())
    assert saved["place"] == "beside" and saved["checks"]["halo"]["passed"] is False


def test_rented_flow_waits_for_the_card_and_cli_exits_3(studio, monkeypatch, capsys):
    shots, remote, media_fake = rented_case(studio, {"s03": "good"})
    compute = FakeCompute(FakeMachine(remote), block=NeedsApproval(7))
    with pytest.raises(NeedsApproval):
        matte.matte_rented(shots, compute, cap_usd=1.0, runner=media_fake, log=lambda *_: None)
    assert compute.sessions[0]["s"].closed and not compute.machine.puts
    monkeypatch.setattr(matte_cli, "load_compute", lambda: compute)
    monkeypatch.setattr(matte, "probe", lambda p, runner=None: {"types": ["video"], "width": W, "height": H,
                                                                "fps": 25.0, "frames": 4})
    code = matte_cli.main(["run", "--episode", EP, "--shots", "s03", "--cap", "1", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 3 and out["card"] == 7 and out["exit"] == 3
    compute.block = Refused("the month cap is reached")
    assert matte_cli.main(["run", "--episode", EP, "--shots", "s03", "--cap", "1"]) == 3
    assert matte_cli.main(["run", "--episode", EP, "--shots", "nope", "--cap", "1"]) == 1
    assert matte_cli.main(["run", "--episode", EP, "--shots", "s03"]) == 2, "--cap is required"


def test_cli_check_with_folders_prints_the_decision(tmp_path, capsys):
    fd, ad = write_case(tmp_path, "cutout", frames=2, moving=False)
    code = matte_cli.main(["check", "--frames", str(fd), "--alpha", str(ad), "--out", str(tmp_path / "o"),
                           "--face", ",".join(map(str, FACE)), "--every", "2", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["passed"] is False and out["decision"]["place"] == "beside"
    assert "bottom edge" in out["decision"]["reason"] and (tmp_path / "o" / "decision.json").is_file()
    assert matte_cli.main(["check", "--frames", str(fd)]) == 1
    assert matte_cli.main(["check", "--frames", str(fd), "--alpha", str(ad), "--out", str(tmp_path / "p"),
                           "--face", "1,2"]) == 1


def test_prepare_cuts_again_when_the_span_changed(studio):
    ep = studio / "episodes" / EP
    run = FakeMedia()
    shot = matte.Shot("s03", ep, Path("/rec/take.mov"), 12.0, 16.5, fps=25)
    first = matte.prepare(shot, run)
    n = len(run.calls)
    assert matte.prepare(shot, run)["sha256"] == first["sha256"] and len(run.calls) == n + 1, "reused: one probe only"
    moved = matte.Shot("s03", ep, Path("/rec/take.mov"), 13.0, 16.5, fps=25)
    matte.prepare(moved, run)
    assert any("-ss" in c and c[c.index("-ss") + 1] == "12.520" for c in run.calls[n + 1:]), "the new span is cut"
    assert first["ratio"] == 1.0 and first["seconds"] == 5.46
    with pytest.raises(matte.MatteError, match="not picture-only"):
        matte.prepare(matte.Shot("s03", ep), FakeMedia(("video", "audio")))
    with pytest.raises(matte.MatteError, match="no source"):
        matte.prepare(matte.Shot("s09", ep), run)
