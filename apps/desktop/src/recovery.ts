import {
  areaClient,
  goalClient,
  goalMilestoneClient,
  projectClient,
  projectMilestoneClient,
} from "./organizer";
import { taskClient } from "./tasks";
import { invoke } from "@tauri-apps/api/core";

export type RecoveryEntityType =
  "area" | "goal" | "goal_milestone" | "project" | "project_milestone" | "task";

export type RecoveryItem = {
  entity_type: RecoveryEntityType;
  entity_id: string;
  label: string;
  lifecycle: string;
  revision: number;
  trashed_at: string;
  owner_label: string | null;
};

export type RecoveryActivity = {
  event_id: string;
  occurred_at: string;
  entity_type: RecoveryEntityType;
  entity_id: string;
  label: string;
  action: string;
  authority: "direct";
};

export type RecoveryOutput = {
  trash: RecoveryItem[];
  recent_activity: RecoveryActivity[];
};

export const recoveryClient = {
  get: () => invoke<RecoveryOutput>("get_recovery"),
};

export function restoreRecoveryItem(item: RecoveryItem) {
  const identity = { id: item.entity_id, revision: item.revision };
  switch (item.entity_type) {
    case "area":
      return areaClient.restore(identity);
    case "goal":
      return goalClient.restore(identity);
    case "goal_milestone":
      return goalMilestoneClient.restore(identity);
    case "project":
      return projectClient.restore(identity);
    case "project_milestone":
      return projectMilestoneClient.restore(identity);
    case "task":
      return taskClient.restore(identity);
  }
}
