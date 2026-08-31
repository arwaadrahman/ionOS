import {
  memo,
  useEffect,
  useMemo,
  useRef,
  type CSSProperties,
  type DragEvent as ReactDragEvent,
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
  minuteOfDay,
  occurrencesForDay,
  timedSegmentsForDay,
} from "./calendarProjection";

const hours = Array.from({ length: 24 }, (_, index) => index);

function dayLabel(date: string) {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: "UTC",
    weekday: "short",
    month: "short",
    day: "numeric",
  }).format(new Date(`${date}T12:00:00Z`));
}

function clockTime(minutes: number) {
  const hour = Math.floor(minutes / 60);
  const minute = minutes % 60;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

export const CalendarTimeGrid = memo(function CalendarTimeGrid({
  range,
  occurrences,
  localTimeZone,
  today,
  now = new Date(),
  density,
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
  onSelect(occurrence: CalendarOccurrence): void;
  onCreate(seed: CalendarCreateSeed): void;
  onEditSeed(occurrence: CalendarOccurrence, seed: CalendarEditSeed): void;
}) {
  const hourHeight = calendarDensityHeights[density];
  const grid = useRef<HTMLElement>(null);
  const dragStart = useRef<{ date: string; minute: number } | null>(null);
  const editDrag = useRef<{
    occurrence: CalendarOccurrence;
    kind: "move" | "resize";
  } | null>(null);
  useEffect(() => {
    const stage = grid.current?.closest<HTMLElement>(".calendar-stage");
    if (stage) stage.scrollTop = 7 * hourHeight;
  }, [hourHeight, range.start]);
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
  const minuteAtDrop = (event: ReactDragEvent<HTMLElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const raw = ((event.clientY - bounds.top) / bounds.height) * 24 * 60;
    return Math.max(0, Math.min(23 * 60 + 45, Math.round(raw / 15) * 15));
  };
  const addCivilDays = (value: string, amount: number) => {
    const next = new Date(`${value}T12:00:00Z`);
    next.setUTCDate(next.getUTCDate() + amount);
    return next.toISOString().slice(0, 10);
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
                onDragOver={(event) => {
                  if (!editDrag.current) return;
                  event.preventDefault();
                  event.dataTransfer.dropEffect = "move";
                }}
                onDrop={(event) => {
                  const edit = editDrag.current;
                  editDrag.current = null;
                  if (!edit) return;
                  event.preventDefault();
                  const minute = minuteAtDrop(event);
                  if (edit.kind === "move") {
                    const duration = Math.max(
                      15,
                      Math.round(
                        ((edit.occurrence.end?.valueOf() ?? 0) -
                          (edit.occurrence.start?.valueOf() ?? 0)) /
                          60_000,
                      ),
                    );
                    const endMinute = minute + duration;
                    onEditSeed(edit.occurrence, {
                      editKind: "move",
                      startDate: date,
                      startTime: clockTime(minute),
                      endDate: addCivilDays(date, Math.floor(endMinute / 1440)),
                      endTime: clockTime(endMinute % 1440),
                    });
                  } else {
                    onEditSeed(edit.occurrence, {
                      editKind: "resize",
                      endDate: date,
                      endTime: clockTime(minute),
                    });
                  }
                }}
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
                      className="calendar-timed-position"
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
                        onSelect={onSelect}
                        draggable={
                          segment.occurrence.block.provider_write_capability
                            .eligible &&
                          segment.occurrence.block.provider_write_state ===
                            "synced" &&
                          segment.occurrence.block.recurrence_kind ===
                            "single" &&
                          segment.occurrence.block.start_timezone ===
                            localTimeZone
                        }
                        onDragStart={() => {
                          editDrag.current = {
                            occurrence: segment.occurrence,
                            kind: "move",
                          };
                        }}
                      />
                      {segment.occurrence.block.provider_write_capability
                        .eligible &&
                      segment.occurrence.block.provider_write_state ===
                        "synced" &&
                      segment.occurrence.block.recurrence_kind === "single" &&
                      segment.occurrence.block.start_timezone ===
                        localTimeZone ? (
                        <button
                          type="button"
                          draggable
                          className="calendar-event-resize-handle"
                          aria-label={`Resize ${segment.occurrence.block.title}`}
                          title="Drag to resize"
                          onClick={(event) => event.stopPropagation()}
                          onDragStart={(event) => {
                            event.stopPropagation();
                            editDrag.current = {
                              occurrence: segment.occurrence,
                              kind: "resize",
                            };
                          }}
                        />
                      ) : null}
                    </div>
                  );
                })}
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
  onSelect,
  draggable = false,
  onDragStart,
}: {
  occurrence: CalendarOccurrence;
  localTimeZone: string;
  detail: "title" | "title-two-line" | "time" | "full";
  onSelect(occurrence: CalendarOccurrence): void;
  draggable?: boolean;
  onDragStart?(): void;
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
      aria-label={`${occurrence.block.title}, ${time}`}
      title={`${occurrence.block.title} · ${time}`}
      data-write-state={occurrence.block.provider_write_state}
      draggable={draggable}
      onDragStart={(event) => {
        if (!draggable || !onDragStart) {
          event.preventDefault();
          return;
        }
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", "ion-calendar-event");
        onDragStart();
      }}
      onPointerDown={(event) => event.stopPropagation()}
      onClick={(event) => {
        event.stopPropagation();
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
              : occurrence.block.provider_write_state === "conflict"
                ? "Needs review"
                : occurrence.block.provider_write_detail === "reauth_required"
                  ? "Reconnect Google"
                  : "Pending Google"}
        </small>
      ) : null}
    </button>
  );
});
