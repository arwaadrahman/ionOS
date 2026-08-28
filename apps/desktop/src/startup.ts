import {
  Area,
  Goal,
  Project,
  areaClient,
  goalClient,
  projectClient,
} from "./organizer";
import { Task, taskClient } from "./tasks";

export type StartupData = {
  tasks: Task[];
  areas: Area[];
  goals: Goal[];
  projects: Project[];
};

export async function loadStartupData(): Promise<StartupData> {
  const [tasks, areas, goals, projects] = await Promise.all([
    taskClient.list(),
    areaClient.list("all"),
    goalClient.list("all"),
    projectClient.list("all"),
  ]);
  return { tasks, areas, goals, projects };
}
