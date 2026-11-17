# Compute: rented GPUs (optional)

Crewcut never needs a rented GPU. Every step has a local way. Renting is a speed-up for the slow parts, mainly 3D
scenes in Blender. This page says how the compute module (`crewcut/compute/`) estimates, rents, uses and destroys
machines, which money rules hold, and what is still untested.

Provider: [Vast.ai](https://vast.ai), a marketplace of GPU machines, through its REST API. RunPod and Modal are planned.

## The short version

**Build cheap, render expensive.** One real night: ten 3D runs on four RTX 5090 each cost $89, because the cards
waited at full price while the agent built the scene. So Crewcut builds scenes, previews and tests on this machine or
on **one** RTX 4090, rents several GPUs only for the final render of an approved scene, and deletes every machine that
runs nothing for a few minutes.

1. **Estimate both ways.** Time here and time on rented GPUs, with the price. One sentence, for example
   "840 frames: about 34 h here, or about 87 min on 8 rented GPUs for about $5.21." (config defaults, no probe yet)
2. **Ask once.** The first rent in an episode makes a spend card. After the yes, the episode has a budget.
3. **Rent with a deadline.** Each machine has one GPU and a deadline. It must answer SSH within 4 minutes and pass a
   5 MB upload probe and the setup, or it is destroyed and the next offer is tried.
4. **Work.** Upload code and fonts, run commands, fetch results. Fetched files are scanned for secrets first.
5. **Destroy and prove.** Leaving the session destroys every machine, books the cost per machine and writes the proof
   "0 own machines left" into the cost book.
6. **Guard.** A background guard destroys our machines that have no live session or whose deadline passed, also after
   a crash.

## Local or rented

| Way | When | Speed (studio numbers, not measured on Crewcut's own templates yet) |
|---|---|---|
| Local CPU | always possible | a laptop CPU renders the studio's 3D scenes at about 144 s per frame |
| Local NVIDIA GPU | Linux or Windows with the GPU passed into the container | about as fast as one rented GPU of the same class |
| Rented GPU | when it saves a lot, with a yes | an RTX 4090 renders the same scenes at about 20 to 70 s per frame (128 samples) |

The render workbench times a short probe on this machine and stores it (`compute.record_probe(kind, sec_per_frame)`).
From then on, estimates use the median of the last measurements and say `local_measured: true`. Without a probe they
use the config default and say `local_measured: false`, and the sentence adds "(not measured on this machine yet)".
Measured probes on rented GPUs (`where="rented"`) replace the GPU default in the same way.

## The estimate

```python
from crewcut import compute
est = compute.estimate(kind="blender", frames=840, local_sec_per_frame=None, gpus=None)
```

| Key | Meaning |
|---|---|
| `local_seconds` | frames x seconds per frame here (measured, else `kinds.blender.local_sec_per_frame`) |
| `local_measured` | true only when the number comes from a probe on this machine (or the caller passed it) |
| `rented_seconds` | ceil(frames / gpus) x `gpu_sec_per_frame` + `estimate.overhead_minutes` (boot, setup, upload, fetch) |
| `rented_usd` | sum of the GPU prices per hour x `rented_seconds` |
| `rented_usd_worst` | the same with `gpu_sec_per_frame_worst` (70 s per frame by default) |
| `gpus` | given, or enough to finish in about `estimate.target_minutes`, at most `limits.max_gpus` and at most the number of live offers |
| `price_per_hour` | per GPU: from live offers when a Vast key exists (cached for a few minutes), else `estimate.price_per_hour` |
| `suggest_rent`, `reason` | see below |
| `sentence` | the one sentence for the card |
| `referral` | `{"url", "note"}` or null, see below |

Other kinds (music with ACE-Step, image to 3D, cutouts, long encodes) use the same session interface. Their default
numbers are planned; until they are measured, pass `local_sec_per_frame` and `gpu_sec_per_frame` (seconds per unit).

## The suggestion and the referral link

Crewcut suggests renting only when it really helps, in one sentence with one button. The rules:

- Never when this machine has its own NVIDIA GPU: then the work stays local.
- Only when renting saves more than `suggest.min_minutes_saved` (15) minutes **and** is more than `suggest.min_speedup`
  (3) times faster.
- At most once per job (the job id comes from `CREWCUT_JOB` or the `job` argument).
- Never again in an episode after the user said "local is fine" (`compute.local_is_fine(episode)` or
  `crewcut compute estimate --episode ID --local-fine …`). This is stored in the studio.
- The numbers are real: see the table above. No rounded-down prices, no hidden overhead.

The referral link shows only with a suggestion, only when the user has **no** Vast key (a key means an account, and
the link counts only for new accounts), and only when the config has a link. It comes with this note:

> Referral link: the author of Crewcut earns 3% of your Vast spend as credit. It costs you nothing extra.

The link lives in `config/compute.toml`:

```toml
vast_referral = "https://cloud.vast.ai/?ref_id=855305"   # the author's referral link; change or empty it in your fork
```

To change it for your studio, put the same key into `studio/config/compute.toml`. To remove it, set it to `""`: then no
link is shown anywhere. A fork can change or empty the line in `config/compute.toml`. `vast_template` is reserved for a
public Vast template of the Crewcut GPU image (planned).

## Money rules

- **Rights.** Only identities with `may_spend: true` may rent (`approvals.require_right("spend")`). A human at the
  command line (no `CREWCUT_IDENTITY`) may.
- **Spend card.** The first rent in an episode proposes a `spend` card with the amount and both estimates
  (`approvals.require_spend`). While it is open, `rent` raises `NeedsApproval(card_id)`; the CLI exits with 3. A second
  call does not make a second card, and neither does any other open spend card of the episode (for example one the
  render workbench proposed from its estimate): one money question at a time. After the yes, the episode budget covers
  later rents until it is used up. When a session's cap is above what is left of the approved budget, the first rent
  lowers the session cap to that rest instead of asking again, as long as at least 15 minutes of the planned machines
  fit; otherwise a new card asks.
- **Month cap.** `money.cap_month_usd` in `config/crewcut.toml`. Before each rent, the month's booked costs plus the
  worst case of every running machine plus the new worst case must fit. Otherwise renting is refused, without a card.
- **Session cap.** Each session has a cap (`cap_usd`, default `limits.session_cap_usd`). The session tracks money live
  (price x time for every machine, also the dropped ones). At 100 % it destroys all its machines and says so in the
  chat. Every later call on a machine raises `Refused`.
- **Credit.** Before renting, the Vast credit must cover the worst case: every running machine until its deadline plus
  the new ones. Without a readable credit nothing is rented. Only the field `credit` is read from the account record.
- **Cost book.** Each machine is booked when it is destroyed (`ledger.add("gpu", …)`, ref `vast:<instance>`): price per
  hour (disk included) x time from the rent call to the destroy. Vast bills network traffic separately; that part is
  not in the cost book. The proof line carries the credit before and after the session, which includes everything.

## Three delete safeguards per machine

1. **The session.** Leaving the `with` block, reaching the cap or reaching a machine's deadline destroys machines.
   A destroy is confirmed by listing the account's machines; an unconfirmed destroy marks the machine `lost`.
2. **The watchdog on the machine.** Vast runs our `onstart` hook when the machine starts. It writes and starts a small
   script that deletes the machine at its deadline with the instance's own key (`CONTAINER_API_KEY`, which Vast puts
   into every container and which works only for that machine). The key goes to `curl` on stdin, never as an argument
   or into a log. `setup.sh` checks that the watchdog runs and starts it if not.
3. **The local guard.** `compute.guard.sweep()` destroys every machine with our label that has no rental record, no live
   session, an unconfirmed destroy, or a deadline more than `limits.guard_grace_minutes` ago. It also enforces session
   caps and books machines that vanished (watchdog or host). The server calls `compute.guard.start_background()` at
   startup: a daemon thread that sweeps at once and then every `limits.guard_every_minutes` (3). `crewcut compute guard`
   runs it in a loop, `--once` for one pass.

**Labels.** Every machine carries the label `<label_prefix>-<studio id>` (for example `crewcut-3f9a1c`). The studio id is
made once per studio. Nothing ever touches a machine without exactly this label: not the guard, not
`destroy --all-ours`. The proof also counts the other machines in the account and says they were not touched.

## Choosing machines

- **The RTX 4090 is the default** (`vast.gpus`: RTX 4090, then RTX 4080S and RTX 3090). **Premium GPUs**
  (`vast.premium_gpus`: RTX 5090, RTX PRO 6000, L40S, A100, H100, H200, B200) are never rented unless the user names
  one ("render the final on an RTX 5090" → `crewcut compute rent --gpu "RTX 5090"`); then only that model is rented.
- **Hard price cap per GPU and hour:** `vast.max_price_per_gpu_hour`, default **$0.60**. Offers above it are never
  rented. The GPU card shows the price and the cap.
- **Several GPUs only for the final render** (`limits.build_max_gpus = 1`): more than one GPU needs `--final` (the
  render workbench sets it for the render itself), and those machines are deleted after `limits.idle_minutes_final`
  (2) minutes without work. Any rented machine that runs no command, upload or download for `limits.idle_minutes` (5)
  is deleted, by the session and by the background guard.
- **Render defaults** (`[render3d]`): Cycles at about 128 samples with the OptiX denoiser on NVIDIA (Open Image Denoise
  on the CPU); the graphics templates (counters, stacks, scales, boxes) render with Eevee on a GPU and fall back to
  Cycles on the CPU.
- **Idle risk on the card:** the estimate states what waiting costs: boot, setup and the minutes before an idle machine
  is deleted ("at most about $0.10 on top"), and the price cap.
- Offers: one GPU per machine, preferred GPUs first, then the price; never above the cap;
  regions, reliability, network speed and disk from `[vast]`; no host that leaves within `vast.min_hours_left`.
- One offer per host IP, and never a host IP where a machine of this account already runs.
- Hosts that fail us (no SSH while running, failed upload probe, failed setup) go into
  `studio/.crewcut/compute/blocked.json`. The list starts empty and is learned per studio.
- Image: the Crewcut GPU image (`vast.image`, Blender at `/opt/blender/blender`, the app at `/app`, work folder `/work`).
  If it cannot be pulled, the machine is destroyed (the host is not blocked), and renting falls back to
  `vast.fallback_image` for 24 hours. On the fallback image, `setup.sh` installs Blender `vast.blender_version` to
  `/opt/blender/` (checksum checked when the mirror has one) and Crewcut uploads `templates/3d/` to `/app/templates/`.
  A session opened with `blender=False` (the matting job) runs `setup.sh --blender none` and skips both.

## Privacy

Only code and fonts go to rented machines (plus small scene files such as images and JSON). `Machine.put` refuses:
video and audio files, anything from an episode's `originals/`, `audio/`, `inbox/`, `broll/`, `export/` or `work/`
(transcripts) folder, the studio state (`.crewcut/`), files that look like keys (`.env`, `*.pem`, `id_*`), symbolic links,
and files that contain something that looks like a key or token. Vast hosts are other people's machines, so there is no
switch to send recordings there. No login, no Claude token and no Vast key ever goes to a machine.

**One narrow exception: the picture of a shot for graphics behind the speaker** ([motion-matte.md](motion-matte.md)).
A video file may go up only when all of these hold: it lies directly in an episode's `render/matte/` folder, where
Crewcut itself cut it for one shot; ffprobe finds exactly one video stream and nothing else (no sound, subtitles or
data); and its sha256 is named on an accepted spend card of the running session, which says in plain words that the
shot's picture goes to the rented machine and is deleted with it. A session asks for that card when it is opened with
`picture={"files": [{"shot", "file", "sha256", "seconds"}]}`, also inside an approved budget (that card adds no money).
Sound, originals, raw folders and every other recording stay refused inside such a session too, and a session without
`picture` refuses every video file as before.

Everything fetched lands in a temporary folder first. Known secret values (the Vast key and other keys in Crewcut's
environment) are replaced in every file; secret patterns (Claude tokens, `CONTAINER_API_KEY=…`,
`Authorization: Bearer …`) are replaced in text files. The chat says which files were cleaned. If a known secret is
still there afterwards, nothing is handed on. Command output from `run` is cleaned the same way.

## Keys

- **Vast key:** env `VAST_API_KEY`, set once in the `.env` file of your Crewcut folder. Without it, `rent` exits with 4
  and one sentence: where to create the key (<https://cloud.vast.ai/manage-keys/>), where to sign up, and where to put it.
- **SSH key:** Crewcut makes its own ed25519 key in `studio/.crewcut/compute/ssh/` on first use and registers the public
  half with the Vast account. The private key is never printed. Each machine gets its own `known_hosts` file.

## Python interface

```python
from crewcut import compute
with compute.session(episode="003-x", step="edit", purpose="3D scenes", cap_usd=1.5) as s:
    machines = s.rent(gpus=2, max_minutes=60)       # NeedsApproval(card_id) | Refused(reason) | MissingKey | NoMachine
    m = machines[0]
    m.put([Path("scene.py")], "/work/")
    rc, out = m.run("blender -b …", timeout=600, doing="rendering")   # right column: "Rented GPU 1 of 2: rendering"
    m.get("/work/out/", Path("render/"))
compute.guard.sweep()
```

`compute.session(..., picture={...}, blender=False)` is the matting job's session: see Privacy above and
[motion-matte.md](motion-matte.md).

## Command line

```
crewcut compute estimate --kind blender --frames N [--local-sec-per-frame S] [--gpu-sec-per-frame S] [--gpus N]
                         [--scene NAME] [--episode ID] [--job ID] [--local-fine] [--json]
crewcut compute rent --episode ID [--gpus 1] [--minutes 60] [--max-usd X] [--step edit] [--purpose "…"] [--json]
crewcut compute put <machine> <local path> [<local path> …] <remote dir>
crewcut compute run <machine> [--timeout S] [--doing "rendering"] -- <command>
crewcut compute fetch <machine> <remote dir> <local dir>
crewcut compute destroy [<machine> | --all-ours]
crewcut compute guard [--once] [--every S]
crewcut compute ledger [--episode ID]
```

`<machine>` is the number `rent` prints (the rental id). Machines rented by the command line stay until `destroy`, their
deadline or the session cap; every later command and the guard enforce both. Exit codes: 0 ok, 1 error, 2 usage,
3 waiting for a yes or refused (card open, cap reached, no right, privacy), 4 missing key.

## State

| Where | What |
|---|---|
| database `rentals` | one row per machine: instance, label, episode, job, price, started, deadline, ended, status, detail |
| database `costs` | one row per destroyed machine, plus the proof line of each session |
| database `kv`, `compute.session.<id>` | open and recent sessions (closed ones are forgotten after 30 days) |
| `studio/.crewcut/compute/` | `studio-id`, `blocked.json`, `local.json` (probe timings), `choices.json` (local is fine, suggested jobs, image fallback), `offers.json` (price cache), `ssh/` |

## Untested

Everything below needs a real rental, and none has been done with this module yet. The tests run against a fake Vast
API and a fake SSH runner.

- The real Vast API answers: offer search filters, the shape of `/api/v1/instances/` paging, the `ssh` key list, the
  `credit` field, the error codes. The endpoints follow the official `vast-cli` source as of 16 Nov 2026.
- The `onstart` hook starting the watchdog, and the self-delete with `CONTAINER_API_KEY`.
- How long Vast needs to pull the Crewcut GPU image (several gigabytes); `limits.image_wait_minutes` is a guess.
- `setup.sh` on the fallback image, including the Blender download and checksum.
- SSH and rsync against real hosts, the 5 MB probe on slow hosts.
- The speed numbers: they come from the studio Crewcut grew out of, not from Crewcut's own templates.
- RunPod and Modal as providers (planned).
