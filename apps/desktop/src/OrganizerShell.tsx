import { useCallback, useEffect, useState } from "react";
import { AreasGoalsWorkspace } from "./AreasGoalsWorkspace";
import { ProjectsWorkspace } from "./ProjectsWorkspace";
import { StartupData, loadStartupData } from "./startup";
import { TaskWorkspace } from "./TaskWorkspace";
import { TodayWorkspace } from "./TodayWorkspace";
import {
  currentTodayContext,
  millisecondsUntilNextMidnight,
  sameTodayContext,
  todayClient,
} from "./today";

export function OrganizerShell({
  initialData,
  todayContextProvider = currentTodayContext,
}: {
  initialData: StartupData;
  todayContextProvider?: typeof currentTodayContext;
}) {
  const [workspace, setWorkspace] = useState<
    "today" | "areas" | "projects" | "tasks"
  >("today");
  const [tasks, setTasks] = useState(initialData.tasks);
  const [areas, setAreas] = useState(initialData.areas);
  const [goals, setGoals] = useState(initialData.goals);
  const [projects, setProjects] = useState(initialData.projects);
  const [today, setToday] = useState(initialData.today);
  const [todayContext, setTodayContext] = useState(initialData.todayContext);

  const refreshToday = useCallback(async () => {
    const context = todayContextProvider();
    const output = await todayClient.get(context);
    setTodayContext(context);
    setToday(output);
  }, [todayContextProvider]);

  useEffect(() => {
    let timeout = window.setTimeout(() => undefined, 0);
    let disposed = false;
    const schedule = () => {
      window.clearTimeout(timeout);
      timeout = window.setTimeout(
        () => void check(),
        millisecondsUntilNextMidnight(),
      );
    };
    const check = async () => {
      const next = todayContextProvider();
      if (!sameTodayContext(todayContext, next)) {
        try {
          await refreshToday();
        } catch {
          // The visible canonical state remains intact until a later recheck succeeds.
        }
      }
      if (!disposed) schedule();
    };
    const focus = () => void check();
    const visible = () => {
      if (document.visibilityState === "visible") void check();
    };
    window.addEventListener("focus", focus);
    document.addEventListener("visibilitychange", visible);
    schedule();
    return () => {
      disposed = true;
      window.clearTimeout(timeout);
      window.removeEventListener("focus", focus);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [refreshToday, todayContext, todayContextProvider]);

  async function refresh() {
    const data = await loadStartupData();
    setTasks(data.tasks);
    setAreas(data.areas);
    setGoals(data.goals);
    setProjects(data.projects);
    setToday(data.today);
    setTodayContext(data.todayContext);
  }

  return (
    <main className="app-shell">
      <nav className="workspace-switcher" aria-label="Phase 1B workspaces">
        <button
          className={workspace === "today" ? "is-active" : ""}
          onClick={() => setWorkspace("today")}
        >
          Today
        </button>
        <button
          className={workspace === "areas" ? "is-active" : ""}
          onClick={() => setWorkspace("areas")}
        >
          Areas &amp; Goals
        </button>
        <button
          className={workspace === "projects" ? "is-active" : ""}
          onClick={() => setWorkspace("projects")}
        >
          Projects
        </button>
        <button
          className={workspace === "tasks" ? "is-active" : ""}
          onClick={() => setWorkspace("tasks")}
        >
          Tasks
        </button>
      </nav>
      {workspace === "today" && (
        <TodayWorkspace
          today={today}
          tasks={tasks}
          onToday={setToday}
          onTaskConfirmed={(confirmed) =>
            setTasks((current) =>
              current.map((task) =>
                task.id === confirmed.id ? confirmed : task,
              ),
            )
          }
          onDayChanged={refreshToday}
        />
      )}
      {workspace === "areas" && (
        <AreasGoalsWorkspace
          areas={areas}
          goals={goals}
          tasks={tasks}
          onAreas={setAreas}
          onGoals={setGoals}
          onTasks={setTasks}
          onRefresh={refresh}
        />
      )}
      {workspace === "projects" && (
        <ProjectsWorkspace
          projects={projects}
          goals={goals}
          tasks={tasks}
          onProjects={setProjects}
          onTasks={setTasks}
          onRefresh={refresh}
        />
      )}
      {workspace === "tasks" && (
        <TaskWorkspace
          initialTasks={tasks}
          goals={goals}
          projects={projects}
          onTasksChange={setTasks}
        />
      )}
    </main>
  );
}
