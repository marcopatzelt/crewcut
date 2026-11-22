import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";
import { InterviewBar } from "../components/InterviewBar";
import { mockApi, resetApp } from "./helpers";

beforeEach(resetApp);

const waiting = { status: "waiting" as const, label: "Interview: waiting for your answers", answers: 0, questions: 6 };

it("says the episode waits for the answers and skips the interview on request", async () => {
  const calls = mockApi({ "POST /api/episodes/test/interview": { ...waiting, status: "skipped", label: "Interview: skipped" } });
  render(<InterviewBar episode="test" interview={waiting} />);
  expect(screen.getByRole("status").textContent).toContain("Interview: waiting for your answers");
  expect(screen.queryByRole("button", { name: "Done answering" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Skip interview" }));
  await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
  expect(calls.find((c) => c.method === "POST")?.body).toEqual({ action: "skip" });
});

it("offers Done answering once answers came in several messages", async () => {
  const calls = mockApi({ "POST /api/episodes/test/interview": { ...waiting, status: "done", answers: 2 } });
  render(<InterviewBar episode="test" interview={{ ...waiting, answers: 2 }} />);
  fireEvent.click(screen.getByRole("button", { name: "Done answering" }));
  await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ action: "done" }));
});

it("shows nothing once the interview is done", () => {
  const { container } = render(<InterviewBar episode="test" interview={{ ...waiting, status: "done" }} />);
  expect(container.textContent).toBe("");
});
