import { memo, useMemo } from "react";
import { CalendarStatus, calendarCategoryDisplay } from "./calendar";
import {
  buildCalendarProjectionIndex,
  calendarFreeGaps,
  calendarRange,
  categoryColor,
  formatMinutes,
  formatOccurrenceTime,
  localCivilDate,
  minuteOfDay,
  occurrencesForDay,
  projectCalendarIndex,
  timedSegmentsForDay,
} from "./calendarProjection";

const WINDOW_START = 360;
const WINDOW_END = 1_380;

export const TodaySchedule = memo(function TodaySchedule({
  calendar,
  date,
  localTimeZone,
  now = new Date(),
}: {
  calendar: CalendarStatus;
  date: string;
  localTimeZone: string;
  now?: Date;
}) {
  const range = useMemo(() => calendarRange("day", date), [date]);
  const projectionIndex = useMemo(
    () => buildCalendarProjectionIndex(calendar),
    [calendar],
  );
  const projection = useMemo(
    () => projectCalendarIndex(projectionIndex, range, localTimeZone),
    [localTimeZone, projectionIndex, range],
  );
  const day = useMemo(
    () => occurrencesForDay(projection.occurrences, date, localTimeZone),
    [date, localTimeZone, projection.occurrences],
  );
  const allDay = useMemo(
    () => day.filter((occurrence) => occurrence.allDay),
    [day],
  );
  const timed = useMemo(
    () =>
      timedSegmentsForDay(day, date, localTimeZone).filter(
        (segment) =>
          segment.endMinute > WINDOW_START && segment.startMinute < WINDOW_END,
      ),
    [date, day, localTimeZone],
  );
  const gaps = useMemo(
    () => calendarFreeGaps(day, date, localTimeZone, WINDOW_START, WINDOW_END),
    [date, day, localTimeZone],
  );
  const enabledCalendars = calendar.calendars.filter(
    (item) =>
      item.enabled_in_ion && !item.hidden_in_ion && !item.provider_deleted,
  );
  const stale = enabledCalendars.some((item) =>
    ["failed", "retry_wait", "reauth_required", "disconnected"].includes(
      item.sync_state,
    ),
  );
  const today = localCivilDate(localTimeZone, now);
  const nowMinute = minuteOfDay(now, localTimeZone);
  const height = 620;
  const position = (minute: number) =>
    ((Math.max(WINDOW_START, Math.min(WINDOW_END, minute)) - WINDOW_START) /
      (WINDOW_END - WINDOW_START)) *
    height;

  if (enabledCalendars.length === 0) {
    return (
      <aside className="schedule-context" aria-label="Schedule context">
        <p className="eyebrow">Schedule context</p>
        <h2>Calendar is not connected yet.</h2>
        <p>Ion cannot calculate occupied or available time.</p>
        <p className="context-note">
          Selected Tasks are unscheduled. They do not occupy specific times.
        </p>
      </aside>
    );
  }

  return (
    <aside
      className="schedule-context today-calendar"
      aria-label="Today schedule"
    >
      <div className="today-calendar-heading">
        <div>
          <p className="eyebrow">Schedule context</p>
          <h2>Calendar occupancy</h2>
        </div>
        <span>
          {day.length} block{day.length === 1 ? "" : "s"}
        </span>
      </div>
      {stale ? (
        <p className="calendar-cache-status">
          Cached schedule shown; one or more sources could not refresh.
        </p>
      ) : null}
      {allDay.length > 0 ? (
        <section className="today-all-day" aria-label="All-day events">
          <h3>All day</h3>
          <ul>
            {allDay.map((occurrence) => {
              const color = categoryColor(
                occurrence.block.category,
                occurrence.block.category_subtype,
              );
              const category = calendarCategoryDisplay(
                occurrence.block.category,
                occurrence.block.category_subtype,
              );
              return (
                <li key={occurrence.key}>
                  <span
                    style={{ background: color.accent }}
                    aria-hidden="true"
                  />
                  <strong>{occurrence.block.title}</strong>
                  <small>
                    {category} · {occurrence.calendar.summary}
                  </small>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
      <div className="today-timeline" style={{ height }}>
        {[360, 540, 720, 900, 1080, 1260].map((minute) => (
          <div
            className="today-timeline-hour"
            key={minute}
            style={{ top: position(minute) }}
            aria-hidden="true"
          >
            <span>{formatMinutes(minute)}</span>
          </div>
        ))}
        {date === today &&
        nowMinute >= WINDOW_START &&
        nowMinute <= WINDOW_END ? (
          <div
            className="today-now-line"
            style={{ top: position(nowMinute) }}
            aria-label="Current time"
          />
        ) : null}
        <div className="today-timeline-events">
          {timed.map((segment) => {
            const color = categoryColor(
              segment.occurrence.block.category,
              segment.occurrence.block.category_subtype,
            );
            const category = calendarCategoryDisplay(
              segment.occurrence.block.category,
              segment.occurrence.block.category_subtype,
            );
            const start = Math.max(WINDOW_START, segment.startMinute);
            const end = Math.min(WINDOW_END, segment.endMinute);
            const width = 100 / segment.columnCount;
            return (
              <article
                className={`today-calendar-block ${segment.occurrence.block.transparency === "transparent" ? "is-transparent" : ""}`}
                key={segment.occurrence.key}
                style={{
                  top: position(start),
                  height: Math.max(28, position(end) - position(start)),
                  left: `${segment.column * width}%`,
                  width: `${width}%`,
                  borderColor: color.accent,
                  background: color.fill,
                }}
                aria-label={`${segment.occurrence.block.title}, ${formatOccurrenceTime(segment.occurrence, localTimeZone)}, ${category}`}
              >
                <strong>{segment.occurrence.block.title}</strong>
                <span>
                  {formatOccurrenceTime(segment.occurrence, localTimeZone)} ·{" "}
                  {category} · {segment.occurrence.calendar.summary}
                </span>
              </article>
            );
          })}
        </div>
      </div>
      <section className="today-free-gaps" aria-label="Calendar-open gaps">
        <h3>Calendar-open gaps · 6 AM–11 PM</h3>
        {gaps.length === 0 ? (
          <p>No gap of at least 30 minutes is visible in this window.</p>
        ) : (
          <ul>
            {gaps.map((gap) => (
              <li key={`${gap.startMinute}-${gap.endMinute}`}>
                {formatMinutes(gap.startMinute)}–{formatMinutes(gap.endMinute)}
              </li>
            ))}
          </ul>
        )}
      </section>
      <p className="context-note">
        These gaps reflect real opaque CalendarBlocks only. Today Tasks remain
        unscheduled and are not assigned to open time.
      </p>
      <p className="context-note">
        All-day and transparent events are shown but do not fabricate timed
        occupancy.
      </p>
    </aside>
  );
});
