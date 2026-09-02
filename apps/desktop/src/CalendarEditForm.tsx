import { useEffect, useRef, useState } from "react";
import type { CalendarOccurrence } from "./calendarProjection";
import type {
  ChangedField,
  DirectHumanEditDraft,
} from "./calendarWriteContract";

export type CalendarEditDraft = {
  changedFields: ChangedField[];
  draft: DirectHumanEditDraft;
};

/** Local wall-clock value an `<input type="datetime-local">` understands. */
function localInputValue(value: Date | null, timeZone: string) {
  if (!value) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(value);
  const at = (type: string) =>
    parts.find((part) => part.type === type)?.value ?? "";
  return `${at("year")}-${at("month")}-${at("day")}T${at("hour")}:${at("minute")}`;
}

/**
 * The ordinary event edit.
 *
 * Two properties matter more than anything else here, and both are the direct
 * answer to how Phase 2C v1 failed:
 *
 * 1. **Save is never disabled by provider state.** A pending write is not a
 *    reason to refuse the owner's next edit, so this form knows nothing about
 *    provider lifecycle and has no way to consult it.
 * 2. **Only the exact same synchronous submission is de-duplicated.** The guard
 *    below resets as soon as the submission is handed off, so a *newer* edit is
 *    always accepted -- it is a double-click guard, not a provider lock.
 */
export function CalendarEditForm({
  occurrence,
  localTimeZone,
  onSubmit,
}: {
  occurrence: CalendarOccurrence;
  localTimeZone: string;
  onSubmit(draft: CalendarEditDraft): void;
}) {
  const block = occurrence.block;
  const zone = block.start_timezone ?? localTimeZone;
  const [title, setTitle] = useState(block.title);
  const [start, setStart] = useState(() =>
    localInputValue(occurrence.start, zone),
  );
  const [end, setEnd] = useState(() => localInputValue(occurrence.end, zone));
  const submitting = useRef(false);

  // Re-seed from the newest projected values whenever the occurrence changes,
  // including after the owner's own edit settles. The form always describes
  // what the Calendar currently shows.
  useEffect(() => {
    setTitle(block.title);
    setStart(localInputValue(occurrence.start, zone));
    setEnd(localInputValue(occurrence.end, zone));
  }, [
    block.title,
    block.id,
    occurrence.key,
    occurrence.start,
    occurrence.end,
    zone,
  ]);

  const allDay = occurrence.allDay;

  return (
    <form
      className="calendar-edit-form"
      aria-label={`Edit ${block.title}`}
      onSubmit={(event) => {
        event.preventDefault();
        if (submitting.current) return;
        submitting.current = true;
        const changedFields: ChangedField[] = [];
        const draft: DirectHumanEditDraft = {};
        if (title !== block.title) {
          changedFields.push("title");
          draft.title = title;
        }
        if (!allDay) {
          const original = localInputValue(occurrence.start, zone);
          if (start && start !== original) {
            changedFields.push("start");
            draft.start = {
              date_time: new Date(`${start}:00`).toISOString(),
              time_zone: zone,
            };
          }
          const originalEnd = localInputValue(occurrence.end, zone);
          if (end && end !== originalEnd) {
            changedFields.push("end");
            draft.end = {
              date_time: new Date(`${end}:00`).toISOString(),
              time_zone: zone,
            };
          }
        }
        if (changedFields.length > 0) onSubmit({ changedFields, draft });
        // Released immediately: this guards one click, never the next edit.
        submitting.current = false;
      }}
    >
      <label>
        Title
        <input
          value={title}
          maxLength={1024}
          onChange={(event) => setTitle(event.currentTarget.value)}
        />
      </label>
      {allDay ? (
        <p className="context-note">
          All-day times are not editable in Ion yet.
        </p>
      ) : (
        <div className="calendar-edit-times">
          <label>
            Starts
            <input
              type="datetime-local"
              value={start}
              onChange={(event) => setStart(event.currentTarget.value)}
            />
          </label>
          <label>
            Ends
            <input
              type="datetime-local"
              value={end}
              onChange={(event) => setEnd(event.currentTarget.value)}
            />
          </label>
        </div>
      )}
      {/* Never disabled by provider work: the owner may always edit again. */}
      <button type="submit">Save</button>
    </form>
  );
}
