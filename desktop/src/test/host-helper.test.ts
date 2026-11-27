// The host helper next to the desktop app: its key, the second opinion's settings, its environment, and a real run of
// host/crewcut-host.sh with a fake second-opinion command (bash and openssl; nothing real is started).
import { strict as assert } from "node:assert";
import { execFileSync, spawn } from "node:child_process";
import { createHash, createHmac, randomBytes } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { HostHelper, helperEnv, hostToken, isHelperProcess, secondOpinionConfig, type HelperConfig } from "../host-helper";
import { composeEnv } from "../stack";

const ROOT = join(__dirname, "..", "..", "..");
const SCRIPT = join(ROOT, "host", "crewcut-host.sh");
const tools = (() => {
  try {
    execFileSync("openssl", ["version"], { stdio: "ignore" });
    execFileSync("bash", ["--version"], { stdio: "ignore" });
    return process.platform !== "win32";
  } catch {
    return false;
  }
})();

async function until<T>(what: () => T | undefined | null | false, ms = 15_000): Promise<T> {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    const v = what();
    if (v) return v;
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error("timed out");
}

const readJson = (f: string) => {
  try {
    return JSON.parse(readFileSync(f, "utf8")) as Record<string, unknown>;
  } catch {
    return null;
  }
};

test("the host key is made once, owner-only, next to the stack, and keeps the file's other lines", () => {
  const dir = join(mkdtempSync(join(tmpdir(), "crewcut-key-")), "stack");
  const first = hostToken(dir);
  assert.match(first, /^[0-9a-f]{64}$/);
  assert.equal(hostToken(dir), first);
  const file = join(dir, ".env");
  if (process.platform !== "win32") assert.equal(statSync(file).mode & 0o777, 0o600);
  writeFileSync(file, "OTHER=1\nCREWCUT_HOST_TOKEN=\n");
  const second = hostToken(dir);
  assert.notEqual(second, first);
  assert.equal(readFileSync(file, "utf8"), `OTHER=1\nCREWCUT_HOST_TOKEN=${second}\n`);
});

test("the container gets the host key from the docker command's environment, never the shell's", () => {
  const cfg = { composeFiles: [], projectDir: "/data/stack", studioDir: "/home/me/Crewcut", image: "i", tag: "t",
    port: 4747 };
  assert.equal(composeEnv({ ...cfg, hostToken: "k".repeat(64) }, {}).CREWCUT_HOST_TOKEN, "k".repeat(64));
  assert.equal(composeEnv(cfg, { CREWCUT_HOST_TOKEN: "from-the-shell" }).CREWCUT_HOST_TOKEN, "");
  const override = readFileSync(join(ROOT, "desktop/stack/desktop.yaml"), "utf8");
  assert.match(override, /CREWCUT_HOST_TOKEN: \$\{CREWCUT_HOST_TOKEN:-\}/);
  const builder = readFileSync(join(ROOT, "desktop/electron-builder.config.cjs"), "utf8");
  assert.match(builder, /from: "\.\.\/host", to: "host", filter: \["crewcut-host\.sh", "prompts\/\*\*"\]/);
  const main = readFileSync(join(ROOT, "desktop/src/main.ts"), "utf8");
  assert.match(main, /hostHelper\.stop\(\)/);
  assert.equal((main.match(/startHelper\(\);/g) ?? []).length, 2); // a healthy stack and a fresh start
});

test("the second opinion: the environment first, then settings.json; its own folder, never the home folder", () => {
  const home = "/home/me";
  const data = "/home/me/.config/Crewcut";
  assert.deepEqual(secondOpinionConfig(undefined, {}, data, home),
    { command: "", dir: join(data, "second-opinion"), parallel: 2 });
  assert.deepEqual(secondOpinionConfig({ command: "neon", dir: "~/zweitmeinung", parallel: 1 }, {}, data, home),
    { command: "neon", dir: join(home, "zweitmeinung"), parallel: 1 });
  assert.deepEqual(secondOpinionConfig({ command: "neon", parallel: 1 },
    { CREWCUT_SECOND_OPINION_CMD: "other", CREWCUT_SECOND_OPINION_DIR: "/tmp/so", CREWCUT_SECOND_OPINION_PARALLEL: "3" },
    data, home), { command: "other", dir: "/tmp/so", parallel: 3 });
  assert.equal(secondOpinionConfig({ dir: "~" }, {}, data, home).dir, join(data, "second-opinion"));
  assert.equal(secondOpinionConfig({ dir: home }, {}, data, home).dir, join(data, "second-opinion"));
  assert.equal(secondOpinionConfig({ parallel: 0 }, {}, data, home).parallel, 2);
  assert.equal(secondOpinionConfig({ parallel: 99 }, {}, data, home).parallel, 2);
});

test("the helper's environment: studio, key, its parent, a PATH that finds the user's tools", () => {
  const c: HelperConfig = { script: SCRIPT, studioDir: "/home/me/Crewcut", token: "t".repeat(64), parentPid: 4242,
    secondOpinion: { command: "", dir: "/home/me/.config/Crewcut/second-opinion", parallel: 2 } };
  const env = helperEnv(c, { PATH: "/usr/bin", CREWCUT_SECOND_OPINION_CMD: "stale", DISPLAY: ":0" }, "linux", "/home/me");
  assert.equal(env.CREWCUT_STUDIO_DIR, "/home/me/Crewcut");
  assert.equal(env.CREWCUT_HOST_TOKEN, "t".repeat(64));
  assert.equal(env.CREWCUT_HOST_BY, "desktop app");
  assert.equal(env.CREWCUT_HOST_PARENT, "4242");
  assert.equal(env.CREWCUT_SECOND_OPINION_CMD, undefined);
  assert.equal(env.CREWCUT_SECOND_OPINION_DIR, "/home/me/.config/Crewcut/second-opinion");
  assert.equal(env.DISPLAY, ":0");
  assert.ok(env.PATH?.split(":").includes("/home/me/.local/bin"));
  const withCmd = helperEnv({ ...c, secondOpinion: { ...c.secondOpinion, command: "neon" } }, {}, "linux", "/home/me");
  assert.equal(withCmd.CREWCUT_SECOND_OPINION_CMD, "neon");
  assert.equal(isHelperProcess(process.pid), false);
  assert.equal(isHelperProcess(1), false);
});

