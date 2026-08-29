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
import { OrganizerShell } from "./OrganizerShell";
import { HomeOutput } from "./home";
import { Area, Goal, GoalDetail, Project } from "./organizer";
import { StartupData } from "./startup";
import { TodayOutput } from "./today";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
const time = "2030-01-01T00:00:00Z";
const area: Area = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "Synthetic Area",
  description: null,
  archived_at: null,
  created_at: time,
  updated_at: time,
  revision: 1,
  trashed_at: null,
};
const goal: Goal = {
  id: "22222222-2222-4222-8222-222222222222",
  area_id: area.id,
  title: "Synthetic Goal",
  description: null,
  kind: "outcome",
  state: "active",
  archived_at: null,
  created_at: time,
  updated_at: time,
  revision: 1,
  trashed_at: null,
};
const project: Project = {
  id: "33333333-3333-4333-8333-333333333333",
  goal_id: goal.id,
  title: "Synthetic Project",
  description: null,
  state: "active",
  completed_at: null,
  archived_at: null,
  created_at: time,
  updated_at: time,
  revision: 1,
  trashed_at: null,
};
const detail: GoalDetail = {
  goal,
  summary: {
    milestone_total: 0,
    milestone_achieved: 0,
    project_total: 1,
    task_total: 0,
    task_completed: 0,
  },
  milestones: [],
  projects: [project],
  direct_tasks: [],
  project_tasks: [],
};
const today: TodayOutput = {
  planning_date: "2030-01-01",
  timezone: "UTC",
  generated_at: time,
  plan: { priorities: [], planned: [], backups: [] },
  deadlines: { overdue: [], due_today: [], approaching: [] },
  needs_attention: [],
  unfinished_from_yesterday: [],
  completed_today: [],
};
const home: HomeOutput = {
  planning_date: today.planning_date,
  timezone: today.timezone,
  generated_at: time,
  core: { nodes: [], edges: [] },
  focus: null,
  needs_attention: [],
  upcoming: [],
};
const data: StartupData = {
  areas: [area],
  goals: [goal],
  projects: [project],
  tasks: [],
  today,
  home,
  todayContext: {
    planning_date: today.planning_date,
    timezone: today.timezone,
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "get_goal_detail") return detail;
    if (command.startsWith("list_")) return [];
    throw new Error(`Unexpected command: ${command}`);
  });
});
afterEach(cleanup);

test("keeps an active Goal visible with archived-parent context", async () => {
  render(
    <OrganizerShell
      initialData={{ ...data, areas: [{ ...area, archived_at: time }] }}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Areas & Goals" }));
  expect(await screen.findByText("Archived parent")).toBeInTheDocument();
  expect(
    screen.getByText("Parent Area is archived. Existing context is retained."),
  ).toBeInTheDocument();
});

test("groups Projects by status and creates contextual Tasks without inferring Goal", async () => {
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "get_project_detail")
      return {
        project,
        summary: {
          milestone_total: 0,
          milestone_achieved: 0,
          task_total: 0,
          task_completed: 0,
        },
        milestones: [],
        current_milestone: null,
        tasks: [],
        next_actions: [],
        recent_activity: [],
      };
    if (command === "create_task")
      return {
        id: "44444444-4444-4444-8444-444444444444",
        title: "Project context Task",
        state: "open",
      };
    throw new Error(`Unexpected command: ${command}`);
  });
  render(<OrganizerShell initialData={data} />);
  fireEvent.click(screen.getByRole("button", { name: "Projects" }));
  expect(
    await screen.findByRole("heading", { name: "Active" }),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox", { name: "New Project Task" }), {
    target: { value: "Project context Task" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create Task" }));
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("create_task", {
      input: expect.objectContaining({
        title: "Project context Task",
        project_id: project.id,
        goal_id: null,
      }),
    }),
  );
});

test("renders direct blocker counts and retains the canonical Area on failed Trash", async () => {
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "trash_area")
      throw { code: "trash_blocked", blockers: [{ entity: "goal", count: 2 }] };
    throw new Error(`Unexpected command: ${command}`);
  });
  render(<OrganizerShell initialData={{ ...data, goals: [], projects: [] }} />);
  fireEvent.click(screen.getByRole("button", { name: "Areas & Goals" }));
  fireEvent.click(screen.getByRole("button", { name: "Move Area to Trash" }));
  expect(
    await screen.findByText("Cannot move this record to Trash yet."),
  ).toBeInTheDocument();
  expect(screen.getByText("2 Goals")).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Synthetic Area" }),
  ).toBeInTheDocument();
});

