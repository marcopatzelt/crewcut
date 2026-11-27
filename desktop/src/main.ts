// Crewcut's desktop app. It runs the same Docker stack as ./start.sh, connects Claude (the token stays in the system
// keychain), and shows the local Crewcut page in its own window. On quit it stops the stack, unless "keep the crew
// working in the background" is on: then closing the window leaves a tray (menu-bar) icon and the crew keeps working.
// Next to the stack it runs the host helper (host-helper.ts), as ./start.sh does, and stops it on quit.
import { app, BrowserWindow, dialog, ipcMain, Menu, nativeTheme, shell, Tray, type IpcMainInvokeEvent } from "electron";
import { mkdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { CODE_RE, deviceAllowed, signInAllowed, Steps, type Step } from "./connect";
import { bytesWords, checkDocker, docker, dockerEnv, dockerSocket, imageExists, pullImage } from "./docker";
import { IMAGE, imageTag, RELEASES } from "./release";
import { deleteToken, getToken, initializeSecrets, keychainAvailable, loginProblem, setToken } from "./secrets";
import { SettingsFile } from "./settings";
import { profileConfig } from "./profile";
import * as stack from "./stack";
import { startUpdates } from "./updater";
import { applyTheme, createMainWindow, createSettingsWindow, guard, isMac, localApp, ownPage, themeNow } from "./window";
import type { ThemeName } from "./theme";
import { DesktopPrompter } from "./prompter";
import { DesktopMedia, removableRoots } from "./media";
import { HostHelper, hostToken, secondOpinionConfig } from "./host-helper";

if (process.platform === "linux" && process.env.WAYLAND_DISPLAY && process.env.DISPLAY &&
    !app.commandLine.hasSwitch("ozone-platform")) {
  app.relaunch({ args: [...process.argv.slice(1), "--ozone-platform=x11"] });
  app.exit(0);
}
let desktopPrompter: DesktopPrompter;
let desktopMedia: DesktopMedia;

const PROFILE = profileConfig(process.env.CREWCUT_PROFILE, app.getPath("userData"), homedir(), app.isPackaged);
if (PROFILE.development) {
  mkdirSync(PROFILE.userData, { recursive: true });
  app.setPath("userData", PROFILE.userData);
  app.setPath("sessionData", PROFILE.userData);
  app.setName(PROFILE.title);
}
const PORT = PROFILE.development ? PROFILE.port : Number(process.env.CREWCUT_PORT || PROFILE.port);
const APP_URL = `http://localhost:${PORT}/`;
const UI = join(__dirname, "ui");
const PRELOAD = join(__dirname, "preload.js");
const SHOTS = process.env.CREWCUT_DESKTOP_SHOTS || "";
const res = (name: string) => (app.isPackaged ? join(process.resourcesPath, name) : join(__dirname, "..", "build", name));
const ICON = res("icon.png");
const HELPER = app.isPackaged ? join(process.resourcesPath, "host", "crewcut-host.sh")
  : join(__dirname, "..", "..", "host", "crewcut-host.sh");

// `crewcut --help` / `--version` from a shell: print and leave, without Docker and without a window.
if (process.argv.some((a) => a === "--help" || a === "-h")) {
  process.stdout.write("Crewcut desktop app. Start it from the app menu; it runs Crewcut in Docker and opens it.\n" +
    "  --version   print the version\n  --help      this text\n");
  app.exit(0);
}
if (process.argv.includes("--version")) {
  process.stdout.write(`${app.getVersion()}\n`);
  app.exit(0);
}
// One app at a time: a second start only brings the running window to the front.
const firstInstance = app.requestSingleInstanceLock();
if (!firstInstance) app.exit(0);
// CI's virtual machines have no GPU; the pictures of the pages are then drawn in software
if (SHOTS) app.disableHardwareAcceleration();

let settings: SettingsFile;
let main: BrowserWindow | null = null;
let settingsWin: BrowserWindow | null = null;
let settingsDone: ((r: { connected: boolean; text?: string }) => void) | null = null;
let tray: Tray | null = null;
let quitting = false;
let stackStarted = false;
let signIn: { engine: "claude" | "codex"; steps: Steps } | null = null;
const logLines: string[] = [];
const log = (line: string) => {
  logLines.push(`${new Date().toISOString()} ${line}`);
  if (logLines.length > 500) logLines.shift();
  if (!app.isPackaged) console.log(line);
};
const hostHelper = new HostHelper(log);

function stackConfig(): stack.StackConfig {
  const s = settings.get();
  const files = app.isPackaged
    ? [join(process.resourcesPath, "stack", "compose.yaml"), join(process.resourcesPath, "stack", "desktop.yaml")]
    : [join(__dirname, "..", "..", "compose.yaml"), join(__dirname, "..", "stack", "desktop.yaml")];
  return {
    composeFiles: files,
    projectDir: join(app.getPath("userData"), "stack"),
    projectName: PROFILE.projectName,
    studioDir: s.studioDir,
    image: IMAGE,
    tag: imageTag(app.getVersion(), PROFILE.development ? false : app.isPackaged,
                  PROFILE.development ? process.env.CREWCUT_DEV_TAG : process.env.CREWCUT_TAG),
    port: PORT,
    prompterPort: PROFILE.prompterPort,
    prompterBind: PROFILE.development ? "127.0.0.1" : "0.0.0.0",
    token: getToken(),
    hostToken: hostToken(join(app.getPath("userData"), "stack")),
  };
}

/** The host helper for the studio the stack runs, with the second opinion from the environment or settings.json. */
function startHelper(): void {
  const cfg = stackConfig();
  hostHelper.start({ script: HELPER, studioDir: cfg.studioDir, token: cfg.hostToken ?? "", parentPid: process.pid,
    secondOpinion: secondOpinionConfig(settings.get().secondOpinion, process.env, app.getPath("userData")) });
}

function send(channel: string, data: unknown): void {
  for (const w of [main, settingsWin]) if (w && !w.isDestroyed()) w.webContents.send(channel, data);
}

// ---------- who may call what ----------

type Handler = (e: IpcMainInvokeEvent, ...args: never[]) => unknown;
const fromOwnPage = (e: IpcMainInvokeEvent) => ownPage(e.senderFrame?.url ?? "", UI);
const fromAppPage = (e: IpcMainInvokeEvent) => localApp(e.senderFrame?.url ?? "", PORT) || fromOwnPage(e);

function own(channel: string, fn: Handler): void {
  ipcMain.handle(channel, (e, ...args) => {
    if (!fromOwnPage(e)) throw new Error("Not allowed from this page.");
    return (fn as (e: IpcMainInvokeEvent, ...a: unknown[]) => unknown)(e, ...args);
  });
}

function page(channel: string, fn: Handler): void {
  ipcMain.handle(channel, (e, ...args) => {
    if (!fromAppPage(e)) throw new Error("Not allowed from this page.");
    return (fn as (e: IpcMainInvokeEvent, ...a: unknown[]) => unknown)(e, ...args);
  });
}

// ---------- windows, tray and menu ----------

function openSettings(focus = ""): void {
  if (!main) return;
  if (settingsWin && !settingsWin.isDestroyed()) {
    settingsWin.focus();
    return;
  }
  settingsWin = createSettingsWindow(main, PRELOAD, UI, focus);
  guard(settingsWin.webContents, PORT, UI);
  settingsWin.on("closed", () => {
    settingsWin = null;
    settingsDone?.({ connected: Boolean(getToken()) || Boolean(settings.get().claude) || Boolean(settings.get().codex) });
    settingsDone = null;
  });
}

function showMain(): void {
  if (!main || main.isDestroyed()) {
    createMain();
    return;
  }
  if (main.isMinimized()) main.restore();
  main.show();
  main.focus();
}

function updateTray(): void {
  const keep = settings.get().keepRunning;
  if (!keep) {
    tray?.destroy();
    tray = null;
    return;
  }
  if (tray) return;
  tray = new Tray(res("tray.png"));
  tray.setToolTip("Crewcut: the crew keeps working");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Open Crewcut", click: showMain },
      { label: "Settings…", click: () => { showMain(); openSettings(); } },
      { type: "separator" },
      { label: "Quit Crewcut (stops the crew)", click: () => app.quit() },
    ]),
  );
  tray.on("click", showMain);
}

