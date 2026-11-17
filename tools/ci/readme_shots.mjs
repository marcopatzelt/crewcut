// README images, rendered in CI only (never on a laptop). The app draws its own desk (the rendered wallpaper) and its
// glass window, so this script only opens it in demo mode and takes the picture: 1440 x 1000, the width the design
// is made for, at twice the pixel density (2880 x 2000 PNG), light and dark, plus a short animation of the demo.
//   node tools/ci/readme_shots.mjs <base url of web/dist> <out dir>
// Needs the `playwright` package (CI installs it) and ffmpeg for the animation.
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { mkdirSync, readdirSync, renameSync } from "node:fs";
import { join } from "node:path";

const [base, out] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const W = 1440;
const H = 1000;
// The main demo episode: thumbnails, the cut, the commercial's 3D scenes and a running GPU rental.
const EPISODE = "#/e/012-website-100-times";

/** Waits until the pictures in view have loaded and the fonts are ready, so no frame shows half a page. */
async function settle(page) {
  await page.waitForLoadState("networkidle");
  await page.evaluate(async () => {
    await document.fonts.ready;
    const imgs = Array.from(document.images).filter((i) => !i.complete);
    await Promise.all(imgs.map((i) => new Promise((r) => { i.onload = i.onerror = r; })));
  });
}

async function still(browser, theme, hash, name) {
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 2, colorScheme: theme });
  await page.goto(`${base}/index.html?demo=1&theme=${theme}${hash}`, { waitUntil: "load" });
  await settle(page);
  await page.waitForTimeout(2500); // Slate's states play once and hold still
  await page.screenshot({ path: join(out, `${name}-${theme}.png`) });
  await page.close();
}

async function animation(browser) {
  const dir = join(out, "video-tmp");
  const ctx = await browser.newContext({
    viewport: { width: W, height: H }, colorScheme: "dark",
    recordVideo: { dir, size: { width: W, height: H } },
  });
  const page = await ctx.newPage();
  // Play mode opens episode 012 by itself; the card plays in its crew chat.
  await page.goto(`${base}/index.html?demo=1&play=1&theme=dark`, { waitUntil: "load" });
  await settle(page);
  try {
    await page.waitForFunction(() => window.__crewcutPlayDone === true, null, { timeout: 15000 });
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
    "-vf", "scale=1440:-2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", "-an", join(out, "crewcut-demo.mp4")]);
}

const browser = await chromium.launch();
for (const theme of ["dark", "light"]) {
  await still(browser, theme, EPISODE, "crewcut");
  await still(browser, theme, "#/episodes", "crewcut-episodes");
}
await animation(browser);
await browser.close();
console.log("README images in", out);
