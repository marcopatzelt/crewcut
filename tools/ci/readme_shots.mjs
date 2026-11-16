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
const W = 1600, H = 1000, PAD = 80, TITLE = 38;

// A calm, self-made wallpaper (no photos): sky and three soft hills in Crewcut's greens.
function wallpaper(theme) {
  const c = theme === "dark"
    ? { sky1: "#0d1715", sky2: "#18302a", h1: "#1e3d35", h2: "#17594a", h3: "#0f6e5c" }
    : { sky1: "#d7f1e8", sky2: "#f5f2ea", h1: "#a8e2cd", h2: "#5fbf9f", h3: "#2e9a7c" };
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1760 1160" preserveAspectRatio="xMidYMid slice">
    <defs><linearGradient id="s" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${c.sky1}"/>
    <stop offset="1" stop-color="${c.sky2}"/></linearGradient></defs>
    <rect width="1760" height="1160" fill="url(#s)"/>
    <path d="M0 760 C320 640 620 700 900 760 S1460 660 1760 720 V1160 H0Z" fill="${c.h1}"/>
    <path d="M0 880 C360 780 760 900 1080 860 S1560 800 1760 860 V1160 H0Z" fill="${c.h2}"/>
    <path d="M0 1010 C420 940 900 1040 1300 990 S1640 960 1760 990 V1160 H0Z" fill="${c.h3}"/>
  </svg>`;
  return `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}") center / cover no-repeat`;
}

// The app as a macOS window: a title bar with the three traffic lights, a large soft shadow, on the wallpaper.
function framePage(theme, query, hash = "") {
  const dark = theme === "dark";
  const shadow = dark
    ? "0 0 0 0.5px rgba(255,255,255,.16), 0 40px 90px rgba(0,0,0,.6), 0 10px 30px rgba(0,0,0,.4)"
    : "0 0 0 0.5px rgba(0,0,0,.14), 0 40px 90px rgba(10,40,32,.30), 0 10px 30px rgba(10,40,32,.14)";
  const bar = dark ? "rgba(38,38,40,.92)" : "rgba(246,246,244,.92)";
  const ink = dark ? "#c7c7cc" : "#55555a";
  return `<!doctype html><html><head><meta charset="utf-8"><style>
    html,body{margin:0;width:${W + 2 * PAD}px;height:${H + 2 * PAD + TITLE}px;background:${wallpaper(theme)};overflow:hidden}
    .win{position:absolute;left:${PAD}px;top:${PAD}px;width:${W}px;height:${H + TITLE}px;border-radius:12px;overflow:hidden;
      box-shadow:${shadow};display:flex;flex-direction:column}
    .bar{height:${TITLE}px;flex:none;background:${bar};display:flex;align-items:center;position:relative;
      box-shadow:inset 0 -0.5px 0 ${dark ? "rgba(255,255,255,.10)" : "rgba(0,0,0,.10)"}}
    .lights{display:flex;gap:8px;padding-left:16px}
    .lights i{width:12px;height:12px;border-radius:50%;display:block;box-shadow:inset 0 0 0 .5px rgba(0,0,0,.18)}
    .title{position:absolute;left:0;right:0;text-align:center;font:600 13px/1 -apple-system,"Inter",system-ui,sans-serif;
      color:${ink};letter-spacing:-.01em}
    iframe{width:100%;flex:1;border:0;display:block}
  </style></head><body><div class="win"><div class="bar"><div class="lights"><i style="background:#ff5f57"></i>
  <i style="background:#febc2e"></i><i style="background:#28c840"></i></div><div class="title">Crewcut</div></div>
  <iframe src="${base}/index.html?demo=1&theme=${theme}${query}${hash}"></iframe></div>
  </body></html>`;
}

async function still(browser, theme, hash = "", name = "crewcut") {
  const page = await browser.newPage({
    viewport: { width: W + 2 * PAD, height: H + 2 * PAD + TITLE }, deviceScaleFactor: 2, colorScheme: theme,
  });
  await page.setContent(framePage(theme, "", hash), { waitUntil: "load" });
  await page.frames()[1].waitForLoadState("networkidle");
  await page.waitForTimeout(2500);
  await page.screenshot({ path: join(out, `${name}-${theme}.png`) });
  await page.close();
}

async function animation(browser) {
  const dir = join(out, "video-tmp");
  const ctx = await browser.newContext({
    viewport: { width: W + 2 * PAD, height: H + 2 * PAD + TITLE }, colorScheme: "light",
    recordVideo: { dir, size: { width: W + 2 * PAD, height: H + 2 * PAD + TITLE } },
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
await still(browser, "light", "#/episodes", "crewcut-episodes");
await still(browser, "dark", "#/episodes", "crewcut-episodes");
await animation(browser);
await browser.close();
console.log("README images in", out);
