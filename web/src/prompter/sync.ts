// How a teleprompter screen stays in step with the others. Commands (play, a jump, a hand scroll) are written to the
// server at once and in order; the server numbers every write (seq). The screen asks for the state with the seq it has
// and the server answers as soon as anything newer exists (a long poll), so a command reaches every screen in a
// fraction of a second. A screen applies only newer states, never reports its own scroll position, and asks again at
// once when the phone wakes up or comes back online.
import type { PrompterControl, PrompterScript } from "../api/types";
import { ClockSync, DEFAULT_CPS, reduce, type ControlPatch } from "./timeline";

export const DEFAULT_CONTROL: PrompterControl = { playing: false, speed: 1, position: 0, mirror: false, size: 1 };
const WAIT_SECONDS = 20;

export interface PrompterSource {
  script(): Promise<PrompterScript>;
  /** With `after` (the seq this screen has) and `wait` (seconds) the server answers when something newer exists. */
  getControl(options?: { after?: number; wait?: number; signal?: AbortSignal }): Promise<PrompterControl>;
  /** Writes a command; the answer is the new shared state. */
  setControl(c: ControlPatch & { client?: string }): Promise<PrompterControl | void>;
  /** false when nothing else follows this screen (a source without a server, as in the tests). */
  shared: boolean;
}

/** Reads and writes /p/<token>/control. Writes leave in the order they were made. */
export function httpSource(token: string): PrompterSource {
  const base = `/p/${encodeURIComponent(token)}`;
  let writes: Promise<unknown> = Promise.resolve();
  const json = async <T,>(res: Response): Promise<T> => {
    if (!res.ok) throw new Error(`The server answered ${res.status}.`);
    return (await res.json()) as T;
  };
  return {
    shared: true,
    script: () => fetch(`${base}/script`, { cache: "no-store" }).then((r) => json<PrompterScript>(r)),
    getControl: (o = {}) => {
      const query = o.after !== undefined ? `?after=${o.after}&wait=${o.wait ?? 0}` : "";
      return fetch(`${base}/control${query}`, { cache: "no-store", signal: o.signal }).then((r) => json<PrompterControl>(r));
    },
    setControl: (c) => {
      const sent = writes.then(async () => {
        const res = await fetch(`${base}/control`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(c),
        });
        return json<PrompterControl>(res);
      });
      writes = sent.catch(() => undefined);
      return sent;
    },
  };
}

const seqOf = (s: PrompterControl | null | undefined) => (s && Number.isFinite(s.seq) ? (s.seq as number) : 0);

export interface SyncOptions {
  /** Seconds the server may hold a read open. */
  wait?: number;
  /** This screen's clock in ms (tests replace it). */
  now?: () => number;
  id?: string;
}

export class PrompterSync {
  readonly id: string;
  readonly clock: ClockSync;
  state: PrompterControl = { ...DEFAULT_CONTROL };
  private applied = -Infinity;
  private newest: PrompterControl | null = null; // arrived while this screen's own writes were on the way
  private writes = 0;
  private commandAt = -Infinity; // when this screen last sent a command
  private commandSeq = Infinity; // the seq the server gave it (unknown until the answer)
  private stopped = true;
  private woken = false;
  private offline = false;
  private controller: AbortController | null = null;
  private sleeper: { timer: ReturnType<typeof setTimeout>; done: () => void } | null = null;
  private scrollNext: ControlPatch | null = null;
  private scrollBusy = false;
  private weights: number[] = [];
  private cps = DEFAULT_CPS;
  private readonly wait: number;
  private readonly now: () => number;

  constructor(private source: PrompterSource, private onChange: (state: PrompterControl, offline: boolean) => void,
    options: SyncOptions = {}) {
    this.wait = options.wait ?? WAIT_SECONDS;
    this.now = options.now ?? (() => Date.now());
    this.clock = new ClockSync(this.now);
    this.id = options.id ?? Math.random().toString(36).slice(2, 12);
  }

