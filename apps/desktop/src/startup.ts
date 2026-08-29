import { HomeOutput, homeClient } from "./home";
import {
  CalendarStatus,
  emptyCalendarStatus,
  googleCalendarClient,
} from "./calendar";
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
  calendar: CalendarStatus;
  todayContext: TodayContext;
};

export async function loadStartupData(): Promise<StartupData> {
  const todayContext = currentTodayContext();
  const calendarStatus = googleCalendarClient
    .status()
    .catch(() => emptyCalendarStatus());
  const [tasks, areas, goals, projects, today, home, calendar] =
    await Promise.all([
      taskClient.list(),
      areaClient.list("all"),
      goalClient.list("all"),
      projectClient.list("all"),
      todayClient.get(todayContext),
      homeClient.get(todayContext),
      calendarStatus,
    ]);
  return {
    tasks,
    areas,
    goals,
    projects,
    today,
    home,
    calendar,
    todayContext,
  };
}
