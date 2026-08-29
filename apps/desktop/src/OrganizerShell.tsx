import { useCallback, useEffect, useState } from "react";
import { AreasGoalsWorkspace } from "./AreasGoalsWorkspace";
import { HomeNavigationTarget, HomeWorkspace } from "./HomeWorkspace";
import { homeClient } from "./home";
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

type Workspace = "home" | "today" | "areas" | "projects" | "tasks";

export function OrganizerShell({
  initialData,
  todayContextProvider = currentTodayContext,
}: {
  initialData: StartupData;
  todayContextProvider?: typeof currentTodayContext;
}) {
  const [workspace, setWorkspace] = useState<Workspace>("home");
  const [navigationTarget, setNavigationTarget] =
    useState<HomeNavigationTarget | null>(null);
  const [tasks, setTasks] = useState(initialData.tasks);
  const [areas, setAreas] = useState(initialData.areas);
  const [goals, setGoals] = useState(initialData.goals);
  const [projects, setProjects] = useState(initialData.projects);
  const [today, setToday] = useState(initialData.today);
  const [home, setHome] = useState(initialData.home);
  const [todayContext, setTodayContext] = useState(initialData.todayContext);
  const [homeDirty, setHomeDirty] = useState(false);
  const [homeProcessing, setHomeProcessing] = useState(false);
  const [homeStale, setHomeStale] = useState(false);

  const refreshHome = useCallback(
    async (context = todayContextProvider()) => {
      setHomeProcessing(true);
      try {
        const output = await homeClient.get(context);
        setHome(output);
        setHomeDirty(false);
        setHomeStale(false);
      } catch {
        setHomeStale(true);
      } finally {
        setHomeProcessing(false);
      }
    },
    [todayContextProvider],
  );

  const refreshToday = useCallback(async () => {
    const context = todayContextProvider();
    const output = await todayClient.get(context);
    setTodayContext(context);
    setToday(output);
    setHomeDirty(true);
  }, [todayContextProvider]);

  useEffect(() => {
    if (workspace === "home" && homeDirty) void refreshHome();
  }, [homeDirty, refreshHome, workspace]);

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
          // Confirmed canonical state remains visible until a later recheck succeeds.
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
    setHome(data.home);
    setTodayContext(data.todayContext);
    setHomeDirty(false);
    setHomeStale(false);
  }

  function markHomeDirty() {
    setHomeDirty(true);
  }

  function navigate(target: HomeNavigationTarget) {
    setNavigationTarget(target);
    setWorkspace(target.workspace);
  }

  function chooseWorkspace(next: Workspace) {
    if (next === "home" && workspace !== "home") setHomeDirty(true);
    setNavigationTarget(null);
    setWorkspace(next);
  }

  return (
    <main className="app-shell">
      <nav className="workspace-switcher" aria-label="Ion workspaces">
        {(["home", "today", "areas", "projects", "tasks"] as const).map(
          (item) => (
            <button
              key={item}
              className={workspace === item ? "is-active" : ""}
              onClick={() => chooseWorkspace(item)}
            >
              {item === "areas"
                ? "Areas & Goals"
                : item.charAt(0).toUpperCase() + item.slice(1)}
            </button>
          ),
        )}
      </nav>
      {workspace === "home" ? (
        <HomeWorkspace
          home={home}
          processing={homeProcessing}
          stale={homeStale}
          onRetry={() => void refreshHome()}
          onNavigate={navigate}
        />
      ) : null}
      {workspace === "today" ? (
        <TodayWorkspace
          today={today}
          tasks={tasks}
          onToday={(output) => {
            setToday(output);
            markHomeDirty();
          }}
          onTaskConfirmed={(confirmed) => {
            setTasks((current) =>
              current.map((task) =>
                task.id === confirmed.id ? confirmed : task,
              ),
            );
            markHomeDirty();
          }}
          onDayChanged={refreshToday}
        />
      ) : null}
      {workspace === "areas" ? (
        <AreasGoalsWorkspace
          areas={areas}
          goals={goals}
          tasks={tasks}
          onAreas={(items) => {
            setAreas(items);
            markHomeDirty();
          }}
          onGoals={(items) => {
            setGoals(items);
            markHomeDirty();
          }}
          onTasks={(items) => {
            setTasks(items);
            markHomeDirty();
          }}
          onRefresh={refresh}
          navigationTarget={
            navigationTarget?.workspace === "areas"
              ? { type: navigationTarget.entityType, id: navigationTarget.id }
              : null
          }
        />
      ) : null}
      {workspace === "projects" ? (
        <ProjectsWorkspace
          projects={projects}
          goals={goals}
          tasks={tasks}
          onProjects={(items) => {
            setProjects(items);
            markHomeDirty();
          }}
          onTasks={(items) => {
            setTasks(items);
            markHomeDirty();
          }}
          onRefresh={refresh}
          navigationTarget={
            navigationTarget?.workspace === "projects"
              ? navigationTarget.id
              : null
          }
        />
      ) : null}
      {workspace === "tasks" ? (
        <TaskWorkspace
          initialTasks={tasks}
          goals={goals}
          projects={projects}
          onTasksChange={(items) => {
            setTasks(items);
            markHomeDirty();
          }}
          navigationTaskId={
            navigationTarget?.workspace === "tasks" ? navigationTarget.id : null
          }
        />
      ) : null}
    </main>
  );
}
