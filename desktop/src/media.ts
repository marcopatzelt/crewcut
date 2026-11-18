import { createHash, randomUUID } from "node:crypto";
import { createReadStream, createWriteStream } from "node:fs";
import { lstat, mkdir, readdir, readFile, realpath, rename, stat, unlink, writeFile } from "node:fs/promises";
import { basename, extname, isAbsolute, join, relative, resolve } from "node:path";
import { pipeline } from "node:stream/promises";
import { Transform } from "node:stream";

export interface MediaRoot { path: string; label: string }
const MEDIA = new Set(".mp4 .mov .mxf .mts .m2ts .avi .mkv .webm .m4v .wav .mp3 .m4a .aac .flac .ogg .aiff .aif .jpg .jpeg .png .webp .heic .tif .tiff .dng .arw .cr2 .cr3 .nef".split(" "));
const ID = /^[a-f0-9]{32}$/;

export async function contained(root: string, path: string): Promise<string> {
  if (isAbsolute(path)) throw new Error("Use a path relative to the media source.");
  const base = await realpath(root), target = await realpath(resolve(base, path));
  const rel = relative(base, target);
  if (rel === ".." || rel.startsWith("../") || rel.startsWith("..\\") || isAbsolute(rel)) throw new Error("Path leaves the source.");
  return target;
}

/** Re-scan mounted drives on every request, not only at app startup. */
export async function removableRoots(platform: string, home: string): Promise<MediaRoot[]> {
  const roots: MediaRoot[] = [];
  const parents = platform === "darwin" ? ["/Volumes"] : platform === "linux" ? [join("/run/media", basename(home)), join("/media", basename(home)), "/media"] : [];
  for (const parent of parents) {
    for (const entry of await readdir(parent, { withFileTypes: true }).catch(() => [])) {
      if (!entry.isDirectory() || entry.name === basename(home)) continue;
      roots.push({ path: join(parent, entry.name), label: entry.name });
    }
  }
  if (platform === "win32") {
    for (const letter of "DEFGHIJKLMNOPQRSTUVWXYZ") {
      const path = `${letter}:\\`;
      if (path.toLowerCase() !== home.slice(0, 3).toLowerCase()) roots.push({ path, label: `Drive ${letter}` });
    }
  }
  return roots;
}

export class DesktopMedia {
  private busy = false;
  constructor(private studio: () => string, private roots: () => Promise<MediaRoot[]>) {}

  async sources() {
    const sources = [];
    const seen = new Set<string>();
    for (const entry of await this.roots()) {
      try {
        const path = await realpath(entry.path);
        if (seen.has(path) || !(await stat(path)).isDirectory()) continue;
        seen.add(path);
        sources.push({ id: createHash("sha256").update(path).digest("hex").slice(0, 24), label: entry.label, path });
      } catch { /* missing or disconnected source */ }
    }
    return sources;
  }

  async execute(request: Record<string, unknown>) {
    const sources = await this.sources();
    if (request.action === "sources") return { sources: sources.map(({ id, label }) => ({ id, label })) };
    const source = sources.find(item => item.id === request.source);
    if (!source) throw new Error("Media source is disconnected. List sources again.");
    if (typeof request.path !== "string") throw new Error("Missing media path.");
    const path = await contained(source.path, request.path);
    if (request.action === "list") {
      const offset = Number(request.offset ?? 0);
      if (!Number.isInteger(offset) || offset < 0) throw new Error("Invalid offset.");
      const entries = (await readdir(path, { withFileTypes: true })).filter(e => !e.name.startsWith(".") &&
        (e.isDirectory() || (e.isFile() && MEDIA.has(extname(e.name).toLowerCase())))).sort((a, b) => a.name.localeCompare(b.name));
      return { entries: await Promise.all(entries.slice(offset, offset + 200).map(async e => {
        const info = await stat(join(path, e.name));
        return { name: e.name, path: join(request.path as string, e.name), directory: e.isDirectory(), bytes: info.size, modified: info.mtime.toISOString() };
      })), next_offset: offset + 200 < entries.length ? offset + 200 : null, total: entries.length };
    }
    if (request.action !== "import" || typeof request.episode !== "string" || !/^[A-Za-z0-9_-]+$/.test(request.episode)) throw new Error("Invalid import request.");
    if (!MEDIA.has(extname(path).toLowerCase()) || !(await stat(path)).isFile()) throw new Error("Choose a media file.");
    // Resolve every destination under the studio; a studio symlink must not become arbitrary host writes.
    const studio = await realpath(this.studio());
    const episode = await contained(studio, join("episodes", request.episode));
    if (!(await stat(join(episode, "project.json"))).isFile()) throw new Error("Unknown episode.");
    await mkdir(join(studio, "inbox"), { recursive: true });
    const inbox = await contained(studio, "inbox");
    await mkdir(join(inbox, request.episode), { recursive: true });
    const destination = await contained(studio, join("inbox", request.episode));
    const name = `${randomUUID()}-${basename(path)}`;
    const target = join(destination, name), partial = `${target}.part`;
    const before = await stat(path);
    const hash = createHash("sha256");
    try {
      await pipeline(createReadStream(path), new Transform({ transform(chunk, _encoding, callback) { hash.update(chunk); callback(null, chunk); } }), createWriteStream(partial, { flags: "wx" }));
      const sha256 = hash.digest("hex");
      const copied = createHash("sha256");
      for await (const chunk of createReadStream(partial)) copied.update(chunk);
      const after = await stat(path);
      if (copied.digest("hex") !== sha256 || before.size !== after.size || before.mtimeMs !== after.mtimeMs) throw new Error("Source changed or copy check failed. Try again after recording stops.");
      await rename(partial, target);
      return { file: `/studio/inbox/${request.episode}/${name}`, bytes: after.size, sha256, source_unchanged: true };
    } catch (error) { await unlink(partial).catch(() => undefined); throw error; }
  }

  async poll() {
    if (this.busy) return;
    this.busy = true;
    try {
      const studio = await realpath(this.studio());
      const dir = await contained(studio, ".crewcut/desktop-media").catch(() => null);
      if (!dir) return;
      for (const name of await readdir(dir)) {
        if (!/^[a-f0-9]{32}\.json$/.test(name)) continue;
        const file = join(dir, name), info = await lstat(file);
        if (!info.isFile() || info.isSymbolicLink() || info.size > 16384) continue;
        let request: Record<string, unknown>;
        try { request = JSON.parse(await readFile(file, "utf8")); } catch { continue; }
        if (!request || request.status !== "pending" || typeof request.id !== "string" || !ID.test(request.id) || name !== `${request.id}.json`) continue;
        const save = async (result: object) => {
          // Re-check the queue before writes; the agent controls studio files.
          if (await contained(studio, ".crewcut/desktop-media") !== dir) throw new Error("Queue moved.");
          const temp = join(dir, `${randomUUID()}.tmp`);
          await writeFile(temp, JSON.stringify({ ...request, ...result }), { flag: "wx", mode: 0o600 });
          await rename(temp, file);
        };
        try {
          if (typeof request.created !== "number" || Math.abs(Date.now() - request.created * 1000) > 120000) throw new Error("Request expired. Submit it again.");
          await save({ status: "running" });
          const result = await this.execute(request);
          await save({ status: "done", ...result });
        } catch (error) { await save({ status: "failed", message: error instanceof Error ? error.message : "Media request failed." }); }
        break;
      }
    } finally { this.busy = false; }
  }
}
