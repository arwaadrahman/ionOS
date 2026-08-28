import { invoke } from "@tauri-apps/api/core";

export type Deadline =
  | { kind: "none"; date?: null; at?: null; timezone?: null }
  | { kind: "date"; date: string; at?: null; timezone?: null }
  | { kind: "instant"; at: string; timezone: string; date?: null };

export type Task = {
  id: string;
  title: string;
  details: string | null;
  state: "open" | "in_progress" | "paused" | "completed" | "canceled";
  importance: "low" | "normal" | "high" | null;
  estimated_minutes: number | null;
  progress_percent: number | null;
  deadline: Deadline;
  revision: number;
  trashed_at: string | null;
};

export type TaskInput = {
  title: string;
  details: string | null;
  importance: Task["importance"];
  estimated_minutes: number | null;
  progress_percent: number | null;
  deadline: Deadline;
  project_id: null;
  goal_id: null;
  completion_evidence: null;
};

export const taskClient = {
  list: () => invoke<Task[]>("list_tasks"),
  listTrash: () => invoke<Task[]>("list_trashed_tasks"),
  create: (input: TaskInput) => invoke<Task>("create_task", { input }),
  update: (task: Task, input: TaskInput) =>
    invoke<Task>("update_task", {
      taskId: task.id,
      input: { ...input, expected_revision: task.revision },
    }),
  complete: (task: Task) =>
    invoke<Task>("complete_task", {
      taskId: task.id,
      input: { expected_revision: task.revision },
    }),
  reopen: (task: Task) =>
    invoke<Task>("reopen_task", {
      taskId: task.id,
      input: { expected_revision: task.revision },
    }),
  trash: (task: Task) =>
    invoke<Task>("trash_task", {
      taskId: task.id,
      input: { expected_revision: task.revision },
    }),
  restore: (task: Task) =>
    invoke<Task>("restore_task", {
      taskId: task.id,
      input: { expected_revision: task.revision },
    }),
};
