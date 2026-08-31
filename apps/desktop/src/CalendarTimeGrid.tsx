import { memo, useEffect, useMemo, useRef, type CSSProperties } from "react";
import { CalendarDensity, calendarDensityHeights } from "./calendar";
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

export const CalendarTimeGrid = memo(function CalendarTimeGrid({
  range,
  occurrences,
  localTimeZone,
  today,
  now = new Date(),
  density,
  onSelect,
}: {
  range: CalendarRange;
  occurrences: CalendarOccurrence[];
  localTimeZone: string;
  today: string;
  now?: Date;
  density: CalendarDensity;
  onSelect(occurrence: CalendarOccurrence): void;
}) {
  const hourHeight = calendarDensityHeights[density];
  const grid = useRef<HTMLElement>(null);
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
              >
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
                      />
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
}: {
  occurrence: CalendarOccurrence;
  localTimeZone: string;
  detail: "title" | "title-two-line" | "time" | "full";
  onSelect(occurrence: CalendarOccurrence): void;
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
      onClick={() => onSelect(occurrence)}
    >
      <strong>{occurrence.block.title}</strong>
      {detail === "time" || detail === "full" ? <span>{time}</span> : null}
    </button>
  );
});
