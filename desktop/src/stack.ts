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

/** Waits until Crewcut answers; tick(seconds) is called every 2 s for the screen. */
export async function waitHealthy(port: number, timeoutMs: number, tick: (seconds: number) => void): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await health(port)) return true;
    tick(Math.round((Date.now() - start) / 1000));
    await new Promise((r) => setTimeout(r, 2000));
  }
  return false;
}
