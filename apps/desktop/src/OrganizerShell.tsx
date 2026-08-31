import { useCallback, useEffect, useMemo, useState } from "react";
import { listen, UnlistenFn } from "@tauri-apps/api/event";
import { AreasGoalsWorkspace } from "./AreasGoalsWorkspace";
import { CommandPalette } from "./CommandPalette";
import { CalendarWorkspace } from "./CalendarWorkspace";
import { googleCalendarClient } from "./calendar";
import { HomeWorkspace } from "./HomeWorkspace";
import { CommandItem, buildCommandItems } from "./commandSearch";
import { homeClient } from "./home";
import {
  NavigationTarget,
  Workspace,
  workspaceLabel,
  workspaces,
} from "./navigation";
import { ProjectsWorkspace } from "./ProjectsWorkspace";
import { RecoveryWorkspace } from "./RecoveryWorkspace";
import { StartupData, loadStartupData } from "./startup";
import { TaskWorkspace } from "./TaskWorkspace";
import { TodayWorkspace } from "./TodayWorkspace";
import { Task } from "./tasks";
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
  const [workspace, setWorkspace] = useState<Workspace>("home");
  const [navigationTarget, setNavigationTarget] =
    useState<NavigationTarget | null>(null);
  const [commandOpen, setCommandOpen] = useState(false);
  const [tasks, setTasks] = useState(initialData.tasks);
  const [areas, setAreas] = useState(initialData.areas);
  const [goals, setGoals] = useState(initialData.goals);
  const [projects, setProjects] = useState(initialData.projects);
  const [today, setToday] = useState(initialData.today);
  const [home, setHome] = useState(initialData.home);
  const [calendar, setCalendar] = useState(initialData.calendar);
  const [todayContext, setTodayContext] = useState(initialData.todayContext);
  const [homeDirty, setHomeDirty] = useState(false);
  const [homeProcessing, setHomeProcessing] = useState(false);
  const [homeStale, setHomeStale] = useState(false);
  const connectedAccountKey = useMemo(
    () =>
      calendar.accounts
        .filter((account) => account.auth_state === "connected")
        .map((account) => account.id)
        .sort()
        .join(","),
    [calendar.accounts],
  );
  const commandItems = useMemo(() => buildCommandItems(home), [home]);

  useEffect(() => {
    let disposed = false;
    let unlisteners: UnlistenFn[] = [];
    void Promise.all([
      listen<string>("ion:navigate", ({ payload }) => {
        if (payload !== "home" && payload !== "today") return;
        setNavigationTarget(null);
        setWorkspace(payload);
        if (payload === "home") setHomeDirty(true);
      }),
      listen<Task>("ion:task-created", ({ payload }) => {
        setTasks((current) => {
          const withoutDuplicate = current.filter(
            (task) => task.id !== payload.id,
          );
          return [...withoutDuplicate, payload];
        });
        setHomeDirty(true);
      }),
    ])
      .then((registered) => {
        if (disposed) registered.forEach((unlisten) => unlisten());
        else unlisteners = registered;
      })
      .catch(() => undefined);
    return () => {
      disposed = true;
      unlisteners.forEach((unlisten) => unlisten());
    };
  }, []);

  useEffect(() => {
    if (!connectedAccountKey) return;
    let disposed = false;
    let lastAttempt = 0;
    const sync = async () => {
      const now = Date.now();
      if (now - lastAttempt < 5 * 60 * 1000) return;
      lastAttempt = now;
      try {
        const output = await googleCalendarClient.sync();
        if (!disposed) setCalendar(output);
      } catch {
        // Cached canonical blocks remain visible; persisted sync state reports failure.
      }
    };
    const foreground = () => {
      if (document.visibilityState === "visible") void sync();
    };
    void sync();
    window.addEventListener("focus", foreground);
    document.addEventListener("visibilitychange", foreground);
    return () => {
      disposed = true;
      window.removeEventListener("focus", foreground);
      document.removeEventListener("visibilitychange", foreground);
    };
  }, [connectedAccountKey]);

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
    if (commandOpen) void refreshHome();
  }, [commandOpen, refreshHome]);

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
    setCalendar(data.calendar);
    setTodayContext(data.todayContext);
    setHomeDirty(false);
    setHomeStale(false);
  }

  function markHomeDirty() {
    setHomeDirty(true);
  }

  function navigate(target: NavigationTarget) {
    setNavigationTarget(target);
    setWorkspace(target.workspace);
  }

  function chooseWorkspace(next: Workspace) {
    if (next === "home" && workspace !== "home") setHomeDirty(true);
    setNavigationTarget(null);
    setWorkspace(next);
  }

  function executeCommand(item: CommandItem) {
    if (item.action.type === "workspace") {
      chooseWorkspace(item.action.workspace);
      return;
    }
    if (item.action.type === "recovery") {
      chooseWorkspace("recovery");
      return;
    }
    navigate(item.action.target);
  }

  return (
    <main
      className={`app-shell ${workspace === "calendar" ? "is-calendar-active" : ""}`}
    >
      <nav className="workspace-switcher" aria-label="Ion workspaces">
        {workspaces.map((item) => (
          <button
            key={item}
            className={workspace === item ? "is-active" : ""}
            onClick={() => chooseWorkspace(item)}
          >
            {workspaceLabel(item)}
          </button>
        ))}
        <button
          className="command-trigger"
          type="button"
          aria-keyshortcuts="Meta+K"
          onClick={() => setCommandOpen(true)}
        >
          Search <kbd>⌘K</kbd>
        </button>
      </nav>
      <CommandPalette
        items={commandItems}
        open={commandOpen}
        stale={homeStale}
        onOpenChange={setCommandOpen}
        onExecute={executeCommand}
      />
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
          calendar={calendar}
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
      {workspace === "calendar" ? (
        <CalendarWorkspace status={calendar} onStatus={setCalendar} />
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
      {workspace === "recovery" ? (
        <RecoveryWorkspace
          onRestored={async () => {
            await refresh();
            markHomeDirty();
          }}
        />
      ) : null}
    </main>
  );
}
