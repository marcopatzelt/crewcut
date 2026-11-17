// The desktop app (desktop/, Electron) puts a small bridge on window.crewcutDesktop through its preload script, only for
// the local Crewcut page. In a browser tab it is not there and the web UI does everything itself.
import type { ClaudeAccount } from "../api/types";

export interface DesktopBridge {
  /** "darwin", "win32" or "linux". */
  platform: string;
  /** The app's own sign-in: it keeps the Claude token in the system keychain and restarts the container with it. */
  connect(engine: "claude" | "codex"): Promise<{ connected: boolean; account?: ClaudeAccount; text?: string }>;
  /** Opens the app's settings (Claude and Codex, the studio folder, keep working in the background). */
  openSettings(): void;
  /** The page's theme, so the window's own controls match it. */
  setTheme(theme: "light" | "dark"): void;
}

export function desktop(): DesktopBridge | null {
  if (typeof window === "undefined") return null;
  return (window as Window & { crewcutDesktop?: DesktopBridge }).crewcutDesktop ?? null;
}