  /** The block lengths and pace, so this screen can show its own commands before the server answers. */
  setScript(weights: number[], cps: number): void {
    this.weights = weights;
    this.cps = cps;
  }

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    if (typeof document !== "undefined") document.addEventListener("visibilitychange", this.onVisible);
    if (typeof window !== "undefined") {
      window.addEventListener("online", this.wake);
      window.addEventListener("pageshow", this.wake);
    }
    if (this.source.shared) void this.loop();
    else {
      this.state = { ...this.state, seq: 0 };
      this.emit();
    }
  }

  stop(): void {
    this.stopped = true;
    this.controller?.abort();
    this.endSleep();
    if (typeof document !== "undefined") document.removeEventListener("visibilitychange", this.onVisible);
    if (typeof window !== "undefined") {
      window.removeEventListener("online", this.wake);
      window.removeEventListener("pageshow", this.wake);
    }
  }

  /** Ask the server again at once, with a fresh clock (the phone woke up or came back online). */
  readonly wake = (): void => {
    if (this.stopped) return;
    this.clock.reset();
    this.woken = true;
    this.controller?.abort();
    this.endSleep();
  };

  private readonly onVisible = (): void => {
    if (document.visibilityState === "visible") this.wake();
  };

  /** A command from this screen: shown here at once, written to the server, then followed by every screen. */
  async send(patch: ControlPatch): Promise<void> {
    if (this.stopped) return;
    this.state = reduce(this.state, patch, this.weights, this.cps, this.clock.now());
    if (!this.source.shared) {
      this.state = { ...this.state, seq: seqOf(this.state) + 1, by: this.id };
      this.applied = seqOf(this.state);
      this.emit();
      return;
    }
    this.emit();
    this.writes += 1;
    this.commandAt = this.now();
    this.commandSeq = Infinity;
    const sent = this.now();
    try {
      const answer = await this.source.setControl({ ...patch, client: this.id });
      if (answer && typeof answer === "object") {
        this.clock.sample(sent, this.now(), answer.now);
        this.commandSeq = seqOf(answer);
        this.keep(answer);
      }
      this.setOffline(false);
    } catch {
      this.setOffline(true);
    } finally {
      this.writes -= 1;
      if (this.writes === 0 && this.newest) {
        const newest = this.newest;
        this.newest = null;
        if (seqOf(newest) > this.applied) this.apply(newest);
      }
    }
  }

  /** A hand scroll on this screen. Only one write is on the way at a time; a newer place replaces a waiting one. */
  scroll(block: number, offset: number, final: boolean): void {
    this.scrollNext = { action: final ? "scrolled" : "scroll", block, offset };
    if (!this.scrollBusy) void this.flushScroll();
  }

  private async flushScroll(): Promise<void> {
    this.scrollBusy = true;
    try {
      while (this.scrollNext && !this.stopped) {
        const patch = this.scrollNext;
        this.scrollNext = null;
        const started = this.now();
        await this.send(patch);
        const rest = 80 - (this.now() - started);
        const waiting = this.scrollNext as ControlPatch | null;
        if (rest > 0 && waiting?.action === "scroll") await new Promise((r) => setTimeout(r, rest));
      }
    } finally {
      this.scrollBusy = false;
    }
  }

  private async loop(): Promise<void> {
    let failures = 0;
    while (!this.stopped) {
      const controller = new AbortController();
      this.controller = controller;
      const watchdog = setTimeout(() => controller.abort(), (this.wait + 10) * 1000);
      const sent = this.now();
      // the newest seq this screen knows, also one that waits behind its own write
      const after = Math.max(Number.isFinite(this.applied) ? this.applied : -1, this.newest ? seqOf(this.newest) : -1);
      this.woken = false;
      try {
        const answer = await this.source.getControl({ after, wait: this.wait, signal: controller.signal });
        const received = this.now();
        failures = 0;
        this.setOffline(false);
        this.receive(answer, sent, received);
        // A server that answered at once with nothing newer (an older server that does not wait, or one that lost its
        // state): ask again gently. Anything newer: ask again at once.
        if (seqOf(answer) <= after && received - sent < 200) await this.sleep(250);
      } catch {
        if (this.stopped) break;
        if (this.woken) {
          this.woken = false;
          continue;
        }
        failures += 1;
        if (failures >= 3) this.setOffline(true);
        await this.sleep(Math.min(2000, 250 * failures));
      } finally {
        clearTimeout(watchdog);
      }
    }
  }

  /** A state read from the server. */
  private receive(s: PrompterControl, sent: number, received: number): void {
    if (!s || typeof s !== "object") return;
    this.clock.sample(sent, received, s.now, s.waited);
    // A read that started before this screen's last command shows the state before it (or the command itself, which
    // its own answer brings), unless it is newer than the command's answer.
    if (sent < this.commandAt && !(seqOf(s) > this.commandSeq)) return;
    this.keep(s);
  }

  private keep(s: PrompterControl): boolean {
    if (seqOf(s) <= this.applied) return false;
    if (this.writes > 0) {
      if (!this.newest || seqOf(s) >= seqOf(this.newest)) this.newest = s;
      return true;
    }
    this.apply(s);
    return true;
  }

  private apply(s: PrompterControl): void {
    this.applied = seqOf(s);
    this.state = s;
    this.emit();
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => {
      const done = () => {
        if (this.sleeper?.done === done) this.sleeper = null;
        resolve();
      };
      this.sleeper = { timer: setTimeout(done, ms), done };
    });
  }

  private endSleep(): void {
    const s = this.sleeper;
    if (!s) return;
    clearTimeout(s.timer);
    s.done();
  }

  private setOffline(value: boolean): void {
    if (this.offline === value) return;
    this.offline = value;
    this.emit();
  }

  private emit(): void {
    this.onChange(this.state, this.offline);
  }
}
