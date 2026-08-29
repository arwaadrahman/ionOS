import { FormEvent, useEffect, useRef, useState } from "react";
import { Goal, Project, asProductError } from "./organizer";
import { ProductErrorNotice } from "./ProductErrorNotice";
import {
  Task,
  TaskCreateInput,
  TaskEditInput,
  blankTaskInput,
  taskClient,
} from "./tasks";

type Props = {
  initialTasks: Task[];
  goals?: Goal[];
  projects?: Project[];
  onTasksChange?(tasks: Task[]): void;
  navigationTaskId?: string | null;
};

export function TaskWorkspace({
  initialTasks,
  goals = [],
  projects = [],
  onTasksChange,
  navigationTaskId,
}: Props) {
  const [tasks, setTasks] = useState(initialTasks);
  const [trash, setTrash] = useState<Task[]>([]);
  const [input, setInput] = useState<TaskCreateInput>(blankTaskInput);
  const [editing, setEditing] = useState<Task | null>(null);
  const [error, setError] = useState<ReturnType<typeof asProductError> | null>(
    null,
  );
  const submitInFlight = useRef(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setTasks(initialTasks);
  }, [initialTasks]);

  useEffect(() => {
    if (!navigationTaskId) return;
    document.getElementById(`task-${navigationTaskId}`)?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  }, [navigationTaskId]);

  function commit(next: Task[]) {
    setTasks(next);
    onTasksChange?.(next);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!input.title.trim() || submitInFlight.current) return;
    submitInFlight.current = true;
    setSubmitting(true);
    try {
      const editInput: TaskEditInput = {
        title: input.title,
        details: input.details,
        importance: input.importance,
        estimated_minutes: input.estimated_minutes,
        progress_percent: input.progress_percent,
        deadline: input.deadline,
        completion_evidence: input.completion_evidence,
      };
      const result = editing
        ? await taskClient.update(editing, editInput)
        : await taskClient.create(input);
      commit([result, ...tasks.filter((task) => task.id !== result.id)]);
      setEditing(null);
      setInput(blankTaskInput());
      setError(null);
    } catch (reason) {
      setError(asProductError(reason));
    } finally {
      submitInFlight.current = false;
      setSubmitting(false);
    }
  }

  async function apply(
    task: Task,
    action: "complete" | "reopen" | "trash" | "restore",
  ) {
    try {
      const result = await taskClient[action](task);
      if (action === "trash") {
        commit(tasks.filter((item) => item.id !== task.id));
        setTrash((current) => [result, ...current]);
      } else if (action === "restore") {
        setTrash((current) => current.filter((item) => item.id !== task.id));
        commit([result, ...tasks]);
      } else
        commit(tasks.map((item) => (item.id === result.id ? result : item)));
      setError(null);
    } catch (reason) {
      setError(asProductError(reason));
    }
  }

  async function relationships(
    task: Task,
    goal_id: string | null,
    project_id: string | null,
  ) {
    try {
      const result = await taskClient.setRelationships(task, {
        goal_id,
        project_id,
      });
      commit(tasks.map((item) => (item.id === result.id ? result : item)));
      setError(null);
    } catch (reason) {
      setError(asProductError(reason));
    }
  }

  const assignableGoals = goals.filter(
    (goal) => !goal.archived_at && !goal.trashed_at,
  );
  const assignableProjects = projects.filter(
    (project) => project.state !== "archived" && !project.trashed_at,
  );

  return (
    <section className="workspace" aria-label="Tasks">
      <header>
        <p className="eyebrow">ION OS · PHASE 1B</p>
        <h1>Tasks</h1>
        <p className="summary">
          Canonical work, with explicit Goal and Project context.
        </p>
      </header>
      <form onSubmit={submit} className="entity-form">
        <label>
          Title
          <input
            value={input.title}
            onChange={(event) =>
              setInput({ ...input, title: event.target.value })
            }
          />
        </label>
        <label>
          Details
          <textarea
            value={input.details ?? ""}
            onChange={(event) =>
              setInput({ ...input, details: event.target.value || null })
            }
          />
        </label>
        <label>
          Importance
          <select
            value={input.importance ?? ""}
            onChange={(event) =>
              setInput({
                ...input,
                importance: (event.target.value || null) as Task["importance"],
              })
            }
          >
            <option value="">None</option>
            <option value="low">Low</option>
            <option value="normal">Normal</option>
            <option value="high">High</option>
          </select>
        </label>
        {!editing && (
          <>
            <label>
              Goal
              <select
                value={input.goal_id ?? ""}
                onChange={(event) =>
                  setInput({ ...input, goal_id: event.target.value || null })
                }
              >
                <option value="">Unassigned</option>
                {assignableGoals.map((goal) => (
                  <option key={goal.id} value={goal.id}>
                    {goal.title}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Project
              <select
                value={input.project_id ?? ""}
                onChange={(event) =>
                  setInput({ ...input, project_id: event.target.value || null })
                }
              >
                <option value="">Unassigned</option>
                {assignableProjects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.title}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
        <div className="form-actions">
          <button disabled={submitting} type="submit">
            {editing ? "Save task" : "Create task"}
          </button>
          {editing && (
            <button
              type="button"
              onClick={() => {
                setEditing(null);
                setInput(blankTaskInput());
              }}
            >
              Cancel
            </button>
          )}
        </div>
      </form>
      <ProductErrorNotice error={error} />
      <ul className="entity-list task-list">
        {tasks.map((task) => (
          <TaskRow
            key={task.id}
            task={task}
            highlighted={task.id === navigationTaskId}
            goals={goals}
            projects={projects}
            assignableGoals={assignableGoals}
            assignableProjects={assignableProjects}
            onEdit={() => {
              setEditing(task);
              setInput({
                ...blankTaskInput(),
                title: task.title,
                details: task.details,
                importance: task.importance,
                estimated_minutes: task.estimated_minutes,
                progress_percent: task.progress_percent,
                deadline: task.deadline,
                completion_evidence: task.completion_evidence,
                goal_id: task.goal_id,
                project_id: task.project_id,
              });
            }}
            onApply={(action) => void apply(task, action)}
            onRelationships={(goal, project) =>
              void relationships(task, goal, project)
            }
          />
        ))}
      </ul>
      <button
        type="button"
        className="quiet-button"
        onClick={() =>
          void taskClient
            .listTrash()
            .then(setTrash)
            .catch((reason) => setError(asProductError(reason)))
        }
      >
        Show Task Trash
      </button>
      {trash.length > 0 && (
        <ul className="entity-list" aria-label="Trash">
          {trash.map((task) => (
            <li key={task.id}>
              <strong>{task.title}</strong>
              <button onClick={() => void apply(task, "restore")}>
                Restore
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function TaskRow({
  task,
  highlighted,
  goals,
  projects,
  assignableGoals,
  assignableProjects,
  onEdit,
  onApply,
  onRelationships,
}: {
  task: Task;
  highlighted: boolean;
  goals: Goal[];
  projects: Project[];
  assignableGoals: Goal[];
  assignableProjects: Project[];
  onEdit(): void;
  onApply(action: "complete" | "reopen" | "trash"): void;
  onRelationships(goal: string | null, project: string | null): void;
}) {
  const [goalId, setGoalId] = useState(task.goal_id ?? "");
  const [projectId, setProjectId] = useState(task.project_id ?? "");
  useEffect(() => {
    setGoalId(task.goal_id ?? "");
    setProjectId(task.project_id ?? "");
  }, [task.goal_id, task.project_id]);
  const linkedGoal = goals.find((goal) => goal.id === task.goal_id);
  const linkedProject = projects.find(
    (project) => project.id === task.project_id,
  );
  return (
    <li
      id={`task-${task.id}`}
      className={highlighted ? "is-home-target" : undefined}
    >
      <div className="entity-copy">
        <strong>{task.title}</strong>
        <small>{task.state.replace("_", " ")}</small>
        {linkedGoal?.archived_at && (
          <span className="badge">Archived Goal: {linkedGoal.title}</span>
        )}
        {linkedProject?.state === "archived" && (
          <span className="badge">Archived Project: {linkedProject.title}</span>
        )}
      </div>
      <div className="relationship-controls">
        <select
          aria-label={`${task.title} Goal`}
          value={goalId}
          onChange={(event) => setGoalId(event.target.value)}
        >
          <option value="">No Goal</option>
          {assignableGoals.map((goal) => (
            <option key={goal.id} value={goal.id}>
              {goal.title}
            </option>
          ))}
          {linkedGoal &&
            !assignableGoals.some((goal) => goal.id === linkedGoal.id) && (
              <option value={linkedGoal.id}>
                {linkedGoal.title} (archived)
              </option>
            )}
        </select>
        <select
          aria-label={`${task.title} Project`}
          value={projectId}
          onChange={(event) => setProjectId(event.target.value)}
        >
          <option value="">No Project</option>
          {assignableProjects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.title}
            </option>
          ))}
          {linkedProject &&
            !assignableProjects.some(
              (project) => project.id === linkedProject.id,
            ) && (
              <option value={linkedProject.id}>
                {linkedProject.title} (archived)
              </option>
            )}
        </select>
        <button
          onClick={() => onRelationships(goalId || null, projectId || null)}
        >
          Save relationships
        </button>
      </div>
      <div className="row-actions">
        <button onClick={onEdit}>Edit</button>
        {task.state === "completed" ? (
          <button onClick={() => onApply("reopen")}>Reopen</button>
        ) : (
          <button onClick={() => onApply("complete")}>Complete</button>
        )}
        <button onClick={() => onApply("trash")}>Trash</button>
      </div>
    </li>
  );
}
