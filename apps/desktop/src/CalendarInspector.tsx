import { useEffect, useState } from "react";
import {
  addDays,
  CalendarOccurrence,
  formatOccurrenceTime,
  localCivilDate,
} from "./calendarProjection";
import {
  CalendarCategory,
  CalendarDeleteDraft,
  CalendarEditDraft,
  CalendarEditSeed,
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

function zonedParts(value: string, timezone: string) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(value));
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? "";
  return {
    date: `${part("year")}-${part("month")}-${part("day")}`,
    time: `${part("hour")}:${part("minute")}`,
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

function providerWriteLabel(
  state: CalendarOccurrence["block"]["provider_write_state"],
  detail: CalendarOccurrence["block"]["provider_write_detail"],
) {
  if (state === "synced") return "Confirmed by Google";
  if (state === "conflict") return "Changed elsewhere · needs review";
  if (state === "failed") return "Google sync failed";
  if (detail === "reauth_required") return "Reconnect Google to finish";
  if (detail === "syncing") return "Syncing with Google";
  if (detail === "retry_wait") return "Saved locally · retry waiting";
  return "Saved locally · pending Google";
}

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
  recurrence_unsupported: "Recurring-event changes are deferred to Phase 2C-5.",
  write_pending: "Finish reviewing the current Google write state first.",
};

