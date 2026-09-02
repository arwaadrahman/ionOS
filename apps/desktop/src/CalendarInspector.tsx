import { useEffect, useRef, useState } from "react";
import { CalendarRecurrenceScopeDialog } from "./CalendarRecurrenceScopeDialog";
import {
  addDays,
  CalendarOccurrence,
  formatOccurrenceTime,
  localCivilDate,
} from "./calendarProjection";
import {
  buildCalendarEditDraft,
  occurrenceIsFirstInSeries,
  occurrenceOriginalStart,
  zonedParts,
} from "./calendarEdits";
import {
  CalendarCategory,
  CalendarRecurrenceScope,
  calendarSplitAvailability,
  CalendarDeleteDraft,
  CalendarEditDraft,
  CalendarRecurrencePreset,
  ConflictResolutionDraft,
  calendarCategories,
  calendarCategoryDisplay,
  calendarCategoryLabels,
  calendarSubtypesFor,
  calendarSubtypeLabel,
} from "./calendar";

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: "UTC",
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(new Date(`${value}T12:00:00Z`));
}

function civilTimedValue(date: string, time: string) {
  const value = new Date(`${date}T${time}:00Z`).valueOf();
  return Number.isNaN(value) ? null : value;
}

function civilTimedParts(value: number) {
  const date = new Date(value);
  return {
    date: date.toISOString().slice(0, 10),
    time: date.toISOString().slice(11, 16),
  };
}

function recurrenceLabel(occurrence: CalendarOccurrence) {
  if (occurrence.recurrenceContext === "occurrence") {
    return "Recurring series occurrence";
  }
  if (occurrence.recurrenceContext === "exception") {
    const block = occurrence.block;
    const moved = occurrence.allDay
      ? block.original_start_kind === "date" &&
        block.original_start_date !== occurrence.startDate
      : block.original_start_kind === "instant" &&
        new Date(block.original_start_at ?? "").valueOf() !==
          occurrence.start?.valueOf();
    return moved
      ? "Moved occurrence · explicit recurring-event exception"
      : "Modified occurrence · explicit recurring-event exception";
  }
  return "Does not repeat";
}

function categoryDraftSubtype(
  category: CalendarCategory | null,
  currentSubtype: string | null,
) {
  return currentSubtype ?? calendarSubtypesFor(category)[0]?.value ?? null;
}

/**
 * Ordinary version drift is reconciled automatically and never reaches here, so
 * a `conflict` now always means something a person genuinely has to settle.
 * Exhausted automatic recovery is not a disagreement about facts, so it says so
 * rather than borrowing the semantic-conflict wording.
 */
function providerWriteLabel(
  state: CalendarOccurrence["block"]["provider_write_state"],
  detail: CalendarOccurrence["block"]["provider_write_detail"],
  failureReason?: string | null,
) {
  if (state === "synced") return "Confirmed by Google";
  if (state === "conflict" && failureReason === "automatic_rebase_exhausted") {
    return "Google kept changing · not saved yet";
  }
  if (state === "conflict") return "Not saved yet";
  if (state === "failed") return "Google sync failed";
  if (detail === "reauth_required") return "Reconnect Google to finish";
  if (detail === "syncing") return "Syncing with Google";
  if (detail === "retry_wait") return "Saved locally · retry waiting";
  return "Saved locally · pending Google";
}

// Augments (never replaces) providerWriteLabel's coarse summary with a more
// specific, still-safe explanation on demand -- no raw Google error body or
// status. Answers: what happened, will Ion retry, what can the user do.
const failureDetailCopy: Record<
  NonNullable<CalendarOccurrence["block"]["provider_write_failure_class"]>,
  string
> = {
  retryable_quota:
    "Google asked Ion to slow down (rate limit). Ion will retry automatically.",
  retryable_backend:
    "Google had a temporary problem. Ion will retry automatically.",
  retryable_transport:
    "The request to Google didn't complete. Ion will retry automatically.",
  reauthentication_required:
    "Google needs this account reconnected before Ion can finish.",
  stale_precondition:
    "Google's copy of this event changed since Ion last confirmed it.",
  provider_not_found: "Google no longer has this event.",
  duplicate_or_ambiguous_create:
    "Ion couldn't confirm whether Google already created this event. Ion will check and retry automatically.",
  invalid_target:
    "Google rejected this request as invalid. This needs a new change from you.",
  terminal_provider_rejection:
    "Google permanently rejected this change. This needs a new change from you.",
};

