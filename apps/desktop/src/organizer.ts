import { invoke } from "@tauri-apps/api/core";
import { Task } from "./tasks";

export type ListView = "active" | "archived" | "trash" | "all";
export type GoalKind =
  "outcome" | "skill" | "habit" | "project" | "academic" | "personal";
export type GoalState = "active" | "paused" | "achieved" | "retired";
export type ProjectState =
  | "idea"
  | "exploring"
  | "planned"
  | "active"
  | "paused"
  | "completed"
  | "archived"
  | "abandoned";
export type MilestoneState = "planned" | "in_progress" | "achieved" | "skipped";
export type Blocker = { entity: string; count: number };
export type ProductError = {
  code:
    | "not_found"
    | "revision_conflict"
    | "validation"
    | "assignment_unavailable"
    | "trash_blocked"
    | "unavailable";
  blockers: Blocker[];
};

export function asProductError(reason: unknown): ProductError {
  if (typeof reason === "object" && reason !== null && "code" in reason) {
    const value = reason as Partial<ProductError>;
    const valid = [
      "not_found",
      "revision_conflict",
      "validation",
      "assignment_unavailable",
      "trash_blocked",
      "unavailable",
    ];
    if (typeof value.code === "string" && valid.includes(value.code)) {
      return {
        code: value.code as ProductError["code"],
        blockers: Array.isArray(value.blockers) ? value.blockers : [],
      };
    }
  }
  return { code: "unavailable", blockers: [] };
}

type Canonical = {
  id: string;
  created_at: string;
  updated_at: string;
  revision: number;
  trashed_at: string | null;
};
export type Area = Canonical & {
  name: string;
  description: string | null;
  archived_at: string | null;
};
export type Goal = Canonical & {
  area_id: string | null;
  title: string;
  description: string | null;
  kind: GoalKind;
  state: GoalState;
  archived_at: string | null;
};
export type Project = Canonical & {
  goal_id: string | null;
  title: string;
  description: string | null;
  state: ProjectState;
  completed_at: string | null;
  archived_at: string | null;
};
type Milestone = Canonical & {
  title: string;
  state: MilestoneState;
  target_date: string | null;
  achieved_at: string | null;
  position: number;
};
export type GoalMilestone = Milestone & { goal_id: string };
export type ProjectMilestone = Milestone & { project_id: string };
export type AreaDetail = { area: Area; goals: Goal[] };
export type GoalSummary = {
  milestone_total: number;
  milestone_achieved: number;
  project_total: number;
  task_total: number;
  task_completed: number;
};
export type GoalDetail = {
  goal: Goal;
  summary: GoalSummary;
  milestones: GoalMilestone[];
  projects: Project[];
  direct_tasks: Task[];
  project_tasks: Task[];
};
export type ProjectSummary = {
  milestone_total: number;
  milestone_achieved: number;
  task_total: number;
  task_completed: number;
};
export type Activity = {
  event_id: string;
  occurred_at: string;
  entity_type: "project" | "project_milestone";
  entity_id: string;
  action: string;
  from_revision: number | null;
  to_revision: number | null;
  command_id: string;
};
export type ProjectDetail = {
  project: Project;
  summary: ProjectSummary;
  milestones: ProjectMilestone[];
  current_milestone: ProjectMilestone | null;
  tasks: Task[];
  next_actions: Task[];
  recent_activity: Activity[];
};

const revision = (item: Pick<Canonical, "revision">) => ({
  expected_revision: item.revision,
});

export const areaClient = {
  list: (view: ListView = "all") => invoke<Area[]>("list_areas", { view }),
  get: (area: Pick<Area, "id">) =>
    invoke<AreaDetail>("get_area", { areaId: area.id }),
  create: (input: { name: string; description: string | null }) =>
    invoke<Area>("create_area", { input }),
  update: (area: Area, input: { name?: string; description?: string | null }) =>
    invoke<Area>("update_area", {
      areaId: area.id,
      input: { ...input, expected_revision: area.revision },
    }),
  archive: (area: Area) =>
    invoke<Area>("archive_area", { areaId: area.id, input: revision(area) }),
  unarchive: (area: Area) =>
    invoke<Area>("unarchive_area", { areaId: area.id, input: revision(area) }),
  trash: (area: Area) =>
    invoke<Area>("trash_area", { areaId: area.id, input: revision(area) }),
  restore: (area: Pick<Area, "id" | "revision">) =>
    invoke<Area>("restore_area", { areaId: area.id, input: revision(area) }),
};

export const goalClient = {
  list: (view: ListView = "all") => invoke<Goal[]>("list_goals", { view }),
  get: (goal: Pick<Goal, "id">) =>
    invoke<GoalDetail>("get_goal_detail", { goalId: goal.id }),
  create: (input: {
    title: string;
    description: string | null;
    kind: GoalKind;
    area_id: string | null;
  }) => invoke<Goal>("create_goal", { input }),
  update: (
    goal: Goal,
    input: { title?: string; description?: string | null; kind?: GoalKind },
  ) =>
    invoke<Goal>("update_goal", {
      goalId: goal.id,
      input: { ...input, expected_revision: goal.revision },
    }),
  setState: (goal: Goal, state: GoalState) =>
    invoke<Goal>("set_goal_state", {
      goalId: goal.id,
      input: { state, expected_revision: goal.revision },
    }),
  setArea: (goal: Goal, area_id: string | null) =>
    invoke<Goal>("set_goal_area", {
      goalId: goal.id,
      input: { area_id, expected_revision: goal.revision },
    }),
  archive: (goal: Goal) =>
    invoke<Goal>("archive_goal", { goalId: goal.id, input: revision(goal) }),
  unarchive: (goal: Goal) =>
    invoke<Goal>("unarchive_goal", { goalId: goal.id, input: revision(goal) }),
  trash: (goal: Goal) =>
    invoke<Goal>("trash_goal", { goalId: goal.id, input: revision(goal) }),
  restore: (goal: Pick<Goal, "id" | "revision">) =>
    invoke<Goal>("restore_goal", { goalId: goal.id, input: revision(goal) }),
};

