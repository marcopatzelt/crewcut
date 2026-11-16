// README images, rendered in CI only (never on a laptop): the app in demo mode as a window with a soft shadow on a
// calm background, at twice the pixel density, light and dark, and a short animation of the scripted demo.
//   node tools/ci/readme_shots.mjs <base url of web/dist> <out dir>
// Needs the `playwright` package (CI installs it) and ffmpeg for the animation.
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { mkdirSync, readdirSync, renameSync } from "node:fs";
import { join } from "node:path";

const [base, out] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const W = 1600, H = 1000, PAD = 80;

function framePage(theme, query) {
  const bg = theme === "dark"
    ? "radial-gradient(1200px 700px at 20% 10%, #23302d 0%, transparent 60%), radial-gradient(900px 600px at 90% 100%, #1d2226 0%, transparent 60%), #111214"
    : "radial-gradient(1200px 700px at 20% 10%, #e3ece8 0%, transparent 60%), radial-gradient(900px 600px at 90% 100%, #e8e8ee 0%, transparent 60%), #f3f3f1";
  const shadow = theme === "dark"
    ? "0 0 0 0.5px rgba(255,255,255,.14), 0 30px 80px rgba(0,0,0,.65), 0 8px 24px rgba(0,0,0,.4)"
    : "0 0 0 0.5px rgba(0,0,0,.10), 0 30px 80px rgba(0,0,0,.22), 0 8px 24px rgba(0,0,0,.10)";
  return `<!doctype html><html><head><meta charset="utf-8"><style>
    html,body{margin:0;width:${W + 2 * PAD}px;height:${H + 2 * PAD}px;background:${bg};overflow:hidden}
    .win{position:absolute;left:${PAD}px;top:${PAD}px;width:${W}px;height:${H}px;border-radius:18px;overflow:hidden;
      box-shadow:${shadow}}
    iframe{width:100%;height:100%;border:0;display:block}
  </style></head><body><div class="win"><iframe src="${base}/index.html?demo=1&theme=${theme}${query}"></iframe></div>
  </body></html>`;
}

async function still(browser, theme) {
  const page = await browser.newPage({
    viewport: { width: W + 2 * PAD, height: H + 2 * PAD }, deviceScaleFactor: 2, colorScheme: theme,
  });
  await page.setContent(framePage(theme, ""), { waitUntil: "load" });
  await page.frames()[1].waitForLoadState("networkidle");
  await page.waitForTimeout(2500);
  await page.screenshot({ path: join(out, `crewcut-${theme}.png`) });
  await page.close();
}

async function animation(browser) {
  const dir = join(out, "video-tmp");
  const ctx = await browser.newContext({
    viewport: { width: W + 2 * PAD, height: H + 2 * PAD }, colorScheme: "light",
    recordVideo: { dir, size: { width: W + 2 * PAD, height: H + 2 * PAD } },
  });
  const page = await ctx.newPage();
  await page.setContent(framePage("light", "&play=1"), { waitUntil: "load" });
  const app = page.frames()[1];
  await app.waitForLoadState("networkidle");
  try {
    await app.waitForFunction(() => window.__crewcutPlayDone === true, null, { timeout: 15000 });
  } catch {
    console.error("the demo timeline did not report done within 15 s; recording what is there");
  }
  await page.waitForTimeout(1200);
  await ctx.close();
  const file = readdirSync(dir).find((f) => f.endsWith(".webm"));
  renameSync(join(dir, file), join(out, "crewcut-demo.webm"));
  // animated WebP for the README (shows inline on GitHub), 1200 px wide, 20 frames per second, no sound
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-ss", "0.4", "-i", join(out, "crewcut-demo.webm"),
    "-vf", "fps=20,scale=1200:-1:flags=lanczos", "-c:v", "libwebp_anim", "-lossless", "0", "-q:v", "72",
    "-loop", "0", "-an", join(out, "crewcut-demo.webp")]);
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-ss", "0.4", "-i", join(out, "crewcut-demo.webm"),
    "-vf", "scale=1600:-2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", "-an", join(out, "crewcut-demo.mp4")]);
}

const browser = await chromium.launch();
await still(browser, "light");
await still(browser, "dark");
await animation(browser);
await browser.close();
console.log("README images in", out);
