import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { MilestoneList } from "./MilestoneList";
import {
  Area,
  Goal,
  GoalDetail,
  GoalKind,
  GoalMilestone,
  GoalState,
  ProductError,
  areaClient,
  asProductError,
  goalClient,
  goalMilestoneClient,
} from "./organizer";
import { ProductErrorNotice } from "./ProductErrorNotice";
import { Task, blankTaskInput, taskClient } from "./tasks";

type Props = {
  areas: Area[];
  goals: Goal[];
  tasks: Task[];
  onAreas(areas: Area[]): void;
  onGoals(goals: Goal[]): void;
  onTasks(tasks: Task[]): void;
  onRefresh(): Promise<void>;
  navigationTarget?: { type: "area" | "goal"; id: string } | null;
};

const replace = <T extends { id: string }>(items: T[], item: T) => [
  item,
  ...items.filter((candidate) => candidate.id !== item.id),
];

export function AreasGoalsWorkspace({
  areas,
  goals,
  tasks,
  onAreas,
  onGoals,
  onTasks,
  onRefresh,
  navigationTarget,
}: Props) {
  const [selection, setSelection] = useState<{
    type: "area" | "goal";
    id: string;
  } | null>(() =>
    goals[0]
      ? { type: "goal", id: goals[0].id }
      : areas[0]
        ? { type: "area", id: areas[0].id }
        : null,
  );
  const [detail, setDetail] = useState<GoalDetail | null>(null);
  const [milestoneTrash, setMilestoneTrash] = useState<GoalMilestone[]>([]);
  const [error, setError] = useState<ProductError | null>(null);
  const [areaName, setAreaName] = useState("");
  const [goalTitle, setGoalTitle] = useState("");
  const [goalKind, setGoalKind] = useState<GoalKind>("outcome");
  const [contextTask, setContextTask] = useState("");
  const areaCreateInFlight = useRef(false);
  const goalCreateInFlight = useRef(false);
  const [creatingArea, setCreatingArea] = useState(false);
  const [creatingGoal, setCreatingGoal] = useState(false);

  const selectedArea =
    selection?.type === "area"
      ? (areas.find((area) => area.id === selection.id) ?? null)
      : null;
  const selectedGoal =
    selection?.type === "goal"
      ? (goals.find((goal) => goal.id === selection.id) ?? null)
      : null;
  const areaById = useMemo(
    () => new Map(areas.map((area) => [area.id, area])),
    [areas],
  );
  const selectedGoalId = selectedGoal?.id ?? null;

  useEffect(() => {
    if (navigationTarget) setSelection(navigationTarget);
  }, [navigationTarget]);

  useEffect(() => {
    if (!selectedGoalId) {
      setDetail(null);
      return;
    }
    let active = true;
    goalClient
      .get({ id: selectedGoalId })
      .then((result) => {
        if (active) setDetail(result);
      })
      .catch((reason) => {
        if (active) setError(asProductError(reason));
      });
    return () => {
      active = false;
    };
  }, [selectedGoalId]);

  async function run<T>(
    operation: () => Promise<T>,
    accept: (result: T) => void,
  ) {
    try {
      const result = await operation();
      accept(result);
      setError(null);
    } catch (reason) {
      const productError = asProductError(reason);
      setError(productError);
      if (productError.code === "revision_conflict") await onRefresh();
    }
  }

  function acceptGoal(goal: Goal) {
    onGoals(replace(goals, goal));
    setDetail((current) =>
      current?.goal.id === goal.id ? { ...current, goal } : current,
    );
  }

  async function createArea(event: FormEvent) {
    event.preventDefault();
    if (!areaName.trim() || areaCreateInFlight.current) return;
    areaCreateInFlight.current = true;
    setCreatingArea(true);
    try {
      await run(
        () => areaClient.create({ name: areaName, description: null }),
        (area) => {
          onAreas(replace(areas, area));
          setAreaName("");
          setSelection({ type: "area", id: area.id });
        },
      );
    } finally {
      areaCreateInFlight.current = false;
      setCreatingArea(false);
    }
  }

  async function createGoal(event: FormEvent) {
    event.preventDefault();
    if (!goalTitle.trim() || goalCreateInFlight.current) return;
    const area_id =
      selectedArea && !selectedArea.archived_at && !selectedArea.trashed_at
        ? selectedArea.id
        : null;
    goalCreateInFlight.current = true;
    setCreatingGoal(true);
    try {
      await run(
        () =>
          goalClient.create({
            title: goalTitle,
            description: null,
            kind: goalKind,
            area_id,
          }),
        (goal) => {
          onGoals(replace(goals, goal));
          setGoalTitle("");
          setSelection({ type: "goal", id: goal.id });
        },
      );
    } finally {
      goalCreateInFlight.current = false;
      setCreatingGoal(false);
    }
  }

  const activeAreas = areas.filter(
    (area) => !area.archived_at && !area.trashed_at,
  );
  const archivedAreas = areas.filter(
    (area) => area.archived_at && !area.trashed_at,
  );
  const trashedAreas = areas.filter((area) => area.trashed_at);
  const activeGoals = goals.filter(
    (goal) => !goal.archived_at && !goal.trashed_at,
  );
  const archivedGoals = goals.filter(
    (goal) => goal.archived_at && !goal.trashed_at,
  );
  const trashedGoals = goals.filter((goal) => goal.trashed_at);

  return (
    <section className="workspace">
      <header>
        <p className="eyebrow">ION OS · PHASE 1B</p>
        <h1>Areas &amp; Goals</h1>
        <p className="summary">
          Durable context, independent lifecycle, and explicit progress.
        </p>
      </header>
      <div className="split-workspace">
        <aside className="navigator" aria-label="Areas and Goals hierarchy">
          <form className="quick-create" onSubmit={createArea}>
            <input
              aria-label="New Area name"
              placeholder="New Area"
              value={areaName}
              onChange={(event) => setAreaName(event.target.value)}
            />
            <button disabled={creatingArea}>Create Area</button>
          </form>
          <form className="quick-create" onSubmit={createGoal}>
            <input
              aria-label="New Goal title"
              placeholder={
                selectedArea
                  ? `Goal in ${selectedArea.name}`
                  : "New unassigned Goal"
              }
              value={goalTitle}
              onChange={(event) => setGoalTitle(event.target.value)}
            />
            <select
              aria-label="New Goal kind"
              value={goalKind}
              onChange={(event) => setGoalKind(event.target.value as GoalKind)}
            >
              {[
                "outcome",
                "skill",
                "habit",
                "project",
                "academic",
                "personal",
              ].map((kind) => (
                <option key={kind}>{kind}</option>
              ))}
            </select>
            <button disabled={creatingGoal}>Create Goal</button>
          </form>
          {activeAreas.map((area) => (
            <div className="tree-group" key={area.id}>
              <button
                className={
                  selection?.id === area.id
                    ? "tree-item is-selected"
                    : "tree-item"
                }
                onClick={() => setSelection({ type: "area", id: area.id })}
              >
                {area.name}
              </button>
              {activeGoals
                .filter((goal) => goal.area_id === area.id)
                .map((goal) => (
                  <GoalButton
                    key={goal.id}
                    goal={goal}
                    selected={selection?.id === goal.id}
                    archivedParent={false}
                    onSelect={() => setSelection({ type: "goal", id: goal.id })}
                  />
                ))}
            </div>
          ))}
          <div className="tree-group">
            <h3>Unassigned Goals</h3>
            {activeGoals
              .filter((goal) => !goal.area_id)
              .map((goal) => (
                <GoalButton
                  key={goal.id}
                  goal={goal}
                  selected={selection?.id === goal.id}
                  archivedParent={false}
                  onSelect={() => setSelection({ type: "goal", id: goal.id })}
                />
              ))}
          </div>
          <div className="tree-group">
            <h3>Archived context</h3>
            {archivedAreas.map((area) => (
              <button
                key={area.id}
                className="tree-item"
                onClick={() => setSelection({ type: "area", id: area.id })}
              >
                {area.name} <span className="badge">Archived</span>
              </button>
            ))}
            {archivedGoals.map((goal) => (
              <GoalButton
                key={goal.id}
                goal={goal}
                selected={selection?.id === goal.id}
                archivedParent={false}
                onSelect={() => setSelection({ type: "goal", id: goal.id })}
              />
            ))}
            {activeGoals
              .filter(
                (goal) =>
                  goal.area_id && areaById.get(goal.area_id)?.archived_at,
              )
              .map((goal) => (
                <GoalButton
                  key={goal.id}
                  goal={goal}
                  selected={selection?.id === goal.id}
                  archivedParent
                  onSelect={() => setSelection({ type: "goal", id: goal.id })}
                />
              ))}
          </div>
          <div className="tree-group">
            <h3>Trash</h3>
            {trashedAreas.map((area) => (
              <button
                key={area.id}
                className="tree-item"
                onClick={() => setSelection({ type: "area", id: area.id })}
              >
                {area.name}
              </button>
            ))}
            {trashedGoals.map((goal) => (
              <GoalButton
                key={goal.id}
                goal={goal}
                selected={selection?.id === goal.id}
                archivedParent={false}
                onSelect={() => setSelection({ type: "goal", id: goal.id })}
              />
            ))}
          </div>
        </aside>
        <main className="detail-pane">
          <ProductErrorNotice error={error} />
          {selectedArea && (
            <AreaPanel
              key={selectedArea.id}
              area={selectedArea}
              goals={goals.filter(
                (goal) => goal.area_id === selectedArea.id && !goal.trashed_at,
              )}
              onResult={(area) => onAreas(replace(areas, area))}
              onError={setError}
              onRefresh={onRefresh}
            />
          )}
          {selectedGoal && detail && (
            <GoalPanel
              key={selectedGoal.id}
              detail={detail}
              areas={areas}
              tasks={tasks}
              milestoneTrash={milestoneTrash}
              onGoal={acceptGoal}
              onDetail={setDetail}
              onMilestoneTrash={setMilestoneTrash}
              onTasks={onTasks}
              contextTask={contextTask}
              setContextTask={setContextTask}
              onError={setError}
              onRefresh={onRefresh}
            />
          )}
          {!selection && (
            <p className="empty-state">Create an Area or Goal to begin.</p>
          )}
        </main>
      </div>
    </section>
  );
}

