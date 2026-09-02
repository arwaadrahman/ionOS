import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  CalendarRecurrenceScope,
  calendarRecurrenceScopeOptions,
} from "./calendar";

const FOCUSABLE =
  'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

/**
 * The single recurrence-scope chooser used by every recurring interaction.
 *
 * Google Calendar's desktop convention is to describe the change first and pick
 * its scope afterwards, so this opens only once the user has committed to an
 * edit, a completed drag/resize review, or a delete. Cancelling never produces
 * a canonical or provider mutation.
 */
export function CalendarRecurrenceScopeDialog({
  mode,
  eventTitle,
  seriesOnly = false,
  splitAvailable = false,
  splitUnavailableReason = null,
  pending = false,
  onChoose,
  onCancel,
}: {
  mode: "edit" | "delete";
  eventTitle: string;
  /** A repeat-rule change is inherently series-wide, as it is in Google. */
  seriesOnly?: boolean;
  /**
   * Whether a `this and following` split is offered. Google omits it at the
   * first occurrence, where it would mean the same as All events; Ion also
   * withholds it for a series whose pattern it cannot faithfully continue.
   */
  splitAvailable?: boolean;
  splitUnavailableReason?: string | null;
  pending?: boolean;
  onChoose(scope: CalendarRecurrenceScope, seriesConfirmed: boolean): void;
  onCancel(): void;
}) {
  const [scope, setScope] = useState<CalendarRecurrenceScope>(
    seriesOnly ? "series" : "occurrence",
  );
  const destructive = mode === "delete";
  // What the chosen scope will actually remove, stated where it is chosen.
  // Ion says this only where it is true: it cannot restore a deleted provider
  // event, because recreating one produces a new identity.
  const irreversibleWarning = !destructive
    ? null
    : scope === "this_and_following"
      ? "Deletes this event and every later one. These may not be recoverable."
      : scope === "series"
        ? "Deletes the whole recurring series. These may not be recoverable."
        : "Deletes this occurrence. It may not be recoverable.";
  const blocked = false;
  const dialogRef = useRef<HTMLElement | null>(null);
  const titleId = useId();

  // A scope choice blocks the interaction it interrupts, so the modal takes
  // focus, keeps it, and returns it to whatever opened the chooser.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    dialogRef.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    return () => opener?.focus?.();
  }, []);

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape" && !pending) {
      event.stopPropagation();
      onCancel();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [],
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && active === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return createPortal(
    <div
      className="calendar-modal-overlay"
      // The backdrop blocks the surface underneath; dismissing from it is the
      // same no-op cancel as the Cancel button.
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !pending) onCancel();
      }}
    >
      <section
        ref={dialogRef}
        className="calendar-scope-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={onKeyDown}
      >
        <h3 id={titleId}>
          {destructive ? "Delete recurring event" : "Save recurring event"}
        </h3>
        <p className="context-note">
          {destructive
            ? `Choose which occurrences of “${eventTitle}” to delete.`
            : `Choose which occurrences of “${eventTitle}” this change applies to.`}
        </p>
        <div className="calendar-scope-options" role="radiogroup">
          {calendarRecurrenceScopeOptions.map((option) => {
            if (option.value === "this_and_following" && !splitAvailable) {
              return null;
            }
            const disabled = seriesOnly && option.value !== "series";
            return (
              <label
                key={option.value}
                className={disabled ? "is-disabled" : undefined}
              >
                <input
                  type="radio"
                  name="calendar-recurrence-scope"
                  value={option.value}
                  checked={scope === option.value}
                  disabled={disabled || pending}
                  onChange={() => {
                    setScope(option.value);
                  }}
                />
                <span>
                  <strong>{option.label}</strong>
                  <small>{option.description}</small>
                </span>
              </label>
            );
          })}
        </div>
        {seriesOnly ? (
          <p className="context-note">
            Changing how often this event repeats always applies to every event
            in the series.
          </p>
        ) : null}
        {splitUnavailableReason ? (
          <p className="context-note">{splitUnavailableReason}</p>
        ) : null}
        {irreversibleWarning ? (
          // The consequence belongs beside the choice that causes it. Saying it
          // here, and then asking again afterwards, would be asking the same
          // question twice.
          <p className="calendar-scope-warning" role="note">
            {irreversibleWarning}
          </p>
        ) : null}
        <div className="calendar-scope-actions">
          <button type="button" onClick={onCancel} disabled={pending}>
            Cancel
          </button>
          <button
            type="button"
            disabled={blocked || pending}
            onClick={() => onChoose(scope, destructive)}
          >
            {pending
              ? destructive
                ? "Deleting…"
                : "Saving…"
              : destructive
                ? "Delete"
                : "Save"}
          </button>
        </div>
      </section>
    </div>,
    document.body,
  );
}
