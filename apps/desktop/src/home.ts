import { invoke } from "@tauri-apps/api/core";
import { Deadline, TaskState } from "./tasks";
import {
  AttentionReason,
  GoalContext,
  ProjectContext,
  TodayContext,
  TodayRole,
} from "./today";

export type CoreEntityType =
  "area" | "goal" | "goal_milestone" | "project" | "project_milestone" | "task";
export type CoreLifecycle =
  "active" | "paused" | "completed" | "archived" | "inactive";
export type CoreRelationshipType =
  | "goal_area"
  | "project_goal"
  | "goal_milestone_goal"
  | "project_milestone_project"
  | "task_goal"
  | "task_project";

export type CoreNode = {
  id: string;
  entity_type: CoreEntityType;
  label: string;
  lifecycle: CoreLifecycle;
  today_role: TodayRole | null;
  attention_reason: AttentionReason | null;
};
export type CoreEdge = {
  source_id: string;
  target_id: string;
  relationship_type: CoreRelationshipType;
};
export type CoreGraph = { nodes: CoreNode[]; edges: CoreEdge[] };

export type HomeTaskSummary = {
  id: string;
  title: string;
  state: TaskState;
  deadline: Deadline;
  goal: GoalContext | null;
  project: ProjectContext | null;
};
export type HomeAttentionSummary = HomeTaskSummary & {
  reason: AttentionReason;
};
export type HomeOutput = TodayContext & {
  generated_at: string;
  core: CoreGraph;
  focus: HomeTaskSummary | null;
  needs_attention: HomeAttentionSummary[];
  upcoming: HomeTaskSummary[];
};

export const homeClient = {
  get: (context: TodayContext) => invoke<HomeOutput>("get_home", { context }),
};