test("the app runs the helper: a signed second opinion runs the command in its own folder, Quit stops it",
  { skip: !tools && "bash and openssl are needed" }, async () => {
    const tmp = mkdtempSync(join(tmpdir(), "crewcut-helper-"));
    const studio = join(tmp, "studio");
    const brief = join(studio, "episodes", "001", "brief");
    mkdirSync(brief, { recursive: true });
    writeFileSync(join(brief, "CUES-v001.md"), "Hook line.\n---\nnotes\n");
    writeFileSync(join(brief, "CUES-v001.kritik.json"), "{\"verdict\": \"pass\"}\n");
    const dir = join(tmp, "data", "second-opinion");
    const token = randomBytes(32).toString("hex");
    const command = "pwd > \"$INPUT_FILE.cwd\"; grep -c 'Hook line.' \"$INPUT_FILE\" > /dev/null && "
      + "printf '{\"agree\": true, \"points\": [], \"model\": \"fake\"}'";
    const lines: string[] = [];
    const helper = new HostHelper((l) => lines.push(l));
    const cfg: HelperConfig = { script: SCRIPT, studioDir: studio, token, parentPid: process.pid,
      secondOpinion: { command, dir, parallel: 2 } };
    helper.start(cfg);
    try {
      const box = join(studio, ".crewcut", "host");
      const beat = await until(() => readJson(join(box, "helper.json")));
      assert.equal(beat.by, "desktop app");
      assert.equal(beat.second_opinion, true);
      assert.equal(beat.second_opinion_parallel, 2);
      assert.ok(existsSync(join(box, "helper.pid")));
      helper.start(cfg); // nothing changed: the same helper keeps running
      assert.equal(lines.filter((l) => l.startsWith("host helper: started")).length, 1);

      const fields: Record<string, string> = { kind: "second-opinion", id: "so-1-abc", at: String(Math.floor(Date.now() / 1000)),
        nonce: randomBytes(16).toString("hex"),
        prompt_sha256: createHash("sha256").update(readFileSync(join(ROOT, "host", "prompts", "second-opinion.md")))
          .digest("hex"),
        file: "episodes/001/brief/CUES-v001.md", verdict: "episodes/001/brief/CUES-v001.kritik.json",
        answer: "episodes/001/brief/CUES-v001.second.json" };
      const msg = Object.keys(fields).map((k) => `${k}=${fields[k]}`).join(";");
      fields.sig = createHmac("sha256", token).update(msg).digest("hex");
      mkdirSync(join(box, "requests"), { recursive: true });
      writeFileSync(join(box, "requests", "so-1-abc.req"), Object.entries(fields).map(([k, v]) => `${k}=${v}\n`).join(""));
      const answer = await until(() => readJson(join(box, "runs", "so-1-abc.json")));
      assert.deepEqual(answer, { agree: true, points: [], model: "fake" });
      assert.equal(readFileSync(join(box, "runs", "so-1-abc.input.cwd"), "utf8").trim(), dir);

      // a request signed with another key is refused, and its answer file says so at once
      const bad = { ...fields, id: "so-2-abc", nonce: randomBytes(16).toString("hex"), sig: "0".repeat(64) };
      writeFileSync(join(box, "requests", "so-2-abc.req"), Object.entries(bad).map(([k, v]) => `${k}=${v}\n`).join(""));
      const refused = await until(() => readJson(join(box, "runs", "so-2-abc.json")));
      assert.equal(refused.status, "unavailable");
      assert.match(String(refused.error), /not signed by this Crewcut/);
    } finally {
      helper.stop();
    }
    await until(() => !existsSync(join(studio, ".crewcut", "host", "helper.json")));
    assert.equal(helper.running, false);
    assert.ok(!readFileSync(join(studio, ".crewcut", "logs", "host.log"), "utf8").includes(token));
  });

test("the helper stops by itself when the app is gone", { skip: !tools && "bash and openssl are needed" }, async () => {
  const tmp = mkdtempSync(join(tmpdir(), "crewcut-orphan-"));
  const studio = join(tmp, "studio");
  const parent = spawn(process.execPath, ["-e", "setTimeout(() => {}, 1500)"], { stdio: "ignore" });
  const c: HelperConfig = { script: SCRIPT, studioDir: studio, token: randomBytes(32).toString("hex"),
    parentPid: parent.pid ?? 0, secondOpinion: { command: "", dir: join(tmp, "so"), parallel: 2 } };
  const child = spawn("bash", [SCRIPT], { env: helperEnv(c), stdio: "ignore" });
  const exited = new Promise<number | null>((r) => child.on("exit", (code) => r(code)));
  await until(() => readJson(join(studio, ".crewcut", "host", "helper.json")));
  const ended = await Promise.race([exited, new Promise<string>((r) => setTimeout(() => r("still running"), 10_000))]);
  if (ended !== 0) child.kill();
  assert.equal(ended, 0);
  assert.ok(!existsSync(join(studio, ".crewcut", "host", "helper.json")));
});
