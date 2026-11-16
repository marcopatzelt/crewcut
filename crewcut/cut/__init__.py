"""From the recording to the speaker cut: ingest, sound checks, speech recognition, cut tools, grade, subtitles.

Commands (see docs/recording.md):

    crewcut ingest <episode> <file> ...          save recordings, check the sound to the end
    crewcut transcribe <file>                    words with times (faster-whisper)
    crewcut cut islands|probe|dips|takes|plan|build|verify|doubles|grade|srt|audio|loudness ...

Modules keep the parsing and the decisions pure (text or lists in, data out) so they are unit-tested without media.
Only `media.run` starts ffmpeg or ffprobe, and only `transcribe.Engine` loads a speech model.
"""
