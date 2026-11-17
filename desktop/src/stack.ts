// The Crewcut stack, as ./start.sh runs it: the repository's compose.yaml (shipped unchanged inside the app), the
// project name "crewcut", the studio folder mounted at /studio, the LAN address for the teleprompter's QR code. The app
// adds stack/desktop.yaml (no build, no pull by Compose) and passes the Claude token from the keychain in the
// environment of the docker command only, never in a file.
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { mkdirSync } from "node:fs";
import { get } from "node:http";
import { networkInterfaces } from "node:os";
import { join } from "node:path";
import { docker, dockerEnv, type Ran } from "./docker";

export interface StackConfig {
  composeFiles: string[];
  /** Compose resolves relative paths (.env, build) against it: the app's data folder, never the user's checkout. */
  projectDir: string;
  studioDir: string;
  image: string;
  tag: string;
  port: number;
  token?: string | null;
}

export const PROJECT = "crewcut";
export const SERVICE = "crewcut";

export function composeArgs(c: StackConfig): string[] {
  return ["compose", "-p", PROJECT, "--project-directory", c.projectDir, ...c.composeFiles.flatMap((f) => ["-f", f])];
}

/** The first IPv4 address in the local network, as ./start.sh finds it (for the teleprompter's QR code). */
export function lanHost(): string | undefined {
  for (const list of Object.values(networkInterfaces())) {
    for (const a of list ?? []) {
      if (a.family === "IPv4" && !a.internal && !a.address.startsWith("169.254.")) return a.address;
    }
  }
  return undefined;
}

export function composeEnv(c: StackConfig, base: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  return {
    ...dockerEnv(base),
    CREWCUT_TAG: c.tag,
    CREWCUT_PULL_POLICY: "never",
    CREWCUT_STUDIO_DIR: c.studioDir,
    CREWCUT_IMPORT_DIR: join(c.studioDir, "import"),
    CREWCUT_PORT: String(c.port),
    CREWCUT_LAN_HOST: lanHost() ?? "",
    // Always set, also when empty: a token in the user's shell must not slip into the container unasked.
    CLAUDE_CODE_OAUTH_TOKEN: c.token ?? "",
  };
}

export async function up(c: StackConfig): Promise<Ran> {
  mkdirSync(c.studioDir, { recursive: true });
  mkdirSync(join(c.studioDir, "import"), { recursive: true });
  mkdirSync(c.projectDir, { recursive: true });
  return docker([...composeArgs(c), "up", "-d", "--no-build", "--remove-orphans"], { env: composeEnv(c), timeout: 300_000 });
}

export async function stop(c: StackConfig): Promise<Ran> {
  return docker([...composeArgs(c), "stop"], { env: composeEnv(c), timeout: 120_000 });
}

/** The last lines of the container's log, for a step that takes long (the engine install on the first start). */
export async function lastLog(c: StackConfig): Promise<string> {
  const r = await docker([...composeArgs(c), "logs", "--no-log-prefix", "--tail", "3", SERVICE], {
    env: composeEnv(c), timeout: 20_000 });
  return r.stdout.trim().split("\n").filter(Boolean).pop() ?? "";
}

/** `docker compose exec -T crewcut <args>` with pipes, for `crewcut engine connect` (JSON lines). */
export function exec(c: StackConfig, args: string[]): ChildProcessWithoutNullStreams {
  return spawn("docker", [...composeArgs(c), "exec", "-T", SERVICE, ...args], {
    env: composeEnv(c), windowsHide: true, stdio: ["pipe", "pipe", "pipe"] });
}

export function health(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const req = get({ host: "127.0.0.1", port, path: "/api/health", headers: { Host: `localhost:${port}` }, timeout: 3000 },
      (res) => {
        let body = "";
        res.on("data", (d: Buffer) => (body += d.toString()));
        res.on("end", () => {
          try {
            resolve(res.statusCode === 200 && (JSON.parse(body) as { ok?: boolean }).ok === true);
          } catch {
            resolve(false);
          }
        });
      });
    req.on("timeout", () => req.destroy());
    req.on("error", () => resolve(false));
  });
}

export interface ContainerState {
  status: string;
  restarts: number;
  exitCode: number;
}

export function parseState(line: string): ContainerState | null {
  const [status, restarts, exitCode] = line.trim().split("|");
  if (!status) return null;
  return { status, restarts: Number(restarts) || 0, exitCode: Number(exitCode) || 0 };
}

/** The Crewcut container's state: running, restarting (its start failed and Docker tries again), exited. */
export async function containerState(c: StackConfig): Promise<ContainerState | null> {
  const ps = await docker([...composeArgs(c), "ps", "-a", "-q", SERVICE], { env: composeEnv(c), timeout: 20_000 });
  const id = ps.stdout.trim().split("\n")[0];
  if (!id) return null;
  const r = await docker(["inspect", "--format", "{{.State.Status}}|{{.RestartCount}}|{{.State.ExitCode}}", id],
    { env: composeEnv(c), timeout: 20_000 });
  return r.code === 0 ? parseState(r.stdout) : null;
}

/** The container stopped or started over since `base`: its start fails, and waiting longer will not help. */
export function failing(base: ContainerState | null, now: ContainerState | null): boolean {
  if (!now) return false;
  if (now.status === "exited" || now.status === "dead") return true;
  return now.restarts > (base?.restarts ?? 0);
}

/** Waits until Crewcut answers; tick(seconds) is called every 2 s for the screen. Stops early with the reason when
 *  check() returns one (the container's start fails over and over). */
export async function waitHealthy(port: number, timeoutMs: number, tick: (seconds: number) => void,
  check?: () => Promise<string | null>): Promise<true | string> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await health(port)) return true;
    const why = check ? await check() : null;
    if (why) return why;
    tick(Math.round((Date.now() - start) / 1000));
    await new Promise((r) => setTimeout(r, 2000));
  }
  return "Crewcut did not answer in time.";
}
