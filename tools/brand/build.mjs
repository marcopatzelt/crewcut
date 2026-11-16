// Writes the static brand files of Crewcut from the one source of Slate's geometry (web/src/slate/art.ts).
//
//   node --experimental-strip-types tools/brand/build.mjs           write docs/brand/ and web/public/
//   node --experimental-strip-types tools/brand/build.mjs --check   exit 1 when a committed file is out of date
//
// PNG sizes are rendered from these SVGs in CI (tools/ci/brand_png.mjs), never on a developer machine.
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { appIcon, avatar, mark, smallIcon, standing, BOUNDS, figure } from "../../web/src/slate/art.ts";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const TEXT = JSON.parse(readFileSync(join(ROOT, "tools/brand/text-paths.json"), "utf8"));

export const LIGHT = {
  body: "#0F6E5C",
  stripe: "#34C3A4",
  face: "#FFFFFF",
  tile: "#BFEEDF",
  paper: "#FFFFFF",
  red: "#E5484D",
  soft: "#8EDCC4",
};
// For dark backgrounds without a tile: a lighter board so it stays visible on near-black.
export const DARK = { ...LIGHT, body: "#1A9078", stripe: "#5FE3C3" };
const INK = "#16201D";
const PAPER_BG = "#F7F4EC";

export const CREW = [
  ["showrunner", "headset"],
  ["scout", "magnifier"],
  ["writer", "pencil"],
  ["editor", "scissors"],
  ["critic", "clipboard"],
  ["designer", "brush"],
  ["publisher", "plane"],
  ["brand", "swatches"],
];

const f = (n) => String(Math.round(n * 100) / 100);
const inner = (svg) => svg.trim().replace(/^<svg[^>]*>/, "").replace(/<\/svg>$/, "").replace(/<title>.*?<\/title>/, "");
const viewBoxOf = (svg) => /viewBox="([^"]+)"/.exec(svg)[1].split(" ").map(Number);

/** Place one SVG inside another at (x, y) with width w. */
function place(svg, x, y, w) {
  const [vx, vy, vw] = viewBoxOf(svg);
  const s = w / vw;
  return `<g transform="translate(${f(x)} ${f(y)}) scale(${f(s)}) translate(${f(-vx)} ${f(-vy)})">${inner(svg)}</g>`;
}

function text(key, x, baseline, size, color) {
  const t = TEXT[key];
  const s = size / 100;
  return `<path transform="translate(${f(x)} ${f(baseline)}) scale(${f(s)})" d="${t.d}" fill="${color}"/>`;
}

function doc(w, h, body, title) {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" ` +
    `aria-label="${title}"><title>${title}</title>${body}</svg>\n`
  );
}

/** Slate next to the word "Crewcut", as in the reference sheet: the board a little taller than the capitals. */
function lockup(p, ink) {
  const size = 100; // font size of the word
  const cap = TEXT.wordmark.cap; // at size 100
  const markH = cap * 1.42;
  const scale = markH / BOUNDS.h;
  const markW = BOUNDS.w * scale;
  const gap = 18;
  const w = Math.ceil(markW + gap + TEXT.wordmark.width + 4);
  const h = Math.ceil(markH + 8);
  const baseline = 4 + markH - 0.6; // the word sits on the board's bottom edge
  const art = `<g transform="translate(${f(2 - BOUNDS.x * scale)} ${f(4 - BOUNDS.y * scale)}) scale(${f(scale)})">${figure(p, "plain")}</g>`;
  return doc(w, h, art + text("wordmark", 2 + markW + gap, baseline, size, ink), "Crewcut");
}

function social() {
  const W = 1280;
  const H = 640;
  let body = `<rect width="${W}" height="${H}" fill="${PAPER_BG}"/>`;
  // The lockup, centred.
  const lock = lockup(LIGHT, LIGHT.body);
  const [, , lw, lh] = viewBoxOf(lock);
  const lockW = 560;
  body += place(lock, (W - lockW) / 2, 92, lockW);
  const lockBottom = 92 + (lh * lockW) / lw;
  // The promise.
  const tagSize = 44;
  const tagW = (TEXT.tagline.width * tagSize) / 100;
  body += text("tagline", (W - tagW) / 2, lockBottom + 86, tagSize, INK);
  const subSize = 26;
  const subW = (TEXT.subline.width * subSize) / 100;
  body += text("subline", (W - subW) / 2, lockBottom + 136, subSize, "#4A5753");
  // The crew.
  const size = 92;
  const gap = 22;
  const rowW = CREW.length * size + (CREW.length - 1) * gap;
  CREW.forEach(([, prop], i) => {
    body += place(avatar(LIGHT, prop, "plain"), (W - rowW) / 2 + i * (size + gap), H - 56 - size, size);
  });
  return doc(W, H, body, "Crewcut: your Claude Code subscription, now a YouTube crew");
}

const files = {
  "docs/brand/slate.svg": mark(LIGHT, { title: "Slate, the Crewcut mascot" }) + "\n",
  "docs/brand/slate-dark.svg": mark(DARK, { title: "Slate, the Crewcut mascot" }) + "\n",
  "docs/brand/slate-icon.svg": appIcon(LIGHT, { title: "Crewcut" }) + "\n",
  "docs/brand/slate-icon-small.svg": smallIcon(LIGHT) + "\n",
  "docs/brand/crewcut-lockup.svg": lockup(LIGHT, LIGHT.body),
  "docs/brand/crewcut-lockup-dark.svg": lockup(DARK, "#F2F5F4"),
  "docs/brand/social-preview.svg": social(),
  "web/public/favicon.svg": smallIcon(LIGHT) + "\n",
  "web/public/app-icon.svg": appIcon(LIGHT, { title: "Crewcut" }) + "\n",
};
for (const [id, prop] of CREW) {
  const name = id.charAt(0).toUpperCase() + id.slice(1);
  files[`docs/brand/crew/${id}.svg`] = avatar(LIGHT, prop, "plain", { title: name }) + "\n";
}
for (const state of ["idle", "working", "waiting", "done"]) {
  files[`docs/brand/states/${state}.svg`] = avatar(LIGHT, null, state, { title: `Slate, ${state}` }) + "\n";
}
files["docs/brand/states/wave.svg"] = standing(LIGHT, "wave", { title: "Slate waving" }) + "\n";

const check = process.argv.includes("--check");
const stale = [];
for (const [path, content] of Object.entries(files)) {
  const full = join(ROOT, path);
  if (check) {
    if (!existsSync(full) || readFileSync(full, "utf8") !== content) stale.push(path);
    continue;
  }
  mkdirSync(dirname(full), { recursive: true });
  writeFileSync(full, content);
}
if (check) {
  if (stale.length) {
    console.error(`brand files out of date (run tools/brand/build.mjs): ${stale.join(", ")}`);
    process.exit(1);
  }
  console.log(`brand: ${Object.keys(files).length} files up to date`);
} else {
  console.log(`brand: wrote ${Object.keys(files).length} files under ${relative(process.cwd(), ROOT) || "."}`);
}
