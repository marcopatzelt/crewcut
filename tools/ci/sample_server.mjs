// The CI picture server: the built web app (web/dist) with its /api answered from the sample data in
// tests/web-sample, so the README, docs and landing pictures show real-looking content while the app itself ships no
// sample data at all. CI only, never on a laptop and never in the image.
//
//   web/node_modules/.bin/esbuild tests/web-sample/backend.ts --bundle --platform=node --format=esm \
//     --outfile=/tmp/sample-backend.mjs
//   node tools/ci/sample_server.mjs /tmp/sample-backend.mjs web/dist tests/web-sample/public 8099
//
// Routes: /api/* from the sample backend (the same calls as docs/api.md), /api/events as a real server-sent event
// stream, /api/files/<episode>/<path> and /sample/* from the sample pictures, /p/sample-token for the teleprompter,
// everything else from web/dist (the app). Control routes for the scripted README animation:
//   POST /__sample/reset[?play=1]   fresh sample data (play: the start of the scripted sequence)
//   POST /__sample/play/card-in     the GPU card springs into the crew chat
//   POST /__sample/play/after-yes   after the yes: the rented GPU starts
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const [bundle, dist, samplePublic, portArg] = process.argv.slice(2);
if (!bundle || !dist || !samplePublic) {
  console.error("usage: node sample_server.mjs <bundled backend> <web dist> <sample public> [port]");
  process.exit(2);
}
const port = Number(portArg || 8099);
const { createSampleBackend, makeSample } = await import(pathToFileURL(resolve(bundle)).href);

const TYPES = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
  ".woff": "font/woff", ".woff2": "font/woff2", ".mp4": "video/mp4", ".webm": "video/webm", ".md": "text/plain",
  ".webmanifest": "application/manifest+json",
};

const streams = new Set();
let backend;
let unsubscribe = () => undefined;
function reset(play) {
  unsubscribe();
  backend = createSampleBackend({ latency: 0, play, base: "/" });
  unsubscribe = backend.subscribe((kind, data) => {
    for (const res of streams) res.write(`event: ${kind}\ndata: ${JSON.stringify(data)}\n\n`);
  });
}
reset(false);

const script = makeSample().script;
let control = { playing: false, speed: 1, position: 0, mirror: false, size: 1 };

function sendFile(res, root, rel) {
  const base = resolve(root);
  const file = normalize(join(base, rel));
  if (!file.startsWith(base) || !existsSync(file) || !statSync(file).isFile()) return false;
  res.writeHead(200, { "content-type": TYPES[extname(file).toLowerCase()] ?? "application/octet-stream" });
  createReadStream(file).pipe(res);
  return true;
}

function json(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body ?? null));
}

async function readBody(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  if (!chunks.length) return undefined;
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    return undefined;
  }
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${port}`);
  const path = decodeURIComponent(url.pathname);
  try {
    if (path === "/__sample/reset" && req.method === "POST") {
      reset(url.searchParams.get("play") === "1");
      return json(res, 200, { ok: true });
    }
    if (path === "/__sample/play/card-in" && req.method === "POST") {
      backend.play.cardIn();
      return json(res, 200, { ok: true });
    }
    if (path === "/__sample/play/after-yes" && req.method === "POST") {
      await backend.play.afterYes();
      return json(res, 200, { ok: true });
    }
    if (path === "/api/events") {
      res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache", connection: "keep-alive" });
      res.write(": sample data\n\n");
      streams.add(res);
      req.on("close", () => streams.delete(res));
      return;
    }
    if (path.startsWith("/api/files/")) {
      const [episode, ...rest] = url.pathname.slice("/api/files/".length).split("/").map(decodeURIComponent);
      const mapped = backend.fileUrl(episode, rest.join("/"));
      if (mapped.startsWith("/sample/") && sendFile(res, samplePublic, mapped.slice("/sample/".length))) return;
      return json(res, 404, { detail: "No such file in the sample data." });
    }
    if (path.startsWith("/api/")) {
      const body = req.method === "GET" ? undefined : await readBody(req);
      try {
        const out = await backend.request(req.method, url.pathname + url.search, body);
        return out === undefined ? (res.writeHead(204), res.end()) : json(res, 200, out);
      } catch (e) {
        return json(res, e?.status || 500, { detail: e?.message || "Sample backend error." });
      }
    }
    if (path.startsWith("/sample/") && sendFile(res, samplePublic, path.slice("/sample/".length))) return;
    const prompter = path.match(/^\/p\/[^/]+(\/(script|control))?$/);
    if (prompter) {
      if (prompter[2] === "script") return json(res, 200, script);
      if (prompter[2] === "control") {
        if (req.method === "POST") control = { ...control, ...((await readBody(req)) ?? {}) };
        return json(res, 200, control);
      }
      if (sendFile(res, dist, "prompter.html")) return;
    }
    if (path !== "/" && sendFile(res, dist, path.slice(1))) return;
    if (sendFile(res, dist, "index.html")) return;
    res.writeHead(404);
    res.end();
  } catch (e) {
    console.error(e);
    if (!res.headersSent) json(res, 500, { detail: String(e) });
  }
});
server.listen(port, "127.0.0.1", () => console.log(`sample data server on http://localhost:${port}`));