function GoalButton({
  goal,
  selected,
  archivedParent,
  onSelect,
}: {
  goal: Goal;
  selected: boolean;
  archivedParent: boolean;
  onSelect(): void;
}) {
  return (
    <button
      className={
        selected
          ? "tree-item tree-item--child is-selected"
          : "tree-item tree-item--child"
      }
      onClick={onSelect}
    >
      {goal.title}
      {goal.archived_at && <span className="badge">Archived</span>}
      {archivedParent && <span className="badge">Archived parent</span>}
    </button>
  );
}

function AreaPanel({
  area,
  goals,
  onResult,
  onError,
  onRefresh,
}: {
  area: Area;
  goals: Goal[];
  onResult(area: Area): void;
  onError(error: ProductError | null): void;
  onRefresh(): Promise<void>;
}) {
  const [name, setName] = useState(area.name);
  const [description, setDescription] = useState(area.description ?? "");
  async function act(operation: () => Promise<Area>) {
    try {
      onResult(await operation());
    } catch (reason) {
      const error = asProductError(reason);
      onError(error);
      if (error.code === "revision_conflict") await onRefresh();
    }
  }
  return (
    <article>
      <p className="eyebrow">Area</p>
      <h2>{area.name}</h2>
      {area.trashed_at ? (
        <button onClick={() => void act(() => areaClient.restore(area))}>
          Restore Area
        </button>
      ) : (
        <>
          <form
            className="entity-form"
            onSubmit={(event) => {
              event.preventDefault();
              void act(() =>
                areaClient.update(area, {
                  name,
                  description: description || null,
                }),
              );
            }}
          >
            <label>
              Name
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label>
              Description
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>
            <button>Save Area</button>
          </form>
          <div className="action-bar">
            {area.archived_at ? (
              <button
                onClick={() => void act(() => areaClient.unarchive(area))}
              >
                Unarchive
              </button>
            ) : (
              <button onClick={() => void act(() => areaClient.archive(area))}>
                Archive
              </button>
            )}
            <button
              className="danger-button"
              onClick={() => void act(() => areaClient.trash(area))}
            >
              Move Area to Trash
            </button>
          </div>
        </>
      )}
      <section className="detail-section">
        <h3>Contained Goals</h3>
        <ul className="read-list">
          {goals.map((goal) => (
            <li key={goal.id}>
              {goal.title} <span className="badge">{goal.state}</span>
            </li>
          ))}
        </ul>
      </section>
    </article>
  );
}

