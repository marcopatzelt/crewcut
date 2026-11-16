"""Portrait capture: scroll keys, the terminal transcript and its page, the browser and ffmpeg argument lists, versions
and the info file. The browser part is always a fake (no Chromium here); the colour range check runs the real ffmpeg on
three tiny frames, and the terminal page's script runs in jsdom (no browser, no layout)."""

import functools
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from crewcut import paths
from crewcut.render import capture, cli, media
from crewcut.render.capture import CaptureError

FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")
NODE = shutil.which("node")
JSDOM = paths.app_root() / "web" / "node_modules" / "jsdom"


class FakeBrowser:
    """Stands in for node + Chromium: writes the PNG frames the script would write. ffmpeg is faked too (it writes
    the output file), unless real_ffmpeg."""

    def __init__(self, real_ffmpeg=False, fail=False, short=0, png=None):
        self.calls: list[list[str]] = []
        self.real_ffmpeg, self.fail, self.short, self.png = real_ffmpeg, fail, short, png

    def __call__(self, cmd, timeout=600, cwd=None):
        cmd = [str(c) for c in cmd]
        self.calls.append(cmd)
        if any(c.endswith("capture_page.js") for c in cmd):
            if self.fail:
                return 1, "Page not loaded: https://example.com/ (net::ERR_NAME_NOT_RESOLVED)"
            out = Path(cmd[3])
            out.mkdir(parents=True, exist_ok=True)
            for i in range(int(cmd[cmd.index("--frames") + 1]) - self.short):
                if self.png:
                    self.png(out / f"{i:04d}.png")
                else:
                    (out / f"{i:04d}.png").write_bytes(b"png")
            return 0, "some log\n" + json.dumps({"title": "Docs", "warnings": ["Console error: x"]}) + "\n"
        if Path(cmd[0]).name.startswith("ffmpeg"):
            if self.real_ffmpeg:
                return media.run(cmd, timeout=timeout)
            Path(cmd[-1]).write_bytes(b"video")
            return 0, ""
        return 0, ""

    def browser_calls(self):
        return [c for c in self.calls if any(x.endswith("capture_page.js") for x in c)]


def test_scroll_keys():
    assert capture.parse_scroll("0:0, 1.5:0, 6:end, 8:40%", 8) == [[0.0, 0], [1.5, 0], [6.0, "end"], [8.0, "40%"]]
    assert capture.parse_scroll('[[0, 0], [3, "end"]]', 3) == [[0.0, 0], [3.0, "end"]]
    assert capture.parse_scroll(None, 5) == [] and capture.parse_scroll("", 5) == []
    for bad in ("0:0,3:1,2:5", "0:top", "x:0", "0:-5", "0:0,9:end", "[[0]]", "[oops"):
        with pytest.raises(CaptureError):
            capture.parse_scroll(bad, 8)


def test_transcript_timing_and_format():
    text = ("$ npm test\n\x1b[32mPASS\x1b[0m 12 tests\n[+1.5] Done in 2.1 s\n\\$ not a command\n"
            "[+0] $ ls\n\tsrc\n\n\n")
    lines = capture.parse_transcript(text, line_delay=0.5, type_cps=10)
    assert [(x.kind, x.text) for x in lines] == [("cmd", "npm test"), ("out", "PASS 12 tests"),
                                                 ("out", "Done in 2.1 s"), ("out", "$ not a command"),
                                                 ("cmd", "ls"), ("out", "    src")]
    assert (lines[0].at, lines[0].done) == (0.5, 1.3)          # 8 characters at 10 per second
    assert (lines[1].at, lines[2].at, lines[3].at) == (1.8, 3.3, 3.8)
    assert (lines[4].at, lines[4].done, lines[5].at) == (3.8, 4.0, 4.5)
    with pytest.raises(CaptureError, match="empty"):
        capture.parse_transcript("\n\n")
    with pytest.raises(CaptureError):
        capture.parse_transcript("x", type_cps=0)


def test_page_and_encode_commands(tmp_path):
    cmd = capture.page_cmd("https://example.com/", tmp_path / "f", 75, 25, "stage", 2.5, [[0, 0], [3, "end"]], 1.0,
                           hide_overlays=True)
    assert cmd[1].endswith("tools/capture_page.js") and cmd[2] == "https://example.com/" and cmd[3] == str(tmp_path / "f")
    opts = dict(zip(cmd[4::2], cmd[5::2], strict=False))
    assert opts["--frames"] == "75" and opts["--fps"] == "25" and opts["--zoom"] == "2.5" and opts["--wait"] == "1"
    assert (opts["--width"], opts["--height"]) == ("1080", "960")
    assert json.loads(cmd[cmd.index("--scroll") + 1]) == [[0, 0], [3, "end"]]
    assert "--hide-overlays" in cmd and "--strict" not in cmd
    enc = capture.encode_cmd(tmp_path / "f", tmp_path / "o.mp4", 25, (1080, 1920))
    vf = enc[enc.index("-vf") + 1]
    # one explicit conversion: RGB -> BT.709 limited range, then yuv420p, frames tagged
    assert vf.startswith("scale=1080:1920:force_original_aspect_ratio=increase:")
    assert "out_color_matrix=bt709:out_range=tv,crop=1080:1920,format=yuv420p" in vf
    assert vf.endswith("setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709")
    for k, v in (("-color_range", "tv"), ("-colorspace", "bt709"), ("-color_primaries", "bt709"), ("-color_trc", "bt709")):
        assert enc[enc.index(k) + 1] == v
    assert enc[enc.index("-i") + 1] == str(tmp_path / "f" / "%04d.png") and enc[-1] == str(tmp_path / "o.mp4")
    assert capture.frame_count(1.02, 25) == 26 and capture.frame_count(3, 25) == 75


