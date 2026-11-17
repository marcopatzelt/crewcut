// The app window: no browser around the page and no second title bar. On macOS the real traffic lights sit over the
// web app's own top bar (hiddenInset, moved to its middle); on Windows and Linux the system's window buttons sit over
// it as an overlay in the token colours. Either way the page gets the window-controls-overlay variables
// (env(titlebar-area-*)) and keeps its controls clear of the buttons; its empty parts move the window.
import { BrowserWindow, nativeTheme, screen, shell, type WebContents } from "electron";
import { join } from "node:path";
import { visibleBounds, type SettingsFile } from "./settings";
import { BAR_HEIGHT, THEME, type ThemeName } from "./theme";

export const isMac = process.platform === "darwin";

export function themeNow(): ThemeName {
  return nativeTheme.shouldUseDarkColors ? "dark" : "light";
}

export function overlayFor(theme: ThemeName) {
  return { color: THEME[theme].panel, symbolColor: THEME[theme].ink, height: BAR_HEIGHT };
}

export function applyTheme(win: BrowserWindow, theme: ThemeName): void {
  win.setBackgroundColor(THEME[theme].window);
  if (!isMac) {
    try {
      win.setTitleBarOverlay(overlayFor(theme));
    } catch {
      // a window without an overlay (none here): nothing to recolour
    }
  }
}

export function localApp(url: string, port: number): boolean {
  try {
    const u = new URL(url);
    return u.protocol === "http:" && (u.hostname === "localhost" || u.hostname === "127.0.0.1") && u.port === String(port);
  } catch {
    return false;
  }
}

export function ownPage(url: string, uiDir: string): boolean {
  try {
    const u = new URL(url);
    if (u.protocol !== "file:") return false;
    const path = decodeURIComponent(u.pathname).replace(/^\/([A-Za-z]:)/, "$1");
    return path.replace(/\\/g, "/").startsWith(uiDir.replace(/\\/g, "/"));
  } catch {
    return false;
  }
}

/** Links: the local app and the app's own pages stay in the window; http(s) anywhere else opens in the default
 *  browser; nothing else opens at all. */
export function guard(contents: WebContents, port: number, uiDir: string): void {
  const external = (url: string) => {
    if (/^https?:\/\//.test(url) && !localApp(url, port)) void shell.openExternal(url);
  };
  contents.setWindowOpenHandler(({ url }) => {
    external(url);
    return { action: "deny" };
  });
  const stay = (event: { preventDefault: () => void }, url: string) => {
    if (localApp(url, port) || ownPage(url, uiDir)) return;
    event.preventDefault();
    external(url);
  };
  contents.on("will-navigate", stay);
  contents.on("will-redirect", stay);
  contents.session.setPermissionRequestHandler((wc, permission, callback, details) => {
    const from = details.requestingUrl || wc.getURL();
    // the microphone of the composer and the clipboard, only for the local Crewcut page
    callback(localApp(from, port) && ["media", "clipboard-sanitized-write", "fullscreen"].includes(permission));
  });
}

export function createMainWindow(settings: SettingsFile, preload: string, iconPath: string): BrowserWindow {
  const s = settings.get();
  const work = screen.getPrimaryDisplay().workAreaSize;
  const bounds = visibleBounds(s.bounds, screen.getAllDisplays().map((d) => d.workArea));
  const theme = themeNow();
  const win = new BrowserWindow({
    width: bounds?.width ?? Math.min(1440, work.width - 40),
    height: bounds?.height ?? Math.min(900, work.height - 40),
    x: bounds?.x,
    y: bounds?.y,
    minWidth: 900,
    minHeight: 600,
    show: false,
    title: "Crewcut",
    icon: process.platform === "linux" ? iconPath : undefined,
    backgroundColor: THEME[theme].window,
    titleBarStyle: isMac ? "hiddenInset" : "hidden",
    ...(isMac ? { trafficLightPosition: { x: 16, y: Math.round((BAR_HEIGHT - 14) / 2) } } : {}),
    titleBarOverlay: isMac ? true : overlayFor(theme),
    webPreferences: {
      preload,
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      webSecurity: true,
      spellcheck: false,
    },
  });
  if (s.maximized) win.maximize();
  win.once("ready-to-show", () => win.show());

  let timer: NodeJS.Timeout | undefined;
  const remember = () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (win.isDestroyed() || win.isMinimized()) return;
      const maximized = win.isMaximized() || win.isFullScreen();
      settings.set({ maximized, ...(maximized ? {} : { bounds: win.getBounds() }) });
    }, 300);
  };
  for (const ev of ["resize", "move", "maximize", "unmaximize"] as const) win.on(ev as "resize", remember);
  return win;
}

export function createSettingsWindow(parent: BrowserWindow, preload: string, uiDir: string, focus: string):
  BrowserWindow {
  const theme = themeNow();
  const win = new BrowserWindow({
    parent,
    modal: false,
    width: 560,
    height: 640,
    resizable: false,
    minimizable: false,
    maximizable: false,
    show: false,
    title: "Crewcut settings",
    backgroundColor: THEME[theme].window,
    titleBarStyle: isMac ? "hiddenInset" : "hidden",
    ...(isMac ? { trafficLightPosition: { x: 16, y: Math.round((BAR_HEIGHT - 14) / 2) } } : {}),
    titleBarOverlay: isMac ? true : overlayFor(theme),
    webPreferences: { preload, contextIsolation: true, sandbox: true, nodeIntegration: false, spellcheck: false },
  });
  win.once("ready-to-show", () => win.show());
  setTimeout(() => {
    if (!win.isDestroyed() && !win.isVisible()) win.show(); // never a settings window nobody sees
  }, 2000);
  void win.loadFile(join(uiDir, "onboarding.html"), { hash: `settings${focus ? `-${focus}` : ""}` });
  return win;
}