/**
 * What Ion says, and offers, for each condition a person genuinely has to
 * settle. Every entry names the actual situation and offers only actions that
 * are truthful for it.
 *
 * There is no generic entry, and that is the point. The old surface asked the
 * owner to choose between "their version" and "Google's version" for any
 * provider disagreement, which turned ordinary version drift -- something Ion
 * resolves by itself -- into a decision. Anything not classified here is not a
 * decision at all; it is Ion's job to finish.
 */
const calendarRecovery = (
  kind: CalendarOccurrence["block"]["provider_recovery_kind"],
) => {
  switch (kind) {
    case "retry_available":
      return {
        explanation:
          "Google changed this event several times while Ion was saving your change, so Ion stopped retrying on its own. Your change is still here.",
        retry: true,
        discard: false,
      };
    case "provider_deleted":
      return {
        explanation:
          "Google deleted this event while Ion was saving your change. Ion won't recreate it, because that would make a different event.",
        retry: false,
        discard: true,
      };
    case "recurrence_target_changed":
      return {
        explanation:
          "This event's recurrence changed in Google, so Ion can no longer tell which occurrence your change belongs to.",
        retry: false,
        discard: true,
      };
    case "duplicate_identity":
      return {
        explanation:
          "Google already has an event with this identity. Ion won't write over it.",
        retry: false,
        discard: true,
      };
    case "reauthentication_required":
      return {
        explanation:
          "Reconnect Google Calendar to finish saving this change. Your change is kept until you do.",
        retry: false,
        discard: false,
      };
    case "provider_rejected":
      return {
        explanation:
          "Google rejected this change and will not accept it as written. This needs a new change from you.",
        retry: false,
        discard: true,
      };
    default:
      return null;
  }
};

const readOnlyReason: Record<string, string> = {
  account_read_only: "Enable Calendar writing for this Google account.",
  reauth_required: "Reconnect Google before editing this event.",
  calendar_disabled: "This calendar is disabled in Ion.",
  calendar_deleted: "This source calendar is no longer available.",
  access_role_read_only: "Google exposes this calendar as read-only.",
  special_event: "Google special event types remain read-only.",
  provider_locked: "Google marks this event as provider-locked.",
  attendees_present: "Events with attendees remain read-only.",
  provider_deleted: "This provider event is no longer active.",
  provider_unconfirmed: "Google has not confirmed a safe editable version yet.",
  recurrence_unsupported:
    "This recurring-event change isn't supported yet. Try a bounded recurrence preset or a single occurrence instead.",
  write_pending:
    "Another change to this recurring series is still syncing with Google. Wait for it to finish before editing another occurrence.",
};

