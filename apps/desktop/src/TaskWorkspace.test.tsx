import "@testing-library/jest-dom/vitest";
import { invoke } from "@tauri-apps/api/core";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { TaskWorkspace } from "./TaskWorkspace";
import { Task } from "./tasks";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

const existingTask: Task = {
  id: "task-edit-synthetic",
  title: "Before edit",
  details: null,
  state: "open",
  importance: null,
  estimated_minutes: null,
  progress_percent: null,
  deadline: { kind: "none" },
  revision: 7,
  trashed_at: null,
};

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(cleanup);

test("saves an existing Task through update_task before rendering the edit", async () => {
  let resolveUpdate: (task: Task) => void = () => undefined;
  const updateResponse = new Promise<Task>((resolve) => {
    resolveUpdate = resolve;
  });
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "update_task") return updateResponse;
    throw new Error(`Unexpected command: ${command}`);
  });

  render(<TaskWorkspace initialTasks={[existingTask]} />);
  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Title" }), {
    target: { value: "After edit" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save task" }));

  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("update_task", {
      taskId: existingTask.id,
      input: {
        title: "After edit",
        details: null,
        importance: null,
        estimated_minutes: null,
        progress_percent: null,
        deadline: { kind: "none" },
        project_id: null,
        goal_id: null,
        completion_evidence: null,
        expected_revision: existingTask.revision,
      },
    }),
  );
  expect(screen.getByText("Before edit")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save task" })).toBeInTheDocument();

  await act(async () => {
    resolveUpdate({
      ...existingTask,
      title: "After edit",
      revision: existingTask.revision + 1,
    });
    await updateResponse;
  });

  expect(await screen.findByText("After edit")).toBeInTheDocument();
  expect(screen.queryByText("Before edit")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Create task" }),
  ).toBeInTheDocument();
});
