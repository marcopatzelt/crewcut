// Updates from GitHub Releases (electron-updater). Windows and Linux (AppImage) download and install them on quit.
// A Mac build without a Developer ID is only ad-hoc signed, and macOS's updater refuses to swap such an app, so there
// the app says a new version is out and opens the download (or the one-line install command) instead.
import { app, dialog, shell } from "electron";
import { autoUpdater } from "electron-updater";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { RELEASES } from "./release";

/** CI writes dist/build-info.json: {"signed": true} only when a Developer ID signed the Mac build. */
function signedBuild(): boolean {
  try {
    return (JSON.parse(readFileSync(join(__dirname, "build-info.json"), "utf8")) as { signed?: boolean }).signed === true;
  } catch {
    return false;
  }
}

const SIGNED = signedBuild();

export function startUpdates(log: (line: string) => void): void {
  if (!app.isPackaged || process.env.CREWCUT_NO_UPDATES === "1") return;
  const silentInstall = process.platform !== "darwin" || SIGNED;
  autoUpdater.autoDownload = silentInstall;
  autoUpdater.autoInstallOnAppQuit = silentInstall;
  autoUpdater.on("error", (e) => log(`update check: ${e.message}`));
  autoUpdater.on("update-available", (info) => {
    if (silentInstall) return;
    void dialog
      .showMessageBox({
        type: "info",
        message: `Crewcut ${info.version} is out.`,
        detail: "Download it from the releases page, or run the one-line install command again.",
        buttons: ["Open the download", "Later"],
        defaultId: 0,
        cancelId: 1,
      })
      .then((r) => {
        if (r.response === 0) void shell.openExternal(`${RELEASES}/latest`);
      });
  });
  const check = () => autoUpdater.checkForUpdates().catch((e: Error) => log(`update check: ${e.message}`));
  void check();
  setInterval(check, 6 * 60 * 60 * 1000).unref();
}
