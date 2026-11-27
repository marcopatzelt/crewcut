// The host helper (host/crewcut-host.sh) next to the desktop app, as ./start.sh runs it next to Docker: the things the
// container cannot do itself (set up YouTube in the user's Chrome, ask a second model about a script). It acts only on
// requests signed with CREWCUT_HOST_TOKEN. The app makes that key once and keeps it in its data folder (stack/.env,
// owner-only, never inside the studio); the container gets it in its environment, the crew's runs never
// (SERVER_ONLY_ENV). The helper runs as the app's child process and stops with it. No Electron in here, so the tests
// run in plain Node.
import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";
import { chmodSync, closeSync, existsSync, mkdirSync, openSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { homedir, platform } from "node:os";
import { delimiter, join, resolve } from "node:path";
import { extraPaths } from "./docker";

export const TOKEN_KEY = "CREWCUT_HOST_TOKEN";

/** The host key from `<dir>/.env`, made once (32 random bytes as hex, file mode 600) when there is none. The value
 *  is never logged or shown. */
export function hostToken(dir: string): string {
  const file = join(dir, ".env");
  let lines: string[] = [];
  try {
    lines = readFileSync(file, "utf8").split(/\r?\n/);
  } catch {
    lines = []; // none yet
  }
  const found = lines.find((l) => l.startsWith(`${TOKEN_KEY}=`))?.slice(TOKEN_KEY.length + 1).trim() ?? "";
  if (found.length >= 32) return found;
  const token = randomBytes(32).toString("hex");
  mkdirSync(dir, { recursive: true });
  const kept = lines.filter((l) => l.trim() && !l.startsWith(`${TOKEN_KEY}=`));
  const tmp = `${file}.tmp`;
  writeFileSync(tmp, [...kept, `${TOKEN_KEY}=${token}`].join("\n") + "\n", { mode: 0o600 });
  renameSync(tmp, file);
  chmodSync(file, 0o600);
  return token;
}

/** What the user set for the second opinion in the app's settings.json (`secondOpinion`). */
export interface SecondOpinionSetting {
  /** The command the helper runs; it reads the prompt from $INPUT_FILE and prints the JSON answer. */
  command?: string;
  /** Its own work folder; default `<the app's data folder>/second-opinion`, never the home folder. */
  dir?: string;
  /** At most this many runs at a time (default 2). */
  parallel?: number;
}

export interface SecondOpinion {
  command: string;
  dir: string;
  parallel: number;
}

/** The user's environment first (CREWCUT_SECOND_OPINION_CMD, _DIR, _PARALLEL), then the setting. The work folder is
 *  never the home folder or the root: a command with tools works only in a folder of its own. */
export function secondOpinionConfig(setting: SecondOpinionSetting | undefined, env: NodeJS.ProcessEnv,
  userData: string, home = homedir()): SecondOpinion {
  const s = setting && typeof setting === "object" ? setting : {};
  const command = (env.CREWCUT_SECOND_OPINION_CMD || (typeof s.command === "string" ? s.command : "")).trim();
  const fallback = join(userData, "second-opinion");
  let dir = env.CREWCUT_SECOND_OPINION_DIR || (typeof s.dir === "string" ? s.dir : "") || fallback;
  if (dir === "~" || dir.startsWith("~/")) dir = join(home, dir.slice(1));
  dir = resolve(dir);
  if (dir === resolve(home) || dir === resolve("/")) dir = fallback;
  const n = Number(env.CREWCUT_SECOND_OPINION_PARALLEL || s.parallel || 2);
  const parallel = Number.isInteger(n) && n >= 1 && n <= 8 ? n : 2;
  return { command, dir, parallel };
}

export interface HelperConfig {
  /** host/crewcut-host.sh (in the app's resources, or in the repository when run from the source). */
  script: string;
  studioDir: string;
  token: string;
  secondOpinion: SecondOpinion;
  /** The app's process id: the helper stops by itself when the app is gone (a crash, a kill). */
  parentPid: number;
}

/** The helper's environment: the app's own (the screen, HOME), a PATH that also finds `claude` and the user's
 *  second-opinion tools (an app started from the menu has no terminal PATH), the studio, the key and the command. */
export function helperEnv(c: HelperConfig, base: NodeJS.ProcessEnv = process.env, os = platform(),
  home = homedir()): NodeJS.ProcessEnv {
  const path = [base.PATH ?? "", join(home, ".local", "bin"), ...extraPaths(os, home), "/bin"].filter(Boolean)
    .join(delimiter);
  const env: NodeJS.ProcessEnv = { ...base, PATH: path, CREWCUT_STUDIO_DIR: c.studioDir, [TOKEN_KEY]: c.token,
    CREWCUT_HOST_BY: "desktop app", CREWCUT_HOST_PARENT: String(c.parentPid),
    CREWCUT_SECOND_OPINION_DIR: c.secondOpinion.dir, CREWCUT_SECOND_OPINION_PARALLEL: String(c.secondOpinion.parallel) };
  if (c.secondOpinion.command) env.CREWCUT_SECOND_OPINION_CMD = c.secondOpinion.command;
  else delete env.CREWCUT_SECOND_OPINION_CMD;
  return env;
}

/** The helper's files inside the studio, as ./start.sh uses them. */
export function helperFiles(studioDir: string): { pid: string; log: string } {
  return { pid: join(studioDir, ".crewcut", "host", "helper.pid"), log: join(studioDir, ".crewcut", "logs", "host.log") };
}

/** Is `pid` a running host helper? The pid file lies in the studio, which the crew can write, so the app only ever
 *  stops a process whose command line is crewcut-host.sh. */
export function isHelperProcess(pid: number): boolean {
  if (!Number.isInteger(pid) || pid <= 1) return false;
  try {
    return readFileSync(`/proc/${pid}/cmdline`, "utf8").includes("crewcut-host.sh");
  } catch {
    try {
      return execFileSync("ps", ["-p", String(pid), "-o", "command="], { encoding: "utf8", timeout: 5000 })
        .includes("crewcut-host.sh");
    } catch {
      return false;
    }
  }
}

/** Starts and stops the helper; starts it again when it ends by itself (at most a few quick failures). */
export class HostHelper {
  private child: ChildProcess | null = null;
  private key = "";
  private stopping = false;
  private quickFailures = 0;
  private timer: NodeJS.Timeout | null = null;

  constructor(private readonly log: (line: string) => void, private readonly os = platform()) {}

  get running(): boolean {
    return this.child !== null && this.child.exitCode === null && this.child.signalCode === null;
  }

  /** Starts the helper for this studio, or leaves it running when nothing changed. */
  start(c: HelperConfig): void {
    if (this.os === "win32") {
      this.log("host helper: not on Windows yet (it is a bash script); the second opinion and the YouTube setup "
        + "through Chrome are unavailable");
      return;
    }
    if (!existsSync(c.script)) {
      this.log(`host helper: ${c.script} is missing`);
      return;
    }
    if (!c.token) {
      this.log("host helper: no key");
      return;
    }
    const key = JSON.stringify([c.script, c.studioDir, c.secondOpinion, c.parentPid]);
    if (this.running && key === this.key) return;
    this.stop();
    this.stopping = false;
    this.key = key;
    this.spawn(c);
  }

  private spawn(c: HelperConfig): void {
    const files = helperFiles(c.studioDir);
    mkdirSync(join(c.studioDir, ".crewcut", "host"), { recursive: true });
    mkdirSync(join(c.studioDir, ".crewcut", "logs"), { recursive: true });
    mkdirSync(c.secondOpinion.dir, { recursive: true });
    // one helper per studio: an older one (./start.sh, or an app that crashed) gives way
    try {
      const old = Number(readFileSync(files.pid, "utf8").trim());
      if (isHelperProcess(old)) process.kill(old, "SIGTERM");
    } catch {
      // no pid file, or the process is gone
    }
    const out = openSync(files.log, "a", 0o600);
    const started = Date.now();
    let child: ChildProcess;
    try {
      child = spawn("bash", [c.script], { env: helperEnv(c, process.env, this.os), stdio: ["ignore", out, out],
        windowsHide: true });
    } finally {
      closeSync(out);
    }
    this.child = child;
    child.on("error", (e) => this.log(`host helper: ${e.message}`));
    if (child.pid) writeFileSync(files.pid, `${child.pid}\n`);
    this.log(`host helper: started for ${c.studioDir}` + (c.secondOpinion.command
      ? `, second opinion in ${c.secondOpinion.dir}, at most ${c.secondOpinion.parallel} at a time`
      : ", no second-opinion command"));
    child.on("exit", (code, signal) => {
      if (this.child !== child) return;
      this.child = null;
      if (this.stopping) return;
      this.log(`host helper: ended (${signal ?? `exit code ${code}`}); see ${files.log}`);
      this.quickFailures = Date.now() - started < 60_000 ? this.quickFailures + 1 : 0;
      if (this.quickFailures > 3) {
        this.log("host helper: it keeps ending, so the app stops starting it until the next start");
        return;
      }
      this.timer = setTimeout(() => { this.timer = null; if (!this.stopping) this.spawn(c); }, 5000);
      this.timer.unref();
    });
  }

  /** Stops the helper (the app quits). A second opinion that runs already finishes and leaves its answer. */
  stop(): void {
    this.stopping = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    const child = this.child;
    this.child = null;
    if (child && child.exitCode === null && child.signalCode === null) child.kill("SIGTERM");
  }
}
