// Plain-Node tests of the parts without Electron: image tags, settings, Docker progress, the sign-in lines, the
// stack's command and environment, and the window colours against the web app's tokens.
import { strict as assert } from "node:assert";
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { CODE_RE, deviceAllowed, parseStep, signInAllowed, Steps, TOKEN_RE } from "../connect";
import { bytesWords, composeOk, PullProgress, socketFromHost } from "../docker";
import { imageTag } from "../release";
import { SettingsFile, visibleBounds } from "../settings";
import { composeArgs, composeEnv, failing, parseState } from "../stack";
import { THEME } from "../theme";

const ROOT = join(__dirname, "..", "..", "..");

test("a release runs exactly its own image, everything else :edge", () => {
  assert.equal(imageTag("0.2.1", true), "0.2.1");
  assert.equal(imageTag("0.2.1-dev.42", true), "edge");
  assert.equal(imageTag("0.2.1", false), "edge");
  assert.equal(imageTag("0.2.1", true, "abc123"), "abc123");
  assert.equal(imageTag("0.2.1", true, "bad tag; rm"), "0.2.1");
});

test("settings: defaults, saved, a broken file starts over, bounds only when on a screen", () => {
  const dir = mkdtempSync(join(tmpdir(), "crewcut-settings-"));
  const f = new SettingsFile(join(dir, "settings.json"), "/home/me");
  assert.equal(f.get().studioDir, join("/home/me", "Crewcut"));
  assert.equal(f.get().keepRunning, false);
  f.set({ keepRunning: true, studioDir: "/data/videos" });
  const again = new SettingsFile(join(dir, "settings.json"), "/home/me");
  assert.equal(again.get().keepRunning, true);
  assert.equal(again.get().studioDir, "/data/videos");
  assert.ok(!readFileSync(join(dir, "settings.json"), "utf8").includes("sk-ant"));
  const screens = [{ x: 0, y: 0, width: 1920, height: 1080 }];
  assert.deepEqual(visibleBounds({ x: 100, y: 100, width: 1200, height: 800 }, screens), { x: 100, y: 100, width: 1200, height: 800 });
  assert.equal(visibleBounds({ x: 5000, y: 100, width: 1200, height: 800 }, screens), undefined);
});

test("Docker: compose version, sockets, progress from the Engine API's messages", () => {
  assert.equal(composeOk("2.24.0"), true);
  assert.equal(composeOk("2.23.9"), false);
  assert.equal(composeOk("5.6.1"), true);
  assert.equal(socketFromHost("unix:///Users/me/.docker/run/docker.sock"), "/Users/me/.docker/run/docker.sock");
  assert.equal(socketFromHost("npipe:////./pipe/dockerDesktopLinuxEngine"), "\\\\.\\pipe\\dockerDesktopLinuxEngine");
  assert.equal(socketFromHost("tcp://1.2.3.4:2376"), null);
  const p = new PullProgress();
  p.feed({ status: "Pulling from marcopatzelt/crewcut", id: "edge" });
  p.feed({ status: "Pulling fs layer", id: "aaaaaaaaaaaa" });
  p.feed({ status: "Downloading", id: "aaaaaaaaaaaa", progressDetail: { current: 50, total: 200 } });
  p.feed({ status: "Already exists", id: "bbbbbbbbbbbb" });
  let now = p.feed({ status: "Downloading", id: "cccccccccccc", progressDetail: { current: 100, total: 800 } });
  assert.deepEqual(now, { current: 150, total: 1000, layersDone: 1, layers: 3 });
  now = p.feed({ status: "Pull complete", id: "aaaaaaaaaaaa" });
  assert.equal(now?.current, 300);
  assert.throws(() => p.feed({ error: "manifest unknown" }), /manifest unknown/);
  assert.equal(bytesWords(1.2e9, 3.4e9), "1.2 GB of 3.4 GB");
  assert.equal(bytesWords(120e6, 900e6), "120 MB of 900 MB");
});

test("only Anthropic's sign-in and OpenAI's device page are opened; codes and tokens have their shape", () => {
  assert.ok(signInAllowed("https://claude.ai/oauth/authorize?code=true"));
  assert.ok(signInAllowed("https://platform.claude.com/oauth/code/callback"));
  assert.ok(!signInAllowed("http://claude.ai/oauth/authorize"));
  assert.ok(!signInAllowed("https://claude.ai.evil.example/x"));
  assert.ok(!signInAllowed("https://user:pw@claude.ai/x"));
  assert.ok(deviceAllowed("https://auth.openai.com/codex/device"));
  assert.ok(!deviceAllowed("https://claude.ai/x"));
  assert.ok(CODE_RE.test("abcd1234#state-1"));
  assert.ok(!CODE_RE.test("short"));
  assert.ok(!CODE_RE.test("has space 12345"));
  assert.ok(TOKEN_RE.test("sk-ant-oat01-AbCdEfGhIjKlMnOpQrStUvWxYz0123"));
  assert.equal(parseStep("not json"), null);
  assert.deepEqual(parseStep('{"step":"url","url":"https://claude.ai/x"}'), { step: "url", url: "https://claude.ai/x" });
});

