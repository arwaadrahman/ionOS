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
import { App } from "./App";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

const area = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "Persisted synthetic Area",
  description: null,
  archived_at: null,
  created_at: "2030-01-01T00:00:00Z",
  updated_at: "2030-01-01T00:00:00Z",
  revision: 1,
  trashed_at: null,
};
const task = {
  id: "44444444-4444-4444-8444-444444444444",
  title: "Persisted synthetic Task",
  details: null,
  state: "open",
  source_kind: "human",
  importance: "normal",
  estimated_minutes: null,
  progress_percent: null,
  deadline: { kind: "none" },
  project_id: null,
  goal_id: null,
  completion_evidence: null,
  completed_at: null,
  created_at: "2030-01-01T00:00:00Z",
  updated_at: "2030-01-01T00:00:00Z",
  revision: 1,
  trashed_at: null,
};
const today = {
  planning_date: "2030-01-01",
  timezone: "UTC",
  generated_at: "2030-01-01T00:00:00Z",
  plan: {
    priorities: [
      {
        task,
        goal: null,
        project: null,
        plan: {
          id: "88888888-8888-4888-8888-888888888888",
          task_id: task.id,
          planning_date: "2030-01-01",
          role: "priority",
          position: 0,
          created_at: "2030-01-01T00:00:00Z",
          updated_at: "2030-01-01T00:00:00Z",
          revision: 1,
        },
      },
    ],
    planned: [],
    backups: [],
  },
  deadlines: { overdue: [], due_today: [], approaching: [] },
  needs_attention: [],
  unfinished_from_yesterday: [],
  completed_today: [],
};
const home = {
  planning_date: today.planning_date,
  timezone: today.timezone,
  generated_at: today.generated_at,
  core: { nodes: [], edges: [] },
  focus: {
    id: task.id,
    title: task.title,
    state: task.state,
    deadline: task.deadline,
    goal: null,
    project: null,
  },
  needs_attention: [],
  upcoming: [],
};

function mockStartup(overrides: Record<string, unknown> = {}) {
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command in overrides) return overrides[command];
    if (command === "service_health") return { state: "ready" };
    if (command === "list_tasks") return [];
    if (command === "list_areas") return [];
    if (command === "list_goals") return [];
    if (command === "list_projects") return [];
    if (command === "get_today") return today;
    if (command === "get_home") return home;
    throw new Error(`Unexpected command: ${command}`);
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(cleanup);

test("shows Home first and the milestone-local workspaces through narrow commands", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
  mockStartup();
  render(<App />);
  expect(
    await screen.findByRole("heading", { name: "Home" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Areas & Goals" }));
  expect(
    screen.getByRole("heading", { name: "Areas & Goals" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Tasks" }));
  expect(screen.getByRole("heading", { name: "Tasks" })).toBeInTheDocument();
});

test("reports an unavailable development service without exposing diagnostics", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockRejectedValue(new Error("private diagnostic")),
  );
  render(<App />);
  expect(
    await screen.findByText("Local service: unavailable"),
  ).toBeInTheDocument();
  expect(screen.queryByText("private diagnostic")).not.toBeInTheDocument();
});

test("hydrates all persisted organizer data before mounting any workspace", async () => {
  let resolveProjects: (value: unknown[]) => void = () => undefined;
  const projectResponse = new Promise<unknown[]>((resolve) => {
    resolveProjects = resolve;
  });
  mockStartup({
    list_tasks: [task],
    list_areas: [area],
    list_projects: projectResponse,
  });
  render(<App development={false} />);
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("list_projects", { view: "all" }),
  );
  expect(
    screen.queryByRole("heading", { name: "Areas & Goals" }),
  ).not.toBeInTheDocument();
  await act(async () => {
    resolveProjects([]);
    await projectResponse;
  });
  expect(
    await screen.findByText("Persisted synthetic Task"),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Areas & Goals" }));
  expect(await screen.findAllByText("Persisted synthetic Area")).toHaveLength(
    2,
  );
  fireEvent.click(screen.getByRole("button", { name: "Tasks" }));
  expect(
    await screen.findByText("Persisted synthetic Task"),
  ).toBeInTheDocument();
});
