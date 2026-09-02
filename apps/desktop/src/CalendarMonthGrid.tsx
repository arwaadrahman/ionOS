import { memo, useMemo } from "react";
import {
  CalendarOccurrence,
  CalendarRange,
  occurrencesForDay,
} from "./calendarProjection";
import { EventButton } from "./CalendarTimeGrid";

const MAX_ROWS = 3;

function dayNumber(date: string) {
  return Number(date.slice(-2));
}

export const CalendarMonthGrid = memo(function CalendarMonthGrid({
  range,
  anchor,
  occurrences,
  localTimeZone,
  today,
  selectedKey = null,
  onSelect,
}: {
  range: CalendarRange;
  anchor: string;
  occurrences: CalendarOccurrence[];
  localTimeZone: string;
  today: string;
  selectedKey?: string | null;
  onSelect(occurrence: CalendarOccurrence): void;
}) {
  const days = useMemo(
    () =>
      range.days.map((date) => ({
        date,
        items: occurrencesForDay(occurrences, date, localTimeZone),
      })),
    [localTimeZone, occurrences, range.days],
  );
  return (
    <section className="calendar-month" aria-label={range.label}>
      <div className="calendar-month-weekdays" aria-hidden="true">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day) => (
          <span key={day}>{day}</span>
        ))}
      </div>
      <div className="calendar-month-grid">
        {days.map(({ date, items }) => {
          const visible = items.slice(0, MAX_ROWS);
          const overflow = items.length - visible.length;
          return (
            <div
              className={`calendar-month-day ${date.slice(0, 7) !== anchor.slice(0, 7) ? "is-outside" : ""} ${date === today ? "is-today" : ""}`}
              key={date}
              aria-label={date}
            >
              <div className="calendar-month-date">
                <span>{dayNumber(date)}</span>
                {date === today ? <strong>Today</strong> : null}
              </div>
              <div className="calendar-month-events">
                {visible.map((occurrence) => (
                  <EventButton
                    key={occurrence.key}
                    occurrence={occurrence}
                    localTimeZone={localTimeZone}
                    detail="title"
                    selected={occurrence.key === selectedKey}
                    onSelect={onSelect}
                  />
                ))}
                {overflow > 0 ? (
                  <span className="calendar-more">+{overflow} more</span>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
});
