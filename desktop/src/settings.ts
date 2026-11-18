// The app's own settings, a small JSON file in its data folder. No secret ever goes here (secrets.ts).
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

export interface Bounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Settings {
  /** Where the videos live: the studio folder, mounted at /studio. */
  studioDir: string;
  /** Closing the window keeps the crew working; a tray or menu-bar icon stays. Off by default. */
  keepRunning: boolean;
  /** The first-start steps are done (Docker, studio folder, the image). */
  onboarded: boolean;
  bounds?: Bounds;
  maximized?: boolean;
  prompterDisplay?: { id: number; label: string; width: number; height: number };
  /** What Claude Code said about the connected account (shown in the settings; never the token). */
  claude?: { email?: string; orgName?: string; at: string; where: "keychain" | "engine volume" };
  codex?: { at: string };
  /** The image the stack ran last, so a new app version pulls its own image once. */
  image?: string;
}

export function defaults(home: string): Settings {
  return { studioDir: join(home, "Crewcut"), keepRunning: false, onboarded: false };
}

export class SettingsFile {
  private value: Settings;

  constructor(
    private readonly file: string,
    home: string,
    studioDir?: string,
  ) {
    const base = defaults(home);
    if (studioDir) base.studioDir = studioDir;
    let loaded: Partial<Settings> = {};
    try {
      if (existsSync(file)) loaded = JSON.parse(readFileSync(file, "utf8")) as Partial<Settings>;
    } catch {
      loaded = {}; // a broken file: start from the defaults
    }
    this.value = { ...base, ...loaded };
    if (typeof this.value.studioDir !== "string" || !this.value.studioDir) this.value.studioDir = base.studioDir;
  }

  get(): Settings {
    return { ...this.value };
  }

  set(patch: Partial<Settings>): Settings {
    this.value = { ...this.value, ...patch };
    mkdirSync(dirname(this.file), { recursive: true });
    const tmp = `${this.file}.tmp`;
    writeFileSync(tmp, JSON.stringify(this.value, null, 1));
    renameSync(tmp, this.file);
    return this.get();
  }
}

/** Bounds that are at least partly on one of the screens; otherwise none (the window opens centred). */
export function visibleBounds(b: Bounds | undefined, screens: Bounds[]): Bounds | undefined {
  if (!b || b.width < 400 || b.height < 300) return undefined;
  const overlaps = screens.some(
    (s) => b.x < s.x + s.width - 80 && b.x + b.width > s.x + 80 && b.y < s.y + s.height - 40 && b.y + 40 > s.y,
  );
  return overlaps ? b : undefined;
}
