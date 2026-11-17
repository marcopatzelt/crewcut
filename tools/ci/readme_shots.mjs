// README images, rendered in CI only (never on a laptop). The app fills the page from edge to edge; this script opens
// it against the CI picture server (tools/ci/sample_server.mjs, sample data from tests/web-sample) and takes the
// picture: 1440 x 1000, the width the design is made for, at twice the pixel density (2880 x 2000 PNG), light and dark,
// plus a short animation in which the script presses the real buttons.
//   node tools/ci/readme_shots.mjs <base url of the sample server> <out dir>
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
  // Not "networkidle": the live event stream stays open, as with the real server.
  await page.waitForSelector("main h1", { timeout: 15000 });
  await page.waitForTimeout(800);
  await page.evaluate(async () => {
    await document.fonts.ready;
    const imgs = Array.from(document.images).filter((i) => !i.complete);
    await Promise.all(imgs.map((i) => new Promise((r) => { i.onload = i.onerror = r; })));
  });
}

async function still(browser, theme, hash, name) {
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 2, colorScheme: theme });
  await page.goto(`${base}/index.html?theme=${theme}${hash}`, { waitUntil: "load" });
  await settle(page);
  await page.waitForTimeout(2500); // Slate's states play once and hold still
  await page.screenshot({ path: join(out, `${name}-${theme}.png`) });
  await page.close();
}

async function animation(browser) {
  const dir = join(out, "video-tmp");
  await fetch(`${base}/__sample/reset?play=1`, { method: "POST" }); // the start of the sequence: no rented GPU yet
  const ctx = await browser.newContext({
    viewport: { width: W, height: H }, colorScheme: "dark",
    recordVideo: { dir, size: { width: W, height: H } },
  });
  const page = await ctx.newPage();
  await page.goto(`${base}/index.html?theme=dark${EPISODE}`, { waitUntil: "load" });
  await settle(page);
  await page.waitForTimeout(600);
  // 1. The Editor asks: the GPU card springs into the crew chat with "On this machine" chosen.
  await fetch(`${base}/__sample/play/card-in`, { method: "POST" });
  const card = page.locator("[data-open-card]").filter({ has: page.locator('[data-way="rented"]') }).last();
  await card.waitFor({ timeout: 10000 });
  await page.waitForTimeout(1400);
  // 2. The choice moves to the rented GPU; the button text follows.
  await card.locator('[data-way="rented"]').click();
  await page.waitForTimeout(1300);
  // 3. The button is pressed, then released: the yes goes out (the real POST) and the card folds to one line.
  const button = card.locator("[data-accept]");
  await button.evaluate((b) => b.setAttribute("data-pressed", "true"));
  await page.waitForTimeout(220);
  await button.evaluate((b) => b.removeAttribute("data-pressed"));
  await button.click();
  await page.waitForTimeout(250);
  // 4. The rented GPU starts: a new row slides into the crew chat, the GPU card and the render tiles appear.
  await fetch(`${base}/__sample/play/after-yes`, { method: "POST" });
  await page.waitForTimeout(3900);
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
await fetch(`${base}/__sample/reset`, { method: "POST" });
await browser.close();
console.log("README images in", out);