export const projectClient = {
  list: (view: ListView = "all") =>
    invoke<Project[]>("list_projects", { view }),
  get: (project: Pick<Project, "id">) =>
    invoke<ProjectDetail>("get_project_detail", { projectId: project.id }),
  create: (input: {
    title: string;
    description: string | null;
    state: ProjectState;
    goal_id: string | null;
  }) => invoke<Project>("create_project", { input }),
  update: (
    project: Project,
    input: { title?: string; description?: string | null },
  ) =>
    invoke<Project>("update_project", {
      projectId: project.id,
      input: { ...input, expected_revision: project.revision },
    }),
  setState: (project: Project, state: Exclude<ProjectState, "archived">) =>
    invoke<Project>("set_project_state", {
      projectId: project.id,
      input: { state, expected_revision: project.revision },
    }),
  setGoal: (project: Project, goal_id: string | null) =>
    invoke<Project>("set_project_goal", {
      projectId: project.id,
      input: { goal_id, expected_revision: project.revision },
    }),
  archive: (project: Project) =>
    invoke<Project>("archive_project", {
      projectId: project.id,
      input: revision(project),
    }),
  unarchive: (project: Project) =>
    invoke<Project>("unarchive_project", {
      projectId: project.id,
      input: revision(project),
    }),
  trash: (project: Project) =>
    invoke<Project>("trash_project", {
      projectId: project.id,
      input: revision(project),
    }),
  restore: (project: Pick<Project, "id" | "revision">) =>
    invoke<Project>("restore_project", {
      projectId: project.id,
      input: revision(project),
    }),
};

type MilestoneInput = { title: string; target_date: string | null };
const reorderInput = (items: Milestone[]) => ({
  items: items.map((item) => ({
    id: item.id,
    expected_revision: item.revision,
  })),
});

export const goalMilestoneClient = {
  list: (goal: Goal, trashed = false) =>
    invoke<GoalMilestone[]>("list_goal_milestones", {
      goalId: goal.id,
      trashed,
    }),
  create: (goal: Goal, input: MilestoneInput) =>
    invoke<GoalMilestone>("create_goal_milestone", { goalId: goal.id, input }),
  update: (milestone: GoalMilestone, input: Partial<MilestoneInput>) =>
    invoke<GoalMilestone>("update_goal_milestone", {
      milestoneId: milestone.id,
      input: { ...input, expected_revision: milestone.revision },
    }),
  setState: (milestone: GoalMilestone, state: MilestoneState) =>
    invoke<GoalMilestone>("set_goal_milestone_state", {
      milestoneId: milestone.id,
      input: { state, expected_revision: milestone.revision },
    }),
  reorder: (goal: Goal, items: GoalMilestone[]) =>
    invoke<GoalMilestone[]>("reorder_goal_milestones", {
      goalId: goal.id,
      input: reorderInput(items),
    }),
  trash: (milestone: GoalMilestone) =>
    invoke<GoalMilestone>("trash_goal_milestone", {
      milestoneId: milestone.id,
      input: revision(milestone),
    }),
  restore: (milestone: Pick<GoalMilestone, "id" | "revision">) =>
    invoke<GoalMilestone>("restore_goal_milestone", {
      milestoneId: milestone.id,
      input: revision(milestone),
    }),
};

export const projectMilestoneClient = {
  list: (project: Project, trashed = false) =>
    invoke<ProjectMilestone[]>("list_project_milestones", {
      projectId: project.id,
      trashed,
    }),
  create: (project: Project, input: MilestoneInput) =>
    invoke<ProjectMilestone>("create_project_milestone", {
      projectId: project.id,
      input,
    }),
  update: (milestone: ProjectMilestone, input: Partial<MilestoneInput>) =>
    invoke<ProjectMilestone>("update_project_milestone", {
      milestoneId: milestone.id,
      input: { ...input, expected_revision: milestone.revision },
    }),
  setState: (milestone: ProjectMilestone, state: MilestoneState) =>
    invoke<ProjectMilestone>("set_project_milestone_state", {
      milestoneId: milestone.id,
      input: { state, expected_revision: milestone.revision },
    }),
  reorder: (project: Project, items: ProjectMilestone[]) =>
    invoke<ProjectMilestone[]>("reorder_project_milestones", {
      projectId: project.id,
      input: reorderInput(items),
    }),
  trash: (milestone: ProjectMilestone) =>
    invoke<ProjectMilestone>("trash_project_milestone", {
      milestoneId: milestone.id,
      input: revision(milestone),
    }),
  restore: (milestone: Pick<ProjectMilestone, "id" | "revision">) =>
    invoke<ProjectMilestone>("restore_project_milestone", {
      milestoneId: milestone.id,
      input: revision(milestone),
    }),
};
