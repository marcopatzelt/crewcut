// The Claude token in the system keychain: Electron's safeStorage encrypts it with a key that the keychain (macOS),
// DPAPI (Windows) or the desktop's secret service (GNOME Keyring, KWallet) holds. Without one of these the app does
// not keep the token at all (Linux would only obfuscate it); the container's engine volume keeps it instead.
import { app, safeStorage } from "electron";
import { join } from "node:path";
import { TokenStore } from "./token-store";

let store: TokenStore | undefined;

function secureBackend(): boolean {
  if (!safeStorage.isEncryptionAvailable()) return false;
  if (process.platform === "linux") {
    const backend = safeStorage.getSelectedStorageBackend();
    return backend !== "basic_text" && backend !== "unknown";
  }
  return true;
}

function tokenStore(): TokenStore {
  return store ??= new TokenStore(join(app.getPath("userData"), "claude-token.bin"), {
    available: async () => secureBackend() && await safeStorage.isAsyncEncryptionAvailable(),
    encrypt: (token) => safeStorage.encryptStringAsync(token),
    decrypt: async (bytes) => (await safeStorage.decryptStringAsync(bytes)).result,
  });
}

export const initializeSecrets = (): Promise<void> => tokenStore().load();
export const keychainAvailable = (): boolean => tokenStore().isAvailable();
export const loginProblem = (): "no-keychain" | "unreadable" | null => tokenStore().loginProblem();
export const getToken = (): string | null => tokenStore().get();
export const setToken = (token: string): Promise<void> => tokenStore().set(token);
export const deleteToken = (): void => tokenStore().delete();
