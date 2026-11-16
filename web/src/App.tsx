// The main screen: three places (DESIGN.md rule 2) as floating surfaces on the window (rules 7 and 18).
// Episodes left, Chat center, Crew right. The composer floats over the bottom of the chat.
import { WifiOff } from "lucide-react";
import { useEffect, useRef } from "react";
import { ONBOARDING } from "./api/types";
import { Loading, ErrorLine } from "./components/bits";
import { Composer } from "./components/Composer";
import { CrewBar, CrewColumn } from "./components/Crew";
import { Episodes } from "./components/Episodes";
import { Palette } from "./components/Palette";
import {
  boot,
  focusComposer,
  newEpisode,
  onHashChange,
  openEpisodeAt,
  setMenu,
  setPalette,
  setPrompter,
  toggleCrew,
  toggleSide,
} from "./store/actions";
import { getUi, useUi } from "./store/store";
import { EpisodeView, NewEpisodeView } from "./views/EpisodeView";
import { JobLogView, ProfileView, TeamView } from "./views/ReadOnlyViews";
import { EpisodesGrid } from "./views/EpisodesGrid";

/** Ctrl/Cmd+Enter accepts the open card in view (rule 15): the lowest open card visible in the chat. */
function acceptCardInView(): boolean {
  const scroller = document.querySelector<HTMLElement>("[data-testid='chat-scroll']");
  if (!scroller) return false;
  const cards = Array.from(scroller.querySelectorAll<HTMLElement>("[data-open-card]"));
  if (!cards.length) return false;
  const box = scroller.getBoundingClientRect();
  const visible = cards.filter((c) => {
    const r = c.getBoundingClientRect();
    return r.bottom > box.top && r.top < box.bottom;
  });
  const card = visible[visible.length - 1] ?? cards[cards.length - 1];
  const button = card?.querySelector<HTMLButtonElement>("[data-accept]");
  if (!button || button.disabled) return false;
  button.click();
  return true;
}

function inTextField(el: EventTarget | null): boolean {
  return (
    el instanceof HTMLTextAreaElement ||
    el instanceof HTMLInputElement ||
    (el instanceof HTMLElement && el.isContentEditable)
  );
}

/** The shortcuts of rule 15. Cmd on Apple devices, Ctrl elsewhere; both work everywhere. */
function onShortcut(e: KeyboardEvent): void {
  if (e.isComposing) return;
  const mod = e.metaKey || e.ctrlKey;
  const ui = getUi();
  if (e.key === "Enter" && mod) {
    if (acceptCardInView()) e.preventDefault();
    return;
  }
  if (e.key === "Escape") {
    if (ui.paletteOpen) setPalette(false);
    else if (ui.prompterOpen) setPrompter(false);
    else if (ui.menuOpen) setMenu(false);
    return;
  }
  if (mod && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "k") {
    setPalette(!ui.paletteOpen);
    e.preventDefault();
    return;
  }
  if (ui.paletteOpen) return; // the palette owns the keys while it is open
  if (mod && e.code === "KeyB") {
    if (e.altKey) toggleCrew();
    else toggleSide();
    e.preventDefault();
    return;
  }
  if (mod && !e.altKey && e.key.toLowerCase() === "n") {
    newEpisode();
    e.preventDefault();
    return;
  }
  if (mod && !e.altKey && /^[1-9]$/.test(e.key)) {
    if (openEpisodeAt(Number(e.key) - 1)) e.preventDefault();
    return;
  }
  if (e.key === "/" && !mod && !e.altKey && !inTextField(e.target)) {
    focusComposer();
    e.preventDefault();
  }
}

function Notices() {
  const live = useUi((s) => s.live);
  if (live !== "retrying") return null;
  return (
    <div className="notice" role="status">
      <span className="dot warn" aria-hidden="true" />
      <WifiOff size={14} aria-hidden="true" />
      <span>Lost the connection to the container. Retrying…</span>
    </div>
  );
}

function Center() {
  const view = useUi((s) => s.view);
  const status = useUi((s) => s.boot);
  const error = useUi((s) => s.bootError);
  if (status === "loading") return <Loading label="Loading Crewcut" />;
  if (status === "error") {
    return (
      <div className="center-state danger">
        <ErrorLine text={`Couldn't load Crewcut. ${error ?? ""}`} onRetry={() => void boot()} />
      </div>
    );
  }
  switch (view.kind) {
    case "episode":
      return <EpisodeView key={view.id} id={view.id} />;
    case "episodes":
      return <EpisodesGrid />;
    case "profile":
      return <ProfileView />;
    case "crew":
      return <TeamView />;
    case "job":
      return <JobLogView key={view.id} id={view.id} />;
    default:
      return <NewEpisodeView />;
  }
}

export function App({ demo, play }: { demo?: boolean; play?: boolean }) {
  const menuOpen = useUi((s) => s.menuOpen);
  const sideHidden = useUi((s) => s.sideHidden);
  const crewHidden = useUi((s) => s.crewHidden);
  const onboardingView = useUi((s) => s.view.kind === "episode" && s.view.id === ONBOARDING);
  const firstStart = useUi(
    (s) =>
      s.view.kind === "episode" &&
      s.view.id === ONBOARDING &&
      s.threads[ONBOARDING]?.status === "ready" &&
      (s.threads[ONBOARDING]?.messages.length ?? 0) === 0 &&
      !Object.values(s.cards).some((c) => c.episode === ONBOARDING) &&
      !s.uploads.some((u) => u.episode === ONBOARDING),
  );
  const main = useRef<HTMLElement>(null);
  const dock = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void boot({ demo, play });
    window.addEventListener("hashchange", onHashChange);
    window.addEventListener("popstate", onHashChange);
    return () => {
      window.removeEventListener("hashchange", onHashChange);
      window.removeEventListener("popstate", onHashChange);
    };
  }, [demo, play]);

  // A file dropped outside the chat must not replace the app with the file.
  useEffect(() => {
    const stop = (e: DragEvent) => {
      if (e.dataTransfer && Array.from(e.dataTransfer.types).includes("Files")) e.preventDefault();
    };
    window.addEventListener("dragover", stop);
    window.addEventListener("drop", stop);
    return () => {
      window.removeEventListener("dragover", stop);
      window.removeEventListener("drop", stop);
    };
  }, []);

  useEffect(() => {
    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, []);

  // The chat scrolls under the composer: it keeps room at the bottom as tall as the floating dock.
  useEffect(() => {
    const d = dock.current;
    const m = main.current;
    if (!d || !m || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => m.style.setProperty("--dock-h", `${Math.ceil(d.offsetHeight)}px`));
    ro.observe(d);
    return () => ro.disconnect();
  }, []);

  const cls = ["app", sideHidden ? "side-hidden" : null, crewHidden ? "crew-hidden" : null].filter(Boolean).join(" ");
  const dockCls = ["dock", onboardingView ? "narrow" : null, firstStart ? "centered" : null].filter(Boolean).join(" ");

  return (
    <div className={cls}>
      <Episodes />
      {menuOpen ? <div className="scrim" aria-hidden="true" onClick={() => setMenu(false)} /> : null}
      <main className="main" ref={main}>
        <Center />
        <Notices />
        <div className={dockCls} ref={dock}>
          <CrewBar />
          <Composer />
        </div>
      </main>
      <CrewColumn />
      <Palette />
    </div>
  );
}
