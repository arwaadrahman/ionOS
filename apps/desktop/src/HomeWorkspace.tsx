import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import {
  CoreNode,
  HomeAttentionSummary,
  HomeOutput,
  HomeTaskSummary,
} from "./home";
import { IonCoreState } from "./ion-core/renderer";

const CoreCanvas = lazy(() => import("./ion-core/CoreCanvas"));

export type HomeNavigationTarget =
  | { workspace: "areas"; entityType: "area" | "goal"; id: string }
  | { workspace: "projects"; entityType: "project"; id: string }
  | { workspace: "tasks"; entityType: "task"; id: string };

function deadlineLabel(task: HomeTaskSummary) {
  if (task.deadline.kind === "date") return `Due ${task.deadline.date}`;
  if (task.deadline.kind === "instant") {
    return `Due ${new Date(task.deadline.at).toLocaleString()}`;
  }
  return null;
}

function TaskSummary({ task }: { task: HomeTaskSummary }) {
  const deadline = deadlineLabel(task);
  return (
    <article className="home-summary-item">
      <strong>{task.title}</strong>
      <span>
        {task.project?.title ??
          task.goal?.title ??
          task.state.replaceAll("_", " ")}
      </span>
      {deadline ? <time>{deadline}</time> : null}
    </article>
  );
}

function AttentionSummary({ task }: { task: HomeAttentionSummary }) {
  return (
    <article className="home-summary-item is-attention">
      <strong>{task.title}</strong>
      <span>{task.reason.replaceAll("_", " ")}</span>
    </article>
  );
}

function StaticCore({ home }: { home: HomeOutput }) {
  return (
    <div className="ion-core-fallback" role="status">
      <div className="ion-core-fallback-orbit" aria-hidden="true" />
      <p>
        {home.core.nodes.length} canonical nodes · {home.core.edges.length}{" "}
        relationships
      </p>
    </div>
  );
}

function destinationFor(
  home: HomeOutput,
  node: CoreNode,
): HomeNavigationTarget | null {
  if (node.entity_type === "area" || node.entity_type === "goal") {
    return { workspace: "areas", entityType: node.entity_type, id: node.id };
  }
  if (node.entity_type === "project") {
    return { workspace: "projects", entityType: "project", id: node.id };
  }
  if (node.entity_type === "task") {
    return { workspace: "tasks", entityType: "task", id: node.id };
  }
  const relationship =
    node.entity_type === "goal_milestone"
      ? "goal_milestone_goal"
      : "project_milestone_project";
  const owner = home.core.edges.find(
    (edge) =>
      edge.source_id === node.id && edge.relationship_type === relationship,
  );
  if (!owner) return null;
  return node.entity_type === "goal_milestone"
    ? { workspace: "areas", entityType: "goal", id: owner.target_id }
    : { workspace: "projects", entityType: "project", id: owner.target_id };
}

export function HomeWorkspace({
  home,
  processing,
  stale,
  onRetry,
  onNavigate,
}: {
  home: HomeOutput;
  processing: boolean;
  stale: boolean;
  onRetry: () => void;
  onNavigate: (target: HomeNavigationTarget) => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = useMemo(
    () => home.core.nodes.find((node) => node.id === selectedId) ?? null,
    [home.core.nodes, selectedId],
  );
  useEffect(() => {
    if (selectedId && !selected) setSelectedId(null);
  }, [selected, selectedId]);
  const coreState: IonCoreState = processing
    ? "processing"
    : home.needs_attention.length > 0
      ? "attention"
      : "idle";
  const destination = selected ? destinationFor(home, selected) : null;

  return (
    <section className="home-workspace" aria-labelledby="home-heading">
      <header className="home-heading-row">
        <div>
          <p className="eyebrow">Canonical overview</p>
          <h1 id="home-heading">Home</h1>
          <p>Your commitments, held as one navigable system.</p>
        </div>
        <div className={`core-state-badge is-${coreState}`}>
          <span aria-hidden="true" />
          Core {coreState}
        </div>
      </header>

      {stale ? (
        <div className="home-stale-notice" role="status">
          Home is showing the last confirmed overview.
          <button type="button" onClick={onRetry}>
            Retry
          </button>
        </div>
      ) : null}

      <div className="home-core-panel">
        <div className="ion-core-halo" aria-hidden="true" />
        {home.core.nodes.length ? (
          <Suspense fallback={<StaticCore home={home} />}>
            <CoreCanvas
              graph={home.core}
              state={coreState}
              selectedId={selectedId}
              onSelect={(node) => setSelectedId(node?.id ?? null)}
            />
          </Suspense>
        ) : (
          <StaticCore home={home} />
        )}
        <div className="core-counts" aria-label="Ion Core counts">
          <span>
            <strong>{home.core.nodes.length}</strong> nodes
          </span>
          <span>
            <strong>{home.core.edges.length}</strong> links
          </span>
        </div>
      </div>

      {selected ? (
        <aside className="core-selection" aria-live="polite">
          <div>
            <span>{selected.entity_type.replaceAll("_", " ")}</span>
            <h2>{selected.label}</h2>
            <p>
              {selected.lifecycle}
              {selected.today_role ? ` · Today ${selected.today_role}` : ""}
              {selected.attention_reason
                ? ` · ${selected.attention_reason.replaceAll("_", " ")}`
                : ""}
            </p>
          </div>
          <div className="core-selection-actions">
            {destination ? (
              <button type="button" onClick={() => onNavigate(destination)}>
                Open
              </button>
            ) : null}
            <button type="button" onClick={() => setSelectedId(null)}>
              Clear
            </button>
          </div>
        </aside>
      ) : null}

      <div className="home-summary-grid">
        <section className="home-card is-focus" aria-labelledby="focus-heading">
          <div className="home-card-heading">
            <h2 id="focus-heading">Focus</h2>
            <span>Top priority</span>
          </div>
          {home.focus ? (
            <TaskSummary task={home.focus} />
          ) : (
            <p className="empty-copy">No priority chosen for Today.</p>
          )}
        </section>
        <section className="home-card" aria-labelledby="attention-heading">
          <div className="home-card-heading">
            <h2 id="attention-heading">Needs attention</h2>
            <span>{home.needs_attention.length}</span>
          </div>
          {home.needs_attention.length ? (
            home.needs_attention.map((item) => (
              <AttentionSummary key={item.id} task={item} />
            ))
          ) : (
            <p className="empty-copy">Nothing requires immediate attention.</p>
          )}
        </section>
        <section className="home-card" aria-labelledby="upcoming-heading">
          <div className="home-card-heading">
            <h2 id="upcoming-heading">Upcoming</h2>
            <span>{home.upcoming.length}</span>
          </div>
          {home.upcoming.length ? (
            home.upcoming.map((item) => (
              <TaskSummary key={item.id} task={item} />
            ))
          ) : (
            <p className="empty-copy">No near-term deadlines.</p>
          )}
        </section>
      </div>

      <button
        className="ask-ion-placeholder"
        type="button"
        disabled
        title="Ask Ion arrives in a later phase"
      >
        Ask Ion
      </button>
    </section>
  );
}
