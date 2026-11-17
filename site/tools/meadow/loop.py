"""The landing page's meadow loop (hero and close), built from the launch film's meadow plate: the 300 frames that
examples/launch-film/plates.sh renders with meadow3d.py (Blender, 2304 x 1296, 60 fps; $OUT/meadow). No new render.
Build the seamless loop from those frames: 300 frames at 60 fps, played at 30 fps (half speed, calmer
wind), the last 60 frames dissolved into the first 60 (smoothstep), so the loop is 240 frames = 8 s and frame 239 runs
straight into frame 0. Writes raw RGB 1920x1080 to stdout for ffmpeg.
    python3 loop.py SRC_DIR day|dusk | ffmpeg -f rawvideo -pix_fmt rgb24 -s 1920x1080 -r 30 -i - \\
        -c:v libx264 -crf 6 -pix_fmt yuv444p master-day.mkv      (then encode.sh)"""
import os
import sys
from multiprocessing import Pool

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grade  # noqa: E402

SRC, LOOK = sys.argv[1], sys.argv[2]
N, X = 300, 60
L = N - X
def proc(k):  # k: 0-based source index
    im = Image.open(f"{SRC}/meadow_{k + 1:04d}.jpg").convert("RGB").resize((1920, 1080), Image.LANCZOS)
    a = np.asarray(im, dtype=np.float32) / 255
    a = grade.day(a) if LOOK == "day" else grade.dusk(a)
    return a.astype(np.float32)
def frame(i):
    a = proc(i)
    if i < X:
        t = (i + 1) / (X + 1)
        w = t * t * (3 - 2 * t)
        a = w * a + (1 - w) * proc(i + L)
    return (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes()
if __name__ == "__main__":
    with Pool(10) as p:
        for i, buf in enumerate(p.imap(frame, range(L), chunksize=2)):
            sys.stdout.buffer.write(buf)
            if i % 40 == 0:
                print(f"{LOOK} frame {i}", file=sys.stderr, flush=True)
