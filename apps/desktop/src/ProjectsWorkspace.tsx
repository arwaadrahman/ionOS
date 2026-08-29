import { FormEvent, useEffect, useState } from "react";
import { MilestoneList } from "./MilestoneList";
import {
  Goal,
  ProductError,
  Project,
  ProjectDetail,
  ProjectMilestone,
  ProjectState,
  asProductError,
  projectClient,
  projectMilestoneClient,
} from "./organizer";
import { ProductErrorNotice } from "./ProductErrorNotice";
import { Task, blankTaskInput, taskClient } from "./tasks";

type Props = {
  projects: Project[];
  goals: Goal[];
  tasks: Task[];
  onProjects(projects: Project[]): void;
  onTasks(tasks: Task[]): void;
  onRefresh(): Promise<void>;
  navigationTarget?: string | null;
};

const groups: { state: ProjectState; label: string }[] = [
  { state: "idea", label: "Ideas" },
  { state: "exploring", label: "Exploring" },
  { state: "planned", label: "Planned" },
  { state: "active", label: "Active" },
  { state: "paused", label: "Paused" },
  { state: "completed", label: "Completed" },
  { state: "archived", label: "Archived" },
  { state: "abandoned", label: "Abandoned" },
];
const replace = <T extends { id: string }>(items: T[], item: T) => [
  item,
  ...items.filter((candidate) => candidate.id !== item.id),
];

export function ProjectsWorkspace({
  projects,
  goals,
  tasks,
  onProjects,
  onTasks,
  onRefresh,
  navigationTarget,
}: Props) {
  const [selectedId, setSelectedId] = useState(
    projects.find((project) => !project.trashed_at)?.id ??
      projects[0]?.id ??
      null,
  );
  const selected =
    projects.find((project) => project.id === selectedId) ?? null;
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [trash, setTrash] = useState<ProjectMilestone[]>([]);
  const [error, setError] = useState<ProductError | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [contextTask, setContextTask] = useState("");
  const selectedProjectId = selected?.id ?? null;

  useEffect(() => {
    if (navigationTarget) setSelectedId(navigationTarget);
  }, [navigationTarget]);

  useEffect(() => {
    if (!selectedProjectId) {
      setDetail(null);
      return;
    }
    let active = true;
    projectClient
      .get({ id: selectedProjectId })
      .then((result) => {
        if (active) setDetail(result);
      })
      .catch((reason) => {
        if (active) setError(asProductError(reason));
      });
    return () => {
      active = false;
    };
  }, [selectedProjectId]);

  async function run<T>(
    operation: () => Promise<T>,
    accept: (result: T) => void,
  ) {
    try {
      accept(await operation());
      setError(null);
    } catch (reason) {
      const productError = asProductError(reason);
      setError(productError);
      if (productError.code === "revision_conflict") await onRefresh();
    }
  }

  function acceptProject(project: Project) {
    onProjects(replace(projects, project));
    setDetail((current) =>
      current?.project.id === project.id ? { ...current, project } : current,
    );
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!newTitle.trim()) return;
    await run(
      () =>
        projectClient.create({
          title: newTitle,
          description: null,
          state: "idea",
          goal_id: null,
        }),
      (project) => {
        onProjects(replace(projects, project));
        setSelectedId(project.id);
        setNewTitle("");
      },
    );
  }

  return (
    <section className="workspace">
      <header>
        <p className="eyebrow">ION OS · PHASE 1B</p>
        <h1>Projects</h1>
        <p className="summary">
          Status, next actions, Milestones, and attributable history.
        </p>
      </header>
      <div className="split-workspace">
        <aside className="navigator">
          <form className="quick-create" onSubmit={create}>
            <input
              aria-label="New Project title"
              value={newTitle}
              placeholder="New Project"
              onChange={(event) => setNewTitle(event.target.value)}
            />
            <button>Create Project</button>
          </form>
          {groups.map((group) => (
            <div className="tree-group" key={group.state}>
              <h3>{group.label}</h3>
              {projects
                .filter(
                  (project) =>
                    !project.trashed_at && project.state === group.state,
                )
                .map((project) => (
                  <button
                    key={project.id}
                    className={
                      selectedId === project.id
                        ? "tree-item is-selected"
                        : "tree-item"
                    }
                    onClick={() => setSelectedId(project.id)}
                  >
                    {project.title}
                    {project.goal_id &&
                      goals.find((goal) => goal.id === project.goal_id)
                        ?.archived_at && (
                        <span className="badge">Archived Goal</span>
                      )}
                  </button>
                ))}
            </div>
          ))}
          <div className="tree-group">
            <h3>Trash</h3>
            {projects
              .filter((project) => project.trashed_at)
              .map((project) => (
                <button
                  key={project.id}
                  className="tree-item"
                  onClick={() => setSelectedId(project.id)}
                >
                  {project.title}
                </button>
              ))}
          </div>
        </aside>
        <main className="detail-pane">
          <ProductErrorNotice error={error} />
          {selected && detail && (
            <ProjectPanel
              key={selected.id}
              detail={detail}
              goals={goals}
              tasks={tasks}
              milestoneTrash={trash}
              onProject={acceptProject}
              onDetail={setDetail}
              onTrash={setTrash}
              onTasks={onTasks}
              contextTask={contextTask}
              setContextTask={setContextTask}
              onError={setError}
              onRefresh={onRefresh}
            />
          )}
          {!selected && (
            <p className="empty-state">Create a Project to begin.</p>
          )}
        </main>
      </div>
    </section>
  );
}

