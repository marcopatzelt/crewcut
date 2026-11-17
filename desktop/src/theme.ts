// The window's own colours, from web/src/styles/tokens.css (test/theme.test.ts keeps them in step): --panel for the
// window controls' background (Windows, Linux), --ink for their symbols, --window behind the page while it loads.
export type ThemeName = "light" | "dark";

export const THEME: Record<ThemeName, { panel: string; ink: string; window: string }> = {
  light: { panel: "#F1F5F3", ink: "#0E1A17", window: "#E3ECE8" },
  dark: { panel: "#10201C", ink: "#F2F7F5", window: "#0B1613" },
};

/** The top bar's height in the web app (window.css, --bar-h): the window controls take the same height. */
export const BAR_HEIGHT = 46;
