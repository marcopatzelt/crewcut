# Cost: build cheap, render in bursts

Money in motion work goes to rented GPUs. Comps are CPU work; plates and mattes are GPU work. The expensive part is
not rendering, it is a rented machine that waits while someone writes code.

## 1. What things cost (measured on the launch film)

| Job | Time | Note |
|---|---|---|
| One engine frame, 1080p, simple comp | about 70 ms | a 12-frame contact sheet about 3.5 s |
| Whole film comp build (all beats) | 14 s | |
| Film render, 1050 frames at 60 fps, 6 chunk jobs on 72 CPU cores | about 3 min | about 5 min with sheets and strips |
| 3D logo plate (Cycles 128 samples, 1080p RGBA) | 5 to 6 s per frame | 101 frames about 10 min |
| 3D word plate (96 samples) | about 3 s per frame | 170 frames about 8 min |
| Photoreal world (64 samples, 1.5 million instances) | about 20 s per frame per process | 3 processes, 300 frames about 35 min |
| A beat with Shatter and Temporal Motion Blur | 57 CPU minutes for 156 frames | the reason both are banned |

**The whole film, three review rounds, all tests and renders: 1.75 $** (2.9 hours of one RTX 4090 at 0.60 $ per
hour). A beat of new 3D content: roughly 0.10 to 0.30 $. A pure EffectCraft insert: cents. On a user's own computer the
comp speed is not measured: the first frame of each insert is timed and the estimate shown before the rest renders;
expect several seconds per frame on a laptop with blur at 16 samples.

## 2. Caps per video

| Video | Cap |
|---|---|
| Long video | $2 |
| Short | $0.50 |

The cap is written on the motion-plan card with the planned spend per row. Renting still gets its own `spend` card
(`crewcut compute estimate --kind blender --frames N` gives both ways, local and rented), with the plan's number as
the cap. When a piece would pass the cap, a new `spend` card, never a silent overrun. The month cap of the studio
(`money.cap_month_usd`) stays above all of it.

## 3. Where comps render

The studio setting `render.location`:

- `local`: comps render on this computer's CPU inside the Crewcut container (`crewcut render motion <plan>`). Footage
  never leaves the computer.
- `rented`: comps render on the rented machine together with the plates, after the same spend card. A comp without
  footage goes up as code, tokens and fonts. A comp with the speaker's picture (`backdrop`, clip inputs) goes up only
  under the matte rule: the clip is cut to the span, has no sound, and is named by its checksum on an accepted card.
  Choose `rented` when the studio's rule is that nothing heavy renders on its own computer.

Plates always render on a GPU: the studio's own NVIDIA card, else a rented RTX 4090 (never a 5090 by default, at most
about 0.60 $ per GPU hour).

## 4. Build cheap, render in bursts

1. Write the beat sheet, the comp and the plate scripts **before** renting. Test the comp's layout on single frames
   and the plate on a half-size still (a small CPU render or one short rental).
2. Collect every GPU job of the video: all plates, all mattes, rented comp renders. Rent once, run them as one burst,
   fetch, destroy.
3. Probe first on the machine: one half-size still per plate, look, then the animation.
4. Keep working locally while machines load (plan, 2D, the cut). Every remote step has a time limit.
5. **At the end, also after a failure:** `crewcut compute destroy --all-ours`, then `crewcut compute ledger --episode
   ID`. The report to the user holds the spend and the proof that no machine runs.

## 5. In the motion plan

Effort is S, M or L (rounds of work), cost is money with a cap. No time estimates. Example line:
`Budget and density   full-frame 4 of max 5 · all motion 7 in 6:10 (max 12) · heroes 1 · GPU about $0.55, cap $2`.
