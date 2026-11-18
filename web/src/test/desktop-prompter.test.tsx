import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DesktopScreens } from "../components/PrompterPopover";

afterEach(() => { delete (window as unknown as Record<string, unknown>).crewcutDesktop; });

it("requires a screen choice, saves it, then opens only the current episode", async () => {
  const select = vi.fn().mockResolvedValue(undefined);
  const open = vi.fn().mockResolvedValue({ ok: true, message: "Opened on test screen." });
  Object.assign(window, { crewcutDesktop: {
    prompterDisplays: async () => ({ displays: [{ id: 42, label: "Test screen", width: 1280, height: 720 }], selected: null }),
    prompterSelectDisplay: select, prompterOpen: open,
  } });
  render(<DesktopScreens episode="015-example" />);
  const launch = screen.getByRole("button", { name: "Open approved script full screen" }) as HTMLButtonElement;
  expect(launch.disabled).toBe(true);
  fireEvent.click(await screen.findByRole("button", { name: /Test screen/ }));
  await waitFor(() => expect(launch.disabled).toBe(false));
  expect(select).toHaveBeenCalledWith(42);
  fireEvent.click(launch);
  expect(await screen.findByText("Opened on test screen.")).toBeTruthy();
  expect(open).toHaveBeenCalledWith("015-example");
});

it("shows desktop failures without claiming success", async () => {
  Object.assign(window, { crewcutDesktop: {
    prompterDisplays: async () => ({ displays: [{ id: 42, label: "Test screen", width: 1280, height: 720 }], selected: 42 }),
    prompterSelectDisplay: vi.fn(), prompterOpen: async () => ({ ok: false, message: "Screen disconnected." }),
  } });
  render(<DesktopScreens episode="015-example" />);
  const launch = screen.getByRole("button", { name: "Open approved script full screen" }) as HTMLButtonElement;
  await waitFor(() => expect(launch.disabled).toBe(false));
  fireEvent.click(launch);
  expect(await screen.findByText("Screen disconnected.")).toBeTruthy();
});

it("does not offer desktop controls in a browser", () => {
  const { container } = render(<DesktopScreens episode="015-example" />);
  expect(container.textContent).toBe("");
});
