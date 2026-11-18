// The desktop app (desktop/, Electron) puts a small bridge on window.crewcutDesktop through its preload script, only for
// the local Crewcut page. In a browser tab it is not there and the web UI does everything itself.
import type { ClaudeAccount } from "../api/types";

export interface DesktopBridge {
  prompterDisplays?(): Promise<{ displays: Array<{ id: number; label: string; width: number; height: number }>; selected: number | null }>;
  prompterSelectDisplay?(id: number): Promise<void>;
  prompterOpen?(episode: string): Promise<{ ok: boolean; message: string }>;
  /** "darwin", "win32" or "linux". */
  platform: string;
  /** Older apps: the app's settings window signs in (the token goes to the system keychain). */
  connect(engine: "claude" | "codex"): Promise<{ connected: boolean; account?: ClaudeAccount; text?: string }>;
  /** Connect Claude in the page: the app runs the CLI's sign-in in the container and opens Claude's page in the
   *  browser; the page gets the link, then sends the code. The token stays in the app (system keychain). */
  claudeBegin?(): Promise<{ url?: string; text?: string }>;
  claudeCode?(code: string): Promise<{ connected: boolean; account?: ClaudeAccount; text?: string }>;
  codexBegin?(): Promise<{ url?: string; code?: string | null; text?: string }>;
  codexWait?(): Promise<{ connected: boolean; text?: string }>;
  cancelSignIn?(): Promise<void>;
  /** Opens the app's settings (Claude and Codex, the studio folder, keep working in the background). */
  openSettings(): void;
  /** The page's theme, so the window's own controls match it. */
  setTheme(theme: "light" | "dark"): void;
}

export function desktop(): DesktopBridge | null {
  if (typeof window === "undefined") return null;
  return (window as Window & { crewcutDesktop?: DesktopBridge }).crewcutDesktop ?? null;
}
