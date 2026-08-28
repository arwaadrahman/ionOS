import { invoke } from "@tauri-apps/api/core";
import { Task } from "./tasks";

export type TodayRole = "priority" | "planned" | "backup";
export type AttentionReason =
  | "overdue"
  | "due_today"
  | "high_importance_approaching"
  | "in_progress_not_planned";

export type TodayContext = { planning_date: string; timezone: string };
export type DayPlan = {
  id: string;
  task_id: string;
  planning_date: string;
  role: TodayRole;
  position: number;
  created_at: string;
  updated_at: string;
  revision: number;
};
export type GoalContext = {
  id: string;
  title: string;
  state: string;
  archived_at: string | null;
};
export type ProjectContext = GoalContext;
export type TodayTask = {
  task: Task;
  goal: GoalContext | null;
  project: ProjectContext | null;
};
export type TodayPlanItem = TodayTask & { plan: DayPlan };
export type AttentionItem = TodayTask & { reason: AttentionReason };
export type CompletedTodayItem = TodayTask & { plan: DayPlan | null };
export type TodayOutput = TodayContext & {
  generated_at: string;
  plan: {
    priorities: TodayPlanItem[];
    planned: TodayPlanItem[];
    backups: TodayPlanItem[];
  };
  deadlines: {
    overdue: TodayTask[];
    due_today: TodayTask[];
    approaching: TodayTask[];
  };
  needs_attention: AttentionItem[];
  unfinished_from_yesterday: TodayPlanItem[];
  completed_today: CompletedTodayItem[];
};

export function currentTodayContext(now = new Date()): TodayContext {
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const value = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? "";
  return {
    planning_date: `${value("year")}-${value("month")}-${value("day")}`,
    timezone,
  };
}

export function millisecondsUntilNextMidnight(now = new Date()): number {
  const next = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate() + 1,
    0,
    0,
    1,
  );
  return Math.max(1, next.getTime() - now.getTime());
}

export function sameTodayContext(a: TodayContext, b: TodayContext): boolean {
  return a.planning_date === b.planning_date && a.timezone === b.timezone;
}

function replaceTask<T extends TodayTask>(item: T, task: Task): T {
  return item.task.id === task.id ? { ...item, task } : item;
}

export function applyConfirmedTask(
  today: TodayOutput,
  task: Task,
): TodayOutput {
  const priorities = today.plan.priorities.map((item) =>
    replaceTask(item, task),
  );
  const planned = today.plan.planned.map((item) => replaceTask(item, task));
  const backups = today.plan.backups.map((item) => replaceTask(item, task));
  const currentItem = [...priorities, ...planned, ...backups].find(
    (item) => item.task.id === task.id,
  );
  const currentPlan = currentItem?.plan;
  let completed = today.completed_today
    .filter((item) => item.task.id !== task.id)
    .map((item) => replaceTask(item, task));
  let nextPlan = { priorities, planned, backups };
  if (task.state === "completed") {
    nextPlan = {
      priorities: priorities.filter((item) => item.task.id !== task.id),
      planned: planned.filter((item) => item.task.id !== task.id),
      backups: backups.filter((item) => item.task.id !== task.id),
    };
    completed = [
      {
        task,
        goal: currentItem?.goal ?? null,
        project: currentItem?.project ?? null,
        plan: currentPlan ?? null,
      },
      ...completed,
    ];
  } else {
    const completedItem = today.completed_today.find(
      (item) => item.task.id === task.id,
    );
    if (completedItem?.plan) {
      const item: TodayPlanItem = {
        task,
        goal: completedItem.goal,
        project: completedItem.project,
        plan: completedItem.plan,
      };
      const key =
        item.plan.role === "priority"
          ? "priorities"
          : item.plan.role === "backup"
            ? "backups"
            : "planned";
      nextPlan = {
        ...nextPlan,
        [key]: [...nextPlan[key], item].sort(
          (a, b) => a.plan.position - b.plan.position,
        ),
      };
    }
  }
  const keepActive = (item: TodayTask) => item.task.id !== task.id;
  return {
    ...today,
    plan: nextPlan,
    deadlines: {
      overdue: today.deadlines.overdue.filter(keepActive),
      due_today: today.deadlines.due_today.filter(keepActive),
      approaching: today.deadlines.approaching.filter(keepActive),
    },
    needs_attention: today.needs_attention.filter(keepActive),
    unfinished_from_yesterday:
      today.unfinished_from_yesterday.filter(keepActive),
    completed_today: completed,
  };
}

export const todayClient = {
  get: (context: TodayContext) => invoke<TodayOutput>("get_today", { context }),
  add: (context: TodayContext, taskId: string, role: TodayRole) =>
    invoke<TodayOutput>("add_task_to_today", {
      input: { ...context, task_id: taskId, role },
    }),
  remove: (context: TodayContext, plan: DayPlan) =>
    invoke<TodayOutput>("remove_task_from_today", {
      planId: plan.id,
      input: { ...context, expected_revision: plan.revision },
    }),
  setRole: (context: TodayContext, plan: DayPlan, role: TodayRole) =>
    invoke<TodayOutput>("set_today_role", {
      planId: plan.id,
      input: { ...context, expected_revision: plan.revision, role },
    }),
  reorder: (context: TodayContext, role: TodayRole, items: TodayPlanItem[]) =>
    invoke<TodayOutput>("reorder_today_tasks", {
      input: {
        ...context,
        role,
        items: items.map(({ plan }) => ({
          id: plan.id,
          expected_revision: plan.revision,
        })),
      },
    }),
};