function ProjectPanel({
  detail,
  goals,
  tasks,
  milestoneTrash,
  onProject,
  onDetail,
  onTrash,
  onTasks,
  contextTask,
  setContextTask,
  onError,
  onRefresh,
}: {
  detail: ProjectDetail;
  goals: Goal[];
  tasks: Task[];
  milestoneTrash: ProjectMilestone[];
  onProject(project: Project): void;
  onDetail(detail: ProjectDetail): void;
  onTrash(items: ProjectMilestone[]): void;
  onTasks(tasks: Task[]): void;
  contextTask: string;
  setContextTask(value: string): void;
  onError(error: ProductError | null): void;
  onRefresh(): Promise<void>;
}) {
  const project = detail.project;
  const [title, setTitle] = useState(project.title);
  const [description, setDescription] = useState(project.description ?? "");
  async function act<T>(
    operation: () => Promise<T>,
    accept: (result: T) => void | Promise<void>,
  ) {
    try {
      await accept(await operation());
      onError(null);
    } catch (reason) {
      const error = asProductError(reason);
      onError(error);
      if (error.code === "revision_conflict") await onRefresh();
    }
  }
  const updateMilestone = (item: ProjectMilestone) =>
    onDetail({
      ...detail,
      milestones: replace(detail.milestones, item).sort(
        (a, b) => a.position - b.position,
      ),
      current_milestone:
        item.id === detail.current_milestone?.id
          ? item
          : detail.current_milestone,
    });
  const eligibleGoals = goals.filter(
    (goal) => !goal.archived_at && !goal.trashed_at,
  );
  const workingStates: Exclude<ProjectState, "archived">[] = [
    "idea",
    "exploring",
    "planned",
    "active",
    "paused",
    "completed",
    "abandoned",
  ];
  return (
    <article>
      <p className="eyebrow">Project · {project.state}</p>
      <h2>{project.title}</h2>
      {project.goal_id &&
        goals.find((goal) => goal.id === project.goal_id)?.archived_at && (
          <p className="context-note">
            Parent Goal is archived. Existing context is retained.
          </p>
        )}
      <div className="summary-grid">
        <span>
          <strong>
            {detail.summary.milestone_achieved}/{detail.summary.milestone_total}
          </strong>{" "}
          applicable Milestones
        </span>
        <span>
          <strong>{detail.summary.task_total}</strong> open Tasks
        </span>
        <span>
          <strong>{detail.summary.task_completed}</strong> completed Tasks
        </span>
      </div>
      {detail.current_milestone && (
        <p className="context-note">
          Current Milestone: <strong>{detail.current_milestone.title}</strong>
        </p>
      )}
      {project.trashed_at ? (
        <button
          onClick={() =>
            void act(() => projectClient.restore(project), onProject)
          }
        >
          Restore Project
        </button>
      ) : (
        <>
          <form
            className="entity-form"
            onSubmit={(event) => {
              event.preventDefault();
              void act(
                () =>
                  projectClient.update(project, {
                    title,
                    description: description || null,
                  }),
                onProject,
              );
            }}
          >
            <label>
              Title
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
            </label>
            <label>
              Description
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>
            {project.state !== "archived" && (
              <label>
                State
                <select
                  value={project.state}
                  onChange={(event) =>
                    void act(
                      () =>
                        projectClient.setState(
                          project,
                          event.target.value as Exclude<
                            ProjectState,
                            "archived"
                          >,
                        ),
                      onProject,
                    )
                  }
                >
                  {workingStates.map((state) => (
                    <option key={state}>{state}</option>
                  ))}
                </select>
              </label>
            )}
            <label>
              Goal
              <select
                value={project.goal_id ?? ""}
                onChange={(event) =>
                  void act(
                    () =>
                      projectClient.setGoal(
                        project,
                        event.target.value || null,
                      ),
                    onProject,
                  )
                }
              >
                <option value="">Unassigned</option>
                {eligibleGoals.map((goal) => (
                  <option key={goal.id} value={goal.id}>
                    {goal.title}
                  </option>
                ))}
              </select>
            </label>
            <button>Save Project</button>
          </form>
          <div className="action-bar">
            {project.state === "archived" ? (
              <button
                onClick={() =>
                  void act(() => projectClient.unarchive(project), onProject)
                }
              >
                Unarchive to Completed
              </button>
            ) : project.state === "completed" ? (
              <button
                onClick={() =>
                  void act(() => projectClient.archive(project), onProject)
                }
              >
                Archive
              </button>
            ) : (
              <span className="context-note">
                Complete this Project before archiving.
              </span>
            )}
            <button
              className="danger-button"
              onClick={() =>
                void act(() => projectClient.trash(project), onProject)
              }
            >
              Move Project to Trash
            </button>
          </div>
        </>
      )}
      <MilestoneList
        label="Project Milestones"
        items={detail.milestones}
        trashItems={milestoneTrash}
        currentId={detail.current_milestone?.id}
        onCreate={(input) =>
          act(
            () => projectMilestoneClient.create(project, input),
            updateMilestone,
          )
        }
        onUpdate={(item, input) =>
          act(() => projectMilestoneClient.update(item, input), updateMilestone)
        }
        onState={(item, state) =>
          act(
            () => projectMilestoneClient.setState(item, state),
            async () => onDetail(await projectClient.get(project)),
          )
        }
        onReorder={(items) =>
          act(
            () => projectMilestoneClient.reorder(project, items),
            async () => onDetail(await projectClient.get(project)),
          )
        }
        onTrash={(item) =>
          act(
            () => projectMilestoneClient.trash(item),
            async () => onDetail(await projectClient.get(project)),
          )
        }
        onRestore={(item) =>
          act(
            () => projectMilestoneClient.restore(item),
            async () => {
              onTrash(
                milestoneTrash.filter((candidate) => candidate.id !== item.id),
              );
              onDetail(await projectClient.get(project));
            },
          )
        }
        onLoadTrash={() =>
          act(() => projectMilestoneClient.list(project, true), onTrash)
        }
        onError={onError}
      />
      <section className="detail-section">
        <h3>Next actions</h3>
        <ul className="read-list">
          {detail.next_actions.map((task) => (
            <li key={task.id}>
              {task.title} <span className="badge">{task.state}</span>
            </li>
          ))}
        </ul>
      </section>
      <form
        className="quick-create"
        onSubmit={(event) => {
          event.preventDefault();
          if (!contextTask.trim()) return;
          void act(
            () =>
              taskClient.create({
                ...blankTaskInput(),
                title: contextTask,
                project_id: project.id,
                goal_id: null,
              }),
            (task) => {
              onTasks(replace(tasks, task));
              onDetail({
                ...detail,
                tasks: replace(detail.tasks, task),
                next_actions: replace(detail.next_actions, task),
              });
              setContextTask("");
            },
          );
        }}
      >
        <input
          aria-label="New Project Task"
          value={contextTask}
          placeholder="New Task for this Project"
          onChange={(event) => setContextTask(event.target.value)}
        />
        <button>Create Task</button>
      </form>
      <section className="detail-section">
        <h3>Recent activity</h3>
        <ul className="activity-list">
          {detail.recent_activity.map((event) => (
            <li key={event.event_id}>
              <span>{event.action.replace("_", " ")}</span>
              <time>{new Date(event.occurred_at).toLocaleString()}</time>
            </li>
          ))}
        </ul>
      </section>
    </article>
  );
}
