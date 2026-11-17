// The Claude token in the system keychain: Electron's safeStorage encrypts it with a key that the keychain (macOS),
// DPAPI (Windows) or the desktop's secret service (GNOME Keyring, KWallet) holds. Without one of these the app does
// not keep the token at all (Linux would only obfuscate it); the container's engine volume keeps it instead.
import { app, safeStorage } from "electron";
import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { TOKEN_RE } from "./connect";

const file = () => join(app.getPath("userData"), "claude-token.bin");

export function keychainAvailable(): boolean {
  if (!safeStorage.isEncryptionAvailable()) return false;
  if (process.platform === "linux") {
    const backend = safeStorage.getSelectedStorageBackend();
    return backend !== "basic_text" && backend !== "unknown";
  }
  return true;
}

/** Why a stored login cannot be used: "no-keychain" (the app runs without the desktop's keychain, e.g. started from a
 *  terminal outside the desktop session) or "unreadable" (the keychain did not decrypt it). null: fine or none. */
export function loginProblem(): "no-keychain" | "unreadable" | null {
  if (!existsSync(file())) return null;
  if (!keychainAvailable()) return "no-keychain";
  return getToken() ? null : "unreadable";
}

export function getToken(): string | null {
  try {
    if (!existsSync(file()) || !keychainAvailable()) return null;
    const token = safeStorage.decryptString(readFileSync(file()));
    return TOKEN_RE.test(token) ? token : null;
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  if (!TOKEN_RE.test(token)) throw new Error("That is not a Claude Code token.");
  if (!keychainAvailable()) throw new Error("No system keychain is available.");
  writeFileSync(file(), safeStorage.encryptString(token), { mode: 0o600 });
}

export function deleteToken(): void {
  rmSync(file(), { force: true });
}
