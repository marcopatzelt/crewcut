// Docker on this computer: is it there, is it running, and pulling the image with real progress (the Engine API's
// byte counts, through the same socket the docker CLI uses). No Electron in here, so the tests run in plain Node.
import { execFile } from "node:child_process";
import { request } from "node:http";
import { homedir, platform } from "node:os";
import { delimiter, join } from "node:path";

/** Where Docker Desktop, OrbStack, Colima (Homebrew) and Rancher Desktop put the docker CLI. An app started from the
 *  Finder or the start menu does not get the PATH of a terminal. */
export function extraPaths(os = platform(), home = homedir()): string[] {
  if (os === "darwin") {
    return ["/usr/local/bin", "/opt/homebrew/bin", join(home, ".orbstack/bin"), join(home, ".docker/bin"),
      "/Applications/Docker.app/Contents/Resources/bin", join(home, ".rd/bin")];
  }
  if (os === "win32") {
    return ["C:\\Program Files\\Docker\\Docker\\resources\\bin", join(home, "AppData\\Local\\Programs\\Rancher Desktop\\resources\\resources\\win32\\bin")];
  }
  return ["/usr/local/bin", "/usr/bin", "/snap/bin", join(home, ".rd/bin")];
}

export function dockerEnv(base: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  const path = [base.PATH ?? base.Path ?? "", ...extraPaths()].filter(Boolean).join(delimiter);
  return { ...base, PATH: path, DOCKER_CLI_HINTS: "false" };
}

export interface Ran {
  code: number;
  stdout: string;
  stderr: string;
  missing?: boolean;
}

export function docker(args: string[], opts: { env?: NodeJS.ProcessEnv; timeout?: number } = {}): Promise<Ran> {
  return new Promise((resolve) => {
    execFile("docker", args, { env: opts.env ?? dockerEnv(), timeout: opts.timeout ?? 60_000, maxBuffer: 8 << 20,
      windowsHide: true }, (err, stdout, stderr) => {
      const e = err as (NodeJS.ErrnoException & { code?: number | string }) | null;
      resolve({
        code: e ? (typeof e.code === "number" ? e.code : 1) : 0,
        stdout: String(stdout ?? ""),
        stderr: String(stderr ?? ""),
        missing: e?.code === "ENOENT",
      });
    });
  });
}

export interface DockerState {
  /** The docker command exists. */
  cli: boolean;
  /** The engine answers. */
  running: boolean;
  /** docker compose 2.24 or newer (the compose file uses !reset and env_file with required). */
  compose: boolean;
  version?: string;
  composeVersion?: string;
  detail?: string;
}

export function composeOk(v: string | undefined): boolean {
  const m = /(\d+)\.(\d+)/.exec(v ?? "");
  if (!m) return false;
  const [maj, min] = [Number(m[1]), Number(m[2])];
  return maj > 2 || (maj === 2 && min >= 24);
}

export async function checkDocker(): Promise<DockerState> {
  const v = await docker(["version", "--format", "{{.Server.Version}}"], { timeout: 20_000 });
  if (v.missing) return { cli: false, running: false, compose: false };
  const c = await docker(["compose", "version", "--short"], { timeout: 20_000 });
  const composeVersion = c.code === 0 ? c.stdout.trim().replace(/^v/, "") : undefined;
  const state: DockerState = {
    cli: true,
    running: v.code === 0 && Boolean(v.stdout.trim()),
    compose: composeOk(composeVersion),
    version: v.stdout.trim() || undefined,
    composeVersion,
  };
  if (!state.running) state.detail = (v.stderr.trim().split("\n").pop() ?? "").slice(0, 300) || undefined;
  return state;
}

