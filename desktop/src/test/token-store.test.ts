import { strict as assert } from "node:assert";
import { mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { TokenStore, type TokenCipher } from "../token-store";

const fakeToken = "sk-ant-oat01-" + "synthetic".repeat(4);
const encrypted = Buffer.from("synthetic-ciphertext");
const cipher: TokenCipher = {
  available: async () => true,
  encrypt: async () => encrypted,
  decrypt: async () => fakeToken,
};

test("saved login survives a new store instance with restrictive permissions", async () => {
  const folder = mkdtempSync(join(tmpdir(), "crewcut-token-test-"));
  try {
    const file = join(folder, "login.bin");
    const first = new TokenStore(file, cipher);
    await first.load();
    await first.set(fakeToken);
    const restarted = new TokenStore(file, cipher);
    await restarted.load();
    assert.equal(restarted.get(), fakeToken);
    assert.equal(restarted.loginProblem(), null);
    assert.deepEqual(readFileSync(file), encrypted);
    if (process.platform !== "win32") assert.equal(statSync(file).mode & 0o777, 0o600);
  } finally { rmSync(folder, { recursive: true, force: true }); }
});

test("unreadable login is preserved, and failed replacement does not overwrite it", async () => {
  const folder = mkdtempSync(join(tmpdir(), "crewcut-token-test-"));
  try {
    const file = join(folder, "login.bin");
    writeFileSync(file, encrypted);
    const broken = new TokenStore(file, { ...cipher, decrypt: async () => { throw new Error("Synthetic failure"); } });
    await broken.load();
    assert.equal(broken.get(), null);
    assert.equal(broken.loginProblem(), "unreadable");
    await assert.rejects(broken.set(fakeToken));
    assert.deepEqual(readFileSync(file), encrypted);
    const invalid = new TokenStore(file, { ...cipher, decrypt: async () => "not-a-login" });
    await invalid.load();
    assert.equal(invalid.loginProblem(), "unreadable");
    await assert.rejects(invalid.set(fakeToken), /verify/);
    await assert.rejects(invalid.set("invalid"), /not a Claude/);
    assert.deepEqual(readFileSync(file), encrypted);
  } finally { rmSync(folder, { recursive: true, force: true }); }
});

test("temporarily unavailable keychain can be retried without losing the login", async () => {
  const folder = mkdtempSync(join(tmpdir(), "crewcut-token-test-"));
  try {
    const file = join(folder, "login.bin");
    writeFileSync(file, encrypted);
    let available = false;
    const store = new TokenStore(file, { ...cipher, available: async () => available });
    await store.load();
    assert.equal(store.loginProblem(), "no-keychain");
    await assert.rejects(store.set(fakeToken), /No system keychain/);
    available = true;
    await store.load();
    assert.equal(store.get(), fakeToken);
    assert.equal(store.loginProblem(), null);
    store.delete();
    assert.equal(store.get(), null);
  } finally { rmSync(folder, { recursive: true, force: true }); }
});
