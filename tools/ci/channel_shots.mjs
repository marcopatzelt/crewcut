import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || "playwright");
const [base, output] = process.argv.slice(2);
assert(base && output, "Usage: node tools/ci/channel_shots.mjs <sample server URL> <output directory>");
const marker = await fetch(`${base}/__sample/reset`, { method: "POST" });
assert(marker.ok && (await marker.json()).ok === true, "Use the isolated sample server only");
mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
const report = [];
const errors = [];
const layoutIssues = [];

async function visibleInWindow(locator, name) {
  assert(await locator.isVisible(), `${name} must be visible`);
  const box = await locator.boundingBox();
  const viewport = locator.page().viewportSize();
  assert(box && box.x >= 0 && box.y >= 0 && box.x + box.width <= viewport.width + 1 && box.y + box.height <= viewport.height + 1,
    `${name} must fit inside the window: ${JSON.stringify(box)}`);
}

async function picture(page, name) {
  await page.getByRole("dialog", { name: "Command palette" }).waitFor({ state: "hidden" });
  await page.evaluate(() => document.fonts.ready);
  await page.locator("img").evaluateAll((images) => Promise.all(images.map((image) => image.complete ? undefined : new Promise((resolve) => {
    image.addEventListener("load", resolve, { once: true });
    image.addEventListener("error", resolve, { once: true });
  }))));
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name}: horizontal overflow`);
  const broken = await page.locator("img").evaluateAll((images) => images.filter((image) => image.complete && !image.naturalWidth).map((image) => image.src));
  assert.deepEqual(broken, [], `${name}: broken pictures`);
  const overlaps = await page.evaluate(() => {
    const dock = document.querySelector(".channel-main .dock")?.getBoundingClientRect();
    if (!dock) return [];
    return [...document.querySelectorAll(".channel-main .chat-empty p, .channel-main .msg .txt p")].flatMap((element) => {
      const box = element.getBoundingClientRect();
      return box.bottom > dock.top && box.top < dock.bottom && box.right > dock.left && box.left < dock.right
        ? [{ text: element.textContent, top: box.top, bottom: box.bottom, dockTop: dock.top, dockBottom: dock.bottom }] : [];
    });
  });
  if (overlaps.length) layoutIssues.push({ name, overlaps });
  await page.screenshot({ path: join(output, `${name}.png`), fullPage: false });
  report.push({ name, viewport: page.viewportSize(), screenshot: `${name}.png` });
}

try {
  for (const theme of ["light", "dark"]) {
    for (const width of [1440, 390]) {
      await fetch(`${base}/__sample/reset`, { method: "POST" });
      const page = await browser.newPage({ viewport: { width, height: width === 390 ? 844 : 1000 }, colorScheme: theme, reducedMotion: "reduce" });
      page.on("pageerror", (error) => errors.push(String(error)));
      page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
      page.on("response", (response) => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`); });
      await page.goto(`${base}/index.html?theme=${theme}`, { waitUntil: "load" });
      await page.getByRole("log").waitFor();
      await visibleInWindow(page.getByRole("heading", { name: "Showrunner", exact: true }), "Showrunner lead");
      await visibleInWindow(page.locator(".composer-scope"), "Channel scope");
      await visibleInWindow(page.getByLabel("Message", { exact: true }), "Channel composer");
      await picture(page, `channel-${width}-${theme}`);
      const before = await (await page.request.get(`${base}/api/state`)).json();
      await page.getByLabel("Message", { exact: true }).fill("What is ready? Sample question.");
      await page.getByLabel("Message", { exact: true }).press("Enter");
      await page.getByText("These are sample data. Nothing runs here, so nobody picks this up.", { exact: true }).waitFor();
      const after = await (await page.request.get(`${base}/api/state`)).json();
      assert.equal(after.episodes.length, before.episodes.length, "Channel must not create an episode");
      await page.getByLabel("Message", { exact: true }).fill("Keep this channel draft");
      await page.keyboard.press("Control+k");
      await page.getByRole("combobox").fill("Claude improves a website 100 times");
      await page.getByRole("combobox").press("Enter");
      await page.getByRole("heading", { level: 1, name: "Claude improves a website 100 times" }).waitFor();
      await page.getByRole("radiogroup", { name: "Thumbnail variants" }).waitFor();
      if (width === 390) {
        await visibleInWindow(page.getByRole("button", { name: "Media and history", exact: true }), "Media tab");
        assert.equal(await page.getByLabel("Message", { exact: true }).isVisible(), false, "Media has no hidden competing composer");
        await picture(page, `episode-media-${width}-${theme}`);
        await page.getByRole("button", { name: "Episode chat", exact: true }).focus();
        await page.keyboard.press("Enter");
        assert.equal(await page.locator(".media-main").isVisible(), false);
      }
      await page.getByLabel("Message", { exact: true }).waitFor();
      await page.getByLabel("Message", { exact: true }).scrollIntoViewIfNeeded();
      await visibleInWindow(page.getByLabel("Message", { exact: true }), "Episode composer");
      assert.match(await page.locator(".composer-scope").innerText(), /^Episode:/);
      await page.getByLabel("Message", { exact: true }).fill("Keep this episode draft");
      await picture(page, `episode-chat-${width}-${theme}`);
      if (width === 390) {
        await page.getByRole("button", { name: "Media and history", exact: true }).click();
        await page.getByRole("button", { name: "Episode chat", exact: true }).click();
        assert.equal(await page.getByLabel("Message", { exact: true }).inputValue(), "Keep this episode draft");
      }
      await page.keyboard.press("Control+k");
      await page.getByRole("combobox").fill("Show Channel");
      await page.getByRole("combobox").press("Enter");
      await page.getByRole("heading", { name: "Showrunner", exact: true }).waitFor();
      assert.equal(await page.getByLabel("Message", { exact: true }).inputValue(), "Keep this channel draft");
      await picture(page, `channel-reply-${width}-${theme}`);
      await page.close();
    }
  }
  assert.deepEqual(errors, [], "Browser errors");
  assert.deepEqual(layoutIssues, [], "Channel text overlaps the composer");
} finally {
  writeFileSync(join(output, "report.json"), JSON.stringify({ screenshots: report, errors, layoutIssues }, null, 2));
  await browser.close();
}
console.log(`Verified ${report.length} screenshots, keyboard navigation, drafts, tabs, and isolated channel sends.`);
