import { FormEvent, useRef, useState } from "react";
import { MilestoneState, ProductError, asProductError } from "./organizer";

export type VisualMilestone = {
  id: string;
  title: string;
  state: MilestoneState;
  target_date: string | null;
  position: number;
  revision: number;
};

type Props<T extends VisualMilestone> = {
  label: string;
  items: T[];
  trashItems: T[];
  currentId?: string | null;
  onCreate(input: { title: string; target_date: string | null }): Promise<void>;
  onUpdate(
    item: T,
    input: { title: string; target_date: string | null },
  ): Promise<void>;
  onState(item: T, state: MilestoneState): Promise<void>;
  onReorder(items: T[]): Promise<void>;
  onTrash(item: T): Promise<void>;
  onRestore(item: T): Promise<void>;
  onLoadTrash(): Promise<void>;
  onError(error: ProductError): void;
};

export function MilestoneList<T extends VisualMilestone>({
  label,
  items,
  trashItems,
  currentId,
  onCreate,
  onUpdate,
  onState,
  onReorder,
  onTrash,
  onRestore,
  onLoadTrash,
  onError,
}: Props<T>) {
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showTrash, setShowTrash] = useState(false);
  const operationInFlight = useRef(false);

  async function run(operation: () => Promise<void>) {
    if (operationInFlight.current) return;
    operationInFlight.current = true;
    setBusy(true);
    try {
      await operation();
    } catch (reason) {
      onError(asProductError(reason));
    } finally {
      operationInFlight.current = false;
      setBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    await run(async () => {
      if (editing) {
        const item = items.find((candidate) => candidate.id === editing);
        if (item) await onUpdate(item, { title, target_date: date || null });
      } else await onCreate({ title, target_date: date || null });
      setTitle("");
      setDate("");
      setEditing(null);
    });
  }

  function move(index: number, offset: number) {
    const target = index + offset;
    if (target < 0 || target >= items.length) return;
    const reordered = [...items];
    [reordered[index], reordered[target]] = [
      reordered[target],
      reordered[index],
    ];
    void run(() => onReorder(reordered));
  }

  return (
    <section className="detail-section" aria-label={label}>
      <div className="section-heading">
        <h3>{label}</h3>
        <button
          type="button"
          className="quiet-button"
          onClick={() =>
            void run(async () => {
              await onLoadTrash();
              setShowTrash((value) => !value);
            })
          }
        >
          {showTrash ? "Hide Milestone Trash" : "Milestone Trash"}
        </button>
      </div>
      <form className="compact-form" onSubmit={submit}>
        <input
          aria-label={`${label} title`}
          value={title}
          placeholder="Milestone title"
          onChange={(event) => setTitle(event.target.value)}
        />
        <input
          aria-label={`${label} target date`}
          type="date"
          value={date}
          onChange={(event) => setDate(event.target.value)}
        />
        <button disabled={busy} type="submit">
          {editing ? "Save milestone" : "Add milestone"}
        </button>
        {editing && (
          <button
            type="button"
            onClick={() => {
              setEditing(null);
              setTitle("");
              setDate("");
            }}
          >
            Cancel
          </button>
        )}
      </form>
      <ol className="milestone-list">
        {items.map((item, index) => (
          <li
            key={item.id}
            className={item.id === currentId ? "is-current" : ""}
          >
            <div>
              <strong>{item.title}</strong>
              {item.id === currentId && <span className="badge">Current</span>}
              <small>
                {item.target_date ?? "No target date"} ·{" "}
                {item.state.replace("_", " ")}
              </small>
            </div>
            <div className="row-actions">
              <select
                aria-label={`${item.title} state`}
                value={item.state}
                disabled={busy}
                onChange={(event) =>
                  void run(() =>
                    onState(item, event.target.value as MilestoneState),
                  )
                }
              >
                <option value="planned">Planned</option>
                <option value="in_progress">In progress</option>
                <option value="achieved">Achieved</option>
                <option value="skipped">Skipped</option>
              </select>
              <button
                type="button"
                disabled={busy || index === 0}
                onClick={() => move(index, -1)}
              >
                Move Up
              </button>
              <button
                type="button"
                disabled={busy || index === items.length - 1}
                onClick={() => move(index, 1)}
              >
                Move Down
              </button>
              <button
                type="button"
                onClick={() => {
                  setEditing(item.id);
                  setTitle(item.title);
                  setDate(item.target_date ?? "");
                }}
              >
                Edit
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => void run(() => onTrash(item))}
              >
                Trash
              </button>
            </div>
          </li>
        ))}
      </ol>
      {showTrash && (
        <ul className="milestone-list" aria-label={`${label} Trash`}>
          {trashItems.map((item) => (
            <li key={item.id}>
              <strong>{item.title}</strong>
              <button
                type="button"
                disabled={busy}
                onClick={() => void run(() => onRestore(item))}
              >
                Restore
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
