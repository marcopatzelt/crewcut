"""Speech recognition with faster-whisper: words with times for a whole file, or the text of short pieces.

Two uses:
- `crewcut transcribe <file>`: every word with start and end, written as work/words-<name>.json in the edit plan's
  words format [{"w": "...", "s": 1.23, "e": 1.5}]. Fast, but on whole files the recognizer drops or invents sentences
  ("Thanks for watching"). The islands tool finds those gaps.
- `Engine.text()`: the text of one short piece (a speech island, a cut clip), read with 1 s of silence behind it,
  because the recognizer drops or invents the last word when a file ends right after speech.

Device: cuda when a GPU is visible, else the CPU with int8. On the author's laptop (CPU) reading 250 speech pieces one
by one took over half an hour; a whole-file pass is much faster. A rented GPU is optional (`--rented`): it uploads
only the audio track and only after the user said yes on a card, because the default privacy rule sends nothing but
scene code and fonts to a rented machine.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .. import approvals, config, paths
from . import audio, media
from .common import CutError, Waiting, channel_language, episode_dir, find_episode, rel, write_replace

SAMPLE_RATE = 16000
SETTINGS = {
    "model": "large-v3-turbo", "device": "auto", "compute_type_cpu": "int8", "compute_type_cuda": "float16",
    "cpu_threads": 0, "beam_size": 5, "language": "", "model_dir": "", "quiet_db": -25.0, "gain_db": 14.0,
    "rented_cap_usd": 0.5, "rented_max_minutes": 30,
}
# Phrases recognizers invent in silence or music. A hit is only a hint: listen to the place.
HALLUCINATIONS = [
    "thanks for watching", "thank you for watching", "subtitles by", "please subscribe", "amara.org",
    "untertitelung des zdf", "untertitel im auftrag des zdf", "untertitel der amara.org", "vielen dank fürs zuschauen",
    "sous-titres réalisés par", "subtítulos realizados por",
]


def settings() -> dict:
    out = dict(SETTINGS)
    out.update({k: v for k, v in (config.load("speech").get("speech") or {}).items() if v is not None})
    return out


def pick_device(requested: str = "auto", s: dict | None = None) -> tuple[str, str]:
    """(device, compute_type). auto = cuda when CTranslate2 sees a GPU, else cpu."""
    s = s or settings()
    dev = (requested or "auto").lower()
    if dev not in ("auto", "cpu", "cuda"):
        raise CutError("device must be auto, cpu or cuda")
    if dev == "auto":
        try:
            import ctranslate2
            dev = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            dev = "cpu"
    return dev, str(s["compute_type_cuda"] if dev == "cuda" else s["compute_type_cpu"])


def words_from_segments(segments, offset: float = 0.0) -> list[dict]:
    """faster-whisper segments (with .words) -> [{"w", "s", "e"}]."""
    out = []
    for seg in segments:
        for w in getattr(seg, "words", None) or []:
            text = (w.word or "").strip()
            if text:
                out.append({"w": text, "s": round(float(w.start) + offset, 2), "e": round(float(w.end) + offset, 2)})
    return out


def suspects(words: list[dict]) -> list[dict]:
    """Places where the words look invented (known phrases of silence). Each needs a listening check."""
    if not words:
        return []
    joined, starts = "", []
    for w in words:
        starts.append((len(joined), w["s"]))
        joined += re.sub(r"[^\w.' ]", "", w["w"].lower()) + " "
    out = []
    for phrase in HALLUCINATIONS:
        for m in re.finditer(re.escape(phrase), joined):
            at = max((s for pos, s in starts if pos <= m.start()), default=words[0]["s"])
            out.append({"at": at, "text": phrase})
    return sorted(out, key=lambda x: x["at"])


def words_name(src: Path) -> str:
    """work/words-<name>.json. The voice track of cut version NNN (voice-vNNN.wav) gives words-vNNN.json, the file
    the edit plan reads."""
    stem = Path(src).stem
    m = re.fullmatch(r"voice-(v\d{3,})", stem)
    if m:
        return f"words-{m.group(1)}.json"
    return f"words-{re.sub(r'-16k$', '', stem)}.json"


# ---- audio in memory ---------------------------------------------------------------------------------------------
def decode_cmd(src: Path, channel: int | None = None, start: float | None = None, end: float | None = None) -> list:
    """16 kHz mono float samples on stdout. channel picks one input channel (the microphone side)."""
    argv = ["ffmpeg", "-nostdin", "-v", "error"]
    if start:
        argv += ["-ss", f"{start:.3f}"]
    if end is not None:
        argv += ["-to", f"{end:.3f}"]
    argv += ["-i", str(src), "-vn"]
    if channel is not None:
        argv += ["-af", f"pan=mono|c0=c{int(channel)}"]
    return argv + ["-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-acodec", "pcm_f32le", "-"]


def load_audio(src: Path, channel: int | None = None, start: float | None = None, end: float | None = None):
    import numpy as np
    raw = media.run(decode_cmd(src, channel, start, end), binary=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def level_db(samples) -> float:
    import numpy as np
    if len(samples) == 0:
        return -99.0
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    return round(20 * np.log10(rms + 1e-9), 1)


def with_gain(samples, quiet_db: float, gain_db: float):
    """A very quiet recording gets gain before recognition (below about -25 dB the recognizer hears nothing)."""
    import numpy as np
    lv = level_db(samples)
    if lv >= quiet_db:
        return samples, 0.0
    return np.clip(samples * (10 ** (gain_db / 20)), -1.0, 1.0).astype(np.float32), float(gain_db)


def mic_channel_of(src: Path, info: dict | None = None) -> int | None:
    """The channel with the external microphone, when a camera recorded it on one side only."""
    info = info or media.probe(src)
    streams = media.audio_streams(info)
    if not streams or int(streams[0].get("channels") or 1) < 2:
        return None
    return audio.mic_verdict(audio.channel_levels(src, 0.0, 120.0)).get("channel")


# ---- engine ------------------------------------------------------------------------------------------------------
class Engine:
    """One loaded model, used for many pieces."""

    def __init__(self, model: str | None = None, device: str | None = None, language: str | None = None):
        self.s = settings()
        self.model_name = model or self.s["model"]
        self.device, self.compute_type = pick_device(device or self.s["device"], self.s)
        self.language = language or self.s.get("language") or channel_language()
        self._model = None

    def describe(self) -> dict:
        return {"model": self.model_name, "device": self.device, "compute_type": self.compute_type,
                "language": self.language}

    @property
    def model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise CutError("faster-whisper is not installed. In the image it is; elsewhere: "
                               "pip install 'crewcut[speech]'") from exc
            root = Path(self.s["model_dir"]) if self.s.get("model_dir") else paths.state_dir() / "models"
            root.mkdir(parents=True, exist_ok=True)
            self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type,
                                       cpu_threads=int(self.s.get("cpu_threads") or 0), download_root=str(root))
        return self._model

    def words(self, samples) -> list[dict]:
        segments, _ = self.model.transcribe(samples, language=self.language, beam_size=int(self.s["beam_size"]),
                                            word_timestamps=True, vad_filter=False)
        return words_from_segments(segments)

    def text(self, samples) -> str:
        import numpy as np
        padded = np.concatenate([samples.astype(np.float32), np.zeros(SAMPLE_RATE, dtype=np.float32)])
        segments, _ = self.model.transcribe(padded, language=self.language, beam_size=int(self.s["beam_size"]),
                                            vad_filter=False, condition_on_previous_text=False,
                                            without_timestamps=True)
        return " ".join(" ".join(s.text for s in segments).split())


# ---- the command -------------------------------------------------------------------------------------------------
def output_path(src: Path, out: str | None, episode: str | None) -> tuple[Path, Path | None]:
    """(where the words go, the episode folder or None)."""
    ep_dir = episode_dir(episode) if episode else (find_episode(src) or (None, None))[1]
    if out:
        p = Path(out)
        if not p.is_absolute():
            p = (ep_dir / p) if ep_dir else (Path.cwd() / p)
        return p.resolve(), ep_dir
    if not ep_dir:
        raise CutError("the file is not inside an episode folder: give --episode or --out")
    return ep_dir / "work" / words_name(src), ep_dir


def transcribe_local(src: Path, out: Path, engine: Engine, channel: int | None = None, force: bool = False) -> dict:
    if out.exists() and not force:
        raise CutError(f"{out.name} exists already. Use --force to read the file again, or --out for a new name.")
    info = media.probe(src)
    if not media.audio_streams(info):
        raise CutError(f"{src.name} has no sound track")
    if channel is None:
        channel = mic_channel_of(src, info)
    samples = load_audio(src, channel)
    samples, gain = with_gain(samples, float(engine.s["quiet_db"]), float(engine.s["gain_db"]))
    t0 = time.monotonic()
    words = engine.words(samples)
    took = round(time.monotonic() - t0, 1)
    if not words:
        raise CutError("no words recognized. Check the sound (crewcut cut audio <file>).")
    write_replace(out, json.dumps(words, ensure_ascii=False, indent=0) + "\n")
    return {"out": str(out), "words": len(words), "audio_seconds": round(len(samples) / SAMPLE_RATE, 1),
            "seconds_taken": took, "channel": channel, "gain_db": gain, "suspects": suspects(words),
            **engine.describe()}


# ---- rented GPU (optional, untested against a real provider) ----------------------------------------------------
UPLOAD_KIND = "audio_upload"


def upload_consent(episode: str, file_rel: str, sha: str, title: str, body: str) -> tuple[str, int]:
    """The user's yes for sending exactly this audio file to a rented machine.

    Returns ("accepted" | "open" | "declined", card id). Proposes a card the first time.
    """
    for c in reversed(approvals.list_cards(episode=episode)):
        d = c.get("data") or {}
        if c.get("kind") == "other" and d.get("privacy") == UPLOAD_KIND and c.get("sha256") == sha:
            if c["status"] in ("accepted", "open", "declined"):
                return c["status"], c["id"]
    card = approvals.propose(episode, "edit", "other", title, body=body, file=file_rel,
                             data={"privacy": UPLOAD_KIND, "file": file_rel})
    return "open", card["id"]


def extract_upload_cmd(src: Path, dest: Path, channel: int | None) -> list:
    argv = ["ffmpeg", "-nostdin", "-v", "error", "-n", "-i", str(src), "-vn", "-map_metadata", "-1"]
    if channel is not None:
        argv += ["-af", f"pan=mono|c0=c{int(channel)}"]
    return argv + ["-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "flac", str(dest)]


def remote_cmd(remote_in: str, remote_out: str, model: str, language: str) -> str:
    return (f"cd /app && CREWCUT_STUDIO=/work/studio python3 -m crewcut.cut.cli transcribe {remote_in} "
            f"--out {remote_out} --model {model} --language {language} --device cuda --force")


def transcribe_rented(src: Path, out: Path, ep_dir: Path, model: str, language: str, channel: int | None = None,
                      wait: float | None = None, force: bool = False) -> dict:
    """Upload only the audio track (16 kHz mono FLAC, no metadata) after a yes, run the same command there."""
    try:
        from .. import compute
    except ImportError as exc:
        raise CutError("the rented path needs crewcut.compute, which is not in this build") from exc
    if out.exists() and not force:
        raise CutError(f"{out.name} exists already. Use --force to read the file again.")
    episode = ep_dir.name
    info = media.probe(src)
    if channel is None:
        channel = mic_channel_of(src, info)
    upload = ep_dir / "work" / "upload" / f"{Path(src).stem}-16k.flac"
    if not upload.exists():
        upload.parent.mkdir(parents=True, exist_ok=True)
        media.run(extract_upload_cmd(src, upload, channel))
    sha = approvals.sha256(upload)
    minutes = (media.duration(info) or 0) / 60
    status, card_id = upload_consent(
        episode, rel(ep_dir, upload), sha,
        title=f"Send the voice of {src.name} to a rented GPU for speech recognition?",
        body=(f"Only this audio track goes there ({minutes:.0f} min, mono, no picture, no metadata). The machine is "
              "destroyed after the run. Without a yes, recognition runs here on the CPU, which is slower."))
    if status == "open" and wait:
        status = approvals.wait(card_id, timeout=wait)
    if status != "accepted":
        verb = "waiting for your yes" if status == "open" else "you said no"
        raise Waiting(f"{verb} on card {card_id} (sending the audio to a rented GPU)", card_id)
    s = settings()
    with compute.session(episode=episode, step="edit", purpose="speech recognition",
                         cap_usd=float(s["rented_cap_usd"])) as sess:
        machine = sess.rent(gpus=1, max_minutes=int(s["rented_max_minutes"]))[0]
        machine.put([upload], "/work/in/")
        rc, log = machine.run(remote_cmd(f"/work/in/{upload.name}", "/work/out/words.json", model, language),
                              timeout=int(s["rented_max_minutes"]) * 60)
        if rc:
            raise CutError(f"recognition on the rented GPU failed: {str(log)[-1500:]}")
        local = ep_dir / "work" / "upload" / "out"
        local.mkdir(parents=True, exist_ok=True)
        machine.get("/work/out/", local)
    words = json.loads((local / "words.json").read_text(encoding="utf-8"))
    if not isinstance(words, list) or not all({"w", "s", "e"} <= set(w) for w in words):
        raise CutError("the rented GPU returned no valid words file")
    write_replace(out, json.dumps(words, ensure_ascii=False, indent=0) + "\n")
    return {"out": str(out), "words": len(words), "rented": True, "card": card_id, "suspects": suspects(words),
            "model": model, "language": language}