function GoalPanel({
  detail,
  areas,
  tasks,
  milestoneTrash,
  onGoal,
  onDetail,
  onMilestoneTrash,
  onTasks,
  contextTask,
  setContextTask,
  onError,
  onRefresh,
}: {
  detail: GoalDetail;
  areas: Area[];
  tasks: Task[];
  milestoneTrash: GoalMilestone[];
  onGoal(goal: Goal): void;
  onDetail(detail: GoalDetail): void;
  onMilestoneTrash(items: GoalMilestone[]): void;
  onTasks(tasks: Task[]): void;
  contextTask: string;
  setContextTask(value: string): void;
  onError(error: ProductError | null): void;
  onRefresh(): Promise<void>;
}) {
  const goal = detail.goal;
  const [title, setTitle] = useState(goal.title);
  const [description, setDescription] = useState(goal.description ?? "");
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">(
    "idle",
  );
  const contextTaskInFlight = useRef(false);
  const [creatingContextTask, setCreatingContextTask] = useState(false);
  async function act<T>(
    operation: () => Promise<T>,
    accept: (result: T) => void,
  ) {
    try {
      accept(await operation());
      onError(null);
    } catch (reason) {
      const error = asProductError(reason);
      onError(error);
      if (error.code === "revision_conflict") await onRefresh();
    }
  }
  async function saveGoal(event: FormEvent) {
    event.preventDefault();
    if (saveStatus === "saving") return;
    setSaveStatus("saving");
    try {
      const result = await goalClient.update(goal, {
        title,
        description: description || null,
      });
      onGoal(result);
      onError(null);
      setSaveStatus("saved");
    } catch (reason) {
      const error = asProductError(reason);
      onError(error);
      setSaveStatus("idle");
      if (error.code === "revision_conflict") await onRefresh();
    }
  }
  async function createContextTask(event: FormEvent) {
    event.preventDefault();
    if (!contextTask.trim() || contextTaskInFlight.current) return;
    contextTaskInFlight.current = true;
    setCreatingContextTask(true);
    try {
      const input = {
        ...blankTaskInput(),
        title: contextTask,
        goal_id: goal.id,
        project_id: null,
      };
      await act(
        () => taskClient.create(input),
        (task) => {
          onTasks(replace(tasks, task));
          onDetail({
            ...detail,
            direct_tasks: replace(detail.direct_tasks, task),
          });
          setContextTask("");
        },
      );
    } finally {
      contextTaskInFlight.current = false;
      setCreatingContextTask(false);
    }
  }
  const updateMilestone = (item: GoalMilestone) =>
    onDetail({
      ...detail,
      milestones: replace(detail.milestones, item).sort(
        (a, b) => a.position - b.position,
      ),
    });
  const eligibleAreas = areas.filter(
    (area) => !area.archived_at && !area.trashed_at,
  );
  return (
    <article>
      <p className="eyebrow">Goal · {goal.kind}</p>
      <h2>{goal.title}</h2>
      {goal.area_id &&
        areas.find((area) => area.id === goal.area_id)?.archived_at && (
          <p className="context-note">
            Parent Area is archived. Existing context is retained.
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
          <strong>{detail.summary.project_total}</strong> active Projects
        </span>
        <span>
          <strong>{detail.summary.task_total}</strong> direct open Tasks
        </span>
      </div>
      {goal.trashed_at ? (
        <button
          onClick={() => void act(() => goalClient.restore(goal), onGoal)}
        >
          Restore Goal
        </button>
      ) : (
        <>
          <form
            className="entity-form"
            onSubmit={(event) => void saveGoal(event)}
          >
            <label>
              Title
              <input
                value={title}
                onChange={(event) => {
                  setTitle(event.target.value);
                  setSaveStatus("idle");
                }}
              />
            </label>
            <label>
              Description
              <textarea
                value={description}
                onChange={(event) => {
                  setDescription(event.target.value);
                  setSaveStatus("idle");
                }}
              />
            </label>
            <label>
              State
              <select
                value={goal.state}
                onChange={(event) =>
                  void act(
                    () =>
                      goalClient.setState(
                        goal,
                        event.target.value as GoalState,
                      ),
                    onGoal,
                  )
                }
              >
                {["active", "paused", "achieved", "retired"].map((state) => (
                  <option key={state}>{state}</option>
                ))}
              </select>
            </label>
            <label>
              Area
              <select
                value={goal.area_id ?? ""}
                onChange={(event) =>
                  void act(
                    () => goalClient.setArea(goal, event.target.value || null),
                    onGoal,
                  )
                }
              >
                <option value="">Unassigned</option>
                {eligibleAreas.map((area) => (
                  <option key={area.id} value={area.id}>
                    {area.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="form-actions">
              <button disabled={saveStatus === "saving"}>Save Goal</button>
              <span className="save-status" role="status" aria-live="polite">
                {saveStatus === "saving"
                  ? "Saving…"
                  : saveStatus === "saved"
                    ? "Saved"
                    : ""}
              </span>
            </div>
          </form>
          <div className="action-bar">
            {goal.archived_at ? (
              <button
                onClick={() =>
                  void act(() => goalClient.unarchive(goal), onGoal)
                }
              >
                Unarchive
              </button>
            ) : (
              <button
                onClick={() => void act(() => goalClient.archive(goal), onGoal)}
              >
                Archive
              </button>
            )}
            <button
              className="danger-button"
              onClick={() => void act(() => goalClient.trash(goal), onGoal)}
            >
              Move Goal to Trash
            </button>
          </div>
        </>
      )}
      <MilestoneList
        label="Goal Milestones"
        items={detail.milestones}
        trashItems={milestoneTrash}
        onCreate={(input) =>
          act(() => goalMilestoneClient.create(goal, input), updateMilestone)
        }
        onUpdate={(item, input) =>
          act(() => goalMilestoneClient.update(item, input), updateMilestone)
        }
        onState={(item, state) =>
          act(() => goalMilestoneClient.setState(item, state), updateMilestone)
        }
        onReorder={(items) =>
          act(
            () => goalMilestoneClient.reorder(goal, items),
            (milestones) => onDetail({ ...detail, milestones }),
          )
        }
        onTrash={(item) =>
          act(
            () => goalMilestoneClient.trash(item),
            () =>
              onDetail({
                ...detail,
                milestones: detail.milestones.filter(
                  (candidate) => candidate.id !== item.id,
                ),
              }),
          )
        }
        onRestore={(item) =>
          act(
            () => goalMilestoneClient.restore(item),
            (restored) => {
              updateMilestone(restored);
              onMilestoneTrash(
                milestoneTrash.filter((candidate) => candidate.id !== item.id),
              );
            },
          )
        }
        onLoadTrash={() =>
          act(() => goalMilestoneClient.list(goal, true), onMilestoneTrash)
        }
        onError={onError}
      />
      <section className="detail-section">
        <h3>Related Projects</h3>
        <ul className="read-list">
          {detail.projects.map((project) => (
            <li key={project.id}>
              {project.title} · {project.state}
            </li>
          ))}
        </ul>
      </section>
      <TaskContext title="Direct Goal Tasks" items={detail.direct_tasks} />
      <TaskContext
        title="Tasks through child Projects"
        items={detail.project_tasks}
      />
      <form
        className="quick-create"
        onSubmit={(event) => void createContextTask(event)}
      >
        <input
          aria-label="New Goal Task"
          value={contextTask}
          placeholder="New Task for this Goal"
          onChange={(event) => setContextTask(event.target.value)}
        />
        <button disabled={creatingContextTask}>Create Task</button>
      </form>
    </article>
  );
}

function TaskContext({ title, items }: { title: string; items: Task[] }) {
  return (
    <section className="detail-section">
      <h3>{title}</h3>
      <ul className="read-list">
        {items.map((task) => (
          <li key={task.id}>
            {task.title} <span className="badge">{task.state}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