export function CalendarInspector({
  occurrence,
  localTimeZone,
  categoryPending,
  editPending,
  deletePending,
  editSeed,
  onCategory,
  onEdit,
  onDelete,
  onClose,
}: {
  occurrence: CalendarOccurrence;
  localTimeZone: string;
  categoryPending: boolean;
  editPending: boolean;
  deletePending: boolean;
  editSeed: CalendarEditSeed | null;
  onCategory(category: CalendarCategory | null, subtype: string | null): void;
  onEdit(draft: CalendarEditDraft): void;
  onDelete(draft: CalendarDeleteDraft): void;
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
  const [editing, setEditing] = useState(Boolean(editSeed));
  const [commandId, setCommandId] = useState(() => crypto.randomUUID());
  const [title, setTitle] = useState(block.title);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [lockedConfirmed, setLockedConfirmed] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleteLockedConfirmed, setDeleteLockedConfirmed] = useState(false);
  const [deleteCommandId, setDeleteCommandId] = useState(() =>
    crypto.randomUUID(),
  );

  useEffect(() => {
    setDraftCategory(category);
    setDraftSubtype(categoryDraftSubtype(category, currentSubtype));
  }, [category, currentSubtype, block.id]);

  useEffect(() => {
    const timezone = block.start_timezone ?? localTimeZone;
    const start =
      block.temporal_kind === "timed" && block.start_at
        ? zonedParts(block.start_at, timezone)
        : { date: block.start_date ?? "", time: "" };
    const end =
      block.temporal_kind === "timed" && block.end_at
        ? zonedParts(block.end_at, timezone)
        : { date: block.end_date ?? "", time: "" };
    setTitle(block.title);
    setStartDate(editSeed?.startDate ?? start.date);
    setStartTime(editSeed?.startTime ?? start.time);
    setEndDate(editSeed?.endDate ?? end.date);
    setEndTime(editSeed?.endTime ?? end.time);
    setLockedConfirmed(false);
    setCommandId(crypto.randomUUID());
    setEditing(Boolean(editSeed));
    setConfirmingDelete(false);
    setDeleteLockedConfirmed(false);
    setDeleteCommandId(crypto.randomUUID());
  }, [
    block.end_at,
    block.end_date,
    block.id,
    block.start_at,
    block.start_date,
    block.start_timezone,
    block.temporal_kind,
    block.title,
    editSeed,
    localTimeZone,
  ]);

  const draftSubtypes = calendarSubtypesFor(draftCategory);
  const hasCustomDraftSubtype =
    draftSubtype !== null &&
    !draftSubtypes.some((item) => item.value === draftSubtype);
  const categoryChanged =
    draftCategory !== category || draftSubtype !== currentSubtype;
  const eligible =
    block.provider_write_capability.eligible &&
    block.provider_write_state === "synced" &&
    block.recurrence_kind === "single";
  const deleteCapability = block.provider_delete_capability ?? {
    eligible: false,
    mode: null,
    reason: "provider_unconfirmed",
  };
  const deleteEligible = deleteCapability.eligible;
  const localCreateCancel = deleteCapability.mode === "local_create_cancel";
  const temporalValid =
    block.temporal_kind === "all_day"
      ? startDate.length === 10 && endDate > startDate
      : Boolean(sourceTimeZone) &&
        startDate.length === 10 &&
        endDate.length === 10 &&
        startTime.length === 5 &&
        endTime.length === 5 &&
        `${endDate}T${endTime}` > `${startDate}T${startTime}`;
  const formValid =
    title.trim().length > 0 &&
    temporalValid &&
    (block.flexibility !== "locked" || lockedConfirmed);

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
          autoFocus={!editSeed}
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
            if (!formValid) return;
            const editKind = editSeed?.editKind ?? "edit";
            onEdit({
              command_id: commandId,
              calendar_block_id: block.id,
              edit_kind: editKind,
              expected_block_revision: block.revision,
              title: editKind === "edit" ? title.trim() : null,
              start_date: editKind === "resize" ? null : startDate,
              end_date: editKind === "move" ? null : endDate,
              start_time:
                block.temporal_kind === "timed" && editKind !== "resize"
                  ? startTime
                  : null,
              end_time:
                block.temporal_kind === "timed" && editKind !== "move"
                  ? endTime
                  : null,
              timezone: block.temporal_kind === "timed" ? sourceTimeZone : null,
              locked_confirmed: lockedConfirmed,
            });
          }}
        >
          <p className="context-note">
            {editSeed?.editKind === "move"
              ? "Review the moved start. Duration is preserved by Ion."
              : editSeed?.editKind === "resize"
                ? "Review the resized end before saving."
                : "Edit only the provider fields below."}
          </p>
          {editSeed?.editKind !== "move" && editSeed?.editKind !== "resize" ? (
            <label>
              <span>Title</span>
              <input
                autoFocus
                value={title}
                maxLength={512}
                onChange={(event) => setTitle(event.currentTarget.value)}
              />
            </label>
          ) : null}
          <div className="calendar-create-time-row">
            {editSeed?.editKind !== "resize" ? (
              <label>
                <span>Starts</span>
                <input
                  type="date"
                  value={startDate}
                  onChange={(event) => setStartDate(event.currentTarget.value)}
                />
              </label>
            ) : null}
            {editSeed?.editKind !== "move" ? (
              <label>
                <span>Ends</span>
                <input
                  type="date"
                  value={endDate}
                  onChange={(event) => setEndDate(event.currentTarget.value)}
                />
              </label>
            ) : null}
          </div>
          {block.temporal_kind === "timed" ? (
            <>
              <div className="calendar-create-time-row">
                {editSeed?.editKind !== "resize" ? (
                  <label>
                    <span>Start time</span>
                    <input
                      type="time"
                      value={startTime}
                      onChange={(event) =>
                        setStartTime(event.currentTarget.value)
                      }
                    />
                  </label>
                ) : null}
                {editSeed?.editKind !== "move" ? (
                  <label>
                    <span>End time</span>
                    <input
                      type="time"
                      value={endTime}
                      onChange={(event) =>
                        setEndTime(event.currentTarget.value)
                      }
                    />
                  </label>
                ) : null}
              </div>
              <small>Timezone preserved: {sourceTimeZone}</small>
            </>
          ) : (
            <small>All-day end dates remain civil and end-exclusive.</small>
          )}
          {block.flexibility === "locked" ? (
            <label className="calendar-create-check">
              <input
                type="checkbox"
                checked={lockedConfirmed}
                onChange={(event) =>
                  setLockedConfirmed(event.currentTarget.checked)
                }
              />
              <span>I confirm changing this Ion-locked event.</span>
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
              disabled={editPending}
            >
              Cancel
            </button>
            <button type="submit" disabled={!formValid || editPending}>
              {editPending ? "Saving…" : "Save change"}
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
              : "Scope: this event only. Ion will remove it from Google using the last confirmed version. This cannot be undone in Ion."}
          </p>
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
                (block.flexibility === "locked" && !deleteLockedConfirmed)
              }
              onClick={() =>
                onDelete({
                  command_id: deleteCommandId,
                  calendar_block_id: block.id,
                  expected_block_revision: block.revision,
                  locked_confirmed: deleteLockedConfirmed,
                })
              }
            >
              {deletePending
                ? "Deleting…"
                : localCreateCancel
                  ? "Cancel creation"
                  : "Delete event"}
            </button>
          </div>
        </section>
      ) : deleteEligible ? (
        <button
          className="quiet-button calendar-delete-button"
          type="button"
          onClick={() => setConfirmingDelete(true)}
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
            {block.provider_write_operation === "delete_event" &&
            block.provider_write_state === "pending"
              ? block.provider_write_detail === "retry_wait"
                ? "Deletion saved locally · retry waiting"
                : block.provider_write_detail === "reauth_required"
                  ? "Deletion saved locally · reconnect Google"
                  : "Deletion pending with Google"
              : providerWriteLabel(
                  block.provider_write_state,
                  block.provider_write_detail,
                )}
            <small>
              Provider changes use the confirmed event identity and version.
            </small>
          </dd>
        </div>
      </dl>
      {block.description ? (
        <section>
          <h3>Description</h3>
          <p>{block.description}</p>
        </section>
      ) : null}
      {block.provider_write_state === "conflict" ? (
        <p className="context-note">
          Google changed this event elsewhere. Your bounded Ion intent remains
          stored for later conflict review; Ion did not overwrite either side.
        </p>
      ) : null}
    </aside>
  );
}
