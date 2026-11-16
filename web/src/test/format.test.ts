import { describe, expect, it } from "vitest";
import { hashToView, viewToHash } from "../store/actions";
import { about, ago, bytes, clock, countWord, episodeNumber, usd, versionOf } from "../lib/format";
import { foldedText } from "../components/CardView";
import { card } from "./helpers";

describe("format", () => {
  it("writes times and money exactly", () => {
    expect(clock(40)).toBe("0:40");
    expect(clock(252)).toBe("4:12");
    expect(clock(3723)).toBe("1:02:03");
    expect(about(720)).toBe("About 12 min");
    expect(about(11_400)).toBe("About 3 h 10 min");
    expect(usd(0.6)).toBe("$0.60");
    expect(bytes(1_200_000_000)).toBe("1.2 GB");
    expect(countWord(3)).toBe("Three");
    expect(episodeNumber("003-local-llms")).toBe("003");
    expect(versionOf("brief/SCRIPT-v003.md")).toBe("version 3");
  });

  it("says how long ago", () => {
    const now = Date.parse("2026-11-16T12:00:00Z");
    expect(ago("2026-11-16T11:20:00Z", now)).toBe("40 min ago");
    expect(ago("2026-11-16T10:00:00Z", now)).toBe("2 h ago");
    expect(ago("2026-11-13T12:00:00Z", now)).toBe("3 days ago");
  });

  it("folds decided cards into one line", () => {
    expect(foldedText(card({ status: "accepted", choice: 0 }))).toBe("Title approved · First title");
    expect(foldedText(card({ kind: "script", options: null, status: "accepted", file: "brief/SCRIPT-v003.md" }))).toBe(
      "Script approved · version 3",
    );
  });

  it("keeps the view in the URL hash", () => {
    for (const v of [
      { kind: "episode", id: "003-local-llms" } as const,
      { kind: "episode", id: "_onboarding" } as const,
      { kind: "profile" } as const,
      { kind: "crew" } as const,
      { kind: "job", id: 12 } as const,
      { kind: "new" } as const,
    ]) {
      expect(hashToView(viewToHash(v))).toEqual(v);
    }
    expect(hashToView("#/nothing")).toBeNull();
  });
});
