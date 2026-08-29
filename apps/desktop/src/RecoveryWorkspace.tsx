import { useEffect, useState } from "react";
import { ProductErrorNotice } from "./ProductErrorNotice";
import {
  RecoveryItem,
  RecoveryOutput,
  recoveryClient,
  restoreRecoveryItem,
} from "./recovery";
import { asProductError } from "./organizer";

type Props = {
  onRestored(): Promise<void>;
};

const entityLabel: Record<RecoveryItem["entity_type"], string> = {
  area: "Area",
  goal: "Goal",
  goal_milestone: "Goal Milestone",
  project: "Project",
  project_milestone: "Project Milestone",
  task: "Task",
};

function display(value: string) {
  return value.replaceAll("_", " ");
}

export function RecoveryWorkspace({ onRestored }: Props) {
  const [output, setOutput] = useState<RecoveryOutput | null>(null);
  const [error, setError] = useState<ReturnType<typeof asProductError> | null>(
    null,
  );
  const [refreshNotice, setRefreshNotice] = useState<string | null>(null);
  const [restoringId, setRestoringId] = useState<string | null>(null);

  async function load() {
    try {
      setOutput(await recoveryClient.get());
      setError(null);
    } catch (reason) {
      setError(asProductError(reason));
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function restore(item: RecoveryItem) {
    setRestoringId(item.entity_id);
    try {
      await restoreRecoveryItem(item);
      setOutput((current) =>
        current
          ? {
              ...current,
              trash: current.trash.filter(
                (candidate) => candidate.entity_id !== item.entity_id,
              ),
            }
          : current,
      );
      setError(null);
      setRefreshNotice(null);
      try {
        await onRestored();
      } catch {
        setRefreshNotice(
          "Restored. Other workspaces could not refresh yet; retry there when ready.",
        );
      }
    } catch (reason) {
      setError(asProductError(reason));
    } finally {
      setRestoringId(null);
    }
  }

  return (
    <section className="workspace recovery-workspace" aria-label="Recovery">
      <header>
        <p className="eyebrow">ION OS · PHASE 1F</p>
        <h1>Recovery</h1>
        <p className="summary">
          Restore one canonical record at a time. Nothing is permanently deleted
          here.
        </p>
      </header>
      <div className="recovery-layout">
        <section className="recovery-section" aria-labelledby="trash-heading">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Trash</p>
              <h2 id="trash-heading">Recover records</h2>
            </div>
            <button
              className="quiet-button"
              type="button"
              onClick={() => void load()}
            >
              Refresh
            </button>
          </div>
          <p className="context-note">
            Trash is blocked before a parent can move when it still has direct,
            non-trashed dependents. Restore is explicit and never restores a
            parent, child, or relationship on your behalf.
          </p>
          <ProductErrorNotice error={error} />
          {refreshNotice && <p role="status">{refreshNotice}</p>}
          {output?.trash.length === 0 && (
            <p className="empty-state">Trash is empty.</p>
          )}
          <ul className="recovery-list">
            {output?.trash.map((item) => (
              <li key={`${item.entity_type}:${item.entity_id}`}>
                <div>
                  <span className="badge">{entityLabel[item.entity_type]}</span>
                  <strong>{item.label}</strong>
                  <small>
                    {display(item.lifecycle)} · moved to Trash{" "}
                    {new Date(item.trashed_at).toLocaleString()}
                    {item.owner_label ? ` · ${item.owner_label}` : ""}
                  </small>
                </div>
                <button
                  type="button"
                  disabled={restoringId === item.entity_id}
                  onClick={() => void restore(item)}
                >
                  {restoringId === item.entity_id
                    ? "Restoring…"
                    : `Restore ${entityLabel[item.entity_type]}`}
                </button>
              </li>
            ))}
          </ul>
        </section>
        <section className="recovery-section" aria-labelledby="history-heading">
          <p className="eyebrow">Direct human changes</p>
          <h2 id="history-heading">Recent history</h2>
          <p className="context-note">
            A concise, read-only view of recent organizer actions; it is not an
            Undo or version-history system.
          </p>
          <ul className="activity-list">
            {output?.recent_activity.map((event) => (
              <li key={event.event_id}>
                <span>
                  {display(event.action)} · {event.label}
                </span>
                <time>{new Date(event.occurred_at).toLocaleString()}</time>
              </li>
            ))}
          </ul>
          {output?.recent_activity.length === 0 && (
            <p className="empty-state">No organizer changes recorded yet.</p>
          )}
        </section>
      </div>
    </section>
  );
}
