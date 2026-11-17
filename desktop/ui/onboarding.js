// The desktop app's own pages: the first start (Docker, the studio folder, the download, Connect Claude) and the
// settings. Plain script, no framework; it talks to the app only through window.crewcutDesktop (preload).
"use strict";

const D = window.crewcutDesktop;
const view = document.getElementById("view");
const params = new URLSearchParams(location.search);
const SHOTS = params.get("shots") === "1";
const HASH = location.hash.replace(/^#/, "");
const platform = D.platform;

// ---------- small helpers ----------

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

function show(...nodes) {
  view.className = "view";
  view.replaceChildren(...nodes.flat().filter(Boolean));
}

const slate = (state) => h("img", { class: "slate", src: `brand/${state}.svg`, alt: "" });
const spinner = () => h("span", { class: "spin", "aria-hidden": "true" });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const shot = async (name) => {
  if (!SHOTS) return;
  await wait(700);
  try {
    await D.shot(name);
  } catch {
    // a picture that could not be taken does not stop the others (CI only)
  }
};

// ---------- the steps ----------

function welcome() {
  show(
    slate("wave"),
    h("h1", {}, "Crewcut runs on your computer."),
    h("p", {}, "It needs Docker, a folder for your videos and your Claude plan. Three steps; the first start downloads Crewcut once."),
    h("div", { class: "row" }, h("button", { class: "primary", onclick: () => void dockerStep(true) }, "Start")),
  );
}

const DOCKER_HELP = {
  darwin: {
    text: "Install Docker Desktop, OrbStack or Colima, start it, then press Try again.",
    links: [
      ["Docker Desktop", "https://docs.docker.com/desktop/setup/install/mac-install/"],
      ["OrbStack", "https://orbstack.dev/download"],
      ["Colima", "https://github.com/abiosoft/colima#installation"],
    ],
    start: "Start Docker Desktop (or OrbStack, or `colima start`) and wait until it runs, then press Try again.",
  },
  win32: {
    text: "Install Docker Desktop, start it, then press Try again.",
    links: [["Docker Desktop", "https://docs.docker.com/desktop/setup/install/windows-install/"]],
    start: "Start Docker Desktop and wait until it says it is running, then press Try again.",
  },
  linux: {
    text: "Install Docker Engine with the Compose plugin, then press Try again.",
    links: [["Docker Engine", "https://docs.docker.com/engine/install/"]],
    start: "Start Docker (sudo systemctl start docker) and make sure your user may use it, then press Try again.",
  },
};

async function dockerStep(firstRun) {
  show(spinner(), h("p", {}, "Looking for Docker…"));
  const d = await D.checkDocker();
  const help = DOCKER_HELP[platform] || DOCKER_HELP.linux;
  const retry = h("button", { class: "primary", onclick: () => void dockerStep(firstRun) }, "Try again");
  if (!d.cli) {
    show(
      slate("waiting"),
      h("h1", {}, "Crewcut needs Docker."),
      h("p", {}, help.text),
      h("div", { class: "row" }, ...help.links.map(([label, url]) =>
        h("button", { class: "secondary", onclick: () => void D.openExternal(url) }, label)), retry),
    );
    return shot("docker");
  }
  if (!d.running) {
    show(
      slate("waiting"),
      h("h1", {}, "Docker is not running."),
      h("p", {}, help.start),
      d.detail ? h("p", { class: "note" }, d.detail) : null,
      h("div", { class: "row" }, retry),
    );
    return shot("docker");
  }
  if (!d.compose) {
    show(
      slate("waiting"),
      h("h1", {}, "Docker Compose is too old."),
      h("p", {}, `Crewcut needs Docker Compose 2.24 or newer (found ${d.composeVersion || "none"}). Update Docker, then press Try again.`),
      h("div", { class: "row" }, retry),
    );
    return shot("docker");
  }
  if (firstRun) return studioStep();
  return startStep();
}

async function studioStep() {
  const s = await D.settings();
  let dir = s.studioDir;
  const path = h("p", { class: "mono" }, dir);
  show(
    slate("idle"),
    h("h1", {}, "Where should your videos live?"),
    h("p", {}, "Your style pack, every episode and its files go into this folder. Crewcut never uploads it."),
    path,
    h("div", { class: "row" },
      h("button", { class: "primary", onclick: async () => {
        await D.setStudio(dir);
        void startStep();
      } }, "Use this folder"),
      h("button", { class: "secondary", onclick: async () => {
        const chosen = await D.chooseStudio();
        if (chosen) {
          dir = chosen;
          path.textContent = chosen;
        }
      } }, "Choose another folder…")),
  );
  await shot("studio");
}

async function startStep() {
  const meter = h("div", { class: "meter unknown", role: "progressbar", "aria-label": "Progress" }, h("i"));
  const line = h("p", {}, "Starting…");
  const note = h("p", { class: "note" }, "");
  show(slate("working"), h("h1", {}, "Getting Crewcut ready"), meter, line, note);
  const off = D.onProgress((p) => {
    line.textContent = p.text || "";
    if (p.phase === "pull" && p.total) {
      meter.classList.remove("unknown");
      meter.firstChild.style.width = `${Math.round((100 * p.current) / p.total)}%`;
      meter.setAttribute("aria-valuenow", String(Math.round((100 * p.current) / p.total)));
      note.textContent = "Downloading Crewcut (once per version).";
    } else if (p.phase === "engine") {
      meter.classList.add("unknown");
      const m = Math.floor((p.seconds || 0) / 60);
      const s = (p.seconds || 0) % 60;
      note.textContent = p.log ? p.log : `${m}:${String(s).padStart(2, "0")} so far. This happens once.`;
    } else {
      meter.classList.add("unknown");
      note.textContent = "";
    }
  });
  const r = await D.startStack();
  off();
  if (!r.ok) {
    show(
      slate("waiting"),
      h("h1", {}, "Crewcut did not start."),
      h("p", {}, r.text || "Something went wrong."),
      h("div", { class: "row" }, h("button", { class: "primary", onclick: () => void dockerStep(false) }, "Try again")),
    );
    return;
  }
  const s = await D.settings();
  if (!s.claudeConnected) return connectStep(false);
  await D.openCrewcut();
}

// ---------- Connect Claude (and Codex, beta) ----------

function connectBlock(onDone) {
  const box = h("div", { class: "row", style: null });
  const status = h("p", { class: "note" }, "");
  const start = async () => {
    box.replaceChildren(spinner());
    status.textContent = "Opening Claude's sign-in in your browser…";
    const r = await D.claudeBegin();
    if (!r.url) {
      status.textContent = r.text || "Couldn't start the sign-in.";
      status.className = "note error";
      box.replaceChildren(h("button", { class: "primary", onclick: start }, "Try again"));
      return;
    }
    status.className = "note";
    status.textContent = "Sign in on Claude's page. It shows a code: paste it here.";
    const field = h("input", { class: "field", type: "text", "aria-label": "Code from Claude's page",
      placeholder: "Code from Claude's page", autocomplete: "off", spellcheck: "false" });
    const send = async () => {
      if (!field.value.trim()) return;
      box.replaceChildren(spinner());
      status.textContent = "Connecting…";
      const res = await D.claudeCode(field.value.trim());
      if (res.connected) {
        const who = res.account && res.account.email ? ` as ${res.account.email}` : "";
        status.className = "note ok";
        status.textContent = `Claude is connected${who}.`;
        box.replaceChildren();
        onDone({ connected: true });
        return;
      }
      status.className = "note error";
      status.textContent = res.text || "Claude did not accept the code.";
      box.replaceChildren(h("button", { class: "primary", onclick: start }, "Start again"));
    };
    field.addEventListener("keydown", (e) => {
      if (e.key === "Enter") void send();
    });
    box.replaceChildren(field, h("button", { class: "primary", onclick: send }, "Connect"),
      h("button", { class: "link", onclick: () => void D.openExternal(r.url) }, "Open Claude's sign-in again"));
    field.focus();
  };
  box.replaceChildren(h("button", { class: "primary", onclick: start }, "Connect Claude"));
  return { box, status, start };
}

function codexBlock(onDone, label = "Connect Codex (beta) instead") {
  const box = h("div", { class: "row" });
  const status = h("p", { class: "note" }, "");
  const start = async () => {
    box.replaceChildren(spinner());
    status.textContent = "Starting the Codex sign-in…";
    const r = await D.codexBegin();
    if (!r.url) {
      status.className = "note error";
      status.textContent = r.text || "Couldn't start the Codex sign-in.";
      box.replaceChildren(h("button", { class: "secondary", onclick: start }, "Try again"));
      return;
    }
    status.className = "note";
    status.replaceChildren("Your browser shows OpenAI's page. Enter this code there: ",
      h("span", { class: "code" }, r.code || "(shown on the page)"));
    box.replaceChildren(spinner());
    const done = await D.codexWait();
    status.className = done.connected ? "note ok" : "note error";
    status.textContent = done.connected ? "Codex is connected." : `Codex is not connected. ${done.text || ""}`;
    box.replaceChildren();
    if (done.connected) onDone({ connected: true });
  };
  box.replaceChildren(h("button", { class: "link", onclick: start }, label));
  return { box, status, start };
}

function connectStep() {
  const finish = () => setTimeout(() => void D.openCrewcut(), 900);
  const claude = connectBlock(finish);
  const codex = codexBlock(finish);
  show(
    slate("wave"),
    h("h1", {}, "Connect Claude."),
    h("p", {}, "Crewcut runs on your own Claude plan. Claude's page opens in your browser; sign in and paste the code it shows. The login stays in your system's keychain."),
    claude.box,
    claude.status,
    codex.box,
    codex.status,
    h("button", { class: "link", onclick: () => void D.openCrewcut() }, "Later"),
  );
}

// ---------- settings ----------

async function settingsView(preview) {
  const s = await D.settings();
  const v = await D.version();
  view.className = "view settings";
  const close = (connected) => (preview ? undefined : D.closeSettings({ connected }));

  const claudeLine = h("p", {}, s.claudeConnected
    ? `Connected${s.claude && s.claude.email ? ` as ${s.claude.email}` : ""}. ${s.claude && s.claude.where === "keychain"
      ? "The login is in your system's keychain." : "The login is in Crewcut's engine volume."}`
    : "Not connected. Nothing can run until Claude or Codex is connected.");
  const claude = connectBlock(() => close(true));
  const claudeCard = h("section", { class: "card", "aria-label": "Claude" },
    h("h2", {}, "Claude"), claudeLine,
    s.claudeConnected
      ? h("div", { class: "row" }, h("button", { class: "secondary", onclick: async (e) => {
        e.target.disabled = true;
        claudeLine.textContent = "Disconnecting and restarting the crew…";
        await D.disconnect("claude");
        void settingsView(preview);
      } }, "Disconnect"), h("button", { class: "link", onclick: () => {
        claudeCard.append(claude.box, claude.status);
        void claude.start();
      } }, "Connect again"))
      : [claude.box, claude.status],
    s.keychain ? null : h("p", { class: "note" }, "No system keychain was found (on Linux: GNOME Keyring or KWallet), so the login is kept in Crewcut's engine volume instead."));

  const codex = codexBlock(() => void settingsView(preview), "Connect Codex");
  const codexCard = h("section", { class: "card", "aria-label": "Codex" },
    h("h2", {}, "Codex (beta)"),
    h("p", {}, s.codex ? "Connected with your ChatGPT plan. Say \"use Codex\" in the chat to work with it." : "Not connected."),
    s.codex
      ? h("div", { class: "row" }, h("button", { class: "secondary", onclick: async () => {
        await D.disconnect("codex");
        void settingsView(preview);
      } }, "Disconnect"))
      : [codex.box, codex.status]);

  const keep = h("input", { type: "checkbox", checked: s.keepRunning, onchange: (e) => void D.setKeepRunning(e.target.checked) });
  const keepCard = h("section", { class: "card", "aria-label": "In the background" },
    h("label", { class: "switch" }, keep, h("span", {},
      h("h2", {}, "Keep the crew working in the background"),
      h("p", { class: "note" }, platform === "darwin"
        ? "Closing the window leaves Crewcut in the menu bar and the crew keeps working. Quit from there stops it."
        : "Closing the window leaves Crewcut in the tray and the crew keeps working. Quit from there stops it."))));

  const folder = h("p", { class: "mono" }, s.studioDir);
  const studioCard = h("section", { class: "card", "aria-label": "Studio folder" },
    h("h2", {}, "Studio folder"), folder,
    h("div", { class: "row" }, h("button", { class: "secondary", onclick: async () => {
      const chosen = await D.chooseStudio();
      if (chosen) {
        await D.setStudio(chosen);
        folder.textContent = `${chosen} (from the next start)`;
      }
    } }, "Change…")));

  const about = h("section", { class: "card", "aria-label": "Version" },
    h("h2", {}, `Crewcut ${v.version}`),
    h("p", { class: "note" }, `Runs the image ghcr.io/marcopatzelt/crewcut:${v.tag}.`),
    h("div", { class: "row" }, h("button", { class: "link", onclick: () => void D.checkUpdates() }, "See the releases")));

  view.replaceChildren(...[
    h("h1", {}, "Settings"),
    claudeCard, codexCard, keepCard, studioCard, about,
    preview ? null : h("div", { class: "row" }, h("button", { class: "primary", onclick: () => close(s.claudeConnected) }, "Done")),
  ].filter(Boolean));
  if (HASH === "settings-claude" && !s.claudeConnected && !preview) void claude.start();
  if (HASH === "settings-codex" && !s.codex && !preview) void codex.start();
  if (preview) {
    await shot("settings");
    await shot("end");
  }
}

// ---------- start ----------

async function main() {
  if (HASH.startsWith("settings")) return settingsView(false);
  const s = await D.settings();
  if (SHOTS) {
    welcome();
    await shot("welcome");
    return dockerStep(true).then(async () => {
      await settingsView(true);
    });
  }
  if (!s.onboarded) return welcome();
  return dockerStep(false);
}

void main();
