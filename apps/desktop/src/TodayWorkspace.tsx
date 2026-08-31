import { ReactNode, useState } from "react";
import { CalendarStatus } from "./calendar";
import { asProductError, ProductError } from "./organizer";
import { ProductErrorNotice } from "./ProductErrorNotice";
import { Task, taskClient } from "./tasks";
import {
  applyConfirmedTask,
  currentTodayContext,
  DayPlan,
  TodayContext,
  TodayOutput,
  TodayPlanItem,
  TodayRole,
  TodayTask,
  sameTodayContext,
  todayClient,
} from "./today";
import { TodaySchedule } from "./TodaySchedule";

type Props = {
  today: TodayOutput;
  tasks: Task[];
  calendar: CalendarStatus;
  onToday(today: TodayOutput): void;
  onTaskConfirmed(task: Task): void;
  onDayChanged(): Promise<void>;
};

const roleLabels: Record<TodayRole, string> = {
  priority: "Priorities",
  planned: "Planned",
  backup: "Backups",
};

export function TodayWorkspace({
  today,
  tasks,
  calendar,
  onToday,
  onTaskConfirmed,
  onDayChanged,
}: Props) {
  const [taskId, setTaskId] = useState("");
  const [role, setRole] = useState<TodayRole>("planned");
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<ProductError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const context: TodayContext = {
    planning_date: today.planning_date,
    timezone: today.timezone,
  };
  const selected = new Set(
    [
      ...today.plan.priorities,
      ...today.plan.planned,
      ...today.plan.backups,
      ...today.completed_today.filter((item) => item.plan),
    ].map((item) => item.task.id),
  );
  const eligible = tasks.filter(
    (task) =>
      ["open", "in_progress", "paused"].includes(task.state) &&
      !task.trashed_at &&
      !selected.has(task.id),
  );

  async function planningMutation(
    key: string,
    operation: () => Promise<TodayOutput>,
  ) {
    if (pending) return;
    setPending(key);
    setError(null);
    setNotice(null);
    try {
      onToday(await operation());
      setNotice("Today plan updated.");
    } catch (reason) {
      const productError = asProductError(reason);
      const latest = currentTodayContext();
      if (
        productError.code === "validation" &&
        !sameTodayContext(context, latest)
      ) {
        await onDayChanged();
        setNotice(
          "The local day changed. Today was refreshed; retry if needed.",
        );
      } else setError(productError);
    } finally {
      setPending(null);
    }
  }

  async function taskMutation(task: Task, action: "complete" | "reopen") {
    if (pending) return;
    setPending(`${action}-${task.id}`);
    setError(null);
    setNotice(null);
    try {
      const confirmed = await taskClient[action](task);
      onTaskConfirmed(confirmed);
      onToday(applyConfirmedTask(today, confirmed));
      setNotice(action === "complete" ? "Task completed." : "Task reopened.");
      try {
        onToday(await todayClient.get(context));
      } catch {
        setNotice(
          `${action === "complete" ? "Task completed" : "Task reopened"}, but Today could not refresh. The confirmed Task state is retained.`,
        );
      }
    } catch (reason) {
      setError(asProductError(reason));
    } finally {
      setPending(null);
    }
  }

  function move(items: TodayPlanItem[], index: number, offset: number) {
    const target = index + offset;
    if (target < 0 || target >= items.length) return;
    const reordered = [...items];
    [reordered[index], reordered[target]] = [
      reordered[target],
      reordered[index],
    ];
    void planningMutation(`reorder-${items[index].plan.role}`, () =>
      todayClient.reorder(context, items[index].plan.role, reordered),
    );
  }

  return (
    <section className="workspace today-workspace" aria-label="Today">
      <header className="today-header">
        <div>
          <p className="eyebrow">ION OS · PHASE 2B</p>
          <h1>Today</h1>
          <p className="summary">{formatFullDate(today)}</p>
        </div>
        <form
          className="today-add"
          onSubmit={(event) => {
            event.preventDefault();
            if (!taskId) return;
            void planningMutation("add", async () => {
              const output = await todayClient.add(context, taskId, role);
              setTaskId("");
              return output;
            });
          }}
        >
          <label>
            Existing Task
            <select
              value={taskId}
              onChange={(event) => setTaskId(event.target.value)}
            >
              <option value="">Choose a Task</option>
              {eligible.map((task) => (
                <option key={task.id} value={task.id}>
                  {task.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            Today role
            <select
              value={role}
              onChange={(event) => setRole(event.target.value as TodayRole)}
            >
              <option value="priority">Priority</option>
              <option value="planned">Planned</option>
              <option value="backup">Backup</option>
            </select>
          </label>
          <button disabled={!taskId || pending === "add"} type="submit">
            Add to Today
          </button>
        </form>
      </header>
      <ProductErrorNotice error={error} />
      {notice && (
        <p className="context-note" role="status">
          {notice}
        </p>
      )}
      <div className="today-split">
        <div className="today-execution">
          <PlanSection
            label="Priorities"
            hint="Usually keep this to ~3."
            items={today.plan.priorities}
            pending={pending}
            onMove={move}
            onRole={(plan, nextRole) =>
              void planningMutation(`role-${plan.id}`, () =>
                todayClient.setRole(context, plan, nextRole),
              )
            }
            onRemove={(plan) =>
              void planningMutation(`remove-${plan.id}`, () =>
                todayClient.remove(context, plan),
              )
            }
            onComplete={(task) => void taskMutation(task, "complete")}
          />
          <PlanSection
            label="Planned"
            items={today.plan.planned}
            pending={pending}
            onMove={move}
            onRole={(plan, nextRole) =>
              void planningMutation(`role-${plan.id}`, () =>
                todayClient.setRole(context, plan, nextRole),
              )
            }
            onRemove={(plan) =>
              void planningMutation(`remove-${plan.id}`, () =>
                todayClient.remove(context, plan),
              )
            }
            onComplete={(task) => void taskMutation(task, "complete")}
          />
          <PlanSection
            label="Backups"
            hint="Available if capacity remains."
            items={today.plan.backups}
            pending={pending}
            onMove={move}
            onRole={(plan, nextRole) =>
              void planningMutation(`role-${plan.id}`, () =>
                todayClient.setRole(context, plan, nextRole),
              )
            }
            onRemove={(plan) =>
              void planningMutation(`remove-${plan.id}`, () =>
                todayClient.remove(context, plan),
              )
            }
            onComplete={(task) => void taskMutation(task, "complete")}
          />
          <section className="today-group" aria-label="Deadlines">
            <h2>Deadlines</h2>
            <TaskGroup label="Overdue" items={today.deadlines.overdue} />
            <TaskGroup label="Due today" items={today.deadlines.due_today} />
            <TaskGroup
              label="Next 7 days"
              items={today.deadlines.approaching}
            />
          </section>
          <section className="today-group" aria-label="Needs attention">
            <h2>Needs attention</h2>
            {today.needs_attention.length === 0 ? (
              <Empty>No unplanned Tasks need immediate attention.</Empty>
            ) : (
              <ul className="today-list">
                {today.needs_attention.map((item) => (
                  <li key={item.task.id}>
                    <TaskCopy item={item} />
                    <div className="row-actions">
                      <span className="badge">
                        {attentionLabel(item.reason)}
                      </span>
                      <button
                        disabled={pending !== null}
                        onClick={() =>
                          void planningMutation(`add-${item.task.id}`, () =>
                            todayClient.add(context, item.task.id, "planned"),
                          )
                        }
                      >
                        Add to Today
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section
            className="today-group"
            aria-label="Unfinished from yesterday"
          >
            <h2>Unfinished from yesterday</h2>
            {today.unfinished_from_yesterday.length === 0 ? (
              <Empty>Nothing unfinished from yesterday’s plan.</Empty>
            ) : (
              <ul className="today-list">
                {today.unfinished_from_yesterday.map((item) => (
                  <li key={item.task.id}>
                    <TaskCopy item={item} />
                    <button
                      disabled={pending !== null}
                      onClick={() =>
                        void planningMutation(`carry-${item.task.id}`, () =>
                          todayClient.add(
                            context,
                            item.task.id,
                            item.plan.role,
                          ),
                        )
                      }
                    >
                      Add to Today
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="today-group" aria-label="Completed today">
            <h2>Completed today</h2>
            {today.completed_today.length === 0 ? (
              <Empty>Completed Tasks will appear here.</Empty>
            ) : (
              <ul className="today-list">
                {today.completed_today.map((item) => (
                  <li key={item.task.id}>
                    <TaskCopy item={item} />
                    <button
                      disabled={pending !== null}
                      onClick={() => void taskMutation(item.task, "reopen")}
                    >
                      Reopen
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
        <TodaySchedule
          calendar={calendar}
          date={today.planning_date}
          localTimeZone={today.timezone}
        />
      </div>
    </section>
  );
}

function PlanSection({
  label,
  hint,
  items,
  pending,
  onMove,
  onRole,
  onRemove,
  onComplete,
}: {
  label: string;
  hint?: string;
  items: TodayPlanItem[];
  pending: string | null;
  onMove(items: TodayPlanItem[], index: number, offset: number): void;
  onRole(plan: DayPlan, role: TodayRole): void;
  onRemove(plan: DayPlan): void;
  onComplete(task: Task): void;
}) {
  return (
    <section className="today-group" aria-label={label}>
      <div className="section-heading">
        <h2>{label}</h2>
        {hint && <span>{hint}</span>}
      </div>
      {items.length === 0 ? (
        <Empty>No {label.toLowerCase()} selected.</Empty>
      ) : (
        <ul className="today-list">
          {items.map((item, index) => (
            <li key={item.plan.id}>
              <TaskCopy item={item} />
              <div className="today-actions">
                <select
                  aria-label={`${item.task.title} Today role`}
                  disabled={pending !== null}
                  value={item.plan.role}
                  onChange={(event) =>
                    onRole(item.plan, event.target.value as TodayRole)
                  }
                >
                  {(Object.keys(roleLabels) as TodayRole[]).map((role) => (
                    <option key={role} value={role}>
                      {roleLabels[role]}
                    </option>
                  ))}
                </select>
                <button
                  disabled={pending !== null || index === 0}
                  onClick={() => onMove(items, index, -1)}
                >
                  Move Up
                </button>
                <button
                  disabled={pending !== null || index === items.length - 1}
                  onClick={() => onMove(items, index, 1)}
                >
                  Move Down
                </button>
                <button
                  disabled={pending !== null}
                  onClick={() => onComplete(item.task)}
                >
                  Complete
                </button>
                <button
                  disabled={pending !== null}
                  onClick={() => onRemove(item.plan)}
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function TaskGroup({ label, items }: { label: string; items: TodayTask[] }) {
  return (
    <div className="deadline-group">
      <h3>{label}</h3>
      {items.length === 0 ? (
        <Empty>None.</Empty>
      ) : (
        <ul className="today-list compact">
          {items.map((item) => (
            <li key={item.task.id}>
              <TaskCopy item={item} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TaskCopy({ item }: { item: TodayTask }) {
  return (
    <div className="entity-copy">
      <strong>{item.task.title}</strong>
      <small>
        {item.goal?.title ?? item.project?.title ?? "Unassigned"}
        {item.task.importance ? ` · ${item.task.importance} importance` : ""}
      </small>
      {item.task.state === "paused" && <span className="badge">Paused</span>}
      {item.goal?.archived_at && <span className="badge">Archived Goal</span>}
      {item.project?.archived_at && (
        <span className="badge">Archived Project</span>
      )}
    </div>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="today-empty">{children}</p>;
}

function attentionLabel(reason: string) {
  return reason.replaceAll("_", " ");
}

function formatFullDate(today: TodayOutput) {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: "UTC",
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(new Date(`${today.planning_date}T12:00:00Z`));
}
