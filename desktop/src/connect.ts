// "Connect Claude" and "Connect Codex (beta)" in the desktop app: `crewcut engine connect` runs inside the container
// (the CLIs' own sign-in, crewcut/engines/connect.py) and talks in JSON lines. The app opens the sign-in link in the
// default browser, hands over the code the user pastes, and keeps the Claude token in the system keychain.
// No Electron in here, so the tests run in plain Node.
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import { EventEmitter } from "node:events";
import { createInterface } from "node:readline";

export const SIGN_IN_HOSTS = ["claude.ai", "claude.com", "console.anthropic.com", "platform.claude.com"];
export const DEVICE_HOSTS = ["auth.openai.com", "chatgpt.com", "openai.com"];
export const CODE_RE = /^[A-Za-z0-9_\-#.:]{8,1024}$/;
export const TOKEN_RE = /^sk-ant-oat\d\d-[A-Za-z0-9_-]{20,}$/;

function hostIn(url: string, hosts: string[]): boolean {
  try {
    const u = new URL(url);
    return u.protocol === "https:" && !u.username && !u.password &&
      hosts.some((h) => u.hostname === h || u.hostname.endsWith(`.${h}`));
  } catch {
    return false;
  }
}

/** Only Anthropic's own sign-in pages are opened for Claude. */
export const signInAllowed = (url: string) => hostIn(url, SIGN_IN_HOSTS);
/** Only OpenAI's device page is opened for Codex. */
export const deviceAllowed = (url: string) => hostIn(url, DEVICE_HOSTS);

export interface Step {
  step: "status" | "url" | "device" | "done" | "error";
  url?: string;
  code?: string | null;
  token?: string;
  stored?: boolean;
  ok?: boolean;
  text?: string;
  account?: { email?: string; orgName?: string; subscriptionType?: string; authMethod?: string };
}

export function parseStep(line: string): Step | null {
  try {
    const v = JSON.parse(line) as Step;
    return v && typeof v === "object" && typeof v.step === "string" ? v : null;
  } catch {
    return null;
  }
}

/** The JSON lines of one `crewcut engine connect` run, as events; the last lines of stderr for an error message. */
export class Steps extends EventEmitter {
  private errTail = "";
  readonly seen: Step[] = [];
  exited: number | null = null;

  constructor(readonly proc: ChildProcessWithoutNullStreams) {
    super();
    createInterface({ input: proc.stdout }).on("line", (line) => {
      const s = parseStep(line);
      if (!s) return;
      this.seen.push(s);
      this.emit("step", s);
    });
    proc.stderr.on("data", (d: Buffer) => {
      this.errTail = (this.errTail + d.toString()).slice(-600);
    });
    proc.on("close", (code) => {
      this.exited = code ?? 1;
      this.emit("exit", this.exited);
    });
    proc.on("error", (e) => {
      this.errTail += String(e);
      this.exited = 1;
      this.emit("exit", 1);
    });
  }

  stderr(): string {
    return this.errTail.trim().split("\n").slice(-2).join(" ");
  }

  /** The next step that matches (or an error step), within the time. */
  next(match: (s: Step) => boolean, timeoutMs: number): Promise<Step> {
    const earlier = this.seen.find((s) => match(s) || s.step === "error");
    if (earlier) return Promise.resolve(earlier);
    return new Promise((resolve) => {
      const done = (s: Step) => {
        clearTimeout(timer);
        this.off("step", onStep);
        this.off("exit", onExit);
        resolve(s);
      };
      const onStep = (s: Step) => {
        if (match(s) || s.step === "error") done(s);
      };
      const onExit = () => done({ step: "error", text: this.stderr() || "The sign-in stopped." });
      const timer = setTimeout(() => done({ step: "error", text: "No answer in time. Try again." }), timeoutMs);
      this.on("step", onStep);
      this.on("exit", onExit);
      if (this.exited !== null) onExit();
    });
  }

  sendLine(text: string): void {
    this.proc.stdin.write(`${text.replace(/[\r\n]/g, "")}\n`);
  }

  stop(): void {
    if (this.exited === null) this.proc.kill();
  }
}
