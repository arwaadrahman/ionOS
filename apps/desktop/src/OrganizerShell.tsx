import { useState } from "react";
import { AreasGoalsWorkspace } from "./AreasGoalsWorkspace";
import { ProjectsWorkspace } from "./ProjectsWorkspace";
import { StartupData, loadStartupData } from "./startup";
import { TaskWorkspace } from "./TaskWorkspace";

export function OrganizerShell({ initialData }: { initialData: StartupData }) {
  const [workspace, setWorkspace] = useState<"areas" | "projects" | "tasks">(
    "areas",
  );
  const [tasks, setTasks] = useState(initialData.tasks);
  const [areas, setAreas] = useState(initialData.areas);
  const [goals, setGoals] = useState(initialData.goals);
  const [projects, setProjects] = useState(initialData.projects);

  async function refresh() {
    const data = await loadStartupData();
    setTasks(data.tasks);
    setAreas(data.areas);
    setGoals(data.goals);
    setProjects(data.projects);
  }

  return (
    <main className="app-shell">
      <nav className="workspace-switcher" aria-label="Phase 1B workspaces">
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
