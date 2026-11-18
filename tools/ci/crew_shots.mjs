import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || "playwright");
const [base, output] = process.argv.slice(2);
assert(base && output, "Usage: node tools/ci/crew_shots.mjs <sample server> <output directory>");
const marker = await fetch(`${base}/__sample/reset`, { method: "POST" });
assert(marker.ok && (await marker.json()).ok === true, "Use the isolated sample server only");
mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || undefined });
const errors = [];
const screenshots = [];

async function picture(page, name) {
  await page.evaluate(() => document.fonts.ready);
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name}: horizontal overflow`);
  await page.screenshot({ path: join(output, `${name}.png`) });
  screenshots.push(name);
}

async function chooser(page, name) {
  const trigger = page.getByRole("button", { name: /^Chat AI:/ });
  await trigger.scrollIntoViewIfNeeded();
  await trigger.click();
  await page.getByRole("button", { name: "Use Codex", exact: true }).waitFor();
  const popover = page.getByRole("region", { name: "Choose chat AI" });
  const unclipped = await popover.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    if (rect.x < 0 || rect.y < 0 || rect.right > innerWidth || rect.bottom > innerHeight) return false;
    return [[rect.left + 8, rect.top + 8], [rect.right - 8, rect.top + 8], [rect.left + 8, rect.bottom - 8], [rect.right - 8, rect.bottom - 8]]
      .every(([x, y]) => element.contains(document.elementFromPoint(x, y)));
  });
  assert(unclipped, `${name}: AI chooser is clipped or covered`);
  await picture(page, name);
  await page.keyboard.press("Escape");
  assert(await trigger.evaluate((element) => element === document.activeElement), "Escape restores trigger focus");
}

try {
  for (const theme of ["light", "dark"]) {
    for (const width of [1440, 1100, 390]) {
      const page = await browser.newPage({ viewport: { width, height: width === 390 ? 844 : 1000 }, colorScheme: theme, reducedMotion: "reduce" });
      page.on("pageerror", (error) => errors.push(String(error)));
      page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
      page.on("response", (response) => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`); });
      await page.goto(`${base}/index.html?theme=${theme}#/crew`);
      await page.getByRole("article", { name: "Showrunner" }).waitFor();
      assert.equal(await page.locator(".crew-person").count(), 8);
      assert.equal(await page.locator(".crew-person").first().getAttribute("aria-labelledby"), "person-showrunner");
      assert.equal(await page.locator(".crew-details[open]").count(), 0);
      assert.equal(await page.locator(".page-scroll .engine-picker").count(), 0);
      await picture(page, `crew-${width}-${theme}`);
      await chooser(page, `crew-ai-${width}-${theme}`);
      const scout = page.getByRole("article", { name: "Scout", exact: true });
      await scout.getByLabel("About Scout").focus();
      await page.keyboard.press("Enter");
      assert(await scout.locator("details").evaluate((element) => element.open));
      await scout.getByRole("link", { name: "Vexian, in a podcast with Grant Owen" }).scrollIntoViewIfNeeded();
      await picture(page, `crew-details-${width}-${theme}`);
      await page.goto(`${base}/index.html?theme=${theme}#/e/012-website-100-times`);
      await page.getByRole("heading", { level: 1, name: "Claude improves a website 100 times" }).waitFor();
      if (width < 900) await page.getByRole("button", { name: "Episode chat", exact: true }).click();
      await chooser(page, `episode-ai-${width}-${theme}`);
      await page.close();
    }
  }
  assert.deepEqual(errors, [], "Browser errors");
} finally {
  writeFileSync(join(output, "report.json"), JSON.stringify({ screenshots, errors }, null, 2));
  await browser.close();
}
console.log(`Verified ${screenshots.length} screenshots, collapsed crew details, attribution, keyboard and unclipped AI choosers.`);
