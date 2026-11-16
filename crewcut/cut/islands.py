"""Speech islands: the pieces of speech between pauses, each with its text. Cut edges come from here.

Recognizer word times over a whole take drift by up to seconds; level pauses are exact. So: detect pauses on the
microphone channel, cut the take into speech islands, and choose cut points only at island edges or at measured level
dips. Two ways to get the text of each island:

- fast: words of a whole-file transcription (`crewcut transcribe`) are placed into the islands (`--words`).
  Trap: whole-file recognition leaves out whole sentences. Islands over 1 s without words are listed as gaps;
  `--fill` reads exactly those one by one.
- exact: every island is read on its own (slow on a CPU: 250 islands took over half an hour on the author's laptop).

Files: work/raw/<stem>-16k.wav (microphone channel, 16 kHz mono), work/raw/<stem>-silence.txt (pause list),
work/<stem>-islands.json.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

from . import audio, media
from .common import CutError, cut_settings, inside, read_json, rel, write_replace
from .transcribe import SAMPLE_RATE, mic_channel_of

MIN_ISLAND = 0.25      # shorter pieces are clicks and breaths
GAP_MIN = 1.0          # an island this long without words is a gap of the fast way
EDGE_PAD = 0.05        # read a little silence around each island


def raw_paths(ep_dir: Path, source: str) -> tuple[str, Path, Path]:
    stem = Path(source).stem
    raw = ep_dir / "work" / "raw"
    return stem, raw / f"{stem}-16k.wav", raw / f"{stem}-silence.txt"


def islands_path(ep_dir: Path, source: str) -> Path:
    return ep_dir / "work" / f"{Path(source).stem}-islands.json"


def extract_cmd(src: Path, wav: Path, channel: int | None) -> list:
    argv = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(src), "-vn"]
    if channel is not None:
        argv += ["-af", f"pan=mono|c0=c{int(channel)}"]
    return argv + ["-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(wav)]


def wav_duration(wav: Path) -> float:
    with wave.open(str(wav), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def read_wav(wav: Path):
    """Samples as float32 in -1..1 and the sample rate (16-bit PCM WAV, mono)."""
    import numpy as np
    with wave.open(str(wav), "rb") as w:
        if w.getsampwidth() != 2:
            raise CutError(f"{wav.name}: expected 16-bit PCM")
        rate, ch = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, rate


def prepare(ep_dir: Path, source: str, channel: int | None = None, settings: dict | None = None,
            ) -> tuple[Path, list[tuple[float, float]], int | None]:
    """16 kHz mono of the microphone channel plus the pause list. Reused when present."""
    src = inside(ep_dir, source)
    if not src.is_file():
        raise CutError(f"source not found in the episode: {source}")
    s = settings or cut_settings()
    _, wav, sil = raw_paths(ep_dir, source)
    wav.parent.mkdir(parents=True, exist_ok=True)
    if not wav.exists():
        if channel is None:
            channel = mic_channel_of(src)
        tmp = wav.with_name(f".{wav.name}")
        media.run(extract_cmd(src, tmp, channel))
        tmp.replace(wav)
    if not sil.exists():
        text = media.run(audio.silencedetect_cmd(wav, s["silence_db"], s["silence_min"]), check=False).stderr
        write_replace(sil, audio.format_silences(audio.parse_silences(text, wav_duration(wav))))
    return wav, audio.read_silences(sil.read_text()), channel


def speech_pieces(silences: list[tuple[float, float]], duration: float, start: float = 0.0, end: float = 1e9,
                  min_len: float = MIN_ISLAND) -> list[tuple[float, float]]:
    """The speech between pauses, inside [start, end]."""
    edges, prev = [], 0.0
    for a, b in silences:
        edges.append((prev, a))
        prev = b
    edges.append((prev, duration))
    return [(round(a, 3), round(b, 3)) for a, b in edges if b - a >= min_len and a >= start and b <= end]


def assign_words(pieces: list[tuple[float, float]], words: list[dict], slack: float = 0.3) -> tuple[list[dict], int]:
    """Place each word into the island that holds its middle (or the nearest one within slack seconds).

    Returns (rows, number of words that fit no island).
    """
    texts: list[list[str]] = [[] for _ in pieces]
    lost = 0
    for w in words:
        mid = (float(w["s"]) + float(w["e"])) / 2
        best, dist = None, slack
        for i, (a, b) in enumerate(pieces):
            d = 0.0 if a <= mid <= b else min(abs(mid - a), abs(mid - b))
            if d <= dist:
                best, dist = i, d
                if d == 0.0:
                    break
        if best is None:
            lost += 1
        else:
            texts[best].append(str(w["w"]).strip())
    rows = [{"start": a, "end": b, "text": " ".join(t), "source": "words"} for (a, b), t in zip(pieces, texts,
                                                                                                strict=True)]
    return rows, lost


def gaps(rows: list[dict], min_len: float = GAP_MIN) -> list[dict]:
    """Islands of real length without any words: the fast way left out what was said there."""
    return [r for r in rows if not r["text"].strip() and r["end"] - r["start"] >= min_len]


def rms_series(x, rate: int, start: float, end: float, step: float = 0.02) -> list[tuple[float, float]]:
    """Level every 20 ms between start and end: (time, dB)."""
    import numpy as np
    n = max(1, int(round(step * rate)))
    out = []
    i0, i1 = max(0, int(start * rate)), min(len(x), int(end * rate))
    for i in range(i0, i1, n):
        seg = x[i:i + n]
        if len(seg) == 0:
            break
        rms = float(np.sqrt(np.mean(np.square(seg, dtype=np.float64))))
        out.append((round(i / rate, 3), round(20 * np.log10(rms + 1e-9), 1)))
    return out


def usable_dips(series: list[tuple[float, float]], below: float = -40.0, min_len: float = 0.06,
                step: float = 0.02) -> list[dict]:
    """Runs of the level under `below` dB lasting at least min_len: places where a cut inside an island works."""
    out, run = [], []
    for t, db in series + [(None, 0.0)]:
        if t is not None and db < below:
            run.append((t, db))
            continue
        if run and (run[-1][0] - run[0][0] + step) >= min_len - 1e-9:
            out.append({"start": run[0][0], "end": round(run[-1][0] + step, 3), "min_db": min(d for _, d in run)})
        run = []
    return out


def merge_rows(old: list[dict], new: list[dict], start: float, end: float) -> list[dict]:
    """Replace the rows inside [start, end] and keep the others (partial runs with --from/--to)."""
    kept = [r for r in old if r["end"] <= start or r["start"] >= end]
    return sorted(kept + new, key=lambda r: r["start"])


def read_pieces(engine, x, rate: int, pieces: list[tuple[float, float]], pad: float = EDGE_PAD) -> list[str]:
    out = []
    for a, b in pieces:
        out.append(engine.text(x[max(0, int((a - pad) * rate)):int((b + pad) * rate)]))
    return out


def build(ep_dir: Path, source: str, start: float = 0.0, end: float = 1e9, channel: int | None = None,
          words_file: Path | None = None, fill: bool = False, engine_factory=None) -> dict:
    """Write work/<stem>-islands.json. engine_factory() returns a transcribe.Engine (loaded only when needed)."""
    wav, sil, channel = prepare(ep_dir, source, channel)
    pieces = speech_pieces(sil, wav_duration(wav), start, end)
    lost = 0
    if words_file:
        words = read_json(words_file)
        rows, lost = assign_words(pieces, words)
    else:
        rows = [{"start": a, "end": b, "text": "", "source": "island"} for a, b in pieces]
    todo = [i for i, r in enumerate(rows) if r["source"] == "island"
            or (fill and not r["text"].strip() and r["end"] - r["start"] >= GAP_MIN)]
    if todo:
        if engine_factory is None:
            raise CutError("reading islands needs the speech model")
        engine = engine_factory()
        x, rate = read_wav(wav)
        texts = read_pieces(engine, x, rate, [(rows[i]["start"], rows[i]["end"]) for i in todo])
        for i, t in zip(todo, texts, strict=True):
            rows[i] = {**rows[i], "text": t, "source": "island"}
    out_path = islands_path(ep_dir, source)
    old = load_rows(out_path) if out_path.exists() else []
    if old and (start > 0 or end < 1e9):
        rows = merge_rows(old, rows, start, end)
    data = {"source": source, "channel": channel, "words": rel(ep_dir, words_file) if words_file else None,
            "silence": rel(ep_dir, raw_paths(ep_dir, source)[2]), "islands": rows}
    write_replace(out_path, json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    return {"islands": rel(ep_dir, out_path), "rows": rows, "gaps": gaps(rows), "unplaced_words": lost,
            "read_one_by_one": len(todo)}


def load(ep_dir: Path, source: str) -> list[dict]:
    p = islands_path(ep_dir, source)
    if not p.exists():
        raise CutError(f"no islands for {source} yet: run crewcut cut islands {ep_dir.name} {source}")
    return load_rows(p)


def load_rows(p: Path) -> list[dict]:
    """The rows of an islands file ({"islands": [...]}; a plain list is read too)."""
    data = read_json(p)
    return data.get("islands", []) if isinstance(data, dict) else data
