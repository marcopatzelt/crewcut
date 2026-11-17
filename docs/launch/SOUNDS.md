# Sounds: the Crewcut launch film

**Every sound in this film is synthesized from scratch by `examples/launch-film/sfx.py`** (Python, numpy and scipy: noise, sine and
filter maths). No recordings, sample packs or downloads were used: nothing from Kenney, freesound, Pixabay or any other
library. So there is no third-party licence to follow and no attribution to give. The sounds are original work made
for this repository, and they can go into a public repo under the repo's own licence (Crewcut is MIT) or under CC0 1.0.

| Item | Source URL | Licence |
|---|---|---|
| All 115 sound events (list below) | `examples/launch-film/sfx.py` (generated, no external source) | original work, no third-party rights (MIT / CC0 at the owner's choice) |
| Music bed (pad chords) | `examples/launch-film/sfx.py`, function `bed()` | same |
| Reverb (synthetic room, 0.9 s) | `examples/launch-film/sfx.py`, function `room_ir()` | same |
| Third-party sounds | none | none |

## Deliverables

| File | What |
|---|---|
| `crewcut-concept-v2-sfx.mp4` (release asset, not in git) | master: picture copied unchanged from `crewcut-concept-v2.mp4` (H.264 1920×1080, 60 fps, 17.5 s), AAC 256 kbit/s 48 kHz stereo, faststart, 21.6 MB |
| `docs/launch/crewcut-launch-web.mp4` | web (README and landing page): H.264 High 4.2, 1920×1080, 60 fps, two-pass 3.3 Mbit/s, AAC 192 kbit/s, faststart (moov first), 7.6 MB |
| `docs/launch/poster.jpg`, `poster.webp` | poster frame: frame 87 (1.45 s), the 3D Slate on the colour rings, 1920×1080 JPEG |
| `out/audio/mix.flac` (made by `sfx.py`, not in git) | the master mix (48 kHz, 24 bit, lossless) |
| `out/audio/mix-nobed.flac` | the same mix without the music bed, mastered to the same loudness |
| `out/audio/sfx.flac`, `bed.flac` | stems (SFX with reverb, music bed after ducking) at master gain, before compression and limiting |
| `out/audio/cues.json`, `cues.md` | every cue: time, frame, gain, pan, reverb send |

## Mix

| Measure | Target | `mix.flac` | master MP4 (AAC 256k) | web MP4 (AAC 192k) |
|---|---|---|---|---|
| Integrated loudness | −14 LUFS | −14.0 LUFS | −14.1 LUFS | −14.1 LUFS |
| True peak | ≤ −1 dBTP | −1.7 dBTP | −1.6 dBTP | −1.5 dBTP |

Measured with ffmpeg `ebur128=peak=true` on the final files. Chain in `master()`: high-pass 30 Hz → bus compressor
(RMS, 2.5:1, soft knee, 8 ms / 180 ms; up to ~6 dB only on the impact tail, gluing it) → look-ahead true-peak limiter
(4× oversampled, ceiling −1.7 dBTP, at most 3 dB of reduction, only on single transients) → gain loop to −14.0 LUFS
(ITU-R BS.1770-4). The 0.7 dB margin below −1 dBTP is for the AAC encoder: AAC at 128 kbit/s pushed the peak to
−0.5 dBTP, so the web file uses 192 kbit/s (−1.5 dBTP).

**Music bed: kept, low.** A soft pad (detuned additive saw voices, low-passed at 1.3–2.2 kHz, high-passed at 110 Hz)
in D major that changes chord on the cuts: Dadd9 from the burst (0.97 s), Gmaj9 under the meadow (2.04 s), Bm7(add11)
under the grid (6.80 s), A(sus4) under the reel (10.0 s), silence under the "Ship the" typing (12.55–13.28 s) so the
impact lands in a gap, D/F# on the impact (13.28 s), Dmaj9 resolving with the logo whoomp (15.28 s); the chime is in
the same key. It sits 9 LU under the SFX and ducks by up to 7 dB under every sound, so it never covers a cue. If it
should go, `mix-nobed.flac` is ready (same loudness): `ffmpeg -i out/crewcut-concept-v2.mp4 -i out/audio/mix-nobed.flac -map 0:v -map 1:a -c:v copy -c:a aac -b:a 256k -movflags +faststart out.mp4`.

## How each sound is made

| Sound | Recipe in `sfx.py` |
|---|---|
| Whooshes (camera moves, cursor, wipes, card flutter) | `whoosh()`: pink noise through a band that moves in octaves (STFT shaping), centre rises to the peak and falls after it, amplitude rises with a power curve and falls exponentially, stereo from two noises, pan moves with the object; big camera moves add a 45–170 Hz body; spins and rolls add amplitude modulation at the rotation rate |
| Mouse clicks | `click()`: 0.6 ms noise transient + four damped plastic modes (2.3–6.9 kHz) + a 170 Hz thock, release click 50–75 ms later at −9 dB, low-passed ("soft") |
| Keyboard ticks | `tick()`: transient + random key modes (1.5–5.6 kHz; space bar 0.7–1.7 kHz), thock 340 Hz (space 230 Hz), bottom-out tick 6–10 ms later, random level ±2 dB |
| Reel ticks | `reel_tick()`: short mechanical click, rising pitch per word |
| Pops (dock icon, hero card, button, flower, card, star) | `pop()`: bubble sine with a fast exponential pitch glide (rising "bloop"), 2nd harmonic, tiny noise |
| Riser | `riser()`: noise band sweeping 260 Hz → 7.5 kHz + a two-octave gliding tone stack (D3 → D5) + a hiss top, ends hard on the burst frame |
| Glassy shimmer (bristles, converge, retract) | `shimmer()`: granular sine grains on a D-major pentatonic set (D6–A7) with a glass partial at ×2.76, density and level ramp; "fizz" of sparse high noise clicks; played reversed for the converge |
| Iris / glint / star "shing" | `shing()`: bell partials (×1, ×2.76, ×5.4) of D6, A6, D7, F#7 spread in stereo + an air swish |
| Impact | `impact()`: sub sine gliding 78 → 44 Hz with saturation (so it reads on phone speakers), 200 → 110 Hz punch, band-passed body, 0.9–9 kHz crack |
| Splash | `splash()`: band-noise burst with a wet wobble, low splat, 30 rising water droplets thrown to the right (like the picture) |
| Whoomp | `whoomp()`: 0.22 s reversed air swell into a soft 85 → 46 Hz thump with an air puff |
| Chime | `bell()`: additive bell (×1, ×2, ×3, ×4.2, ×5.4) with slight detune, D6 then A6 |
| Meadow air | `wind()`: two slowly moving noise bands + quiet leaf hiss, beat 3 only |
| Room | `room_ir()`: decaying stereo noise, 0.9 s, 12 ms pre-delay; sends are high-passed at 250 Hz (no low-end mud) |

## Timing (frame-accurate)

Times are global seconds of the ad; frame = time × 60; one frame = 800 samples at 48 kHz, so every cue starts on its
exact sample. The times come from `examples/launch-film/ad.sh` and the template timings; the keystrokes and word-reel changes were
**measured in the rendered video** (first frame where a character's ink shows, frame where the selection box changes
width), because they depend on the text animator. Whoosh rows show the start time; the loudest point is later and
sits on the fastest motion (checked against a per-frame motion-energy curve of the video).

| Time (s) | Frame | Cue | What | Gain (dB) |
|---|---|---|---|---|
| 0.050 | 3 | cursor-in | cursor flies into the dock | -25 |
| 0.360 | 22 | hover-1 | hover: camera icon lifts | -30 |
| 0.400 | 24 | riser | riser into the burst (ends on the burst frame 0.99) | -17 |
| 0.560 | 34 | hover-2 | hover: folder icon lifts | -31 |
| 0.920 | 55 | dock-click | soft click on the Crewcut icon | -14 |
| 0.970 | 58 | dock-pop | icon pops into pixels | -19 |
| 0.990 | 59 | burst-thump | disc + rings burst, soft low hit | -16 |
| 0.990 | 59 | burst-bloom | colour bloom fills the frame | -17 |
| 1.040 | 62 | logo-spin | 3D Slate spins in (540 deg) | -17 |
| 1.300 | 78 | logo-glint | light sweeps across the logo | -27 |
| 1.620 | 97 | bristles | bristles grow out of the logo (glassy fizz) | -19 |
| 1.930 | 116 | swirl | flakes release and swirl | -15 |
| 2.040 | 122 | iris-shing | iris opens into the meadow (glassy shimmer) | -16 |
| 2.040 | 122 | iris-air | air of the opening iris | -21 |
| 2.040 | 122 | meadow-wind | meadow air (bed under beat 3) | -31 |
| 2.060 | 124 | bar-in | glass bar slides up | -24 |
| 2.800 | 168 | cursor-in-3 | cursor flies to the bar | -26 |
| 3.450 | 207 | bar-click | click into the bar | -15 |
| 3.470 | 208 | push-in | camera pushes into the bar (100 -> 320 %) | -14 |
| 3.983-4.917 | 239-295 | type | typing ticks, beat 3 ("Make my next video", 18 keys) | -19 |
| 5.550 | 333 | pull-back | camera pulls back out (expo) | -15 |
| 6.000 | 360 | cursor-in-3b | cursor flies to the glyph | -26 |
| 6.550 | 393 | glyph-click | click on the glyph | -15 |
| 6.580 | 395 | wipe-white | white circle grows from the click | -16 |
| 6.860 | 412 | hero-pop | hero card springs in | -17 |
| 6.900 | 414 | hero-wobble | spring wobble | -28 |
| 7.300 | 438 | grid-pull | camera pulls back, grid flies in | -15 |
| 7.418-8.295 | 445-498 | card | card flutter, 26 cards 35 ms apart | -32 |
| 8.300 | 498 | cursor-in-4 | cursor flies to Upload | -26 |
| 8.750 | 525 | button-pop | Upload button pops in | -22 |
| 9.770 | 586 | upload-click | click on Upload | -15 |
| 9.790 | 587 | wipe-dark | dark circle grows from the click | -14 |
| 10.080 | 605 | reel-roll | reel starts to roll | -22 |
| 10.183-10.600 | 611-636 | reel-tick | reel ticks, one per word change (7) | -21 |
| 10.833 | 650 | reel-lock | box lands on "Upload" | -16 |
| 11.300 | 678 | cursor-in-5 | cursor flies to the word | -26 |
| 11.850 | 711 | reel-click | click on "Upload" | -15 |
| 11.950 | 717 | wipe-light | light circle grows from the click | -16 |
| 12.367-12.967 | 742-778 | type6 | typing ticks, beat 6 ("Ship" + "the", 7 keys) | -18 |
| 12.800 | 768 | cursor-swoop | cursor swoops in (echo trail) | -23 |
| 13.110 | 787 | glyphs-fly | 3D letters fly in from the camera | -16 |
| 13.230 | 794 | smash-click | click right before the smash | -17 |
| 13.283 | 797 | impact | "Video!" lands: deep impact | -14 |
| 13.300 | 798 | splash | coral/pink paint splash, thrown to the right | -17 |
| 13.300-13.425 | 798-806 | glyph | letters settle (6 soft thuds) | -27 |
| 13.345 | 801 | flower-pop | lilac flower pops | -21 |
| 13.380 | 803 | card-pop | small crew card pops | -24 |
| 13.410 | 805 | star-pop | yellow star pops | -21 |
| 13.430 | 806 | star-glint | star glint | -29 |
| 15.050 | 903 | converge | flakes swirl back in (reverse shimmer) | -18 |
| 15.050 | 903 | converge-air | swirl sucks in | -16 |
| 15.280 | 917 | whoomp | flakes snap into the logo: whoomp | -14 |
| 15.310 | 919 | retract | bristles retract | -27 |
| 16.290 | 977 | slide | logo slides aside | -24 |
| 16.310 | 979 | chime-1 | chime (D6) | -17 |
| 16.400 | 984 | chime-2 | chime (A6) as "Crewcut" builds in | -21 |

## Rebuild

```bash
cd examples/launch-film     # out/crewcut-concept-v2.mp4 is the silent render of ad.sh + deliver_ad.sh
python3 sfx.py --out out/audio        # ~10 s on any computer, deterministic (seeded); --no-bed, --lufs, --tp, --bed-lu
ffmpeg -i out/crewcut-concept-v2.mp4 -i out/audio/mix.flac -map 0:v:0 -map 1:a:0 -c:v copy \
   -c:a aac -b:a 256k -ar 48000 -movflags +faststart -shortest out/crewcut-concept-v2-sfx.mp4
# web (< 8 MB): two-pass x264 3.3 Mbit/s, AAC 192k
ffmpeg -i out/crewcut-concept-v2.mp4 -an -c:v libx264 -preset slow -b:v 3300k -maxrate 6000k -bufsize 8000k \
   -pix_fmt yuv420p -profile:v high -level 4.2 -pass 1 -passlogfile /tmp/x264 -f mp4 /dev/null
ffmpeg -i out/crewcut-concept-v2.mp4 -i out/audio/mix.flac -map 0:v:0 -map 1:a:0 -c:v libx264 -preset slow \
   -b:v 3300k -maxrate 6000k -bufsize 8000k -pix_fmt yuv420p -profile:v high -level 4.2 -pass 2 -passlogfile /tmp/x264 \
   -c:a aac -b:a 192k -ar 48000 -movflags +faststart -shortest out/crewcut-concept-v2-sfx-web.mp4
ffmpeg -i out/crewcut-concept-v2.mp4 -vf "select=eq(n\,87)" -frames:v 1 -q:v 2 out/crewcut-concept-v2-poster.jpg
ffmpeg -i out/crewcut-concept-v2-sfx.mp4 -map 0:a -af ebur128=peak=true -f null -     # check: I and Peak
```

After a timing change in `ad.sh`, edit the cue list in `cues()` (and the measured lists `TYPE3`, `TYPE6`, `REEL`)
and run the same commands.

Note: the sounds were checked by measurement (spectrogram, loudness, peak, motion-curve alignment), not by ear. Listen
once on headphones and on a phone before publishing; the cue gains in `cues()` are the knobs.
