import {
  memo,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent,
} from "react";
import {
  CalendarCreateSeed,
  CalendarDensity,
  CalendarEditSeed,
  calendarDensityHeights,
} from "./calendar";
import {
  CalendarOccurrence,
  CalendarRange,
  categoryColor,
  formatOccurrenceTime,
  localCivilDate,
  minuteOfDay,
  occurrencesForDay,
  timedSegmentsForDay,
} from "./calendarProjection";

const hours = Array.from({ length: 24 }, (_, index) => index);
const MINIMUM_TIMED_MINUTES = 15;

type DirectKind = "move" | "resize-start" | "resize-end";

type DirectPreview = {
  occurrence: CalendarOccurrence;
  kind: DirectKind;
  date: string;
  startMinute: number;
  durationMinutes: number;
  seed: CalendarEditSeed;
};

type DirectGesture = {
  occurrence: CalendarOccurrence;
  kind: DirectKind;
  pointerId: number;
  originX: number;
  originY: number;
  grabOffsetMinutes: number;
  startDate: string;
  startMinute: number;
  endDate: string;
  endMinute: number;
  moved: boolean;
};

function dayLabel(date: string) {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: "UTC",
    weekday: "short",
    month: "short",
    day: "numeric",
  }).format(new Date(`${date}T12:00:00Z`));
}

