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
import { Goal, Project } from "./organizer";
import { Task } from "./tasks";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

const existingTask: Task = {
  id: "task-edit-synthetic",
  title: "Before edit",
  details: null,
  state: "open",
  source_kind: "human",
  importance: null,
  estimated_minutes: null,
  progress_percent: null,
  deadline: { kind: "none" },
  project_id: "22222222-2222-4222-8222-222222222222",
  goal_id: "11111111-1111-4111-8111-111111111111",
  completion_evidence: null,
  completed_at: null,
  created_at: "2030-01-01T00:00:00Z",
  updated_at: "2030-01-01T00:00:00Z",
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

test("keeps same-title Tasks as distinct canonical records", () => {
  const sameTitleTask: Task = {
    ...existingTask,
    id: "task-same-title-synthetic",
    revision: 1,
  };
  render(<TaskWorkspace initialTasks={[existingTask, sameTitleTask]} />);

  expect(screen.getAllByText("Before edit")).toHaveLength(2);
});

test("accepts externally refreshed Tasks without a workspace reload", async () => {
  const { rerender } = render(<TaskWorkspace initialTasks={[existingTask]} />);
  const capturedTask: Task = {
    ...existingTask,
    id: "task-external-synthetic",
    title: "Captured elsewhere",
    revision: 1,
  };

  rerender(<TaskWorkspace initialTasks={[capturedTask, existingTask]} />);

  expect(await screen.findByText("Captured elsewhere")).toBeInTheDocument();
});

test("submits one Task while canonical creation is pending", async () => {
  let resolveCreate: (task: Task) => void = () => undefined;
  const pendingCreate = new Promise<Task>((resolve) => {
    resolveCreate = resolve;
  });
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "create_task") return pendingCreate;
    throw new Error(`Unexpected command: ${command}`);
  });
  render(<TaskWorkspace initialTasks={[]} />);

  fireEvent.change(screen.getByRole("textbox", { name: "Title" }), {
    target: { value: "Synthetic Task" },
  });
  const form = screen.getByRole("textbox", { name: "Title" }).closest("form");
  expect(form).not.toBeNull();
  fireEvent.submit(form!);
  fireEvent.submit(form!);

  await waitFor(() => expect(invoke).toHaveBeenCalledTimes(1));
  await act(async () => {
    resolveCreate({
      ...existingTask,
      id: "task-created-synthetic",
      title: "Synthetic Task",
    });
    await pendingCreate;
  });
  expect(await screen.findByText("Synthetic Task")).toBeInTheDocument();
});

test("changes Task relationships only through the explicit complete-pair command", async () => {
  const goal: Goal = {
    id: "11111111-1111-4111-8111-111111111111",
    area_id: null,
    title: "Synthetic Goal",
    description: null,
    kind: "outcome",
    state: "active",
    archived_at: null,
    created_at: existingTask.created_at,
    updated_at: existingTask.updated_at,
    revision: 1,
    trashed_at: null,
  };
  const project: Project = {
    id: "22222222-2222-4222-8222-222222222222",
    goal_id: null,
    title: "Synthetic Project",
    description: null,
    state: "active",
    completed_at: null,
    archived_at: null,
    created_at: existingTask.created_at,
    updated_at: existingTask.updated_at,
    revision: 1,
    trashed_at: null,
  };
  vi.mocked(invoke).mockResolvedValue({
    ...existingTask,
    goal_id: null,
    project_id: project.id,
    revision: existingTask.revision + 1,
  });

  render(
    <TaskWorkspace
      initialTasks={[existingTask]}
      goals={[goal]}
      projects={[project]}
    />,
  );
  fireEvent.change(screen.getByRole("combobox", { name: "Before edit Goal" }), {
    target: { value: "" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save relationships" }));

  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("set_task_relationships", {
      taskId: existingTask.id,
      input: {
        expected_revision: existingTask.revision,
        goal_id: null,
        project_id: project.id,
      },
    }),
  );
});

test("confirms complete, reopen, Trash, and restore before changing canonical UI", async () => {
  let resolveComplete: (task: Task) => void = () => undefined;
  const completeResponse = new Promise<Task>((resolve) => {
    resolveComplete = resolve;
  });
  vi.mocked(invoke).mockImplementation(async (command, args) => {
    const task = (args as { input?: { expected_revision?: number } })?.input;
    if (command === "complete_task") return completeResponse;
    if (command === "reopen_task")
      return {
        ...existingTask,
        state: "open",
        revision: task?.expected_revision ?? 9,
      };
    if (command === "trash_task")
      return {
        ...existingTask,
        revision: 10,
        trashed_at: existingTask.updated_at,
      };
    if (command === "restore_task")
      return { ...existingTask, revision: 11, trashed_at: null };
    throw new Error(`Unexpected command: ${command}`);
  });

  render(<TaskWorkspace initialTasks={[existingTask]} />);
  fireEvent.click(screen.getByRole("button", { name: "Complete" }));
  expect(screen.getByText("open")).toBeInTheDocument();
  await act(async () => {
    resolveComplete({ ...existingTask, state: "completed", revision: 8 });
    await completeResponse;
  });
  fireEvent.click(await screen.findByRole("button", { name: "Reopen" }));
  await screen.findByRole("button", { name: "Complete" });
  fireEvent.click(screen.getByRole("button", { name: "Trash" }));
  expect(
    await screen.findByRole("button", { name: "Restore" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Restore" }));
  expect(
    await screen.findByRole("button", { name: "Complete" }),
  ).toBeInTheDocument();
  expect(screen.getByText("Before edit")).toBeInTheDocument();

  expect(vi.mocked(invoke).mock.calls.map(([command]) => command)).toEqual([
    "complete_task",
    "reopen_task",
    "trash_task",
    "restore_task",
  ]);
});
