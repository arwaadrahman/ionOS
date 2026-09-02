import {
  CalendarEditDraft,
  CalendarEditKind,
  CalendarEditSeed,
  CalendarRecurrencePreset,
  CalendarRecurrenceScope,
  ProviderDateTime,
} from "./calendar";
import { CalendarOccurrence } from "./calendarProjection";

export type CalendarEditValues = {
  title: string;
  startDate: string;
  startTime: string;
  endDate: string;
  endTime: string;
};

/** The civil date and clock time an instant falls on in a given zone. */
export function zonedParts(value: string, timezone: string) {
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

/**
 * The immutable identity of a single generated occurrence.
 *
 * A moved occurrence keeps the start it was *generated* at, never the start it
 * was moved to, so a later edit still resolves the same instance.
 */
export function occurrenceOriginalStart(
  occurrence: CalendarOccurrence,
): ProviderDateTime | null {
  const block = occurrence.block;
  if (occurrence.recurrenceContext === "single") return null;
  if (occurrence.recurrenceContext === "exception") {
    return block.original_start_kind === "date"
      ? {
          date: block.original_start_date,
          date_time: null,
          timezone: block.original_start_timezone,
        }
      : {
          date: null,
          date_time: block.original_start_at,
          timezone: block.original_start_timezone,
        };
  }
  return occurrence.allDay
    ? { date: occurrence.startDate, date_time: null, timezone: null }
    : {
        date: null,
        date_time: occurrence.start?.toISOString() ?? null,
        timezone: block.start_timezone,
      };
}

/**
 * Whether this occurrence is the one the series starts at.
 *
 * Splitting there would leave an empty old series, so it means the same thing
 * as All events and the option is withheld -- as it is in Google.
 */
export function occurrenceIsFirstInSeries(
  occurrence: CalendarOccurrence,
): boolean {
  const block = occurrence.block;
  return block.temporal_kind === "all_day"
    ? occurrence.startDate === block.start_date
    : occurrence.start?.valueOf() === new Date(block.start_at ?? "").valueOf();
}

/**
 * The one edit-draft shape, shared by every surface that can produce an edit.
 *
 * A drag, a resize, and an Inspector Save describe the same intent and must
 * reach the provider as the same write; building the draft in one place is what
 * keeps a direct gesture from drifting into a different contract than the form.
 */
export function buildCalendarEditDraft({
  occurrence,
  editKind,
  resizeEdge = "end",
  values,
  scope,
  seriesConfirmed,
  recurrence = null,
  sourceTimeZone,
  commandId,
}: {
  occurrence: CalendarOccurrence;
  editKind: CalendarEditKind;
  resizeEdge?: "start" | "end";
  values: CalendarEditValues;
  scope: "single" | CalendarRecurrenceScope;
  seriesConfirmed: boolean;
  /** Only a whole-series edit may restate the repeat rule. */
  recurrence?: Exclude<CalendarRecurrencePreset, "none"> | null;
  sourceTimeZone: string | null;
  commandId: string;
}): CalendarEditDraft {
  const block = occurrence.block;
  const resizeStart = editKind === "resize" && resizeEdge === "start";
  return {
    command_id: commandId,
    calendar_block_id: block.id,
    edit_kind: editKind,
    expected_block_revision: block.revision,
    title: editKind === "edit" ? values.title.trim() : null,
    start_date: editKind === "resize" && !resizeStart ? null : values.startDate,
    end_date: editKind === "move" || resizeStart ? null : values.endDate,
    start_time:
      block.temporal_kind === "timed" && (editKind !== "resize" || resizeStart)
        ? values.startTime
        : null,
    end_time:
      block.temporal_kind === "timed" && editKind !== "move" && !resizeStart
        ? values.endTime
        : null,
    timezone: block.temporal_kind === "timed" ? sourceTimeZone : null,
    recurrence_scope: scope,
    occurrence_original_start:
      scope === "occurrence" || scope === "this_and_following"
        ? occurrenceOriginalStart(occurrence)
        : null,
    recurrence: scope === "series" ? recurrence : null,
    recurrence_risk_confirmed: seriesConfirmed,
    locked_confirmed: false,
  };
}

/**
 * The values a direct gesture proposes, and the values it replaced.
 *
 * A gesture commits at drop, so both are read from the occurrence and its seed
 * rather than from form state: `proposed` is what the user dragged to, and
 * `previous` is what Undo restores.
 */
export function gestureEditValues(
  occurrence: CalendarOccurrence,
  seed: CalendarEditSeed,
  timezone: string,
): { proposed: CalendarEditValues; previous: CalendarEditValues } {
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
  const previous: CalendarEditValues = {
    title: occurrence.block.title,
    startDate: start.date,
    startTime: start.time,
    endDate: end.date,
    endTime: end.time,
  };
  return {
    proposed: {
      title: occurrence.block.title,
      startDate: seed.startDate ?? previous.startDate,
      startTime: seed.startTime ?? previous.startTime,
      endDate: seed.endDate ?? previous.endDate,
      endTime: seed.endTime ?? previous.endTime,
    },
    previous,
  };
}
