import { CoreNode, HomeOutput } from "./home";

export type Workspace = "home" | "today" | "areas" | "projects" | "tasks";

export type NavigationTarget =
  | { workspace: "areas"; entityType: "area" | "goal"; id: string }
  | { workspace: "projects"; entityType: "project"; id: string }
  | { workspace: "tasks"; entityType: "task"; id: string };

export const workspaces: readonly Workspace[] = [
  "home",
  "today",
  "areas",
  "projects",
  "tasks",
];

export function workspaceLabel(workspace: Workspace) {
  return workspace === "areas"
    ? "Areas & Goals"
    : workspace.charAt(0).toUpperCase() + workspace.slice(1);
}

export function destinationForCoreNode(
  home: HomeOutput,
  node: CoreNode,
): NavigationTarget | null {
  if (node.entity_type === "area" || node.entity_type === "goal") {
    return { workspace: "areas", entityType: node.entity_type, id: node.id };
  }
  if (node.entity_type === "project") {
    return { workspace: "projects", entityType: "project", id: node.id };
  }
  if (node.entity_type === "task") {
    return { workspace: "tasks", entityType: "task", id: node.id };
  }
  const relationship =
    node.entity_type === "goal_milestone"
      ? "goal_milestone_goal"
      : "project_milestone_project";
  const owner = home.core.edges.find(
    (edge) =>
      edge.source_id === node.id && edge.relationship_type === relationship,
  );
  if (!owner) return null;
  return node.entity_type === "goal_milestone"
    ? { workspace: "areas", entityType: "goal", id: owner.target_id }
    : { workspace: "projects", entityType: "project", id: owner.target_id };
}
