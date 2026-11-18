import { BrowserWindow, screen } from "electron";
import { existsSync, lstatSync, readFileSync, readdirSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { SettingsFile } from "./settings";
import { parsePrompterRequest, prompterUrl } from "./prompter-protocol";

export class DesktopPrompter {
  private window: BrowserWindow | null = null;
  private busy = false;

  constructor(private settings: SettingsFile, private apiPort: number, private port: number) {}

  displays() {
    return { displays: screen.getAllDisplays().map(display => ({ id: display.id,
      label: display.label || `Screen ${display.id}`, width: display.size.width, height: display.size.height })),
    selected: this.settings.get().prompterDisplay?.id ?? null };
  }

  select(id: number): void {
    const display = this.displays().displays.find(item => item.id === id);
    if (!display) throw new Error("That screen is no longer connected.");
    this.settings.set({ prompterDisplay: display });
  }

  async open(episode: string): Promise<{ ok: boolean; message: string }> {
    if (this.busy) return { ok: false, message: "A teleprompter is already opening. Try again shortly." };
    this.busy = true;
    try {
      if (typeof episode !== "string" || !/^[A-Za-z0-9_-]+$/.test(episode)) throw new Error("Invalid episode.");
      const choice = this.settings.get().prompterDisplay;
      if (!choice) throw new Error("Choose a screen in the Teleprompter menu first.");
      const display = screen.getAllDisplays().find(item => item.id === choice.id &&
        (item.label || `Screen ${item.id}`) === choice.label);
      if (!display) throw new Error("The selected screen is disconnected. Choose a screen again.");
      const response = await fetch(`http://127.0.0.1:${this.apiPort}/api/episodes/${encodeURIComponent(episode)}/desktop-prompter`,
        { signal: AbortSignal.timeout(5000), redirect: "error" });
      const info = await response.json() as { token?: unknown; detail?: string };
      if (!response.ok) throw new Error(info.detail || "The approved script is not ready.");
      const url = prompterUrl(info.token, this.port);
      this.window?.close();
      const win = new BrowserWindow({ ...display.bounds, title: "Crewcut Teleprompter", frame: false,
        show: false, autoHideMenuBar: true,
        webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false,
          webSecurity: true, partition: "crewcut-prompter" } });
      this.window = win;
      win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
      win.webContents.session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
      const guard = (event: { preventDefault(): void }, target: string) => { if (target !== url) event.preventDefault(); };
      win.webContents.on("will-navigate", guard);
      win.webContents.on("will-redirect", guard);
      win.webContents.on("before-input-event", (_event, input) => { if (input.key === "Escape") win.close(); });
      win.on("closed", () => { if (this.window === win) this.window = null; });
      try {
        await win.loadURL(url);
        win.show();
        win.setBounds(display.bounds);
        await new Promise(resolve => setTimeout(resolve, 250));
        if (win.isDestroyed()) throw new Error("The teleprompter window was closed.");
        win.setBounds(display.bounds);
        win.setFullScreen(true);
        for (let attempt = 0; attempt < 15; attempt++) {
          await new Promise(resolve => setTimeout(resolve, 200));
          if (win.isDestroyed() || (win.isFullScreen() && screen.getDisplayMatching(win.getBounds()).id === display.id)) break;
        }
        if (win.isDestroyed() || screen.getDisplayMatching(win.getBounds()).id !== display.id || !win.isFullScreen()) {
          throw new Error("The desktop could not place the full-screen window on the selected screen.");
        }
        return { ok: true, message: `Teleprompter opened on ${choice.label}. Escape closes it. Recording is not started.` };
      } catch (error) { if (!win.isDestroyed()) win.close(); throw error; }
    } catch (error) {
      return { ok: false, message: error instanceof Error ? error.message : "Could not open the teleprompter." };
    } finally { this.busy = false; }
  }

  async poll(): Promise<void> {
    if (this.busy) return;
    const state = join(this.settings.get().studioDir, ".crewcut");
    const directory = join(state, "desktop-prompter");
    if (!existsSync(directory) || lstatSync(state).isSymbolicLink() || lstatSync(directory).isSymbolicLink()) return;
    for (const filename of readdirSync(directory).filter(name => /^[a-f0-9]{32}\.json$/.test(name)).slice(-100)) {
      const path = join(directory, filename);
      const stat = lstatSync(path);
      if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 4096) continue;
      let value: unknown;
      try { value = JSON.parse(readFileSync(path, "utf8")); } catch { continue; }
      const request = parsePrompterRequest(value, filename);
      if (!request) continue;
      const result = Date.now() - request.created * 1000 > 120_000
        ? { ok: false, message: "Request expired. Ask to open the teleprompter again." }
        : await this.open(request.episode);
      const temporary = `${path}.desktop-tmp`;
      writeFileSync(temporary, JSON.stringify({ ...request, status: result.ok ? "opened" : "failed", message: result.message }),
        { flag: "wx", mode: 0o600 });
      renameSync(temporary, path);
      break;
    }
  }
}
