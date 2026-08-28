import "@testing-library/jest-dom/vitest";
import { invoke } from "@tauri-apps/api/core";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { Task } from "./tasks";
import { TodayWorkspace } from "./TodayWorkspace";
import { DayPlan, TodayOutput, TodayPlanItem, TodayTask } from "./today";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

const time = "2030-01-02T18:00:00Z";
const context = { planning_date: "2030-01-02", timezone: "UTC" };

function task(id: string, title: string, overrides: Partial<Task> = {}): Task {
  return {
    id,
    title,
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
    ...overrides,
  };
}

function plan(
  taskValue: Task,
  role: DayPlan["role"],
  position: number,
): TodayPlanItem {
  return {
    task: taskValue,
    goal: null,
    project: null,
    plan: {
      id: `${position + 1}1111111-1111-4111-8111-111111111111`,
      task_id: taskValue.id,
      planning_date: context.planning_date,
      role,
      position,
      created_at: time,
      updated_at: time,
      revision: 1,
    },
  };
}

const first = task("11111111-1111-4111-8111-111111111111", "First priority");
const second = task("22222222-2222-4222-8222-222222222222", "Second priority");
const paused = task("33333333-3333-4333-8333-333333333333", "Paused work", {
  state: "paused",
});
const due = task("44444444-4444-4444-8444-444444444444", "Exact deadline", {
  importance: "high",
  deadline: { kind: "instant", at: "2030-01-02T20:00:00Z", timezone: "UTC" },
});
const yesterday = task(
  "55555555-5555-4555-8555-555555555555",
  "Yesterday work",
);
const completed = task(
  "66666666-6666-4666-8666-666666666666",
  "Finished work",
  {
    state: "completed",
    completed_at: "2030-01-02T17:00:00Z",
  },
);
const available = task(
  "77777777-7777-4777-8777-777777777777",
  "Available work",
);

function output(): TodayOutput {
  const dueItem: TodayTask = { task: due, goal: null, project: null };
  return {
    ...context,
    generated_at: time,
    plan: {
      priorities: [plan(first, "priority", 0), plan(second, "priority", 1)],
      planned: [plan(paused, "planned", 0)],
      backups: [],
    },
    deadlines: { overdue: [], due_today: [dueItem], approaching: [] },
    needs_attention: [{ ...dueItem, reason: "due_today" }],
    unfinished_from_yesterday: [plan(yesterday, "backup", 0)],
    completed_today: [
      { task: completed, goal: null, project: null, plan: null },
    ],
  };
}

function Harness({ initial = output() }: { initial?: TodayOutput }) {
  const [today, setToday] = useState(initial);
  const [tasks, setTasks] = useState([
    first,
    second,
    paused,
    due,
    yesterday,
    completed,
    available,
  ]);
  return (
    <TodayWorkspace
      today={today}
      tasks={tasks}
      onToday={setToday}
      onTaskConfirmed={(confirmed) =>
        setTasks((current) =>
          current.map((item) => (item.id === confirmed.id ? confirmed : item)),
        )
      }
      onDayChanged={async () => undefined}
    />
  );
}

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

test("renders truthful execution, deadline, attention, carry, and schedule context", () => {
  render(<Harness />);
  expect(screen.getByRole("heading", { name: "Today" })).toBeInTheDocument();
  expect(screen.getByText("Paused")).toBeInTheDocument();
  expect(screen.getAllByText("Exact deadline").length).toBeGreaterThan(1);
  expect(screen.getByText("due today")).toBeInTheDocument();
  expect(screen.getAllByText("Yesterday work").length).toBeGreaterThan(1);
  expect(screen.getByText("Finished work")).toBeInTheDocument();
  expect(
    screen.getByText("Calendar is not connected yet."),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Ion cannot calculate occupied or available time."),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Selected Tasks are unscheduled/),
  ).toBeInTheDocument();
  expect(screen.queryByText(/free time/i)).not.toBeInTheDocument();
});

test("sends complete visible order and revision data for Move Down", async () => {
  vi.mocked(invoke).mockResolvedValue(output());
  render(<Harness />);
  fireEvent.click(screen.getAllByRole("button", { name: "Move Down" })[0]);
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("reorder_today_tasks", {
      input: {
        ...context,
        role: "priority",
        items: [
          { id: plan(second, "priority", 1).plan.id, expected_revision: 1 },
          { id: plan(first, "priority", 0).plan.id, expected_revision: 1 },
        ],
      },
    }),
  );
});

test("adds, moves, and removes through fixed confirmed commands", async () => {
  vi.mocked(invoke).mockResolvedValue(output());
  render(<Harness />);
  fireEvent.change(screen.getByLabelText("Existing Task"), {
    target: { value: available.id },
  });
  fireEvent.change(screen.getByLabelText("Today role"), {
    target: { value: "backup" },
  });
  fireEvent.click(screen.getAllByRole("button", { name: "Add to Today" })[0]);
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("add_task_to_today", {
      input: { ...context, task_id: available.id, role: "backup" },
    }),
  );
  fireEvent.change(screen.getByLabelText("First priority Today role"), {
    target: { value: "planned" },
  });
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("set_today_role", {
      planId: plan(first, "priority", 0).plan.id,
      input: { ...context, expected_revision: 1, role: "planned" },
    }),
  );
  fireEvent.click(screen.getAllByRole("button", { name: "Remove" })[0]);
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("remove_task_from_today", {
      planId: plan(first, "priority", 0).plan.id,
      input: { ...context, expected_revision: 1 },
    }),
  );
});

test("prevents duplicate add submissions while canonical confirmation is pending", async () => {
  let resolve: (value: TodayOutput) => void = () => undefined;
  vi.mocked(invoke).mockReturnValue(
    new Promise<TodayOutput>((done) => {
      resolve = done;
    }),
  );
  render(<Harness />);
  fireEvent.change(screen.getByLabelText("Existing Task"), {
    target: { value: available.id },
  });
  const button = screen.getAllByRole("button", { name: "Add to Today" })[0];
  fireEvent.click(button);
  fireEvent.click(button);
  expect(button).toBeDisabled();
  expect(
    vi
      .mocked(invoke)
      .mock.calls.filter(([name]) => name === "add_task_to_today"),
  ).toHaveLength(1);
  resolve(output());
  await screen.findByText("Today plan updated.");
});

test("retains confirmed completion when the separate Today refresh fails", async () => {
  const confirmed = {
    ...first,
    state: "completed" as const,
    completed_at: "2030-01-02T18:01:00Z",
    revision: 2,
  };
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "complete_task") return confirmed;
    if (command === "get_today") throw { code: "unavailable", blockers: [] };
    throw new Error(`Unexpected command: ${command}`);
  });
  render(<Harness />);
  fireEvent.click(screen.getAllByRole("button", { name: "Complete" })[0]);
  expect(
    await screen.findByText(
      "Task completed, but Today could not refresh. The confirmed Task state is retained.",
    ),
  ).toBeInTheDocument();
  expect(screen.getByText("First priority")).toBeInTheDocument();
  expect(
    screen.queryByText(/could not accept that value/),
  ).not.toBeInTheDocument();
  expect(vi.mocked(invoke).mock.calls.map(([command]) => command)).toEqual([
    "complete_task",
    "get_today",
  ]);
});
