// The bridge between the pages and the app (sandboxed, context-isolated). The local Crewcut page gets three calls
// (connect, settings, theme); the app's own pages (onboarding and settings, file://) get the steps of the first start.
// The main process checks the sender of every call again.
import { contextBridge, ipcRenderer } from "electron";

type Listener = (data: unknown) => void;

const ownPage = location.protocol === "file:";
const call = (channel: string, ...args: unknown[]) => ipcRenderer.invoke(channel, ...args);

const forPage = {
  platform: process.platform,
  connect: (engine: "claude" | "codex") => call("page:connect", engine),
  openSettings: () => void call("page:settings"),
  setTheme: (theme: "light" | "dark") => void call("page:theme", theme),
};

const forOwnPages = {
  ...forPage,
  version: () => call("app:version"),
  settings: () => call("settings:get"),
  setKeepRunning: (on: boolean) => call("settings:keep-running", on),
  checkDocker: () => call("docker:check"),
  defaultStudio: () => call("studio:default"),
  chooseStudio: () => call("studio:choose"),
  setStudio: (dir: string) => call("studio:set", dir),
  startStack: () => call("stack:start"),
  onProgress: (fn: Listener) => {
    const handler = (_e: unknown, data: unknown) => fn(data);
    ipcRenderer.on("stack:progress", handler);
    return () => ipcRenderer.off("stack:progress", handler);
  },
  claudeBegin: () => call("claude:begin"),
  claudeCode: (code: string) => call("claude:code", code),
  codexBegin: () => call("codex:begin"),
  codexWait: () => call("codex:wait"),
  cancelSignIn: () => call("signin:cancel"),
  disconnect: (engine: "claude" | "codex") => call("engine:disconnect", engine),
  openCrewcut: () => call("app:open"),
  closeSettings: (result: unknown) => call("settings:close", result),
  openExternal: (url: string) => call("app:external", url),
  checkUpdates: () => call("app:updates"),
  shot: (name: string) => call("app:shot", name),
};

contextBridge.exposeInMainWorld("crewcutDesktop", ownPage ? forOwnPages : forPage);
