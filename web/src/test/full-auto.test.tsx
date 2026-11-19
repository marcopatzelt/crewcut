import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";
import { FullAuto } from "../components/FullAuto";
import { mockApi, resetApp, type Call } from "./helpers";

beforeEach(resetApp);

it("requires an explicit endpoint choice and lets the user turn automation off", async () => {
  const calls = mockApi({
    "GET /api/episodes/test/full-auto": { mode: "off" },
    "POST /api/episodes/test/full-auto": (call: Call) => call.body,
  });
  render(<FullAuto episode="test" />);
  fireEvent.click(await screen.findByText("Full auto · Off"));
  expect(calls.filter(c => c.method === "POST")).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Finish and upload privately" }));
  await screen.findByText("Full auto · On");
  expect(calls.find(c => c.method === "POST")?.body).toEqual({ mode: "private" });
  fireEvent.click(screen.getByRole("button", { name: "Turn off" }));
  await waitFor(() => expect(screen.getByText("Full auto · Off")).toBeTruthy());
});
