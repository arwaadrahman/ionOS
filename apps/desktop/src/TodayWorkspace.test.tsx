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
import { CalendarBlock, CalendarStatus, emptyCalendarStatus } from "./calendar";

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

function Harness({
  initial = output(),
  calendar = emptyCalendarStatus(),
}: {
  initial?: TodayOutput;
  calendar?: CalendarStatus;
}) {
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
      calendar={calendar}
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

test("shows real CalendarBlock occupancy and free gaps without scheduling Today Tasks", () => {
  const accountId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const calendarId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  const calendarBlock = (
    id: string,
    title: string,
    start: string,
    end: string,
    overrides: Partial<CalendarBlock> = {},
  ): CalendarBlock => ({
    id,
    calendar_id: calendarId,
    provider_event_id: `provider-${id}`,
    ical_uid: null,
    title,
    description: null,
    location: null,
    temporal_kind: "timed",
    start_date: null,
    end_date: null,
    start_at: start,
    end_at: end,
    start_timezone: "UTC",
    end_timezone: "UTC",
    status: "confirmed",
    transparency: "opaque",
    recurrence_kind: "single",
    recurrence_rules: [],
    recurrence_master_block_id: null,
    recurring_event_id: null,
    original_start_kind: "none",
    original_start_date: null,
    original_start_at: null,
    original_start_timezone: null,
    flexibility: "locked",
    notes: null,
    category: null,
    category_subtype: null,
    ion_metadata_revision: 1,
    provider_deleted_at: null,
    revision: 1,
    ...overrides,
  });
  const calendarStatus: CalendarStatus = {
    configured: true,
    configuration_path: "/synthetic/google-oauth.json",
    accounts: [
      {
        id: accountId,
        provider_account_id: "synthetic@example.invalid",
        display_name: "Synthetic account",
        granted_scopes: [],
        auth_state: "connected",
        last_auth_at: time,
        created_at: time,
        updated_at: time,
        revision: 1,
      },
    ],
    calendars: [
      {
        id: calendarId,
        account_id: accountId,
        provider_calendar_id: "synthetic@example.invalid",
        summary: "Synthetic calendar",
        description: null,
        location: null,
        timezone: "UTC",
        access_role: "owner",
        is_primary: true,
        provider_selected: true,
        provider_hidden: false,
        enabled_in_ion: true,
        hidden_in_ion: false,
        provider_deleted: false,
        has_sync_token: true,
        sync_state: "idle",
        last_synced_at: time,
        last_error_code: null,
        retry_count: 0,
        next_retry_at: null,
        revision: 1,
      },
    ],
    blocks: [
      calendarBlock(
        "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        "Occupied calendar interval",
        "2030-01-02T08:00:00Z",
        "2030-01-02T09:00:00Z",
        { category: "academic" },
      ),
      calendarBlock(
        "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        "Transparent calendar interval",
        "2030-01-02T10:00:00Z",
        "2030-01-02T11:00:00Z",
        { transparency: "transparent" },
      ),
      calendarBlock(
        "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        "All-day context",
        "2030-01-02T00:00:00Z",
        "2030-01-03T00:00:00Z",
        {
          temporal_kind: "all_day",
          start_date: "2030-01-02",
          end_date: "2030-01-03",
          start_at: null,
          end_at: null,
          start_timezone: null,
          end_timezone: null,
        },
      ),
    ],
  };

  render(<Harness calendar={calendarStatus} />);
  expect(screen.getByText("Calendar occupancy")).toBeInTheDocument();
  expect(screen.getByText("Occupied calendar interval")).toBeInTheDocument();
  expect(screen.getByText("Transparent calendar interval")).toBeInTheDocument();
  expect(screen.getByText("All-day context")).toBeInTheDocument();
  expect(screen.getByText(/Academic · Synthetic calendar/)).toBeInTheDocument();
  expect(screen.getByText("6 AM–8 AM")).toBeInTheDocument();
  expect(screen.getByText("9 AM–11 PM")).toBeInTheDocument();
  expect(
    screen.getByText(/Today Tasks remain unscheduled/),
  ).toBeInTheDocument();
  expect(screen.queryByText(/assigned to open time/i)).toBeInTheDocument();
  expect(invoke).not.toHaveBeenCalled();
});
