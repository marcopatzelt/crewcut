import { closeSync, existsSync, fsyncSync, openSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { TOKEN_RE } from "./connect";

export interface TokenCipher {
  available(): Promise<boolean>;
  encrypt(token: string): Promise<Buffer>;
  decrypt(bytes: Buffer): Promise<string>;
}

export class TokenStore {
  private token: string | null = null;
  private available = false;
  private problem: "no-keychain" | "unreadable" | null = null;

  constructor(private file: string, private cipher: TokenCipher) {}

  async load(): Promise<void> {
    this.token = null;
    this.available = false;
    this.problem = null;
    try { this.available = await this.cipher.available(); } catch {}
    if (!existsSync(this.file)) return;
    if (!this.available) {
      this.problem = "no-keychain";
      return;
    }
    try {
      const token = await this.cipher.decrypt(readFileSync(this.file));
      if (!TOKEN_RE.test(token)) throw new Error("Invalid stored login.");
      this.token = token;
    } catch { this.problem = "unreadable"; }
  }

  get(): string | null { return this.token; }
  isAvailable(): boolean { return this.available; }
  loginProblem(): "no-keychain" | "unreadable" | null { return this.problem; }

  async set(token: string): Promise<void> {
    if (!TOKEN_RE.test(token)) throw new Error("That is not a Claude Code token.");
    if (!(await this.cipher.available())) throw new Error("No system keychain is available.");
    const encrypted = await this.cipher.encrypt(token);
    if ((await this.cipher.decrypt(encrypted)) !== token) throw new Error("The system keychain could not verify the login.");
    const temporary = `${this.file}.${randomUUID()}.tmp`;
    try {
      const descriptor = openSync(temporary, "wx", 0o600);
      try {
        writeFileSync(descriptor, encrypted);
        fsyncSync(descriptor);
      } finally { closeSync(descriptor); }
      renameSync(temporary, this.file);
    } finally { rmSync(temporary, { force: true }); }
    this.token = token;
    this.available = true;
    this.problem = null;
  }

  delete(): void {
    rmSync(this.file, { force: true });
    this.token = null;
    this.problem = null;
  }
}
