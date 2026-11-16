// DESIGN.md rule 5 and 16: no Apple system font ships with Crewcut. The licence of Apple's fonts allows them only for
// mock-ups and forbids embedding them, so on Apple devices the app asks for the installed font through system-ui and
// ships nothing. This check fails on any font file in the repository or in dist/ whose file name or inner name
// contains one of the names below, and on any @font-face that declares or loads one of them.
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { extname, join, relative } from "node:path";
import { brotliDecompressSync, inflateSync } from "node:zlib";
import { report, walk, webRoot } from "./lib.mjs";

const NAMES = ["SF Pro", "SF Compact", "SFNS", "SF Mono", "New York"];
const FONT_EXT = new Set([".ttf", ".otf", ".woff", ".woff2", ".ttc", ".dfont", ".eot"]);
const repoRoot = join(webRoot, "..");
const problems = [];

// "SF Pro" also matches "SFPro", "SF-Pro" and "sf_pro" in file names.
const loose = (name) => new RegExp(name.split(" ").join("[\\s_-]?"), "i");
const nameRes = NAMES.map((n) => ({ n, re: loose(n) }));

function repoFiles() {
  try {
    const out = execFileSync("git", ["ls-files", "--cached", "--others", "--exclude-standard", "-z"], {
      cwd: repoRoot,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    });
    return out
      .split("\0")
      .filter(Boolean)
      .map((f) => join(repoRoot, f));
  } catch {
    // No git here (for example inside a container build): check the web app's own files.
    return walk(webRoot, [""]).filter((f) => !f.includes("/node_modules/") && !f.includes("/dist/"));
  }
}

function utf16be(s) {
  const b = Buffer.alloc(s.length * 2);
  for (let i = 0; i < s.length; i += 1) b.writeUInt16BE(s.charCodeAt(i), i * 2);
  return b;
}

function base128(buf, at) {
  let value = 0;
  for (let i = 0; i < 5; i += 1) {
    const byte = buf[at.i++];
    value = value * 128 + (byte & 0x7f);
    if (!(byte & 0x80)) return value;
  }
  throw new Error("bad UIntBase128");
}

/** The bytes in which a font keeps its names, readable: WOFF tables inflated, the WOFF2 stream decompressed. */
function fontBytes(file, raw) {
  const ext = extname(file).toLowerCase();
  if (ext === ".woff" && raw.toString("latin1", 0, 4) === "wOFF") {
    const parts = [];
    const n = raw.readUInt16BE(12);
    for (let t = 0; t < n; t += 1) {
      const e = 44 + t * 20;
      const offset = raw.readUInt32BE(e + 4);
      const comp = raw.readUInt32BE(e + 8);
      const orig = raw.readUInt32BE(e + 12);
      const data = raw.subarray(offset, offset + comp);
      parts.push(comp < orig ? inflateSync(data) : data);
    }
    return Buffer.concat(parts);
  }
  if (ext === ".woff2" && raw.toString("latin1", 0, 4) === "wOF2") {
    const numTables = raw.readUInt16BE(12);
    const compressed = raw.readUInt32BE(20);
    const at = { i: 48 };
    for (let t = 0; t < numTables; t += 1) {
      const flags = raw[at.i++];
      const tag = flags & 0x3f;
      if (tag === 63) at.i += 4;
      base128(raw, at); // original length
      const version = (flags >> 6) & 0x03;
      const transformed = tag === 10 || tag === 11 ? version !== 3 : version !== 0; // glyf and loca: 3 means none
      if (transformed) base128(raw, at);
    }
    if (raw.toString("latin1", 4, 8) === "ttcf") return raw; // a collection: search the raw bytes as well as we can
    return brotliDecompressSync(raw.subarray(at.i, at.i + compressed));
  }
  return raw;
}

function checkFont(file) {
  const shown = relative(repoRoot, file);
  const base = file.split("/").pop() ?? file;
  for (const { n, re } of nameRes) if (re.test(base)) problems.push(`${shown}: the file name contains "${n}"`);
  let bytes;
  try {
    bytes = fontBytes(file, readFileSync(file));
  } catch (e) {
    problems.push(`${shown}: could not read the font (${e.message}); remove it or check it by hand`);
    return;
  }
  for (const n of NAMES) {
    if (bytes.includes(Buffer.from(n, "latin1")) || bytes.includes(utf16be(n))) {
      problems.push(`${shown}: the font's inner name contains "${n}"`);
    }
  }
}

/** An @font-face block may neither declare one of the names nor load one through local() or a file. */
function checkCss(file, text) {
  const shown = relative(repoRoot, file);
  for (const m of text.matchAll(/@font-face\s*\{([^}]*)\}/g)) {
    for (const { n, re } of nameRes) if (re.test(m[1])) problems.push(`${shown}: @font-face names "${n}"`);
  }
}

const files = repoFiles();
const dist = join(webRoot, "dist");
if (existsSync(dist)) files.push(...walk(dist, [""]));

let fonts = 0;
let sheets = 0;
for (const file of new Set(files)) {
  if (file.includes("/node_modules/")) continue;
  const ext = extname(file).toLowerCase();
  if (FONT_EXT.has(ext)) {
    fonts += 1;
    checkFont(file);
  } else if (ext === ".css" && existsSync(file)) {
    sheets += 1;
    checkCss(file, readFileSync(file, "utf8"));
  }
}

report("check:fonts", problems, `no Apple system font in ${fonts} font files and ${sheets} style sheets`);
