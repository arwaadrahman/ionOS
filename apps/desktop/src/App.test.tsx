import "@testing-library/jest-dom/vitest";
import { invoke } from "@tauri-apps/api/core";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { App } from "./App";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn().mockResolvedValue([]),
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(invoke).mockResolvedValue([]);
});

afterEach(cleanup);

test("shows the Task workspace through the narrow command path", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
  render(<App />);

  expect(
    await screen.findByRole("heading", { name: "Tasks" }),
  ).toBeInTheDocument();
});

test("reports an unavailable development service without exposing diagnostics", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  render(<App />);

  expect(
    await screen.findByText("Local service: unavailable"),
  ).toBeInTheDocument();
  expect(screen.queryByText("offline")).not.toBeInTheDocument();
});

test("hydrates persisted Tasks before mounting the packaged workspace", async () => {
  let resolveTasks: (tasks: unknown[]) => void = () => undefined;
  const taskResponse = new Promise<unknown[]>((resolve) => {
    resolveTasks = resolve;
  });

  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "service_health") return { state: "ready" };
    if (command === "list_tasks") return taskResponse;
    throw new Error(`Unexpected command: ${command}`);
  });

  render(<App development={false} />);

  await waitFor(() => expect(invoke).toHaveBeenCalledWith("list_tasks"));
  expect(
    screen.queryByRole("heading", { name: "Tasks" }),
  ).not.toBeInTheDocument();

  await act(async () => {
    resolveTasks([
      {
        id: "task-persisted-synthetic",
        title: "Persisted synthetic Task",
        details: null,
        state: "open",
        importance: "normal",
        estimated_minutes: null,
        progress_percent: null,
        deadline: { kind: "none" },
        revision: 1,
        trashed_at: null,
      },
    ]);
    await taskResponse;
  });

  expect(
    await screen.findByText("Persisted synthetic Task"),
  ).toBeInTheDocument();
});
