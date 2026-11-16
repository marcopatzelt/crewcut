// A small store: one state object, setUi() to change it, useUi() to read a slice in a component.
import { useSyncExternalStore } from "react";
import type { Card, EpisodeDetail, Message, State } from "../api/types";

export type View =
  | { kind: "episode"; id: string } // a real episode or the onboarding chat
  | { kind: "new" } // no episode selected: the composer starts one
  | { kind: "profile" }
  | { kind: "crew" }
  | { kind: "job"; id: number };

export interface Thread {
  status: "loading" | "ready" | "error";
  error: string | null;
  messages: Message[];
}

export interface UploadLine {
  key: string;
  episode: string;
  name: string;
  size: number;
  status: "uploading" | "done" | "failed";
  error?: string;
}

export interface UiState {
  boot: "loading" | "ready" | "error";
  bootError: string | null;
  /** null: live data. "asked": ?demo=1. "auto": no API answered, so the app shows demo data. */
  demo: null | "asked" | "auto";
  state: State | null;
  view: View;
  /** The episode chat the composer talks to when a read-only view is open. */
  lastEpisode: string | null;
  threads: Record<string, Thread>;
  cards: Record<number, Card>;
  details: Record<string, EpisodeDetail>;
  /** When each job's `seconds` arrived (ms), so running jobs can count up between events. */
  seen: Record<number, number>;
  live: "idle" | "open" | "retrying";
  uploads: UploadLine[];
  /** The Episodes list as a menu (below 760 px). */
  menuOpen: boolean;
  /** The command palette (Cmd+K). */
  paletteOpen: boolean;
  /** The teleprompter dialog of the open episode. */
  prompterOpen: boolean;
  /** Cmd+B folds the Episodes panel, Cmd+Alt+B the Crew panel. */
  sideHidden: boolean;
  crewHidden: boolean;
}

export function initialUi(): UiState {
  return {
    boot: "loading",
    bootError: null,
    demo: null,
    state: null,
    view: { kind: "new" },
    lastEpisode: null,
    threads: {},
    cards: {},
    details: {},
    seen: {},
    live: "idle",
    uploads: [],
    menuOpen: false,
    paletteOpen: false,
    prompterOpen: false,
    sideHidden: false,
    crewHidden: false,
  };
}

let ui: UiState = initialUi();
const listeners = new Set<() => void>();

export function getUi(): UiState {
  return ui;
}

export function setUi(patch: Partial<UiState> | ((s: UiState) => Partial<UiState>)): void {
  const next = typeof patch === "function" ? patch(ui) : patch;
  ui = { ...ui, ...next };
  for (const l of listeners) l();
}

export function resetUi(): void {
  ui = initialUi();
  for (const l of listeners) l();
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** Read a slice of the store. The selector must return stored values, not new objects. */
export function useUi<T>(select: (s: UiState) => T): T {
  return useSyncExternalStore(
    subscribe,
    () => select(ui),
    () => select(ui),
  );
}

/** A shared empty list, so selectors return the same value on every call. Never mutate it. */
export const EMPTY = Object.freeze([]) as unknown as never[];
