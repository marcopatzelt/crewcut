import datetime as dt
import json
import struct
import zlib

from conftest import load_script

pc = load_script("skills/upload/scripts/package_check.py")
NOW = dt.datetime(2026, 11, 16, 12, 0, tzinfo=dt.UTC)


def rows(r, area=None, level=None):
    return [x for x in r.rows if (area is None or x["area"] == area) and (level is None or x["level"] == level)]


def png(path, w, h):
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * w for _ in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_chapters():
    r = pc.Report()
    pc.check_chapters(r, "0:00 Start\n0:20 Test\n1:05 Verdict\n", 120)
    assert rows(r, "chapters", "ok")
    r = pc.Report()
    pc.check_chapters(r, "0:05 Start\n0:10 Test\n", 120)
    assert len(rows(r, "chapters", "error")) == 3


def test_tag_length_counts_quotes():
    assert pc.youtube_tag_length(["local ai", "ollama"]) == len("local ai") + 2 + len("ollama") + 1


def test_tags(neutral):
    r = pc.Report()
    pc.check_tags(r, ["Ollama", "ollama", "local ai"], "Ollama on a laptop", ["Ollama"], neutral)
    assert rows(r, "tags", "warn")
    r = pc.Report()
    pc.check_tags(r, ["x" * 300, "y" * 300], "t", [], neutral)
    assert rows(r, "tags", "error")


def test_srt():
    good = "1\n00:00:00,500 --> 00:00:02,000\nHello Ollama\n\n2\n00:00:02,000 --> 00:00:04,000\nBye\n"
    r = pc.Report()
    pc.check_srt_text(r, good, 10.0, ["Ollama"])
    assert rows(r, "captions", "ok")
    bad = good + "\n3\n00:00:09,000 --> 00:00:30,000\nUntertitelung des ZDF, 2020\n"
    r = pc.Report()
    pc.check_srt_text(r, bad, 10.0)
    assert len(rows(r, "captions", "error")) == 2


def test_settings_and_schedule(neutral):
    r = pc.Report()
    pc.check_settings(r, {}, neutral, NOW)
    assert len(rows(r, "settings", "error")) == 2
    up = {"made_for_kids": False, "paid_promotion": False, "contains_synthetic_media": False, "synthetic_reason": "Real footage.",
          "privacy": "public", "publish_at": "2026-11-10T08:00:00+01:00"}
    r = pc.Report()
    pc.check_settings(r, up, neutral, NOW)
    assert len(rows(r, "schedule", "error")) == 1 and rows(r, "schedule", "hint")
    up.update(privacy="private", publish_at="2026-11-20T08:00:00+01:00", default_language="en",
              default_audio_language="en")
    r = pc.Report()
    pc.check_settings(r, up, neutral, NOW)
    assert not rows(r, level="error") and rows(r, "schedule", "ok")


def test_description_main_link(striq):
    r = pc.Report()
    pc.check_description(r, "Hook line.\nMore.\nRead: https://striq.de/blog/x\nhttps://striq.de\n", striq)
    assert rows(r, "description", "error")
    r = pc.Report()
    pc.check_description(r, "Hook line.\nAll numbers: https://striq.de/blog/x\nhttps://striq.de\n#a #b\n", striq)
    assert not rows(r, "description", "error")


def test_thumbnail_size(tmp_path):
    p = tmp_path / "t.png"
    png(p, 1280, 720)
    r = pc.Report()
    pc.check_thumbnail(r, p)
    assert rows(r, "thumbnail", "ok")
    png(p, 320, 180)
    r = pc.Report()
    pc.check_thumbnail(r, p)
    assert rows(r, "thumbnail", "error")


def test_whole_package_without_video(tmp_path, neutral):
    ep = tmp_path / "001-test"
    (ep / "export").mkdir(parents=True)
    (ep / "graphics").mkdir()
    png(ep / "graphics" / "t.png", 1280, 720)
    (ep / "export" / "en.srt").write_text("1\n00:00:00,000 --> 00:00:02,000\nHi\n", encoding="utf-8")
    up = {"title": "Ollama runs five models", "description": "Five models.\n", "tags": ["ollama"] * 1,
          "captions": [{"file": "export/en.srt", "language": "en"}], "thumbnail": "graphics/t.png",
          "made_for_kids": False, "paid_promotion": False, "contains_synthetic_media": False, "synthetic_reason": "Real.",
          "names": ["Ollama"], "video": "../outside.mp4"}
    r = pc.check_package(ep, up, neutral, now=NOW)
    assert rows(r, "files", "error")  # the video path escapes the episode folder
    assert rows(r, "thumbnail", "ok") and rows(r, "captions", "ok")
    (ep / "export" / "upload.json").write_text(json.dumps(up), encoding="utf-8")
    assert pc.main([str(ep), "--pack", "packs/neutral"]) == 1
