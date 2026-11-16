// The main screen: three places (DESIGN.md rule 2). Episodes left, Chat center, Crew right.
import { AlertCircle, Menu, WifiOff } from "lucide-react";
import { useEffect } from "react";
import { Loading, ErrorLine } from "./components/bits";
import { Composer } from "./components/Composer";
import { CrewBar, CrewColumn } from "./components/Crew";
import { Episodes, Logo } from "./components/Episodes";
import { boot, onHashChange, setMenu } from "./store/actions";
import { useUi } from "./store/store";
import { EpisodeView, NewEpisodeView } from "./views/EpisodeView";
import { JobLogView, ProfileView, TeamView } from "./views/ReadOnlyViews";

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

function Notices() {
  const engineOk = useUi((s) => s.state?.app.engine_ok ?? true);
  const engine = useUi((s) => s.state?.app.engine ?? "claude");
  const live = useUi((s) => s.live);
  return (
    <>
      {!engineOk ? (
        <div className="notice danger" role="alert">
          <AlertCircle size={16} aria-hidden="true" />
          <span>
            The engine is not logged in, so the crew cannot work. Run{" "}
            {engine === "claude" ? "claude setup-token" : `${engine} login`} on your computer, put the value in .env,
            then restart Crewcut.
          </span>
        </div>
      ) : null}
      {live === "retrying" ? (
        <div className="notice" role="status">
          <WifiOff size={16} aria-hidden="true" />
          <span>Lost the live connection to Crewcut. Trying again; the screen may be a little behind.</span>
        </div>
      ) : null}
    </>
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

export function App({ demo }: { demo?: boolean }) {
  const menuOpen = useUi((s) => s.menuOpen);

  useEffect(() => {
    void boot({ demo });
    window.addEventListener("hashchange", onHashChange);
    window.addEventListener("popstate", onHashChange);
    return () => {
      window.removeEventListener("hashchange", onHashChange);
      window.removeEventListener("popstate", onHashChange);
    };
  }, [demo]);

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
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !e.isComposing) {
        if (acceptCardInView()) e.preventDefault();
      } else if (e.key === "Escape" && menuOpen) {
        setMenu(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  return (
    <div className="app">
      <Episodes />
      {menuOpen ? <div className="scrim" aria-hidden="true" onClick={() => setMenu(false)} /> : null}
      <main className="main">
        <div className="topbar">
          <button
            type="button"
            className="icon-button"
            aria-label="Episodes"
            aria-expanded={menuOpen}
            aria-controls="episodes"
            onClick={() => setMenu(!menuOpen)}
          >
            <Menu size={16} aria-hidden="true" />
          </button>
          <div className="wordmark">
            <Logo />
            Crewcut
          </div>
        </div>
        <Notices />
        <Center />
        <CrewBar />
        <Composer />
      </main>
      <CrewColumn />
    </div>
  );
}