/** The socket of the current docker context, for the Engine API: a unix socket or a Windows named pipe. */
export function socketFromHost(host: string): string | null {
  if (host.startsWith("unix://")) return host.slice("unix://".length);
  if (host.startsWith("npipe://")) return host.slice("npipe://".length).replace(/\//g, "\\");
  return null;
}

export async function dockerSocket(): Promise<string | null> {
  const r = await docker(["context", "inspect", "--format", "{{.Endpoints.docker.Host}}"], { timeout: 15_000 });
  const host = r.code === 0 ? r.stdout.trim() : "";
  if (host) return socketFromHost(host);
  return platform() === "win32" ? "\\\\.\\pipe\\docker_engine" : "/var/run/docker.sock";
}

export async function imageExists(ref: string): Promise<boolean> {
  return (await docker(["image", "inspect", "--format", "{{.Id}}", ref], { timeout: 20_000 })).code === 0;
}

export interface Progress {
  /** Bytes downloaded and the bytes to download, over every layer whose size is known. */
  current: number;
  total: number;
  layersDone: number;
  layers: number;
}

/** Adds up the Engine API's pull messages ({status, id, progressDetail}) into one progress. */
export class PullProgress {
  private layers = new Map<string, { current: number; total: number; done: boolean }>();

  feed(msg: { status?: string; id?: string; progressDetail?: { current?: number; total?: number }; error?: string }):
    Progress | null {
    if (msg.error) throw new Error(msg.error);
    const id = msg.id;
    const status = msg.status ?? "";
    if (!id || !/^[0-9a-f]{6,}$/.test(id)) return null;
    const layer = this.layers.get(id) ?? { current: 0, total: 0, done: false };
    if (status === "Downloading" && msg.progressDetail) {
      layer.total = msg.progressDetail.total ?? layer.total;
      layer.current = msg.progressDetail.current ?? layer.current;
    } else if (/^(Download complete|Verifying Checksum)$/.test(status)) {
      layer.current = layer.total;
    } else if (/^(Pull complete|Already exists)$/.test(status)) {
      layer.current = layer.total;
      layer.done = true;
    }
    this.layers.set(id, layer);
    return this.now();
  }

  now(): Progress {
    let current = 0;
    let total = 0;
    let done = 0;
    for (const l of this.layers.values()) {
      current += Math.min(l.current, l.total);
      total += l.total;
      if (l.done) done += 1;
    }
    return { current, total, layersDone: done, layers: this.layers.size };
  }
}

/** Pulls image:tag through the Engine API and reports the bytes as they come. */
export function pullImage(socketPath: string, image: string, tag: string, onProgress: (p: Progress) => void):
  Promise<void> {
  const progress = new PullProgress();
  return new Promise((resolve, reject) => {
    const req = request(
      { socketPath, method: "POST", path: `/images/create?fromImage=${encodeURIComponent(image)}&tag=${encodeURIComponent(tag)}` },
      (res) => {
        if ((res.statusCode ?? 500) >= 400) {
          let body = "";
          res.on("data", (d: Buffer) => (body += d.toString()));
          res.on("end", () => {
            let text = body.trim();
            try {
              text = (JSON.parse(body) as { message?: string }).message ?? text;
            } catch {
              // not JSON: keep the text
            }
            reject(new Error(text || `Docker answered ${res.statusCode}`));
          });
          return;
        }
        let buf = "";
        res.on("data", (d: Buffer) => {
          buf += d.toString();
          let nl: number;
          while ((nl = buf.indexOf("\n")) >= 0) {
            const line = buf.slice(0, nl).trim();
            buf = buf.slice(nl + 1);
            if (!line) continue;
            try {
              const p = progress.feed(JSON.parse(line));
              if (p) onProgress(p);
            } catch (e) {
              req.destroy();
              reject(e instanceof Error ? e : new Error(String(e)));
              return;
            }
          }
        });
        res.on("end", () => resolve());
        res.on("error", reject);
      },
    );
    req.on("error", reject);
    req.end();
  });
}

/** One line for the screen: "1.2 GB of 3.4 GB". */
export function bytesWords(current: number, total: number): string {
  const gb = (n: number) => (n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : `${Math.round(n / 1e6)} MB`);
  return total ? `${gb(current)} of ${gb(total)}` : "";
}
