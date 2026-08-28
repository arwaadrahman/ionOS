import "@testing-library/jest-dom/vitest";
import { invoke } from "@tauri-apps/api/core";
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { OrganizerShell } from "./OrganizerShell";
import { StartupData } from "./startup";
import { currentTodayContext, TodayOutput } from "./today";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

function emptyToday(): TodayOutput {
  const context = currentTodayContext();
  return {
    ...context,
    generated_at: new Date().toISOString(),
    plan: { priorities: [], planned: [], backups: [] },
    deadlines: { overdue: [], due_today: [], approaching: [] },
    needs_attention: [],
    unfinished_from_yesterday: [],
    completed_today: [],
  };
}

function data(): StartupData {
  const today = emptyToday();
  return {
    tasks: [],
    areas: [],
    goals: [],
    projects: [],
    today,
    todayContext: {
      planning_date: today.planning_date,
      timezone: today.timezone,
    },
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2030-01-01T20:00:00-08:00"));
  vi.clearAllMocks();
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "get_today") return emptyToday();
    throw new Error(`Unexpected command: ${command}`);
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

test("reloads at the next local midnight and cancels its timeout on cleanup", async () => {
  const clear = vi.spyOn(window, "clearTimeout");
  const view = render(<OrganizerShell initialData={data()} />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(4 * 60 * 60 * 1000 + 2_000);
    await Promise.resolve();
  });
  expect(invoke).toHaveBeenCalledWith("get_today", expect.anything());
  view.unmount();
  expect(clear).toHaveBeenCalled();
});

test("focus and visible rechecks reload after a timezone change", async () => {
  let timezone = "America/Los_Angeles";
  const contextProvider = () => ({
    planning_date: timezone === "UTC" ? "2030-01-02" : "2030-01-01",
    timezone,
  });
  const initial = data();
  initial.todayContext = contextProvider();
  initial.today = { ...initial.today, ...initial.todayContext };
  render(
    <OrganizerShell
      initialData={initial}
      todayContextProvider={contextProvider}
    />,
  );
  await act(async () => {
    await Promise.resolve();
  });
  timezone = "UTC";
  await act(async () => {
    window.dispatchEvent(new FocusEvent("focus"));
    await Promise.resolve();
  });
  expect(invoke).toHaveBeenCalledWith("get_today", expect.anything());
  vi.mocked(invoke).mockClear();
  timezone = "America/New_York";
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: "visible",
  });
  await act(async () => {
    document.dispatchEvent(new Event("visibilitychange"));
    await Promise.resolve();
  });
  expect(invoke).toHaveBeenCalledWith("get_today", expect.anything());
});