test("creates a contextual Goal Task without inferring a Project", async () => {
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "get_goal_detail") return detail;
    if (command === "create_task")
      return {
        id: "55555555-5555-4555-8555-555555555555",
        title: "Goal context Task",
        state: "open",
      };
    throw new Error(`Unexpected command: ${command}`);
  });
  render(<OrganizerShell initialData={data} />);
  fireEvent.click(screen.getByRole("button", { name: "Areas & Goals" }));
  fireEvent.change(
    await screen.findByRole("textbox", { name: "New Goal Task" }),
    {
      target: { value: "Goal context Task" },
    },
  );
  fireEvent.click(screen.getByRole("button", { name: "Create Task" }));
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("create_task", {
      input: expect.objectContaining({
        title: "Goal context Task",
        goal_id: goal.id,
        project_id: null,
      }),
    }),
  );
});

test("refreshes a revision conflict while preserving the owner's Area draft", async () => {
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "update_area")
      throw { code: "revision_conflict", blockers: [] };
    if (command === "list_tasks" || command === "list_projects") return [];
    if (command === "list_areas") return [area];
    if (command === "list_goals") return [];
    if (command === "get_today") return today;
    if (command === "get_home") return home;
    throw new Error(`Unexpected command: ${command}`);
  });
  render(<OrganizerShell initialData={{ ...data, goals: [], projects: [] }} />);
  fireEvent.click(screen.getByRole("button", { name: "Areas & Goals" }));
  const input = screen.getByRole("textbox", { name: "Name" });
  fireEvent.change(input, { target: { value: "Owner draft" } });
  fireEvent.click(screen.getByRole("button", { name: "Save Area" }));

  expect(
    await screen.findByText(
      "This record changed elsewhere. Canonical data was refreshed; review your input and try again.",
    ),
  ).toBeInTheDocument();
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("list_areas", { view: "all" }),
  );
  expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue(
    "Owner draft",
  );
});

test("shows pending and confirmed feedback for one successful Goal save", async () => {
  let confirmSave: (value: Goal) => void = () => undefined;
  const saveResponse = new Promise<Goal>((resolve) => {
    confirmSave = resolve;
  });
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "get_goal_detail") return detail;
    if (command === "update_goal") return saveResponse;
    throw new Error(`Unexpected command: ${command}`);
  });
  render(<OrganizerShell initialData={data} />);
  fireEvent.click(screen.getByRole("button", { name: "Areas & Goals" }));

  const title = await screen.findByRole("textbox", { name: "Title" });
  fireEvent.change(title, { target: { value: "Edited Goal" } });
  const save = screen.getByRole("button", { name: "Save Goal" });
  fireEvent.click(save);
  fireEvent.click(save);

  expect(screen.getByText("Saving…")).toBeInTheDocument();
  expect(save).toBeDisabled();
  expect(
    vi
      .mocked(invoke)
      .mock.calls.filter(([command]) => command === "update_goal"),
  ).toHaveLength(1);

  await act(async () => {
    confirmSave({ ...goal, title: "Edited Goal", revision: 2 });
    await saveResponse;
  });

  expect(await screen.findByText("Saved")).toBeInTheDocument();
  expect(screen.queryByText(/Ion could not accept/)).not.toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Edited Goal" }),
  ).toBeInTheDocument();
});

test("shows a genuine Goal validation failure without false success", async () => {
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "get_goal_detail") return detail;
    if (command === "update_goal") throw { code: "validation", blockers: [] };
    throw new Error(`Unexpected command: ${command}`);
  });
  render(<OrganizerShell initialData={data} />);
  fireEvent.click(screen.getByRole("button", { name: "Areas & Goals" }));

  fireEvent.change(await screen.findByRole("textbox", { name: "Title" }), {
    target: { value: "Rejected Goal" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save Goal" }));

  expect(
    await screen.findByText(
      "Ion could not accept that value. Review the fields and try again.",
    ),
  ).toBeInTheDocument();
  expect(screen.queryByText("Saved")).not.toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue(
    "Rejected Goal",
  );
});

test("refreshes Home after a confirmed canonical Task mutation", async () => {
  const confirmedTask = {
    id: "66666666-6666-4666-8666-666666666666",
    title: "New canonical Task",
    details: null,
    state: "open",
    source_kind: "human",
    importance: null,
    estimated_minutes: null,
    progress_percent: null,
    deadline: { kind: "none" },
    project_id: null,
    goal_id: null,
    completion_evidence: null,
    completed_at: null,
    created_at: time,
    updated_at: time,
    revision: 1,
    trashed_at: null,
  };
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "create_task") return confirmedTask;
    if (command === "get_home") return home;
    throw new Error(`Unexpected command: ${command}`);
  });
  render(<OrganizerShell initialData={data} />);
  fireEvent.click(screen.getByRole("button", { name: "Tasks" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Title" }), {
    target: { value: confirmedTask.title },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create task" }));
  expect(await screen.findByText(confirmedTask.title)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Home" }));
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("get_home", expect.anything()),
  );
});
