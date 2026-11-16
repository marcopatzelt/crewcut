// The command palette (DESIGN.md rule 15): Cmd+K, then type to filter episodes, views and actions. Its search field
// only picks from the list; it takes no values (rule 3). Floats with material (rule 18) in the upper third.
import { Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ONBOARDING } from "../api/types";
import { currentTheme, narrow, switchTheme } from "../lib/platform";
import { navigate, newEpisode, setPalette, setPrompter, toggleCrew, toggleSide } from "../store/actions";
import { EMPTY, useUi } from "../store/store";
import { Keys } from "./bits";

export interface Command {
  id: string;
  group: "Episodes" | "Views" | "Actions";
  label: string;
  meta?: string;
  keys?: string[];
  run: () => void;
}

/** True when every word of the query is somewhere in the label or meta. */
export function matches(c: Command, query: string): boolean {
  const hay = `${c.label} ${c.meta ?? ""}`.toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((w) => hay.includes(w));
}

function useCommands(): Command[] {
  const episodes = useUi((s) => s.state?.episodes ?? EMPTY);
  const view = useUi((s) => s.view);
  const sideHidden = useUi((s) => s.sideHidden);
  const crewHidden = useUi((s) => s.crewHidden);
  return useMemo(() => {
    const list: Command[] = episodes.map((e, i) => {
      const step = e.steps.find((s) => s.id === e.step);
      return {
        id: `e-${e.id}`,
        group: "Episodes",
        label: e.title,
        meta: step ? `${step.n} ${step.label}` : undefined,
        keys: i < 9 ? ["mod", String(i + 1)] : undefined,
        run: () => navigate({ kind: "episode", id: e.id }),
      };
    });
    list.push(
      { id: "v-episodes", group: "Views", label: "Show all episodes", run: () => navigate({ kind: "episodes" }) },
      { id: "v-profile", group: "Views", label: "Show profile", run: () => navigate({ kind: "profile" }) },
      { id: "v-crew", group: "Views", label: "Show the crew", run: () => navigate({ kind: "crew" }) },
      { id: "a-new", group: "Actions", label: "New episode", keys: ["mod", "N"], run: newEpisode },
    );
    if (view.kind === "episode" && view.id !== ONBOARDING) {
      list.push({ id: "a-prompter", group: "Actions", label: "Open teleprompter", run: () => setPrompter(true) });
    }
    list.push({
      id: "a-theme",
      group: "Actions",
      label: currentTheme() === "dark" ? "Switch to the light theme" : "Switch to the dark theme",
      run: () => void switchTheme(),
    });
    if (!narrow(760)) {
      list.push({
        id: "a-side",
        group: "Actions",
        label: sideHidden ? "Show the episodes panel" : "Hide the episodes panel",
        keys: ["mod", "B"],
        run: toggleSide,
      });
    }
    if (!narrow(1100)) {
      list.push({
        id: "a-crew",
        group: "Actions",
        label: crewHidden ? "Show the crew column" : "Hide the crew column",
        keys: ["mod", "alt", "B"],
        run: toggleCrew,
      });
    }
    return list;
  }, [episodes, view, sideHidden, crewHidden]);
}

export function Palette() {
  const open = useUi((s) => s.paletteOpen);
  const [shown, setShown] = useState(open);
  const [closing, setClosing] = useState(false);

  // Opening springs in; closing only fades (120 ms), then the palette leaves the page.
  useEffect(() => {
    if (open) {
      setShown(true);
      setClosing(false);
      return;
    }
    if (!shown) return;
    setClosing(true);
    const t = setTimeout(() => {
      setShown(false);
      setClosing(false);
    }, 120);
    return () => clearTimeout(t);
  }, [open]);

  if (!shown) return null;
  return <PaletteBox closing={closing} />;
}

function PaletteBox({ closing }: { closing: boolean }) {
  const commands = useCommands();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const before = useRef<Element | null>(typeof document !== "undefined" ? document.activeElement : null);
  const shown = commands.filter((c) => matches(c, query));
  const current = shown[Math.min(active, shown.length - 1)];

  useEffect(() => {
    input.current?.focus();
    const back = before.current;
    return () => {
      if (back instanceof HTMLElement && back.isConnected) back.focus();
    };
  }, []);

  useEffect(() => setActive(0), [query]);

  useEffect(() => {
    if (!current) return;
    document.getElementById(`cmd-${current.id}`)?.scrollIntoView?.({ block: "nearest" });
  }, [current?.id]);

  function run(c: Command | undefined) {
    if (!c) return;
    setPalette(false);
    c.run();
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      setActive((i) => (shown.length ? (Math.min(i, shown.length - 1) + 1) % shown.length : 0));
      e.preventDefault();
    } else if (e.key === "ArrowUp") {
      setActive((i) => (shown.length ? (Math.min(i, shown.length - 1) - 1 + shown.length) % shown.length : 0));
      e.preventDefault();
    } else if (e.key === "Enter" && !e.nativeEvent.isComposing) {
      run(current);
      e.preventDefault();
    } else if (e.key === "Escape") {
      setPalette(false);
      e.preventDefault();
      e.stopPropagation();
    } else if (e.key === "Tab") {
      e.preventDefault(); // the focus stays in the palette; arrows move through the list
    }
  }

  let lastGroup = "";
  return (
    <div className={closing ? "palette-layer closing" : "palette-layer"} onMouseDown={() => setPalette(false)}>
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="palette-field">
          <Search size={16} aria-hidden="true" />
          <input
            ref={input}
            type="text"
            role="combobox"
            aria-label="Search episodes and actions"
            aria-expanded="true"
            aria-controls="palette-list"
            aria-autocomplete="list"
            aria-activedescendant={current ? `cmd-${current.id}` : undefined}
            placeholder="Go to an episode or do something…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <ul className="palette-list" id="palette-list" role="listbox" aria-label="Results">
          {shown.map((c) => {
            const head = c.group !== lastGroup ? c.group : null;
            lastGroup = c.group;
            return (
              <li key={c.id} role="presentation">
                {head ? (
                  <div className="palette-group" role="presentation">
                    {head}
                  </div>
                ) : null}
                <div
                  id={`cmd-${c.id}`}
                  role="option"
                  aria-selected={c === current}
                  className={c === current ? "palette-item active" : "palette-item"}
                  onMouseMove={() => setActive(shown.indexOf(c))}
                  onClick={() => run(c)}
                >
                  <span className="one-line">{c.label}</span>
                  {c.meta ? <span className="palette-meta one-line">{c.meta}</span> : null}
                  {c.keys ? <Keys keys={c.keys} /> : null}
                </div>
              </li>
            );
          })}
          {shown.length === 0 ? <li className="palette-empty">Nothing matches. Try fewer words.</li> : null}
        </ul>
      </div>
    </div>
  );
}