def test_capture_url_versions_and_info(episode):
    ep = episode.dir
    run = FakeBrowser()
    logs = []
    info = capture.capture(ep, url="https://example.com/docs/start", seconds=3, scroll="0:0,1:0,3:end",
                           hide_overlays=True, runner=run, log=logs.append)
    out = ep / "broll" / "example-com-docs-start-v001.mp4"
    assert info["output"] == str(out) and out.read_bytes() == b"video"
    side = json.loads(out.with_suffix(".json").read_text())
    assert side["source"] == {"kind": "url", "url": "https://example.com/docs/start"}
    assert side["frames"] == 75 and side["fps"] == 25 and side["size"] == "1080x1920" and side["zoom"] == 2.5
    assert side["scroll"] == [[0.0, 0], [1.0, 0], [3.0, "end"]] and side["page"]["title"] == "Docs"
    assert "limited (tv) range" in side["colour"] and side["captured_at"].endswith("Z")
    assert not (ep / "render" / "capture" / "example-com-docs-start-v001").exists()     # frames removed
    assert any("Console error" in x for x in logs)
    page, enc = run.calls
    assert page[page.index("--frames") + 1] == "75" and "--hide-overlays" in page and "--strict" not in page
    assert enc[0].endswith("ffmpeg") and enc[-1].endswith("example-com-docs-start-v001.tmp.mp4")
    again = capture.capture(ep, url="https://example.com/docs/start", seconds=1, runner=FakeBrowser(), log=print)
    assert again["output"].endswith("example-com-docs-start-v002.mp4") and out.read_bytes() == b"video"


def test_capture_html_file_stage_size(episode, tmp_path):
    page = tmp_path / "Result Page.html"
    page.write_text("<html><body>ok</body></html>")
    run = FakeBrowser()
    info = capture.capture(episode.dir, html_file=page, seconds=0.4, size="stage", fps=30, keep_frames=True,
                           runner=run, log=print)
    assert info["output"].endswith("broll/result-page-v001.mp4") and info["size"] == "1080x960" and info["frames"] == 12
    cmd = run.browser_calls()[0]
    assert cmd[2] == page.resolve().as_uri() and cmd[cmd.index("--height") + 1] == "960"
    assert Path(info["frames_dir"]).is_dir()                    # --keep-frames


def test_capture_terminal(episode, tmp_path):
    t = tmp_path / "build log.txt"
    t.write_text("$ make test\n[+1] ok 3 tests\n")
    run = FakeBrowser()
    info = capture.capture(episode.dir, terminal=t, runner=run, log=print)
    # 0.35 s, 9 characters at 20/s, 1 s, then 2 s hold
    assert info["seconds"] == round(0.35 + 9 / 20 + 1 + 2, 2) and info["frames"] == capture.frame_count(info["seconds"], 25)
    assert info["source"]["kind"] == "terminal" and info["source"]["lines"] == 2
    cmd = run.browser_calls()[0]
    page = Path(info["source"]["page"])
    assert cmd[2] == page.as_uri() and "--strict" in cmd and "--scroll" not in cmd
    html = page.read_text()
    assert "window.setFrame" in html and '"make test"' in html and "#111111" in html and "DejaVu Sans Mono" in html
    data = json.loads(html.split('id="data">', 1)[1].split("</script>", 1)[0])
    assert data["frames"] == info["frames"] and data["lines"][1]["at"] == 1.8
    # text keeps out of the right 18 % (the platform's buttons): 64 px left, ends at 82 % of 1080
    assert "left:64px" in html and f"width:{round(1080 * 0.82) - 64}px" in html
    with pytest.raises(CaptureError, match="scrolls by itself"):
        capture.capture(episode.dir, terminal=t, scroll="0:0", runner=run, log=print)


