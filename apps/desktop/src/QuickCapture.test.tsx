import "@testing-library/jest-dom/vitest";
import { invoke } from "@tauri-apps/api/core";
import { emitTo } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { QuickCapture } from "./QuickCapture";

const hide = vi.fn();
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/event", () => ({ emitTo: vi.fn() }));
vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: vi.fn(() => ({ hide })),
}));

const confirmedTask = {
  id: "44444444-4444-4444-8444-444444444444",
  title: "Synthetic captured Task",
  state: "open",
  revision: 1,
};

beforeEach(() => {
  vi.clearAllMocks();
  hide.mockResolvedValue(undefined);
});
afterEach(cleanup);

test("captures one canonical Task then notifies and hides", async () => {
  vi.mocked(invoke).mockResolvedValue(confirmedTask);
  vi.mocked(emitTo).mockResolvedValue(undefined);
  render(<QuickCapture />);

  fireEvent.change(screen.getByRole("textbox", { name: "What needs doing?" }), {
    target: { value: "  Synthetic captured Task  " },
  });
  fireEvent.click(screen.getByRole("button", { name: "Capture" }));

  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("create_task", {
      input: expect.objectContaining({
        title: "Synthetic captured Task",
        goal_id: null,
        project_id: null,
      }),
    }),
  );
  expect(emitTo).toHaveBeenCalledWith(
    "main",
    "ion:task-created",
    confirmedTask,
  );
  expect(hide).toHaveBeenCalledOnce();
});

test("submits one canonical Task when capture is triggered twice before confirmation", async () => {
  let resolveCreate: (task: typeof confirmedTask) => void = () => undefined;
  const pendingCreate = new Promise<typeof confirmedTask>((resolve) => {
    resolveCreate = resolve;
  });
  vi.mocked(invoke).mockResolvedValue(pendingCreate);
  vi.mocked(emitTo).mockResolvedValue(undefined);
  render(<QuickCapture />);

  fireEvent.change(screen.getByRole("textbox", { name: "What needs doing?" }), {
    target: { value: "Synthetic captured Task" },
  });
  const form = screen
    .getByRole("textbox", { name: "What needs doing?" })
    .closest("form");
  expect(form).not.toBeNull();
  fireEvent.submit(form!);
  fireEvent.submit(form!);

  await waitFor(() => expect(invoke).toHaveBeenCalledTimes(1));
  await act(async () => {
    resolveCreate(confirmedTask);
    await pendingCreate;
  });
  await waitFor(() => expect(hide).toHaveBeenCalledOnce());
});

test("does not relabel confirmed creation when secondary notification fails", async () => {
  vi.mocked(invoke).mockResolvedValue(confirmedTask);
  vi.mocked(emitTo).mockRejectedValue(new Error("synthetic event failure"));
  render(<QuickCapture />);

  fireEvent.change(screen.getByRole("textbox", { name: "What needs doing?" }), {
    target: { value: "Synthetic captured Task" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Capture" }));

  await waitFor(() => expect(hide).toHaveBeenCalledOnce());
  expect(
    screen.queryByText("Task was not saved. Check Ion and try again."),
  ).not.toBeInTheDocument();
});

test("reports a failed canonical mutation and keeps the window open", async () => {
  vi.mocked(invoke).mockRejectedValue(new Error("synthetic create failure"));
  render(<QuickCapture />);

  fireEvent.change(screen.getByRole("textbox", { name: "What needs doing?" }), {
    target: { value: "Synthetic captured Task" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Capture" }));

  expect(
    await screen.findByText("Task was not saved. Check Ion and try again."),
  ).toBeInTheDocument();
  expect(getCurrentWindow).not.toHaveBeenCalled();
});
