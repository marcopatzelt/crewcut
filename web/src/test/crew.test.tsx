import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import type { Identity } from "../api/types";
import { TeamView } from "../views/ReadOnlyViews";
import { mockApi, NEVER, Reply, resetApp, state } from "./helpers";

beforeEach(resetApp);

const members: Identity[] = [
  { ...state().team[1]!, soul: "I find the evidence.\nI credit every source.", skills: ["research", "proof"], sources: [
    { name: "Example handbook", url: "https://example.org/handbook", what: "Clear titles and strong evidence" },
    { name: "Printed guide", what: "Research methods" },
    "https://example.org/reference", "Another credited creator",
  ] },
  state().team[0]!,
  { ...state().team[2]!, may_spend: true, may_publish: true },
];

describe("compact crew", () => {
  it("puts Showrunner first and closes every detail by default", async () => {
    mockApi({ "GET /api/team": members });
    const { container } = render(<TeamView />);
    const cards = await screen.findAllByRole("article");
    expect(cards).toHaveLength(3);
    expect(within(cards[0]!).getByRole("heading", { name: "Showrunner" })).toBeTruthy();
    expect(within(cards[0]!).getByText("Your channel lead")).toBeTruthy();
    expect(within(cards[1]!).getByText("Finds topics and proof.")).toBeTruthy();
    expect([...container.querySelectorAll("details")].every((detail) => !detail.open)).toBe(true);
    expect(container.querySelector(".page-scroll .engine-picker")).toBeNull();
    expect(screen.getByText("Crewcut is not affiliated with or endorsed by these creators.")).toBeTruthy();
  });

  it("keeps full roles, soul, skills, rights and all source credits in expandable details", async () => {
    mockApi({ "GET /api/team": members });
    render(<TeamView />);
    const scout = await screen.findByRole("article", { name: "Scout" });
    const summary = within(scout).getByText("Role, skills and sources");
    fireEvent.click(summary);
    const detail = scout.querySelector("details")!;
    expect(detail.open).toBe(true);
    expect(within(detail).getByText("research, proof")).toBeTruthy();
    expect(within(detail).getByText(/I find the evidence/)).toBeTruthy();
    expect(within(detail).getByRole("link", { name: "Example handbook" }).getAttribute("href")).toBe("https://example.org/handbook");
    expect(within(detail).getByText(/Clear titles and strong evidence/)).toBeTruthy();
    expect(within(detail).getByText("Printed guide")).toBeTruthy();
    expect(within(detail).getByRole("link", { name: "https://example.org/reference" })).toBeTruthy();
    expect(within(detail).getByText("Another credited creator")).toBeTruthy();
    expect(within(detail).getByText("Does not spend money. Does not publish.")).toBeTruthy();
    const editor = screen.getByRole("article", { name: "Editor" });
    fireEvent.click(within(editor).getByText("Role, skills and sources"));
    expect(within(editor).getByText("May rent GPUs and pay for APIs, within your cap. May publish, after your yes on the exact file.")).toBeTruthy();
    fireEvent.click(summary);
    expect(detail.open).toBe(false);
  });

  it("keeps long custom roles and names available without inventing a lead", async () => {
    const name = "Custom crew member ".repeat(10);
    const role = "A long role with important responsibilities. ".repeat(15);
    mockApi({ "GET /api/team": [{ ...members[0], name, role, id: "custom" }] });
    render(<TeamView />);
    const card = await screen.findByRole("article", { name: name.trim() });
    expect(card.querySelector("h2")?.title).toBe(name);
    expect(card.querySelector(".crew-role")?.getAttribute("title")).toBe(role);
    expect(card.querySelector(".crew-detail-body p")?.textContent).toBe(role);
    expect(screen.queryByText("Your channel lead")).toBeNull();
  });

  it("shows loading, error and empty states", async () => {
    mockApi({ "GET /api/team": NEVER });
    const loading = render(<TeamView />);
    expect(screen.getByTestId("loading")).toBeTruthy();
    loading.unmount();
    mockApi({ "GET /api/team": new Reply(500, { detail: "Try later" }) });
    const failed = render(<TeamView />);
    expect(await screen.findByText("Couldn't load the crew. Try later")).toBeTruthy();
    failed.unmount();
    mockApi({ "GET /api/team": [] });
    render(<TeamView />);
    expect(await screen.findByText("No crew members found. Check the team folder of the app.")).toBeTruthy();
  });
});