export function CalendarInspector({
  occurrence,
  localTimeZone,
  categoryPending,
  editPending,
  deletePending,
  onCategory,
  onEdit,
  onDelete,
  keepGooglePending,
  applyIonPending,
  onKeepGoogleVersion,
  onApplyIonChanges,
  onClose,
}: {
  occurrence: CalendarOccurrence;
  localTimeZone: string;
  categoryPending: boolean;
  editPending: boolean;
  deletePending: boolean;
  onCategory(category: CalendarCategory | null, subtype: string | null): void;
  onEdit(draft: CalendarEditDraft, undo: CalendarEditDraft | null): void;
  onDelete(draft: CalendarDeleteDraft): void;
  keepGooglePending: boolean;
  applyIonPending: boolean;
  onKeepGoogleVersion(draft: ConflictResolutionDraft): void;
  onApplyIonChanges(draft: ConflictResolutionDraft): void;
  onClose(): void;
}) {
  const block = occurrence.block;
  const sourceTimeZone = block.start_timezone;
  const differentTimeZone =
    !occurrence.allDay && sourceTimeZone && sourceTimeZone !== localTimeZone;
  const category = block.category;
  const currentSubtype = block.category_subtype;
  const [draftCategory, setDraftCategory] = useState<CalendarCategory | null>(
    category,
  );
  const [draftSubtype, setDraftSubtype] = useState<string | null>(
    categoryDraftSubtype(category, currentSubtype),
  );
  const [editing, setEditing] = useState(false);
  const [commandId, setCommandId] = useState(() => crypto.randomUUID());
  const submitLocked = useRef(false);
  const baseline = useRef({
    title: "",
    startDate: "",
    startTime: "",
    endDate: "",
    endTime: "",
  });
  const observedEditPending = useRef(false);
  const [submitted, setSubmitted] = useState(false);
  const [title, setTitle] = useState(block.title);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const recurring = block.recurrence_kind !== "single";
  const [recurrence, setRecurrence] = useState<
    CalendarRecurrencePreset | "custom"
  >(block.recurrence_preset);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleteLockedConfirmed, setDeleteLockedConfirmed] = useState(false);
  const [deleteScope, setDeleteScope] = useState<
    "single" | CalendarRecurrenceScope
  >(recurring ? "occurrence" : "single");
  const [seriesDeleteConfirmed, setSeriesDeleteConfirmed] = useState(false);
  const [deleteCommandId, setDeleteCommandId] = useState(() =>
    crypto.randomUUID(),
  );
  // Which interaction is currently waiting for a recurrence-scope choice.
  // Nothing is dispatched while this is set.
  const [scopeRequest, setScopeRequest] = useState<"edit" | "delete" | null>(
    null,
  );

  useEffect(() => {
    setDraftCategory(category);
    setDraftSubtype(categoryDraftSubtype(category, currentSubtype));
  }, [category, currentSubtype, block.id]);

  useEffect(() => {
    const timezone = block.start_timezone ?? localTimeZone;
    const start = occurrence.allDay
      ? { date: occurrence.startDate ?? "", time: "" }
      : occurrence.start
        ? zonedParts(occurrence.start.toISOString(), timezone)
        : { date: "", time: "" };
    const end = occurrence.allDay
      ? { date: occurrence.endDate ?? "", time: "" }
      : occurrence.end
        ? zonedParts(occurrence.end.toISOString(), timezone)
        : { date: "", time: "" };
    // The values as Google last confirmed them -- never the gesture's proposed
    // seed -- so an Undo restores what was actually there before the change.
    baseline.current = {
      title: block.title,
      startDate: start.date,
      startTime: start.time,
      endDate: end.date,
      endTime: end.time,
    };
    setTitle(block.title);
    setStartDate(start.date);
    setStartTime(start.time);
    setEndDate(end.date);
    setEndTime(end.time);
    setRecurrence(block.recurrence_preset);
    setCommandId(crypto.randomUUID());
    submitLocked.current = false;
    observedEditPending.current = false;
    setSubmitted(false);
    setEditing(false);
    setConfirmingDelete(false);
    setDeleteLockedConfirmed(false);
    setDeleteScope(recurring ? "occurrence" : "single");
    setSeriesDeleteConfirmed(false);
    setDeleteCommandId(crypto.randomUUID());
    setScopeRequest(null);
  }, [
    block.end_at,
    block.end_date,
    block.id,
    block.start_at,
    block.start_date,
    block.start_timezone,
    block.temporal_kind,
    block.title,
    block.recurrence_preset,
    localTimeZone,
    occurrence.allDay,
    occurrence.end,
    occurrence.endDate,
    occurrence.start,
    occurrence.startDate,
    recurring,
  ]);

  useEffect(() => {
    if (editPending) {
      observedEditPending.current = true;
      return;
    }
    if (observedEditPending.current) {
      observedEditPending.current = false;
      submitLocked.current = false;
      setSubmitted(false);
    }
  }, [editPending]);

  const draftSubtypes = calendarSubtypesFor(draftCategory);
  const hasCustomDraftSubtype =
    draftSubtype !== null &&
    !draftSubtypes.some((item) => item.value === draftSubtype);
  const categoryChanged =
    draftCategory !== category || draftSubtype !== currentSubtype;
  // Deliberately not gated on settled provider state: the owner may edit again
  // while the previous write is still on its way to Google. Ion supersedes or
  // queues it; "wait for synchronization" is not something to ask a person.
  const eligible = block.provider_write_capability.eligible;
  const deleteCapability = block.provider_delete_capability ?? {
    eligible: false,
    mode: null,
    reason: "provider_unconfirmed",
  };
  const deleteEligible = deleteCapability.eligible;
  const localCreateCancel = deleteCapability.mode === "local_create_cancel";
  // Drags and resizes commit at drop, so the Inspector only ever performs a
  // form edit. Its draft still names the kind the shared builder expects.
  const editKind = "edit" as const;
  const resizeEdge = "end" as const;
  const startBoundaryValid =
    startDate.length === 10 &&
    (block.temporal_kind === "all_day" || startTime.length === 5);
  const endBoundaryValid =
    endDate.length === 10 &&
    (block.temporal_kind === "all_day" || endTime.length === 5);
  const temporalValid =
    block.temporal_kind === "all_day"
      ? startDate.length === 10 && endDate > startDate
      : Boolean(sourceTimeZone) &&
        startBoundaryValid &&
        endBoundaryValid &&
        `${endDate}T${endTime}` > `${startDate}T${startTime}`;
  // An edit stays reversible, so Save is gated only on the change being valid.
  const formValid = title.trim().length > 0 && temporalValid;
  // Splitting at the first occurrence is identical to All events, so Google
  // omits the option there and so does Ion.
  const recovery = calendarRecovery(block.provider_recovery_kind);
  const splitAvailability = calendarSplitAvailability(
    block,
    occurrenceIsFirstInSeries(occurrence),
  );
  // A repeat-rule change is inherently series-wide, exactly as it is in Google.
  const recurrenceRuleChanged =
    editKind === "edit" &&
    recurrence !== "custom" &&
    recurrence !== "none" &&
    recurrence !== block.recurrence_preset;
  const draftFrom = (
    values: {
      title: string;
      startDate: string;
      startTime: string;
      endDate: string;
      endTime: string;
    },
    scope: "single" | CalendarRecurrenceScope,
    seriesConfirmed: boolean,
    commandIdValue: string,
  ): CalendarEditDraft =>
    buildCalendarEditDraft({
      occurrence,
      editKind,
      resizeEdge,
      values,
      scope,
      seriesConfirmed,
      recurrence: recurrenceRuleChanged ? recurrence : null,
      sourceTimeZone,
      commandId: commandIdValue,
    });

  const buildEditDraft = (
    scope: "single" | CalendarRecurrenceScope,
    seriesConfirmed: boolean,
  ): CalendarEditDraft =>
    draftFrom(
      { title, startDate, startTime, endDate, endTime },
      scope,
      seriesConfirmed,
      commandId,
    );

  /**
   * The same write, aimed back at the values this edit replaced. Ion offers it
   * as Undo rather than restoring silently, so reverting is an ordinary
   * ETag-conditional change the user can see, not a hidden rollback.
   *
   * Two cases are excluded because a reverse write does not undo them. A
   * repeat-rule change restates the rule only in the forward draft, so
   * reversing it is a new deliberate choice. A `this and following` split
   * created a second series, and reversing it would split again into a third
   * rather than rejoining them; rejoining is not an operation Ion offers.
   */
  const buildUndoDraft = (
    scope: "single" | CalendarRecurrenceScope,
    seriesConfirmed: boolean,
  ): CalendarEditDraft | null =>
    recurrenceRuleChanged || scope === "this_and_following"
      ? null
      : draftFrom(
          baseline.current,
          scope,
          seriesConfirmed,
          crypto.randomUUID(),
        );

  const changeTimedStart = (nextDate: string, nextTime: string) => {
    if (editKind === "edit") {
      const previousStart = civilTimedValue(startDate, startTime);
      const previousEnd = civilTimedValue(endDate, endTime);
      const nextStart = civilTimedValue(nextDate, nextTime);
      if (
        previousStart !== null &&
        previousEnd !== null &&
        nextStart !== null &&
        previousEnd > previousStart
      ) {
        const shiftedEnd = civilTimedParts(
          nextStart + (previousEnd - previousStart),
        );
        setEndDate(shiftedEnd.date);
        setEndTime(shiftedEnd.time);
      }
    }
    setStartDate(nextDate);
    setStartTime(nextTime);
  };

  return (
    <aside className="calendar-inspector" aria-label="Event details">
      <div className="calendar-inspector-heading">
        <p className="eyebrow">
          {eligible || deleteEligible ? "Google event" : "Read-only event"}
        </p>
        <button
          className="quiet-button"
          type="button"
          aria-label="Close event details"
          autoFocus
          onClick={onClose}
          disabled={editPending || deletePending}
        >
          Close
        </button>
      </div>
      <h2>{block.title}</h2>

      {editing && eligible ? (
        <form
          className="calendar-create-form calendar-edit-form"
          aria-label="Edit Google event"
          onSubmit={(event) => {
            event.preventDefault();
            if (!formValid || submitLocked.current) return;
            // Google's desktop convention: describe the change, press Save,
            // then choose which occurrences it applies to. Nothing is
            // persisted or dispatched until that scope is chosen, so a
            // cancelled chooser leaves no canonical or provider mutation.
            if (recurring) {
              setScopeRequest("edit");
              return;
            }
            submitLocked.current = true;
            setSubmitted(true);
            onEdit(
              buildEditDraft("single", false),
              buildUndoDraft("single", false),
            );
          }}
        >
          <p className="context-note">Edit only the provider fields below.</p>
          {recurring ? (
            <p className="context-note">
              This event repeats. After you save, Ion asks which occurrences the
              change applies to.
            </p>
          ) : null}
          <label>
            <span>Title</span>
            <input
              autoFocus
              value={title}
              maxLength={512}
              onChange={(event) => setTitle(event.currentTarget.value)}
            />
          </label>
          <div className="calendar-create-time-row">
            <label>
              <span>Starts</span>
              <input
                type="date"
                value={startDate}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  if (block.temporal_kind === "timed") {
                    changeTimedStart(value, startTime);
                  } else {
                    const currentStart = new Date(`${startDate}T12:00:00Z`);
                    const currentEnd = new Date(`${endDate}T12:00:00Z`);
                    const nextStart = new Date(`${value}T12:00:00Z`);
                    if (
                      editKind === "edit" &&
                      !Number.isNaN(currentStart.valueOf()) &&
                      !Number.isNaN(currentEnd.valueOf()) &&
                      !Number.isNaN(nextStart.valueOf())
                    ) {
                      setEndDate(
                        addDays(
                          value,
                          Math.max(
                            1,
                            Math.round(
                              (currentEnd.valueOf() - currentStart.valueOf()) /
                                86_400_000,
                            ),
                          ),
                        ),
                      );
                    }
                    setStartDate(value);
                  }
                }}
              />
            </label>
            <label>
              <span>Ends</span>
              <input
                type="date"
                value={endDate}
                onChange={(event) => setEndDate(event.currentTarget.value)}
              />
            </label>
          </div>
          {block.temporal_kind === "timed" ? (
            <>
              <div className="calendar-create-time-row">
                <label>
                  <span>Start time</span>
                  <input
                    type="time"
                    value={startTime}
                    onChange={(event) =>
                      changeTimedStart(startDate, event.currentTarget.value)
                    }
                  />
                </label>
                <label>
                  <span>End time</span>
                  <input
                    type="time"
                    value={endTime}
                    onChange={(event) => setEndTime(event.currentTarget.value)}
                  />
                </label>
              </div>
              <small>Timezone preserved: {sourceTimeZone}</small>
            </>
          ) : (
            <small>All-day end dates remain civil and end-exclusive.</small>
          )}
          {recurring ? (
            <label>
              <span>Repeat</span>
              <select
                value={recurrence}
                onChange={(event) =>
                  setRecurrence(
                    event.currentTarget.value as
                      CalendarRecurrencePreset | "custom",
                  )
                }
              >
                {recurrence === "custom" ? (
                  <option value="custom">Custom rule (preserved)</option>
                ) : null}
                <option value="daily">Daily</option>
                <option value="weekdays">Every weekday</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
                <option value="yearly">Yearly</option>
              </select>
              <small>Only Ion’s bounded recurrence presets are writable.</small>
            </label>
          ) : null}
          <p className="context-note">
            Save commits durable local intent first. Google is contacted only
            after that transaction, using the last confirmed version.
          </p>
          <div className="calendar-create-actions">
            <button
              className="quiet-button"
              type="button"
              onClick={() => setEditing(false)}
              disabled={editPending || submitted}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!formValid || editPending || submitted}
            >
              {editPending || submitted ? "Saving…" : "Save change"}
            </button>
          </div>
        </form>
      ) : eligible ? (
        <button type="button" onClick={() => setEditing(true)}>
          Edit event
        </button>
      ) : (
        <p className="context-note">
          {readOnlyReason[block.provider_write_capability.reason] ??
            "This event is not eligible for provider changes."}
        </p>
      )}

      {confirmingDelete && deleteEligible ? (
        <section
          className="calendar-delete-confirmation"
          aria-label="Confirm event deletion"
        >
          <h3>
            {localCreateCancel
              ? "Cancel pending creation?"
              : "Delete this event?"}
          </h3>
          <p className="context-note">
            {localCreateCancel
              ? "This create has not reached Google. Ion will remove the local pending event without a provider delete."
              : deleteScope === "series"
                ? "Scope: entire series. Ion will conditionally delete the canonical master; this is not an occurrence cancellation."
                : deleteScope === "this_and_following"
                  ? "Scope: this event and every later one. Ion will shorten the series in Google so these occurrences no longer happen. Earlier occurrences are kept."
                  : recurring
                    ? "Scope: this occurrence only. Ion will preserve Google recurrence exception identity and cancel only this occurrence."
                    : "Scope: this event only. Ion will remove it from Google using the last confirmed version. This cannot be undone in Ion."}
          </p>
          {recurring && !localCreateCancel ? (
            <label>
              <span>Delete scope</span>
              <output aria-label="Delete scope">
                {deleteScope === "series"
                  ? "All events"
                  : deleteScope === "this_and_following"
                    ? "This and following events"
                    : "This event"}
              </output>
              <small>
                <button
                  className="quiet-button"
                  type="button"
                  disabled={deletePending}
                  onClick={() => {
                    setConfirmingDelete(false);
                    setScopeRequest("delete");
                  }}
                >
                  Change scope
                </button>
              </small>
            </label>
          ) : null}
          {(deleteScope === "series" || deleteScope === "this_and_following") &&
          !localCreateCancel ? (
            <label className="calendar-create-check">
              <input
                type="checkbox"
                checked={seriesDeleteConfirmed}
                onChange={(event) =>
                  setSeriesDeleteConfirmed(event.currentTarget.checked)
                }
              />
              <span>
                {deleteScope === "this_and_following"
                  ? "I confirm removing this occurrence and every later one from Google. Earlier occurrences remain."
                  : "I confirm deleting the whole series, including its future occurrences and provider exceptions."}
              </span>
            </label>
          ) : null}
          {block.flexibility === "locked" ? (
            <label className="calendar-create-check">
              <input
                type="checkbox"
                checked={deleteLockedConfirmed}
                onChange={(event) =>
                  setDeleteLockedConfirmed(event.currentTarget.checked)
                }
              />
              <span>I confirm deleting this Ion-locked event.</span>
            </label>
          ) : null}
          <div className="calendar-create-actions">
            <button
              className="quiet-button"
              type="button"
              onClick={() => setConfirmingDelete(false)}
              disabled={deletePending}
            >
              Keep event
            </button>
            <button
              className="danger-button"
              type="button"
              disabled={
                deletePending ||
                (block.flexibility === "locked" && !deleteLockedConfirmed) ||
                ((deleteScope === "series" ||
                  deleteScope === "this_and_following") &&
                  !seriesDeleteConfirmed)
              }
              onClick={() =>
                onDelete({
                  command_id: deleteCommandId,
                  calendar_block_id: block.id,
                  expected_block_revision: block.revision,
                  recurrence_scope: deleteScope,
                  occurrence_original_start:
                    deleteScope === "occurrence" ||
                    deleteScope === "this_and_following"
                      ? occurrenceOriginalStart(occurrence)
                      : null,
                  series_confirmed:
                    (deleteScope === "series" ||
                      deleteScope === "this_and_following") &&
                    seriesDeleteConfirmed,
                  locked_confirmed: deleteLockedConfirmed,
                })
              }
            >
              {deletePending
                ? "Deleting…"
                : localCreateCancel
                  ? "Cancel creation"
                  : deleteScope === "series"
                    ? "Delete entire series"
                    : deleteScope === "this_and_following"
                      ? "Delete this and following"
                      : recurring
                        ? "Cancel occurrence"
                        : "Delete event"}
            </button>
          </div>
        </section>
      ) : deleteEligible ? (
        <button
          className="quiet-button calendar-delete-button"
          type="button"
          onClick={() => {
            // Recurring deletes pick scope first (Google's order), then keep
            // Ion's stronger destructive confirmation.
            if (recurring && !localCreateCancel) {
              setScopeRequest("delete");
              return;
            }
            setConfirmingDelete(true);
          }}
          disabled={editPending || deletePending}
        >
          {localCreateCancel ? "Cancel pending creation" : "Delete event"}
        </button>
      ) : null}

      <label className="calendar-category-editor">
        <span>Ion category</span>
        <select
          aria-label={`${block.title} Ion category`}
          value={draftCategory ?? ""}
          disabled={categoryPending}
          onChange={(event) => {
            const nextCategory = event.currentTarget.value
              ? (event.currentTarget.value as CalendarCategory)
              : null;
            const firstSubtype = calendarSubtypesFor(nextCategory)[0]?.value;
            setDraftCategory(nextCategory);
            setDraftSubtype(firstSubtype ?? null);
          }}
        >
          <option value="">Uncategorized</option>
          {calendarCategories.map((category) => (
            <option key={category} value={category}>
              {calendarCategoryLabels[category]}
            </option>
          ))}
        </select>
        {draftCategory && draftSubtypes.length > 0 ? (
          <select
            aria-label={`${block.title} Ion category subtype`}
            value={draftSubtype ?? draftSubtypes[0].value}
            disabled={categoryPending}
            onChange={(event) => setDraftSubtype(event.currentTarget.value)}
          >
            {hasCustomDraftSubtype ? (
              <option value={draftSubtype!}>
                {calendarSubtypeLabel(draftSubtype!)}
              </option>
            ) : null}
            {draftSubtypes.map((subtype) => (
              <option key={subtype.value} value={subtype.value}>
                {subtype.label}
              </option>
            ))}
          </select>
        ) : null}
        <button
          className="secondary-button calendar-category-save"
          type="button"
          disabled={categoryPending || !categoryChanged}
          onClick={() => onCategory(draftCategory, draftSubtype)}
        >
          {categoryPending ? "Saving…" : "Save category"}
        </button>
        <small>Stored only in Ion; Google event fields remain unchanged.</small>
      </label>
      <dl>
        <div>
          <dt>Ion category</dt>
          <dd>{calendarCategoryDisplay(category, currentSubtype)}</dd>
        </div>
        <div>
          <dt>When</dt>
          <dd>
            {occurrence.allDay ? (
              <>
                {formatDate(occurrence.startDate!)}
                {occurrence.endDate !== addDays(occurrence.startDate!, 1) ? (
                  <span>
                    {" "}
                    through {formatDate(addDays(occurrence.endDate!, -1))}
                  </span>
                ) : null}
                <small>
                  All day · date preserved without a fabricated time
                </small>
              </>
            ) : (
              <>
                {formatDate(localCivilDate(localTimeZone, occurrence.start!))}
                <small>
                  {formatOccurrenceTime(occurrence, localTimeZone)} locally
                </small>
              </>
            )}
          </dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>
            {occurrence.calendar.summary}
            <small>
              {occurrence.account?.display_name ?? "Calendar account"}
            </small>
          </dd>
        </div>
        {block.location ? (
          <div>
            <dt>Location</dt>
            <dd>{block.location}</dd>
          </div>
        ) : null}
        <div>
          <dt>Recurrence</dt>
          <dd>{recurrenceLabel(occurrence)}</dd>
        </div>
        {differentTimeZone ? (
          <div>
            <dt>Original timezone</dt>
            <dd>
              {sourceTimeZone}
              <small>The grid is displayed in {localTimeZone}.</small>
            </dd>
          </div>
        ) : null}
        <div>
          <dt>Calendar state</dt>
          <dd>
            {block.status}
            {block.transparency === "transparent"
              ? " · does not mark time busy"
              : " · occupies calendar time"}
          </dd>
        </div>
        <div>
          <dt>Google write state</dt>
          <dd>
            {block.provider_write_operation &&
            ["delete_event", "delete_series", "cancel_occurrence"].includes(
              block.provider_write_operation,
            ) &&
            block.provider_write_state === "pending"
              ? block.provider_write_detail === "retry_wait"
                ? "Deletion saved locally · retry waiting"
                : block.provider_write_detail === "reauth_required"
                  ? "Deletion saved locally · reconnect Google"
                  : "Deletion pending with Google"
              : providerWriteLabel(
                  block.provider_write_state,
                  block.provider_write_detail,
                  block.provider_write_failure_reason,
                )}
            {block.provider_write_state === "synced" ? null : (
              // Progressive disclosure: the mechanism is worth explaining only
              // while a change is unsettled. A confirmed event says so and stops.
              <small>
                Provider changes use the confirmed event identity and version.
              </small>
            )}
            {block.provider_write_failure_class ? (
              <small className="calendar-write-failure-detail">
                {failureDetailCopy[block.provider_write_failure_class]}
              </small>
            ) : null}
          </dd>
        </div>
      </dl>
      {block.description ? (
        <section>
          <h3>Description</h3>
          <p>{block.description}</p>
        </section>
      ) : null}
      {recovery ? (
        <section
          className="calendar-recovery"
          aria-label="Google Calendar recovery"
        >
          <p className="context-note">{recovery.explanation}</p>
          <div className="calendar-conflict-actions">
            {recovery.retry ? (
              <button
                type="button"
                disabled={applyIonPending}
                onClick={() =>
                  onApplyIonChanges({
                    command_id: crypto.randomUUID(),
                    calendar_block_id: block.id,
                    expected_block_revision: block.revision,
                  })
                }
              >
                {applyIonPending ? "Trying again…" : "Try again"}
              </button>
            ) : null}
            {recovery.discard ? (
              <button
                type="button"
                disabled={keepGooglePending}
                onClick={() =>
                  onKeepGoogleVersion({
                    command_id: crypto.randomUUID(),
                    calendar_block_id: block.id,
                    expected_block_revision: block.revision,
                  })
                }
              >
                {keepGooglePending ? "Discarding…" : "Discard my change"}
              </button>
            ) : null}
          </div>
        </section>
      ) : null}
      {scopeRequest ? (
        <CalendarRecurrenceScopeDialog
          mode={scopeRequest}
          eventTitle={block.title}
          seriesOnly={scopeRequest === "edit" && recurrenceRuleChanged}
          splitAvailable={splitAvailability.available && !recurrenceRuleChanged}
          splitUnavailableReason={splitAvailability.reason}
          pending={scopeRequest === "edit" ? editPending : deletePending}
          onCancel={() => setScopeRequest(null)}
          onChoose={(scope, seriesConfirmed) => {
            setScopeRequest(null);
            if (scopeRequest === "edit") {
              if (submitLocked.current) return;
              submitLocked.current = true;
              setSubmitted(true);
              onEdit(
                buildEditDraft(scope, seriesConfirmed),
                buildUndoDraft(scope, seriesConfirmed),
              );
              return;
            }
            // Choosing the scope is the whole decision. The warning about what
            // cannot be restored lives inside this dialog, so nothing follows
            // it: a second "are you sure" would be asking the same question
            // twice.
            onDelete({
              command_id: deleteCommandId,
              calendar_block_id: block.id,
              expected_block_revision: block.revision,
              recurrence_scope: scope,
              occurrence_original_start:
                scope === "occurrence" || scope === "this_and_following"
                  ? occurrenceOriginalStart(occurrence)
                  : null,
              series_confirmed:
                scope === "series" || scope === "this_and_following",
              locked_confirmed: false,
            });
          }}
        />
      ) : null}
    </aside>
  );
}
