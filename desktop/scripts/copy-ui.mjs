// Puts the local pages of the desktop app together in dist/ui: its own HTML, CSS and script (ui/), the design tokens
// of the web app (one source: web/src/styles/tokens.css), Inter (from web/node_modules, as the web app bundles it),
// Slate's pictures (docs/brand) and the app icons for electron-builder (build/).
import { copyFileSync, cpSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const desktop = join(here, "..");
const root = join(desktop, "..");
const out = join(desktop, "dist", "ui");
mkdirSync(join(out, "brand"), { recursive: true });
mkdirSync(join(out, "fonts"), { recursive: true });

cpSync(join(desktop, "ui"), out, { recursive: true });
copyFileSync(join(root, "web/src/styles/tokens.css"), join(out, "tokens.css"));
for (const f of ["wave", "working", "waiting", "done", "idle"]) {
  copyFileSync(join(root, `docs/brand/states/${f}.svg`), join(out, "brand", `${f}.svg`));
}
copyFileSync(join(root, "docs/brand/slate-icon.svg"), join(out, "brand", "app-icon.svg"));
mkdirSync(join(out, "wallpapers"), { recursive: true });
for (const w of ["mint-dawn-1280.jpg", "green-dusk-1280.jpg"]) {
  copyFileSync(join(root, "web/public/wallpapers", w), join(out, "wallpapers", w));
}

const fonts = join(root, "web/node_modules/@fontsource/inter/files");
let fontCount = 0;
for (const w of [400, 500, 600, 700]) {
  const f = join(fonts, `inter-latin-${w}-normal.woff2`);
  if (existsSync(f)) {
    copyFileSync(f, join(out, "fonts", `inter-${w}.woff2`));
    fontCount += 1;
  }
}
if (!fontCount) console.warn("copy-ui: Inter not found (run npm ci in web/); the pages fall back to the system font");

mkdirSync(join(desktop, "build"), { recursive: true });
copyFileSync(join(root, "docs/brand/icons/slate-icon-1024.png"), join(desktop, "build", "icon.png"));
copyFileSync(join(root, "docs/brand/icons/slate-icon-16.png"), join(desktop, "build", "tray.png"));
copyFileSync(join(root, "docs/brand/icons/slate-icon-32.png"), join(desktop, "build", "tray@2x.png"));
console.log(`copy-ui: dist/ui ready (${fontCount} Inter weights)`);
