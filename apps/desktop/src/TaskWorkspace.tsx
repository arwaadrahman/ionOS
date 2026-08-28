import { FormEvent, useState } from "react";
import { Task, TaskInput, taskClient } from "./tasks";

const blankInput = (): TaskInput => ({
  title: "",
  details: null,
  importance: null,
  estimated_minutes: null,
  progress_percent: null,
  deadline: { kind: "none" },
  project_id: null,
  goal_id: null,
  completion_evidence: null,
});

export function TaskWorkspace({ initialTasks }: { initialTasks: Task[] }) {
  const [tasks, setTasks] = useState(initialTasks);
  const [trash, setTrash] = useState<Task[]>([]);
  const [input, setInput] = useState<TaskInput>(blankInput);
  const [editing, setEditing] = useState<Task | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!input.title.trim()) return;
    try {
      const result = editing
        ? await taskClient.update(editing, input)
        : await taskClient.create(input);
      setTasks((current) => [
        result,
        ...current.filter((task) => task.id !== result.id),
      ]);
      setEditing(null);
      setInput(blankInput());
      setError(null);
    } catch (reason) {
      setError(
        String(reason) === "conflict"
          ? "Task changed elsewhere. Reload and try again."
          : "Task action unavailable.",
      );
    }
  }

  async function apply(
    task: Task,
    action: "complete" | "reopen" | "trash" | "restore",
  ) {
    try {
      const result = await taskClient[action](task);
      if (action === "trash") {
        setTasks((current) => current.filter((item) => item.id !== task.id));
        setTrash((current) => [result, ...current]);
      } else if (action === "restore") {
        setTrash((current) => current.filter((item) => item.id !== task.id));
        setTasks((current) => [result, ...current]);
      } else {
        setTasks((current) =>
          current.map((item) => (item.id === result.id ? result : item)),
        );
      }
      setError(null);
    } catch {
      setError("Task action unavailable.");
    }
  }

  async function showTrash() {
    try {
      setTrash(await taskClient.listTrash());
    } catch {
      setError("Trash is unavailable.");
    }
  }

  return (
    <section className="task-workspace" aria-label="Tasks">
      <header>
        <p className="eyebrow">ION OS · PHASE 1A</p>
        <h1>Tasks</h1>
      </header>
      <form onSubmit={submit} className="task-form">
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
                importance: (event.target.value ||
                  null) as TaskInput["importance"],
              })
            }
          >
            <option value="">None</option>
            <option value="low">Low</option>
            <option value="normal">Normal</option>
            <option value="high">High</option>
          </select>
        </label>
        <button type="submit">{editing ? "Save task" : "Create task"}</button>
        {editing && (
          <button
            type="button"
            onClick={() => {
              setEditing(null);
              setInput(blankInput());
            }}
          >
            Cancel
          </button>
        )}
      </form>
      {error && <p role="alert">{error}</p>}
      <ul className="task-list">
        {tasks.map((task) => (
          <li key={task.id}>
            <strong>{task.title}</strong>
            <span>{task.state}</span>
            <button
              onClick={() => {
                setEditing(task);
                setInput({
                  ...blankInput(),
                  title: task.title,
                  details: task.details,
                  importance: task.importance,
                  estimated_minutes: task.estimated_minutes,
                  progress_percent: task.progress_percent,
                  deadline: task.deadline,
                });
              }}
            >
              Edit
            </button>
            {task.state === "completed" ? (
              <button onClick={() => apply(task, "reopen")}>Reopen</button>
            ) : (
              <button onClick={() => apply(task, "complete")}>Complete</button>
            )}
            <button onClick={() => apply(task, "trash")}>Trash</button>
          </li>
        ))}
      </ul>
      <button type="button" onClick={showTrash}>
        Show Trash
      </button>
      {trash.length > 0 && (
        <ul className="task-list" aria-label="Trash">
          {trash.map((task) => (
            <li key={task.id}>
              <strong>{task.title}</strong>
              <button onClick={() => apply(task, "restore")}>Restore</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
