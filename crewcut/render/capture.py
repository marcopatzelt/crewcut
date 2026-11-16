"""Portrait capture (`crewcut render capture`): a web page or a terminal transcript recorded as an upright video, the
proof material of a Short. The result goes into the episode's broll/ folder as `<name>-vNNN.mp4` (never overwritten),
with `<name>-vNNN.json` beside it: what was recorded, from where, when and how.

Why: a Short's screen material is recorded upright, not cut out of the landscape picture (docs/rendering.md, "Shorts").

- A page (an http(s) URL or a local HTML file): tools/capture_page.js opens it in Chromium (Playwright) with a viewport
  of 1080/zoom x 1920/zoom CSS pixels at device scale `zoom` (default 2.5: 432 x 768, a phone). The page lays out like on
  a phone and every text is 2.5 times bigger. The script scrolls along the scroll keys and takes one screenshot per
  video frame, so the motion is exactly even; the page's JavaScript clock is advanced one frame per screenshot.
- A terminal transcript (plain text): turned into a large-font page here (`terminal_page`) whose `setFrame(n)` shows
  the terminal at frame n; the same script records it. Format in `parse_transcript`.
- `--size stage` records 1080 x 960, the stage of the "proof-top" layout, instead of the full 1080 x 1920.

Colour range: screenshots are RGB, where white is 255. The encode step converts them in one explicit scale filter to
the range of every other piece of the cut: limited ("tv") range with the BT.709 matrix, yuv420p
(`scale=...:out_color_matrix=bt709:out_range=tv`), and tags frames and stream the same way (`setparams` and
`-color_range tv -colorspace bt709 -color_primaries bt709 -color_trc bt709`). Decoded, white is 255 again (a test
encodes white, black and an accent colour with the real ffmpeg and reads them back). In the author's earlier studio, browser
recordings came out as full-range yuvj420p while the speaker pieces were limited range; joined in one cut, the range
of one piece was applied to the others and white turned into 232. One explicit range for every piece prevents that.

The browser runs through `runner` like every other program here, so tests replace it and never start Chromium.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from .. import brand, paths
from . import media
from .plan import PlanError

SIZES = {"full": (1080, 1920), "stage": (1080, 960)}
ZOOM = 2.5                  # 1080 / 2.5 = 432 CSS px: phone layout, every text 2.5 times bigger
WAIT_S = 1.5                # after the page has loaded, before the first frame
HOLD_S = 2.0                # terminal: the finished terminal stays this long
LINE_DELAY_S = 0.35         # terminal: pause before a line that has no [+N] of its own
TYPE_CPS = 20.0             # terminal: characters per second of a typed command
FONT_PX = 44                # terminal: font size (at least the pack's min_text_px)
PROMPT = "$ "
COLOR_ARGS = ["-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
_DELAY = re.compile(r"^\[\+(\d+(?:\.\d+)?)\]\s?")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_KEY = re.compile(r"^(end|\d+(?:\.\d+)?%|\d+)$")


class CaptureError(PlanError):
    """The capture cannot run as asked. The message says what to change."""


# ---- names, versions, scroll keys ----------------------------------------------------------------------------------
def episode_folder(arg: str | Path) -> Path:
    """An episode id (a folder in studio/episodes) or the path of an episode folder."""
    p = Path(arg).expanduser()
    if p.is_dir():
        return p.resolve()
    try:
        d = paths.episode_dir(str(arg))
    except ValueError as e:
        raise CaptureError(f"not an episode folder or id: {arg}") from e
    if not d.is_dir():
        raise CaptureError(f"episode not found: {arg} (looked in {d.parent})")
    return d


def slug(text: str, max_len: int = 32) -> str:
    t = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()[:max_len].rstrip("-")
    return t or "capture"


def next_version(folder: Path, name: str, suffix: str) -> tuple[Path, int]:
    """The next free `<name>-vNNN<suffix>` in folder (versions are never reused)."""
    pat = re.compile(rf"^{re.escape(name)}-v(\d{{3}})\b")
    n = max((int(m.group(1)) for f in folder.glob(f"{name}-v*") if (m := pat.match(f.name))), default=0) + 1
    return folder / f"{name}-v{n:03d}{suffix}", n


def parse_scroll(spec: str | list | None, seconds: float) -> list[list]:
    """Scroll keys: "0:0,1.5:0,6:end" (second:position) or a JSON list [[0, 0], [6, "end"]].

    A position is CSS pixels from the top, "end" (the bottom of the page) or "40%" (of the scrollable height).
    Times must not go back and must lie inside the capture.
    """
    if not spec:
        return []
    if isinstance(spec, str) and spec.strip().startswith("["):
        try:
            spec = json.loads(spec)
        except ValueError as e:
            raise CaptureError(f"scroll keys are not valid JSON: {e}") from e
    raw = spec if isinstance(spec, list) else [x.split(":", 1) for x in spec.split(",") if x.strip()]
    keys: list[list] = []
    for k in raw:
        if not isinstance(k, (list, tuple)) or len(k) != 2:
            raise CaptureError(f"bad scroll key {k!r}: use second:position, e.g. 6:end")
        try:
            t = float(k[0])
        except (TypeError, ValueError) as e:
            raise CaptureError(f"bad scroll time {k[0]!r}") from e
        pos = k[1]
        if isinstance(pos, bool) or not _KEY.match(str(pos).strip()):
            raise CaptureError(f"bad scroll position {pos!r}: CSS pixels, 'end' or a share like '40%'")
        pos = str(pos).strip()
        keys.append([t, int(pos) if pos.isdigit() else pos])
    times = [k[0] for k in keys]
    if times != sorted(times) or times[0] < 0 or times[-1] > seconds + 1e-6:
        raise CaptureError(f"scroll times must rise and lie between 0 and {seconds:g} s, got {times}")
    return keys


# ---- terminal transcript -------------------------------------------------------------------------------------------
@dataclass
class Line:
    text: str
    kind: str                   # "cmd" (typed after the prompt) or "out" (printed at once)
    at: float                   # second the line starts to appear
    done: float                 # second the line is complete (a command is typed out)


def parse_transcript(text: str, line_delay: float = LINE_DELAY_S, type_cps: float = TYPE_CPS) -> list[Line]:
    """A recorded terminal as timed lines.

    Format, one terminal line per text line:
      $ npm test          a command: typed after the prompt at `type_cps` characters per second
      PASS  12 tests      output: appears at once, `line_delay` seconds after the line before
      [+1.5] Done.        waits 1.5 s instead of `line_delay` (works before commands too)
    A leading backslash keeps "$ " or "[+" as plain output. Colour codes (ANSI) are removed, tabs become spaces.
    """
    if type_cps <= 0 or line_delay < 0:
        raise CaptureError("type speed must be above 0 and the line delay at least 0")
    rows = text.replace("\r\n", "\n").split("\n")
    while rows and not rows[-1].strip():
        rows.pop()
    t, out = 0.0, []
    for raw in rows:
        s = _ANSI.sub("", raw.rstrip("\r")).expandtabs(4)
        m = _DELAY.match(s)
        delay = float(m.group(1)) if m else line_delay
        s = s[m.end():] if m else s
        if s.startswith("\\$ ") or s.startswith("\\[+"):
            kind, body = "out", s[1:]
        elif s.startswith(PROMPT):
            kind, body = "cmd", s[len(PROMPT):]
        else:
            kind, body = "out", s
        at = t + delay
        done = at + (len(body) / type_cps if kind == "cmd" else 0.0)
        out.append(Line(body, kind, round(at, 3), round(done, 3)))
        t = done
    if not out:
        raise CaptureError("the transcript is empty")
    return out


def frame_count(seconds: float, fps: int) -> int:
    """Frames of a capture: seconds x fps, halves rounded up (the browser script gets this number, not seconds)."""
    return int(seconds * fps + 0.5)


def terminal_page(lines: list[Line], frames: int, fps: int, size: str = "full", pack: brand.Pack | None = None,
                  font_px: int = FONT_PX, right_free: float | None = None) -> str:
    """A self-contained page that shows the terminal at frame n (`window.setFrame(n)`), in the pack's colours and mono
    font. Text keeps out of the right `right_free` share (the platform's buttons) and, at full size, out of the top 8 %
    and bottom 20 % (platform bars and captions)."""
    pack = pack or brand.load()
    W, H = SIZES[size]
    colors = pack.value("brand.colors", {}) or {}
    mono = pack.value("brand.fonts.mono", {}) or {}
    family = str(mono.get("family") or "DejaVu Sans Mono")
    faces = ""
    for f in mono.get("files") or []:
        p = pack.file(f)
        if p:
            faces += (f"@font-face{{font-family:{json.dumps(family)};src:url({json.dumps(p.as_uri())});"
                      f"font-weight:{int(mono.get('weight') or 400)}}}\n")
    rf = float(pack.value("edit_style.shorts.right_free_frac", 0.18) if right_free is None else right_free)
    size_px = max(int(font_px), int(pack.value("edit_style.min_text_px", 40) or 40))
    left = 64
    top, bottom = (round(H * 0.08), round(H * 0.2)) if size == "full" else (48, 48)
    width = round(W * (1 - rf)) - left
    data = {"lines": [asdict(x) for x in lines], "fps": fps, "frames": frames, "prompt": PROMPT}
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    def c(key: str, default: str) -> str:
        v = str(colors.get(key) or default)
        return v if re.match(r"^#[0-9A-Fa-f]{6}$", v) else default

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Terminal</title>
<style>
{faces}html,body{{margin:0;padding:0;width:{W}px;height:{H}px;overflow:hidden;background:{c('ink', '#111111')}}}
#screen{{position:absolute;left:{left}px;top:{top}px;width:{width}px;height:{H - top - bottom}px;overflow:hidden}}
#t{{font-family:{json.dumps(family)},monospace;font-size:{size_px}px;line-height:1.35;color:{c('paper', '#FFFFFF')};
  white-space:pre-wrap;overflow-wrap:anywhere}}
.l{{min-height:1.35em}}
.p{{color:{c('accent', '#E4572E')}}}
.c{{display:inline-block;width:0.6em;height:1.1em;vertical-align:-0.2em;background:{c('accent', '#E4572E')}}}
</style></head>
<body><div id="screen"><div id="t"></div></div>
<script type="application/json" id="data">{blob}</script>
<script>
// Crewcut terminal page: setFrame(n) shows the terminal at frame n. A pure function of n (no clock).
const D=JSON.parse(document.getElementById('data').textContent);
const screen=document.getElementById('screen'),T=document.getElementById('t');
const rows=D.lines.map(l=>{{const d=document.createElement('div');d.className='l '+l.kind;d.style.display='none';T.appendChild(d);return d;}});
window.FRAMES=D.frames;
window.setFrame=function(n){{
  const now=n/D.fps;let last=-1;
  D.lines.forEach((l,i)=>{{
    const el=rows[i];
    if(now<l.at){{el.style.display='none';return;}}
    el.style.display='block';el.textContent='';
    if(l.kind==='cmd'){{const p=document.createElement('span');p.className='p';p.textContent=D.prompt;el.appendChild(p);}}
    const n=l.text.length,k=l.done>l.at?Math.min(n,Math.floor((now-l.at)/(l.done-l.at)*n+1e-6)):n;
    el.appendChild(document.createTextNode(l.text.slice(0,k)));
    last=i;
  }});
  if(last>=0){{
    const l=D.lines[last],typing=l.kind==='cmd'&&now<l.done;
    if(typing||Math.floor(now*2)%2===0){{const c=document.createElement('span');c.className='c';rows[last].appendChild(c);}}
  }}
  screen.scrollTop=Math.max(0,T.scrollHeight-screen.clientHeight);
  return last;
}};
</script></body></html>
"""


# ---- commands ------------------------------------------------------------------------------------------------------
def page_cmd(url: str, frames_dir: Path, frames: int, fps: int, size: str = "full", zoom: float = ZOOM,
             scroll: list | None = None, wait: float = WAIT_S, hide_overlays: bool = False,
             strict: bool = False) -> list[str]:
    """The browser part: tools/capture_page.js writes <frames_dir>/0000.png ... and one JSON line."""
    W, H = SIZES[size]
    cmd = [media.node(), str(paths.tools_dir() / "capture_page.js"), url, str(frames_dir), "--frames", str(frames),
           "--fps", str(fps), "--width", str(W), "--height", str(H), "--zoom", f"{zoom:g}", "--wait", f"{wait:g}"]
    if scroll:
        cmd += ["--scroll", json.dumps(scroll)]
    if hide_overlays:
        cmd.append("--hide-overlays")
    if strict:
        cmd.append("--strict")
    return cmd


def color_filter(size: tuple[int, int]) -> str:
    """Scale to the exact size and convert RGB to limited-range BT.709 yuv420p in the same, explicit scale filter;
    setparams marks the frames so (the encoder alone left primaries and transfer unknown)."""
    W, H = size
    return (f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd+full_chroma_int:"
            f"out_color_matrix=bt709:out_range=tv,crop={W}:{H},format=yuv420p,setsar=1,"
            "setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709")


def encode_cmd(frames_dir: Path, out: Path, fps: int, size: tuple[int, int]) -> list[str]:
    return [media.ffmpeg(), "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(frames_dir / "%04d.png"),
            "-vf", color_filter(size), "-c:v", "libx264", "-crf", "14", "-preset", "slow", "-pix_fmt", "yuv420p",
            *COLOR_ARGS, "-movflags", "+faststart", str(out)]


def _last_json(text: str) -> dict:
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                d = json.loads(line)
                return d if isinstance(d, dict) else {}
            except ValueError:
                return {}
    return {}


# ---- the capture ---------------------------------------------------------------------------------------------------
def capture(episode: str | Path, *, url: str | None = None, html_file: str | Path | None = None,
            terminal: str | Path | None = None, seconds: float | None = None, size: str = "full", zoom: float = ZOOM,
            fps: int | None = None, scroll: str | list | None = None, wait: float = WAIT_S, hide_overlays: bool = False,
            name: str | None = None, keep_frames: bool = False, line_delay: float = LINE_DELAY_S,
            type_cps: float = TYPE_CPS, font_px: int = FONT_PX, pack: brand.Pack | None = None,
            runner: media.Runner = media.run, log: Callable = print) -> dict:
    """Record one page or terminal transcript into <episode>/broll/<name>-vNNN.mp4. Returns the info that is also
    written to <name>-vNNN.json."""
    if sum(x is not None for x in (url, html_file, terminal)) != 1:
        raise CaptureError("give exactly one source: --url, --html or --terminal")
    if size not in SIZES:
        raise CaptureError(f"size must be one of {', '.join(SIZES)}")
    if zoom <= 0 or wait < 0:
        raise CaptureError("zoom must be above 0 and wait at least 0")
    ep = episode_folder(episode)
    pack = pack or brand.load()
    if fps is None:
        try:
            proj = json.loads((ep / "project.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            proj = {}
        fps = int(proj.get("fps") or pack.value("edit_style.fps", 25))
    broll, work = ep / "broll", ep / "render" / "capture"
    broll.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    strict = False
    if url is not None:
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.netloc:
            raise CaptureError(f"--url must be an http(s) address, got {url!r}")
        name = slug(name or (u.netloc + u.path))
        source = {"kind": "url", "url": url}
        target = url
    elif html_file is not None:
        f = Path(html_file).expanduser().resolve()
        if not f.is_file():
            raise CaptureError(f"HTML file not found: {html_file}")
        name = slug(name or f.stem)
        source = {"kind": "html", "file": str(f)}
        target = f.as_uri()
    else:
        f = Path(terminal).expanduser().resolve()
        if not f.is_file():
            raise CaptureError(f"transcript not found: {terminal}")
        name = slug(name or f.stem)
        lines = parse_transcript(f.read_text(encoding="utf-8"), line_delay, type_cps)
        seconds = seconds if seconds is not None else round(lines[-1].done + HOLD_S, 2)
        if scroll:
            raise CaptureError("the terminal scrolls by itself; --scroll is for pages")
        source = {"kind": "terminal", "file": str(f), "lines": len(lines), "line_delay_s": line_delay,
                  "type_cps": type_cps}
        strict = True
    if seconds is None or seconds <= 0:
        raise CaptureError("--seconds is required for a page (how long to record)")
    keys = parse_scroll(scroll, seconds)
    out, version = next_version(broll, name, ".mp4")
    stem = out.with_suffix("")
    frames_dir = work / stem.name
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    n = frame_count(seconds, fps)
    if terminal is not None:
        page = work / f"{stem.name}.html"
        page.write_text(terminal_page(lines, n, fps, size, pack, font_px), encoding="utf-8")
        source["page"] = str(page)
        target = page.as_uri()
    log(f"capture {name} v{version:03d}: {n} frames at {SIZES[size][0]}x{SIZES[size][1]} from {source.get('url') or source['file']}")
    rc, text = runner(page_cmd(target, frames_dir, n, fps, size, zoom, keys, wait, hide_overlays, strict),
                      timeout=max(300, n * 3 + 120))
    missing = [i for i in range(n) if not (frames_dir / f"{i:04d}.png").is_file()]
    if rc or missing:
        why = media.tail(text, 600) if rc else f"{len(missing)} of {n} frames missing"
        raise RuntimeError(f"capture {name}: the browser part failed: {why}")
    page_info = _last_json(text)
    tmp = out.with_name(out.stem + ".tmp.mp4")
    rc, text = runner(encode_cmd(frames_dir, tmp, fps, SIZES[size]), timeout=max(600, n * 2))
    if rc:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"capture {name}: encoding failed: {media.tail(text, 600)}")
    tmp.replace(out)
    if not keep_frames:
        shutil.rmtree(frames_dir, ignore_errors=True)
    info = {
        "output": str(out), "version": version, "source": source, "seconds": seconds, "fps": fps, "frames": n,
        "size": f"{SIZES[size][0]}x{SIZES[size][1]}", "layout_size": size, "zoom": zoom, "scroll": keys,
        "wait_s": wait, "hide_overlays": hide_overlays,
        "captured_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "how": "Chromium, one screenshot per frame; page JavaScript time advanced one frame per screenshot",
        "colour": "H.264 yuv420p, BT.709, limited (tv) range, converted explicitly from the screenshots' RGB",
        "page": page_info, "frames_dir": str(frames_dir) if keep_frames else None,
    }
    for w in (page_info.get("warnings") or [])[:20]:
        log(f"page: {w}")
    stem.with_suffix(".json").write_text(json.dumps(info, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return info