def test_capture_refusals_and_failures(episode, tmp_path):
    ep = episode.dir
    with pytest.raises(CaptureError, match="exactly one source"):
        capture.capture(ep, url="https://a.b/", html_file=tmp_path / "x.html", seconds=1, runner=FakeBrowser())
    with pytest.raises(CaptureError, match="--seconds is required"):
        capture.capture(ep, url="https://a.b/", runner=FakeBrowser())
    with pytest.raises(CaptureError, match="http"):
        capture.capture(ep, url="ftp://a.b/x", seconds=1, runner=FakeBrowser())
    with pytest.raises(CaptureError, match="not found"):
        capture.capture(ep, html_file=tmp_path / "missing.html", seconds=1, runner=FakeBrowser())
    with pytest.raises(CaptureError, match="episode not found"):
        capture.capture("999-nope", url="https://a.b/", seconds=1, runner=FakeBrowser())
    with pytest.raises(RuntimeError, match="browser part failed.*Page not loaded"):
        capture.capture(ep, url="https://example.com/", seconds=1, runner=FakeBrowser(fail=True), log=print)
    with pytest.raises(RuntimeError, match="1 of 25 frames missing"):
        capture.capture(ep, url="https://example.com/", seconds=1, runner=FakeBrowser(short=1), log=print)
    assert not list((ep / "broll").glob("*.mp4"))               # nothing half-written


def test_capture_cli(episode, monkeypatch, capsys):
    run = FakeBrowser()
    monkeypatch.setattr(capture, "capture", functools.partial(capture.capture, runner=run))
    code = cli.main(["capture", "001-test", "--url", "https://example.com/", "--seconds", "2", "--scroll", "0:0,2:50%",
                     "--size", "stage", "--name", "Home", "--json"])
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == 0 and out["exit"] == 0 and out["output"].endswith("broll/home-v001.mp4") and out["size"] == "1080x960"
    assert cli.main(["capture", "001-test"]) == 2                  # a source is required
    assert cli.main(["capture", "001-test", "--url", "https://example.com/"]) == 1     # no --seconds


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg is not installed")
def test_colour_range_white_stays_255(episode):
    from PIL import Image

    def frame(p: Path) -> None:                     # what a screenshot is: RGB, white 255
        im = Image.new("RGB", (1080, 960), (255, 255, 255))
        im.paste((0, 0, 0), (0, 480, 1080, 960))
        im.paste((228, 87, 46), (0, 0, 240, 240))
        im.save(p)

    info = capture.capture(episode.dir, url="https://example.com/", seconds=0.12, size="stage",
                           runner=FakeBrowser(real_ffmpeg=True, png=frame), log=print)
    out = info["output"]
    tags = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-show_entries",
                           "stream=width,height,pix_fmt,color_range,color_space,color_transfer,color_primaries",
                           "-of", "default=nw=1", out], capture_output=True, text=True).stdout
    for want in ("width=1080", "height=960", "pix_fmt=yuv420p", "color_range=tv", "color_space=bt709",
                 "color_transfer=bt709", "color_primaries=bt709"):
        assert want in tags
    raw = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-i", out, "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True).stdout

    def px(x, y):
        o = (y * 1080 + x) * 3
        return tuple(raw[o:o + 3])

    assert all(v >= 254 for v in px(540, 300))                  # white stays white (not 232)
    assert all(v <= 1 for v in px(540, 700))
    assert all(abs(a - b) <= 4 for a, b in zip(px(120, 120), (228, 87, 46), strict=True))


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_capture_script_parses():
    r = subprocess.run([NODE, "--check", str(paths.tools_dir() / "capture_page.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    r = subprocess.run([NODE, str(paths.tools_dir() / "capture_page.js")], capture_output=True, text=True)
    assert r.returncode == 2 and "Usage" in r.stderr                # no browser starts without arguments


DOM_RUN = r"""
const fs = require('fs');
const { JSDOM, VirtualConsole } = require('jsdom');
const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => errors.push(String(e.detail || e.message || e)));
const dom = new JSDOM(fs.readFileSync(process.argv[1], 'utf8'), { runScripts: 'dangerously', virtualConsole: vc });
const w = dom.window, rows = () => [...w.document.querySelectorAll('.l')];
const seen = {};
for (let n = 0; n < w.FRAMES; n++) {
  w.setFrame(n);
  if (n === Number(process.argv[2])) seen.mid = rows().map(r => r.style.display === 'none' ? null : r.textContent);
}
seen.end = rows().map(r => r.textContent);
console.log(JSON.stringify({ errors, frames: w.FRAMES, ...seen }));
"""


@pytest.mark.skipif(not NODE or not JSDOM.is_dir(), reason="needs node and jsdom (npm ci in web/)")
def test_terminal_page_runs_every_frame(tmp_path):
    lines = capture.parse_transcript("$ make test\n[+1] ok 3 tests\n", line_delay=0.4, type_cps=10)
    page = tmp_path / "t.html"
    page.write_text(capture.terminal_page(lines, 100, 25), encoding="utf-8")
    env = {**os.environ, "NODE_PATH": str(JSDOM.parent)}
    mid = 25                                        # 1.0 s: 6 of 9 characters typed, the output not yet shown
    r = subprocess.run([NODE, "-e", DOM_RUN, str(page), str(mid)], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["errors"] == [] and d["frames"] == 100
    assert d["mid"] == ["$ make t", None]
    assert d["end"][0] == "$ make test" and d["end"][1] == "ok 3 tests"