test("the JSON lines of `crewcut engine connect`: the link, the code goes in, the token comes out", async () => {
  // a stand-in for `docker compose exec ... crewcut engine connect claude --print-token`
  const script = `
    console.log("noise that is not JSON");
    console.log(JSON.stringify({step: "url", url: "https://claude.ai/oauth/authorize?code=true"}));
    process.stdin.once("data", (d) => {
      const code = String(d).trim();
      console.log(JSON.stringify(code === "goodcode#1" ? {step: "done", token: "sk-ant-oat01-${"x".repeat(24)}"}
        : {step: "error", text: "Claude did not accept the code."}));
      process.exit(0);
    });`;
  const steps = new Steps(spawn(process.execPath, ["-e", script], { stdio: ["pipe", "pipe", "pipe"] }));
  const url = await steps.next((s) => s.step === "url", 5000);
  assert.equal(url.url, "https://claude.ai/oauth/authorize?code=true");
  steps.sendLine("goodcode#1\n");
  const done = await steps.next((s) => s.step === "done", 5000);
  assert.equal(done.step, "done");
  assert.ok(TOKEN_RE.test(done.token ?? ""));
  const quiet = new Steps(spawn(process.execPath, ["-e", "process.exit(3)"], { stdio: ["pipe", "pipe", "pipe"] }));
  assert.equal((await quiet.next((s) => s.step === "url", 5000)).step, "error");
});

test("the stack: the same project as ./start.sh, the token only in the docker command's environment", () => {
  const cfg = {
    composeFiles: ["/app/stack/compose.yaml", "/app/stack/desktop.yaml"],
    projectDir: "/data/stack",
    studioDir: "/home/me/Crewcut",
    image: "ghcr.io/marcopatzelt/crewcut",
    tag: "0.2.1",
    port: 4747,
    token: "sk-ant-oat01-secret",
  };
  assert.deepEqual(composeArgs(cfg), ["compose", "-p", "crewcut", "--project-directory", "/data/stack",
    "-f", "/app/stack/compose.yaml", "-f", "/app/stack/desktop.yaml"]);
  const env = composeEnv(cfg, { PATH: "/usr/bin", CLAUDE_CODE_OAUTH_TOKEN: "from-the-shell" });
  assert.equal(env.CREWCUT_TAG, "0.2.1");
  assert.equal(env.CREWCUT_STUDIO_DIR, "/home/me/Crewcut");
  assert.equal(env.CREWCUT_IMPORT_DIR, join("/home/me/Crewcut", "import"));
  assert.equal(env.CLAUDE_CODE_OAUTH_TOKEN, "sk-ant-oat01-secret");
  assert.equal(composeEnv({ ...cfg, token: null }, { CLAUDE_CODE_OAUTH_TOKEN: "from-the-shell" }).CLAUDE_CODE_OAUTH_TOKEN, "");
  assert.ok(!process.env.CLAUDE_CODE_OAUTH_TOKEN?.includes("secret"));
});

test("the window's colours are the web app's tokens", () => {
  const css = readFileSync(join(ROOT, "web/src/styles/tokens.css"), "utf8");
  const light = css.slice(0, css.indexOf(':root[data-theme="dark"]'));
  const dark = css.slice(css.indexOf(':root[data-theme="dark"]'));
  const token = (block: string, name: string) => new RegExp(`${name}:\\s*(#[0-9A-Fa-f]{6})`).exec(block)?.[1];
  for (const [block, theme] of [[light, THEME.light], [dark, THEME.dark]] as const) {
    assert.equal(token(block, "--panel"), theme.panel);
    assert.equal(token(block, "--ink"), theme.ink);
    assert.equal(token(block, "--window"), theme.window);
  }
});

test("the stack file the app ships is the repository's own compose.yaml plus a small override", () => {
  const override = readFileSync(join(ROOT, "desktop/stack/desktop.yaml"), "utf8");
  assert.match(override, /build: !reset null/);
  assert.match(override, /pull_policy: never/);
  const builder = readFileSync(join(ROOT, "desktop/electron-builder.config.cjs"), "utf8");
  assert.match(builder, /from: "\.\.\/compose\.yaml"/);
  const compose = readFileSync(join(ROOT, "compose.yaml"), "utf8");
  assert.match(compose, /CLAUDE_CODE_OAUTH_TOKEN: \$\{CLAUDE_CODE_OAUTH_TOKEN:-\}/);
});

test("a container that starts over and over is a failed start, not a long one", () => {
  assert.deepEqual(parseState("restarting|3|1\n"), { status: "restarting", restarts: 3, exitCode: 1 });
  const base = parseState("running|0|0");
  assert.equal(failing(base, parseState("running|0|0")), false);
  assert.equal(failing(base, parseState("restarting|1|1")), true);
  assert.equal(failing(base, parseState("exited|0|78")), true);
  // a container that was already looping before this start: only a new restart counts
  assert.equal(failing(parseState("restarting|9|1"), parseState("running|9|0")), false);
  assert.equal(failing(parseState("restarting|9|1"), parseState("restarting|10|1")), true);
  assert.equal(failing(null, null), false);
});