function clockTime(minutes: number) {
  const normalized = ((minutes % 1440) + 1440) % 1440;
  const hour = Math.floor(normalized / 60);
  const minute = normalized % 60;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

function addCivilDays(value: string, amount: number) {
  const next = new Date(`${value}T12:00:00Z`);
  next.setUTCDate(next.getUTCDate() + amount);
  return next.toISOString().slice(0, 10);
}

function civilDayDifference(from: string, to: string) {
  return Math.round(
    (new Date(`${to}T12:00:00Z`).valueOf() -
      new Date(`${from}T12:00:00Z`).valueOf()) /
      86_400_000,
  );
}

export const CalendarTimeGrid = memo(function CalendarTimeGrid({
  range,
  occurrences,
  localTimeZone,
  today,
  now = new Date(),
  density,
  selectedKey = null,
  onSelect,
  onCreate,
  onEditSeed,
}: {
  range: CalendarRange;
  occurrences: CalendarOccurrence[];
  localTimeZone: string;
  today: string;
  now?: Date;
  density: CalendarDensity;
  selectedKey?: string | null;
  onSelect(occurrence: CalendarOccurrence): void;
  onCreate(seed: CalendarCreateSeed): void;
  onEditSeed(occurrence: CalendarOccurrence, seed: CalendarEditSeed): void;
}) {
  const hourHeight = calendarDensityHeights[density];
  const grid = useRef<HTMLElement>(null);
  const dragStart = useRef<{ date: string; minute: number } | null>(null);
  const directGesture = useRef<DirectGesture | null>(null);
  const directPreview = useRef<DirectPreview | null>(null);
  const suppressClick = useRef<string | null>(null);
  const [preview, setPreview] = useState<DirectPreview | null>(null);
  useEffect(() => {
    const stage = grid.current?.closest<HTMLElement>(".calendar-stage");
    if (stage) stage.scrollTop = 7 * hourHeight;
  }, [hourHeight, range.start]);
  useEffect(() => {
    const cancelOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || !directGesture.current) return;
      // Clearing the gesture ref (rather than calling finishDirect) means
      // the eventual pointerup for this gesture finds no active gesture and
      // commits nothing -- no provider/local write from a cancelled drag or
      // resize.
      directGesture.current = null;
      setDirectPreview(null);
    };
    window.addEventListener("keydown", cancelOnEscape);
    return () => window.removeEventListener("keydown", cancelOnEscape);
  }, []);
  const nowMinutes = minuteOfDay(now, localTimeZone);
  const dayLayouts = useMemo(
    () =>
      range.days.map((date) => {
        const day = occurrencesForDay(occurrences, date, localTimeZone);
        return {
          date,
          allDay: day.filter((item) => item.allDay),
          segments: timedSegmentsForDay(day, date, localTimeZone),
        };
      }),
    [localTimeZone, occurrences, range.days],
  );
  const minuteAt = (event: PointerEvent<HTMLElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const raw = ((event.clientY - bounds.top) / bounds.height) * 24 * 60;
    return Math.max(0, Math.min(23 * 60 + 45, Math.round(raw / 15) * 15));
  };
  const pointInGrid = (clientX: number, clientY: number) => {
    const columns = Array.from(
      grid.current?.querySelectorAll<HTMLElement>("[data-calendar-date]") ?? [],
    );
    if (columns.length === 0) return null;
    const column =
      columns.find((item) => {
        const bounds = item.getBoundingClientRect();
        return clientX >= bounds.left && clientX <= bounds.right;
      }) ??
      columns.reduce((nearest, item) => {
        const itemBounds = item.getBoundingClientRect();
        const nearestBounds = nearest.getBoundingClientRect();
        const itemDistance = Math.abs(
          clientX - (itemBounds.left + itemBounds.right) / 2,
        );
        const nearestDistance = Math.abs(
          clientX - (nearestBounds.left + nearestBounds.right) / 2,
        );
        return itemDistance < nearestDistance ? item : nearest;
      });
    const bounds = column.getBoundingClientRect();
    if (bounds.height <= 0) return null;
    const raw = ((clientY - bounds.top) / bounds.height) * 24 * 60;
    return {
      date: column.dataset.calendarDate!,
      minute: Math.max(0, Math.min(23 * 60 + 45, Math.round(raw / 15) * 15)),
    };
  };

  const setDirectPreview = (next: DirectPreview | null) => {
    directPreview.current = next;
    setPreview(next);
  };

  const previewForPoint = (
    gesture: DirectGesture,
    date: string,
    minute: number,
  ): DirectPreview | null => {
    const totalDuration = Math.max(
      MINIMUM_TIMED_MINUTES,
      civilDayDifference(gesture.startDate, gesture.endDate) * 1440 +
        gesture.endMinute -
        gesture.startMinute,
    );
    if (gesture.kind === "move") {
      const startMinute = Math.max(
        0,
        Math.min(23 * 60 + 45, minute - gesture.grabOffsetMinutes),
      );
      const endTotal = startMinute + totalDuration;
      const endDate = addCivilDays(date, Math.floor(endTotal / 1440));
      return {
        occurrence: gesture.occurrence,
        kind: gesture.kind,
        date,
        startMinute,
        durationMinutes: totalDuration,
        seed: {
          editKind: "move",
          startDate: date,
          startTime: clockTime(startMinute),
          endDate,
          endTime: clockTime(endTotal),
        },
      };
    }

    const targetFromStart =
      civilDayDifference(gesture.startDate, date) * 1440 + minute;
    const fixedEndFromStart =
      civilDayDifference(gesture.startDate, gesture.endDate) * 1440 +
      gesture.endMinute;
    if (gesture.kind === "resize-end") {
      const endFromStart = Math.max(
        gesture.startMinute + MINIMUM_TIMED_MINUTES,
        targetFromStart,
      );
      const endDate = addCivilDays(
        gesture.startDate,
        Math.floor(endFromStart / 1440),
      );
      return {
        occurrence: gesture.occurrence,
        kind: gesture.kind,
        date: gesture.startDate,
        startMinute: gesture.startMinute,
        durationMinutes: endFromStart - gesture.startMinute,
        seed: {
          editKind: "resize",
          resizeEdge: "end",
          startDate: gesture.startDate,
          startTime: clockTime(gesture.startMinute),
          endDate,
          endTime: clockTime(endFromStart),
        },
      };
    }

    const startFromOrigin = Math.min(
      fixedEndFromStart - MINIMUM_TIMED_MINUTES,
      targetFromStart,
    );
    const startDate = addCivilDays(
      gesture.startDate,
      Math.floor(startFromOrigin / 1440),
    );
    const startMinute = ((startFromOrigin % 1440) + 1440) % 1440;
    return {
      occurrence: gesture.occurrence,
      kind: gesture.kind,
      date: startDate,
      startMinute,
      durationMinutes: fixedEndFromStart - startFromOrigin,
      seed: {
        editKind: "resize",
        resizeEdge: "start",
        startDate,
        startTime: clockTime(startMinute),
        endDate: gesture.endDate,
        endTime: clockTime(gesture.endMinute),
      },
    };
  };

  const beginDirect = (
    event: PointerEvent<HTMLElement>,
    occurrence: CalendarOccurrence,
    kind: DirectKind,
  ) => {
    if (event.button !== 0 || !occurrence.start || !occurrence.end) return;
    const point = pointInGrid(event.clientX, event.clientY);
    if (!point) return;
    const startDate = localCivilDate(localTimeZone, occurrence.start);
    const endDate = localCivilDate(localTimeZone, occurrence.end);
    const startMinute = minuteOfDay(occurrence.start, localTimeZone);
    const endMinute = minuteOfDay(occurrence.end, localTimeZone);
    directGesture.current = {
      occurrence,
      kind,
      pointerId: event.pointerId,
      originX: event.clientX,
      originY: event.clientY,
      grabOffsetMinutes:
        kind === "move" ? Math.max(0, point.minute - startMinute) : 0,
      startDate,
      startMinute,
      endDate,
      endMinute,
      moved: false,
    };
    event.stopPropagation();
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const moveDirect = (event: PointerEvent<HTMLElement>) => {
    const gesture = directGesture.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    const distance = Math.hypot(
      event.clientX - gesture.originX,
      event.clientY - gesture.originY,
    );
    if (!gesture.moved && distance < 4) return;
    gesture.moved = true;
    const point = pointInGrid(event.clientX, event.clientY);
    if (!point) return;
    event.preventDefault();
    setDirectPreview(previewForPoint(gesture, point.date, point.minute));
  };

  const finishDirect = (
    event: PointerEvent<HTMLElement>,
    cancelled = false,
  ) => {
    const gesture = directGesture.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    const finalPreview = directPreview.current;
    directGesture.current = null;
    setDirectPreview(null);
    event.stopPropagation();
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    if (!cancelled && gesture.moved && finalPreview) {
      suppressClick.current = gesture.occurrence.key;
      onEditSeed(gesture.occurrence, finalPreview.seed);
    }
  };
  const finishCreate = (date: string, start: number, finish: number) => {
    const first = Math.min(start, finish);
    const last = Math.max(start, finish);
    const end = Math.min(23 * 60 + 59, last === first ? first + 60 : last);
    onCreate({
      date,
      allDay: false,
      startTime: clockTime(first),
      endTime: clockTime(end),
    });
  };

  return (
    <section
      ref={grid}
      className="calendar-time-view"
      aria-label="Calendar time grid"
      style={
        {
          "--calendar-columns": `var(--calendar-time-gutter) repeat(${range.days.length}, minmax(0, 1fr))`,
          "--calendar-hours-height": `${24 * hourHeight}px`,
          "--hour-height": `${hourHeight}px`,
        } as CSSProperties
      }
    >
      <div className="calendar-grid-header">
        <div className="calendar-day-headings">
          <span aria-hidden="true" />
          {range.days.map((date) => (
            <div className={date === today ? "is-today" : ""} key={date}>
              <span>{dayLabel(date)}</span>
              {date === today ? <strong>Today</strong> : null}
            </div>
          ))}
        </div>
        <div className="calendar-all-day-row">
          <span>All day</span>
          {dayLayouts.map(({ allDay, date }) => {
            return (
              <div className={date === today ? "is-today" : ""} key={date}>
                <button
                  className="calendar-all-day-create-target"
                  type="button"
                  aria-label={`Create all-day event on ${date}`}
                  onClick={() =>
                    onCreate({
                      date,
                      allDay: true,
                      startTime: null,
                      endTime: null,
                    })
                  }
                />
                {allDay.map((occurrence) => (
                  <EventButton
                    key={occurrence.key}
                    occurrence={occurrence}
                    localTimeZone={localTimeZone}
                    detail="title"
                    onSelect={onSelect}
                  />
                ))}
              </div>
            );
          })}
        </div>
      </div>
      <div className="calendar-time-scroll">
        <div className="calendar-time-canvas">
          <div className="calendar-hour-rail" aria-hidden="true">
            {hours.map((hour) => (
              <span key={hour} style={{ top: `${hour * hourHeight}px` }}>
                {hour === 0
                  ? "12 AM"
                  : hour < 12
                    ? `${hour} AM`
                    : hour === 12
                      ? "12 PM"
                      : `${hour - 12} PM`}
              </span>
            ))}
          </div>
          {dayLayouts.map(({ date, segments }) => {
            return (
              <div
                className={`calendar-time-column ${date === today ? "is-today" : ""}`}
                key={date}
                data-calendar-date={date}
              >
                <button
                  className="calendar-time-create-target"
                  type="button"
                  aria-label={`Create timed event on ${date}`}
                  onPointerDown={(event) => {
                    if (event.button !== 0) return;
                    dragStart.current = { date, minute: minuteAt(event) };
                    event.currentTarget.setPointerCapture(event.pointerId);
                  }}
                  onPointerUp={(event) => {
                    const start = dragStart.current;
                    dragStart.current = null;
                    if (!start || start.date !== date) return;
                    finishCreate(date, start.minute, minuteAt(event));
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      finishCreate(date, 9 * 60, 10 * 60);
                    }
                  }}
                />
                {date === today ? (
                  <div
                    className="calendar-now-line"
                    style={{ top: `${(nowMinutes / 60) * hourHeight}px` }}
                    aria-label="Current time"
                  />
                ) : null}
                {segments.map((segment) => {
                  const isDirectOrigin =
                    preview?.occurrence.key === segment.occurrence.key;
                  const width = 100 / segment.columnCount;
                  const eventHeight = Math.max(
                    20,
                    ((segment.endMinute - segment.startMinute) / 60) *
                      hourHeight,
                  );
                  const detail =
                    eventHeight < 30
                      ? "title"
                      : eventHeight < 48
                        ? "title-two-line"
                        : eventHeight < 100
                          ? "time"
                          : "full";
                  return (
                    <div
                      className={`calendar-timed-position${
                        isDirectOrigin ? " is-direct-origin" : ""
                      }`}
                      key={segment.occurrence.key}
                      style={{
                        top: `${(segment.startMinute / 60) * hourHeight}px`,
                        height: `${eventHeight}px`,
                        left: `${segment.column * width}%`,
                        width: `${width}%`,
                      }}
                    >
                      <EventButton
                        occurrence={segment.occurrence}
                        localTimeZone={localTimeZone}
                        detail={detail}
                        selected={segment.occurrence.key === selectedKey}
                        onSelect={onSelect}
                        directManipulation={
                          // Deliberately not gated on settled provider state:
                          // the owner may drag the same event again while the
                          // previous write is still on its way to Google.
                          segment.occurrence.block.provider_write_capability
                            .eligible &&
                          segment.occurrence.block.start_timezone ===
                            localTimeZone
                        }
                        onPointerDown={(event) => {
                          beginDirect(event, segment.occurrence, "move");
                        }}
                        onPointerMove={moveDirect}
                        onPointerUp={finishDirect}
                        onPointerCancel={(event) => finishDirect(event, true)}
                        suppressClick={suppressClick}
                      />
                      {segment.occurrence.block.provider_write_capability
                        .eligible &&
                      segment.occurrence.block.start_timezone ===
                        localTimeZone ? (
                        <>
                          <button
                            type="button"
                            className="calendar-event-resize-handle calendar-event-resize-handle--start"
                            aria-label={`Resize start of ${segment.occurrence.block.title}`}
                            title="Drag the top edge to resize"
                            onClick={(event) => event.stopPropagation()}
                            onPointerDown={(event) =>
                              beginDirect(
                                event,
                                segment.occurrence,
                                "resize-start",
                              )
                            }
                            onPointerMove={moveDirect}
                            onPointerUp={finishDirect}
                            onPointerCancel={(event) =>
                              finishDirect(event, true)
                            }
                          />
                          <button
                            type="button"
                            className="calendar-event-resize-handle calendar-event-resize-handle--end"
                            aria-label={`Resize end of ${segment.occurrence.block.title}`}
                            title="Drag the bottom edge to resize"
                            onClick={(event) => event.stopPropagation()}
                            onPointerDown={(event) =>
                              beginDirect(
                                event,
                                segment.occurrence,
                                "resize-end",
                              )
                            }
                            onPointerMove={moveDirect}
                            onPointerUp={finishDirect}
                            onPointerCancel={(event) =>
                              finishDirect(event, true)
                            }
                          />
                        </>
                      ) : null}
                    </div>
                  );
                })}
                {preview?.date === date ? (
                  <div
                    className="calendar-direct-preview"
                    data-calendar-preview={preview.kind}
                    aria-hidden="true"
                    style={{
                      top: `${(preview.startMinute / 60) * hourHeight}px`,
                      height: `${Math.max(
                        20,
                        (preview.durationMinutes / 60) * hourHeight,
                      )}px`,
                    }}
                  >
                    <strong>{preview.occurrence.block.title}</strong>
                    <span>
                      {clockTime(preview.startMinute)}–
                      {clockTime(preview.startMinute + preview.durationMinutes)}
                    </span>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
});

export const EventButton = memo(function EventButton({
  occurrence,
  localTimeZone,
  detail,
  selected = false,
  onSelect,
  directManipulation = false,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onPointerCancel,
  suppressClick,
}: {
  occurrence: CalendarOccurrence;
  localTimeZone: string;
  detail: "title" | "title-two-line" | "time" | "full";
  selected?: boolean;
  onSelect(occurrence: CalendarOccurrence): void;
  directManipulation?: boolean;
  onPointerDown?(event: PointerEvent<HTMLButtonElement>): void;
  onPointerMove?(event: PointerEvent<HTMLButtonElement>): void;
  onPointerUp?(event: PointerEvent<HTMLButtonElement>): void;
  onPointerCancel?(event: PointerEvent<HTMLButtonElement>): void;
  suppressClick?: { current: string | null };
}) {
  const color = categoryColor(
    occurrence.block.category,
    occurrence.block.category_subtype,
  );
  const time = formatOccurrenceTime(occurrence, localTimeZone);
  return (
    <button
      type="button"
      className={`calendar-event calendar-event--${detail}`}
      style={
        {
          "--event-accent": color.accent,
          "--event-fill": color.fill,
          "--event-strong-fill": color.strongFill,
          "--event-text": color.text,
        } as React.CSSProperties
      }
      aria-label={`${occurrence.block.title}, ${time}${selected ? ", selected" : ""}`}
      title={`${occurrence.block.title} · ${time}`}
      aria-current={selected ? "true" : undefined}
      data-write-state={occurrence.block.provider_write_state}
      data-selected={selected ? "true" : undefined}
      data-direct-manipulation={directManipulation ? "enabled" : undefined}
      onPointerDown={(event) => {
        event.stopPropagation();
        if (directManipulation) onPointerDown?.(event);
      }}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerCancel}
      onClick={(event) => {
        event.stopPropagation();
        if (suppressClick?.current === occurrence.key) {
          suppressClick.current = null;
          return;
        }
        onSelect(occurrence);
      }}
    >
      <strong>{occurrence.block.title}</strong>
      {detail === "time" || detail === "full" ? <span>{time}</span> : null}
      {occurrence.block.provider_write_state !== "synced" ? (
        <small className="calendar-event-write-state">
          {occurrence.block.provider_write_detail === "syncing"
            ? "Syncing"
            : occurrence.block.provider_write_state === "failed"
              ? "Google sync failed"
              : // Exhausted automatic recovery is not a disagreement about
                // facts, so it must not borrow review wording.
                occurrence.block.provider_write_state === "conflict" &&
                  occurrence.block.provider_write_failure_reason ===
                    "automatic_rebase_exhausted"
                ? "Not saved yet"
                : occurrence.block.provider_write_state === "conflict"
                  ? // Every condition a person must settle is classified, so
                    // the tile never has to say "review this" generically.
                    "Not saved yet"
                  : occurrence.block.provider_write_detail === "reauth_required"
                    ? "Reconnect Google"
                    : "Pending Google"}
        </small>
      ) : null}
    </button>
  );
});
