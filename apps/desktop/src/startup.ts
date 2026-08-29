import { HomeOutput, homeClient } from "./home";
import {
  Area,
  Goal,
  Project,
  areaClient,
  goalClient,
  projectClient,
} from "./organizer";
import { Task, taskClient } from "./tasks";
import {
  TodayContext,
  TodayOutput,
  currentTodayContext,
  todayClient,
} from "./today";

export type StartupData = {
  tasks: Task[];
  areas: Area[];
  goals: Goal[];
  projects: Project[];
  today: TodayOutput;
  home: HomeOutput;
  todayContext: TodayContext;
};

export async function loadStartupData(): Promise<StartupData> {
  const todayContext = currentTodayContext();
  const [tasks, areas, goals, projects, today, home] = await Promise.all([
    taskClient.list(),
    areaClient.list("all"),
    goalClient.list("all"),
    projectClient.list("all"),
    todayClient.get(todayContext),
    homeClient.get(todayContext),
  ]);
  return { tasks, areas, goals, projects, today, home, todayContext };
}
