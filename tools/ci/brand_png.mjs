// PNG sizes of the brand files, rendered in CI only (never on a laptop) from the SVGs that tools/brand/build.mjs writes.
//   node tools/ci/brand_png.mjs <docs/brand dir> <out dir>
// Writes icons/slate-icon-<size>.png (16 and 32 from the small icon, 48 to 1024 from the app icon), social-preview.png
// (1280x640) and crew/<id>.png (256). Needs the `playwright` package (CI installs it).
import { chromium } from "playwright";
import { mkdirSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const [src, out] = process.argv.slice(2);
const jobs = [];
for (const s of [16, 32]) jobs.push(["slate-icon-small.svg", s, s, `icons/slate-icon-${s}.png`]);
for (const s of [48, 64, 128, 180, 192, 256, 512, 1024]) jobs.push(["slate-icon.svg", s, s, `icons/slate-icon-${s}.png`]);
jobs.push(["slate.svg", 512, 512, "slate-512.png"]);
jobs.push(["social-preview.svg", 1280, 640, "social-preview.png"]);
for (const f of readdirSync(join(src, "crew"))) jobs.push([`crew/${f}`, 256, 256, `crew/${f.replace(".svg", ".png")}`]);

const browser = await chromium.launch();
for (const [file, w, h, name] of jobs) {
  const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  const data = Buffer.from(readFileSync(join(src, file))).toString("base64");
  await page.setContent(
    `<!doctype html><html><body style="margin:0;background:transparent">` +
      `<img src="data:image/svg+xml;base64,${data}" width="${w}" height="${h}" style="display:block"></body></html>`,
  );
  await page.waitForFunction(() => document.images[0]?.complete);
  const dest = join(out, name);
  mkdirSync(join(dest, ".."), { recursive: true });
  await page.screenshot({ path: dest, omitBackground: true, clip: { x: 0, y: 0, width: w, height: h } });
  await page.close();
  console.log(`${name} ${w}x${h}`);
}
await browser.close();
