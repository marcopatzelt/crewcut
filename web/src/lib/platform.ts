// The platform the page runs on, the shortcut keys to show (DESIGN.md rule 15), and the theme switch.
import { desktop } from "./desktop";

interface UaData {
  platform?: string;
}

/** True on a Mac, iPhone or iPad. Decides the system font (rule 5) and whether shortcuts show ⌘ or Ctrl. */
export function isApple(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = (navigator as Navigator & { userAgentData?: UaData }).userAgentData?.platform ?? navigator.platform ?? "";
  return /mac|iphone|ipad|ipod/i.test(ua);
}

/** Puts the class is-apple on <html> on Apple devices, so the CSS uses the installed system font there. */
export function applyPlatformClass(): void {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("is-apple", isApple());
}

/** "mod" is Cmd on Apple devices and Ctrl elsewhere. Keycaps as the user reads them. */
export function keyLabels(keys: string[]): string[] {
  const apple = isApple();
  return keys.map((k) => {
    switch (k) {
      case "mod":
        return apple ? "⌘" : "Ctrl";
      case "alt":
        return apple ? "⌥" : "Alt";
      case "shift":
        return apple ? "⇧" : "Shift";
      case "enter":
        return "↵";
      default:
        return k;
    }
  });
}

/** "⌘K" on a Mac, "Ctrl+K" elsewhere: for tooltips, where keycaps cannot be drawn. */
export function keyText(keys: string[]): string {
  return keyLabels(keys).join(isApple() ? "" : "+");
}

/** The value for aria-keyshortcuts: both modifiers, because both work. */
export function ariaKeys(keys: string[]): string {
  const map = (mod: string) =>
    keys
      .map((k) => (k === "mod" ? mod : k === "alt" ? "Alt" : k === "shift" ? "Shift" : k === "enter" ? "Enter" : k))
      .join("+");
  return `${map("Meta")} ${map("Control")}`;
}

export function reducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

export function narrow(px: number): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(`(max-width: ${px - 1}px)`).matches
    : false;
}

// ---------- theme: follows the system; the palette can switch it (rule 4). The choice is kept per browser. ----------

const THEME_KEY = "crewcut-theme";

export type Theme = "light" | "dark";

function systemTheme(): Theme {
  return typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function currentTheme(): Theme {
  const set = typeof document !== "undefined" ? document.documentElement.dataset.theme : undefined;
  return set === "light" || set === "dark" ? set : systemTheme();
}

/**
 * The colour of the app window's own bar (meta theme-color) follows a theme chosen in the app. index.html sets both
 * themes' --panel by media query; a chosen theme overrides them with the --panel it now has.
 */
function syncThemeColor(): void {
  if (typeof document === "undefined" || typeof getComputedStyle !== "function") return;
  desktop()?.setTheme(currentTheme()); // the desktop app recolours its window buttons
  const panel = getComputedStyle(document.documentElement).getPropertyValue("--panel").trim();
  if (!panel) return;
  document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]').forEach((m) => {
    m.content = panel;
  });
}

/** ?theme= wins (screenshots), then the stored choice, then the system. */
export function initTheme(param: string | null): void {
  if (param === "light" || param === "dark") {
    document.documentElement.dataset.theme = param;
    syncThemeColor();
    return;
  }
  let stored: string | null = null;
  try {
    stored = window.localStorage.getItem(THEME_KEY);
  } catch {
    stored = null; // storage blocked, for example in a third-party frame: follow the system
  }
  if (stored === "light" || stored === "dark") {
    document.documentElement.dataset.theme = stored;
    syncThemeColor();
  } else {
    desktop()?.setTheme(currentTheme());
  }
}

export function switchTheme(): Theme {
  const next: Theme = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  syncThemeColor();
  try {
    window.localStorage.setItem(THEME_KEY, next);
  } catch {
    // not kept; the switch still works for this page
  }
  return next;
}