function buildMenu(): void {
  const template: Electron.MenuItemConstructorOptions[] = [
    ...(isMac ? [{ role: "appMenu" as const, submenu: [
      { role: "about" as const },
      { type: "separator" as const },
      { label: "Settings…", accelerator: "CmdOrCtrl+,", click: () => openSettings() },
      { type: "separator" as const },
      { role: "hide" as const }, { role: "hideOthers" as const }, { role: "unhide" as const },
      { type: "separator" as const },
      { role: "quit" as const },
    ] }] : [{ label: "Crewcut", submenu: [
      { label: "Settings…", accelerator: "CmdOrCtrl+,", click: () => openSettings() },
      { role: "quit" as const },
    ] }]),
    { role: "editMenu" },
    { label: "View", submenu: [
      { role: "reload" }, { role: "resetZoom" }, { role: "zoomIn" }, { role: "zoomOut" },
      { type: "separator" }, { role: "togglefullscreen" },
      ...(app.isPackaged ? [] : [{ role: "toggleDevTools" as const }]),
    ] },
    { role: "windowMenu" },
    { role: "help", submenu: [
      { label: "Crewcut on GitHub", click: () => void shell.openExternal("https://github.com/marcopatzelt/crewcut") },
      { label: "Releases", click: () => void shell.openExternal(RELEASES) },
    ] },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function createMain(): void {
  main = createMainWindow(settings, PRELOAD, ICON);
  if (PROFILE.development) {
    main.setTitle(PROFILE.title);
    main.on("page-title-updated", (event, title) => {
      event.preventDefault();
      main?.setTitle(`${PROFILE.title} · ${title}`);
    });
  }
  guard(main.webContents, PORT, UI);
  main.on("close", (e) => {
    if (quitting) return;
    if (settings.get().keepRunning) {
      e.preventDefault();
      main?.hide();
      updateTray();
      return;
    }
    e.preventDefault();
    app.quit();
  });
  main.on("closed", () => {
    main = null;
  });
  void main.loadFile(join(UI, "onboarding.html"), { query: SHOTS ? { shots: "1" } : {} });
}

// ---------- the steps: Docker, studio folder, image, stack ----------

const LOGIN_PROBLEM = {
  "no-keychain": "Your Claude login could not be read: Crewcut cannot reach your system's keychain (start it from the " +
    "app menu, not a terminal). The login is kept; connect again, or restart Crewcut from the menu.",
  unreadable: "Your Claude login could not be read; connect again. The old one is kept until then.",
} as const;

async function startStack(): Promise<{ ok: boolean; text?: string; login?: string }> {
  await initializeSecrets();
  const problem = loginProblem();
  const login = problem ? LOGIN_PROBLEM[problem] : undefined;
  if (await stack.health(PORT)) { // Crewcut already runs: never pull or restart a healthy stack on start
    stackStarted = true;
    startHelper();
    return { ok: true, login };
  }
  const d = await checkDocker();
  if (!d.cli || !d.running) return { ok: false, text: "Docker is not running." };
  if (!d.compose) return { ok: false, text: `Docker Compose ${d.composeVersion ?? "(none)"} is too old; 2.24 or newer is needed.` };
  const cfg = stackConfig();
  const ref = `${cfg.image}:${cfg.tag}`;
  try {
    const present = await imageExists(ref);
    if (!present || cfg.tag === "edge") { // a development build follows :edge, so it asks for a newer one each start
      send("stack:progress", { phase: "pull", text: "Downloading Crewcut…" });
      const socket = await dockerSocket();
      let last = 0;
      const report = (p: { current: number; total: number }) => {
        const now = Date.now();
        if (now - last < 250) return;
        last = now;
        send("stack:progress", { phase: "pull", current: p.current, total: p.total, text: bytesWords(p.current, p.total) });
      };
      const pull = async () => {
        if (socket) {
          await pullImage(socket, cfg.image, cfg.tag, report).catch(async (e: Error) => {
            log(`pull through the API: ${e.message}; trying the docker command`);
            const r = await docker(["pull", ref], { env: dockerEnv(), timeout: 3_600_000 });
            if (r.code !== 0) throw new Error(r.stderr.trim().split("\n").pop() || e.message);
          });
        } else {
          const r = await docker(["pull", ref], { env: dockerEnv(), timeout: 3_600_000 });
          if (r.code !== 0) throw new Error(r.stderr.trim().split("\n").pop() || "docker pull failed");
        }
      };
      // offline, or GitHub not answering: the image that is already here will do
      await pull().catch((e: Error) => {
        if (!present) throw e;
        log(`no newer image: ${e.message}`);
      });
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, text: /not found|manifest unknown/i.test(msg)
      ? `The image ${ref} is not published yet. ${msg}` : `Couldn't download Crewcut. ${msg}` };
  }
  send("stack:progress", { phase: "start", text: "Starting Crewcut…" });
  const up = await stack.up(cfg);
  if (up.code !== 0) return { ok: false, text: up.stderr.trim().split("\n").slice(-2).join(" ") || "docker compose up failed" };
  stackStarted = true;
  let lastTail = 0;
  const ready = await stack.waitHealthy(PORT, 20 * 60_000, (seconds) => {
    const msg = { phase: "engine", seconds, text: "Installing Claude Code inside Crewcut (first start only)…" };
    send("stack:progress", msg);
    if (seconds - lastTail >= 10) {
      lastTail = seconds;
      void stack.lastLog(cfg).then((line) => send("stack:progress", { ...msg, log: line.slice(0, 200) }));
    }
  }, startWatch(cfg));
  if (ready !== true) return { ok: false, text: ready };
  startHelper();
  settings.set({ image: ref });
  send("stack:progress", { phase: "ready", text: "Crewcut is ready." });
  return { ok: true, login };
}

/** Watches the container while Crewcut starts: when its start fails and Docker starts it over, say so with the
 *  container's last log line instead of waiting for the full time. */
function startWatch(cfg: stack.StackConfig): () => Promise<string | null> {
  let base: stack.ContainerState | null | undefined;
  return async () => {
    const now = await stack.containerState(cfg);
    if (base === undefined) {
      base = now;
      if (!now || (now.status !== "exited" && now.status !== "dead")) return null;
    }
    if (!stack.failing(base, now)) return null;
    const line = (await stack.lastLog(cfg)).slice(0, 300);
    return `Crewcut stopped while starting${now ? ` (${now.status}, exit code ${now.exitCode})` : ""}.` +
      (line ? ` Its last line: ${line}` : "");
  };
}

async function restartWithToken(): Promise<boolean> {
  send("stack:progress", { phase: "start", text: "Starting the crew with your Claude login…" });
  const cfg = stackConfig();
  const r = await stack.up(cfg);
  if (r.code !== 0) return false;
  const ready = await stack.waitHealthy(PORT, 5 * 60_000, (seconds) =>
    send("stack:progress", { phase: "engine", seconds, text: "Starting the crew with your Claude login…" }),
  startWatch(cfg));
  if (ready !== true) log(ready);
  return ready === true;
}

// ---------- Connect Claude and Codex (crewcut engine connect, JSON lines) ----------

/** Ends a running sign-in: the docker client, and inside the container the CLI it started (a killed
 *  `docker compose exec` client does not stop the process in the container by itself). */
function stopSignIn(): void {
  if (!signIn) return;
  signIn.steps.stop();
  signIn = null;
  const kill = stack.exec(stackConfig(), ["sh", "-c",
    // [c]: the pattern must not match this shell's own command line
    "pkill -f '[c]rewcut engine connect' ; pkill -f '[c]laude setup-token' ; pkill -f '[c]odex login --device-auth' ; true"]);
  kill.on("error", () => undefined);
}

async function claudeBegin(): Promise<{ url?: string; text?: string }> {
  stopSignIn();
  const keychain = keychainAvailable();
  const steps = new Steps(stack.exec(stackConfig(), ["crewcut", "engine", "connect", "claude",
    ...(keychain ? ["--print-token"] : [])]));
  signIn = { engine: "claude", steps };
  // the link comes within seconds; a first start may install Claude Code before (a "status" step), so 5 minutes
  const s = await steps.next((x) => x.step === "url", 5 * 60_000);
  if (s.step !== "url" || !s.url) {
    stopSignIn();
    return { text: s.text ?? "Claude Code did not show a sign-in link." };
  }
  if (!signInAllowed(s.url)) {
    stopSignIn();
    return { text: "The sign-in link did not lead to Claude, so Crewcut did not open it." };
  }
  void shell.openExternal(s.url);
  return { url: s.url };
}

async function claudeCode(code: string): Promise<{ connected: boolean; text?: string; account?: Step["account"] }> {
  if (!signIn || signIn.engine !== "claude") return { connected: false, text: "The sign-in has ended. Start it again." };
  const clean = String(code ?? "").replace(/\s+/g, "");
  if (!CODE_RE.test(clean)) return { connected: false, text: "That does not look like the code from Claude's page." };
  const steps = signIn.steps;
  steps.sendLine(clean);
  const s = await steps.next((x) => x.step === "done", 3 * 60_000);
  stopSignIn();
  if (s.step !== "done") return { connected: false, text: s.text ?? "Claude did not accept the code. Start again." };
  const at = new Date().toISOString();
  if (s.token) {
    await setToken(s.token);
    settings.set({ claude: { email: s.account?.email, orgName: s.account?.orgName, at, where: "keychain" } });
    if (!(await restartWithToken())) return { connected: false, text: "Crewcut did not start again with the login." };
  } else {
    settings.set({ claude: { email: s.account?.email, orgName: s.account?.orgName, at, where: "engine volume" } });
  }
  return { connected: true, account: s.account };
}

async function codexBegin(): Promise<{ url?: string; code?: string | null; text?: string }> {
  stopSignIn();
  const steps = new Steps(stack.exec(stackConfig(), ["crewcut", "engine", "connect", "codex"]));
  signIn = { engine: "codex", steps };
  const s = await steps.next((x) => x.step === "device", 10 * 60_000);
  if (s.step !== "device" || !s.url) {
    stopSignIn();
    return { text: s.text ?? "Codex did not show a sign-in link." };
  }
  if (!deviceAllowed(s.url)) {
    stopSignIn();
    return { text: "The sign-in link did not lead to OpenAI, so Crewcut did not open it." };
  }
  void shell.openExternal(s.url);
  return { url: s.url, code: s.code };
}

async function codexWait(): Promise<{ connected: boolean; text?: string }> {
  if (!signIn || signIn.engine !== "codex") return { connected: false, text: "The sign-in has ended." };
  const s = await signIn.steps.next((x) => x.step === "done", 16 * 60_000);
  stopSignIn();
  if (s.step === "done" && s.ok !== false) {
    settings.set({ codex: { at: new Date().toISOString() } });
    return { connected: true };
  }
  return { connected: false, text: s.text };
}

async function disconnect(engine: "claude" | "codex"): Promise<{ ok: boolean; text?: string }> {
  const cfg = stackConfig();
  if (engine === "claude") {
    deleteToken();
    settings.set({ claude: undefined });
    await new Promise<void>((resolve) => {
      const steps = new Steps(stack.exec(cfg, ["crewcut", "engine", "disconnect", "claude"]));
      steps.once("exit", () => resolve());
    });
    return { ok: await restartWithToken() };
  }
  await new Promise<void>((resolve) => {
    const steps = new Steps(stack.exec(cfg, ["crewcut", "engine", "disconnect", "codex"]));
    steps.once("exit", () => resolve());
  });
  settings.set({ codex: undefined });
  return { ok: true };
}

// ---------- IPC ----------

function registerIpc(): void {
  page("page:connect", (_e, engine: "claude" | "codex") => new Promise((resolve) => {
    settingsDone = resolve;
    showMain();
    openSettings(engine === "codex" ? "codex" : "claude");
  }));
  page("page:settings", () => openSettings());
  page("page:theme", (_e, theme: ThemeName) => {
    if ((theme === "light" || theme === "dark") && main) applyTheme(main, theme);
  });
  own("app:version", () => ({ version: app.getVersion(), packaged: app.isPackaged, platform: process.platform,
    tag: stackConfig().tag }));
  own("settings:get", async () => {
    const s = settings.get();
    const connections = await stack.engineConnections(PORT);
    return { studioDir: s.studioDir, keepRunning: s.keepRunning, onboarded: s.onboarded, claude: s.claude ?? null,
      codex: s.codex ?? null, claudeConnected: connections?.claude ?? false,
      codexConnected: connections?.codex ?? false, connectionsChecked: connections !== null,
      loginProblem: (() => { const p = loginProblem(); return p ? LOGIN_PROBLEM[p] : null; })(),
      keychain: keychainAvailable() };
  });
  own("settings:keep-running", (_e, on: boolean) => {
    settings.set({ keepRunning: Boolean(on) });
    updateTray();
    return true;
  });
  own("docker:check", () => checkDocker());
  own("studio:default", () => join(homedir(), "Crewcut"));
  own("studio:choose", async () => {
    const r = await dialog.showOpenDialog(settingsWin ?? main!, {
      title: "Where should your videos live?",
      defaultPath: settings.get().studioDir,
      properties: ["openDirectory", "createDirectory"],
    });
    return r.canceled ? null : r.filePaths[0] ?? null;
  });
  own("studio:set", (_e, dir: string) => {
    if (typeof dir !== "string" || !dir) throw new Error("No folder.");
    mkdirSync(dir, { recursive: true });
    settings.set({ studioDir: dir });
    return true;
  });
  own("stack:start", async () => {
    const r = await startStack();
    if (r.ok && !settings.get().onboarded) settings.set({ onboarded: true });
    return r;
  });
  // the sign-in steps: from the app's own pages and from the local Crewcut page (its Connect Claude card)
  page("claude:begin", () => claudeBegin());
  page("claude:code", (_e, code: string) => claudeCode(code));
  page("codex:begin", () => codexBegin());
  page("codex:wait", () => codexWait());
  page("signin:cancel", () => stopSignIn());
  page("prompter:displays", () => desktopPrompter.displays());
  page("media:choose-folder", async () => {
    const result = await dialog.showOpenDialog({ title: "Connect a media folder", properties: ["openDirectory"] });
    if (result.canceled || !result.filePaths[0]) return { connected: false };
    const folders = new Set(settings.get().mediaFolders ?? []);
    folders.add(result.filePaths[0]);
    settings.set({ mediaFolders: [...folders] });
    return { connected: true };
  });
  page("prompter:select", (_event, id: number) => desktopPrompter.select(id));
  page("prompter:open", (_event, episode: string) => desktopPrompter.open(episode));
  own("engine:disconnect", (_e, engine: "claude" | "codex") => disconnect(engine === "codex" ? "codex" : "claude"));
  own("app:open", () => {
    void main?.loadURL(APP_URL);
    return true;
  });
  own("settings:close", (_e, result: { connected: boolean; text?: string }) => {
    settingsDone?.(result ?? { connected: false });
    settingsDone = null;
    settingsWin?.close();
    if (result?.connected) main?.webContents.reload();
  });
  own("app:external", (_e, url: string) => {
    if (/^https:\/\/(docs\.docker\.com|www\.docker\.com|orbstack\.dev|github\.com|claude\.ai)\//.test(url)) {
      void shell.openExternal(url);
    }
  });
  own("app:updates", () => shell.openExternal(`${RELEASES}/latest`));
  own("app:shot", async (e, name: string) => {
    if (!SHOTS) return false;
    if (name === "end") {
      setTimeout(() => app.exit(0), 6000); // time for CI to take a picture of the whole screen, window buttons included
      return true;
    }
    const win = BrowserWindow.fromWebContents(e.sender);
    const img = await win?.webContents.capturePage();
    if (img) {
      mkdirSync(SHOTS, { recursive: true });
      writeFileSync(join(SHOTS, `${String(name).replace(/[^\w-]/g, "")}.png`), img.toPNG());
    }
    return true;
  });
}

// ---------- start and quit ----------

app.on("second-instance", showMain);
app.on("activate", showMain);

app.on("before-quit", (e) => {
  if (quitting) return;
  quitting = true;
  stopSignIn();
  hostHelper.stop();
  if (!stackStarted) return;
  e.preventDefault();
  main?.hide();
  void stack.stop(stackConfig()).finally(() => app.exit(0));
});

app.on("window-all-closed", () => {
  if (!settings?.get().keepRunning) app.quit();
});

if (firstInstance) void app.whenReady().then(async () => {
  await initializeSecrets();
  settings = new SettingsFile(join(app.getPath("userData"), "settings.json"), homedir(), PROFILE.studioDir);
  desktopPrompter = new DesktopPrompter(settings, PORT, PROFILE.prompterPort);
  desktopMedia = new DesktopMedia(() => settings.get().studioDir, async () => [
    ...(["videos", "pictures", "music", "downloads", "desktop"] as const).map(name => ({ path: app.getPath(name), label: name })),
    ...await removableRoots(process.platform, homedir()),
    ...(settings.get().mediaFolders ?? []).map(path => ({ path, label: path.split(/[\\/]/).filter(Boolean).at(-1) ?? "Media folder" })),
  ]);
  const mediaPoll = setInterval(() => { void desktopMedia.poll().catch(error => log(`Media: ${String(error)}`)); }, 300);
  mediaPoll.unref();
  const prompterPoll = setInterval(() => { void desktopPrompter.poll().catch(() => undefined); }, 1500);
  prompterPoll.unref();
  if (SHOTS) settings.set({ onboarded: false });
  buildMenu();
  registerIpc();
  createMain();
  updateTray();
  nativeTheme.on("updated", () => {
    for (const w of [main, settingsWin]) if (w && !w.isDestroyed()) applyTheme(w, themeNow());
  });
  if (!PROFILE.development) startUpdates(log);
});
