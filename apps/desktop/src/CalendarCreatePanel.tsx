import { useMemo, useState } from "react";
import {
  CalendarCreateDraft,
  CalendarCreateSeed,
  GoogleCalendar,
} from "./calendar";

export function CalendarCreatePanel({
  seed,
  calendars,
  localTimeZone,
  pending,
  onSubmit,
  onClose,
}: {
  seed: CalendarCreateSeed;
  calendars: GoogleCalendar[];
  localTimeZone: string;
  pending: boolean;
  onSubmit(draft: CalendarCreateDraft): void;
  onClose(): void;
}) {
  const defaultCalendar =
    calendars.find((calendar) => calendar.is_primary) ?? calendars[0];
  const commandId = useMemo(() => crypto.randomUUID(), []);
  const [title, setTitle] = useState("");
  const [calendarId, setCalendarId] = useState(defaultCalendar?.id ?? "");
  const [date, setDate] = useState(seed.date);
  const [allDay, setAllDay] = useState(seed.allDay);
  const [startTime, setStartTime] = useState(seed.startTime ?? "09:00");
  const [endTime, setEndTime] = useState(seed.endTime ?? "10:00");
  const timezoneOptions = useMemo(
    () =>
      [...new Set([localTimeZone, ...calendars.map((item) => item.timezone)])]
        .filter((value): value is string => Boolean(value))
        .sort(),
    [calendars, localTimeZone],
  );
  const [timezone, setTimezone] = useState(
    defaultCalendar?.timezone ?? localTimeZone,
  );
  const valid =
    title.trim().length > 0 &&
    calendarId.length > 0 &&
    date.length === 10 &&
    (allDay ||
      (startTime.length === 5 && endTime > startTime && Boolean(timezone)));

  return (
    <aside className="calendar-create-panel" aria-label="Create calendar event">
      <div className="calendar-inspector-heading">
        <div>
          <p className="eyebrow">New Google event</p>
          <h2>Create event</h2>
        </div>
        <button
          className="icon-button"
          type="button"
          aria-label="Close create event"
          onClick={onClose}
          disabled={pending}
        >
          ×
        </button>
      </div>
      <form
        className="calendar-create-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!valid) return;
          onSubmit({
            command_id: commandId,
            calendar_id: calendarId,
            title: title.trim(),
            date,
            all_day: allDay,
            start_time: allDay ? null : startTime,
            end_time: allDay ? null : endTime,
            timezone: allDay ? null : timezone,
          });
        }}
      >
        <label>
          <span>Title</span>
          <input
            autoFocus
            value={title}
            maxLength={512}
            onChange={(event) => setTitle(event.currentTarget.value)}
            placeholder="Event title"
          />
        </label>
        <label>
          <span>Calendar</span>
          <select
            value={calendarId}
            onChange={(event) => {
              const nextId = event.currentTarget.value;
              setCalendarId(nextId);
              const next = calendars.find((item) => item.id === nextId);
              if (next?.timezone) setTimezone(next.timezone);
            }}
          >
            {calendars.map((calendar) => (
              <option key={calendar.id} value={calendar.id}>
                {calendar.summary}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Date</span>
          <input
            type="date"
            value={date}
            onChange={(event) => setDate(event.currentTarget.value)}
          />
        </label>
        <label className="calendar-create-check">
          <input
            type="checkbox"
            checked={allDay}
            onChange={(event) => setAllDay(event.currentTarget.checked)}
          />
          <span>All day</span>
        </label>
        {!allDay ? (
          <>
            <div className="calendar-create-time-row">
              <label>
                <span>Starts</span>
                <input
                  type="time"
                  value={startTime}
                  onChange={(event) => setStartTime(event.currentTarget.value)}
                />
              </label>
              <label>
                <span>Ends</span>
                <input
                  type="time"
                  value={endTime}
                  onChange={(event) => setEndTime(event.currentTarget.value)}
                />
              </label>
            </div>
            <label>
              <span>Timezone</span>
              <select
                value={timezone}
                onChange={(event) => setTimezone(event.currentTarget.value)}
              >
                {timezoneOptions.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
          </>
        ) : null}
        <p className="context-note">
          Ion saves this event locally first. Google confirmation may follow
          immediately or after the next successful connection.
        </p>
        <div className="calendar-create-actions">
          <button
            className="quiet-button"
            type="button"
            onClick={onClose}
            disabled={pending}
          >
            Cancel
          </button>
          <button type="submit" disabled={!valid || pending}>
            {pending ? "Saving…" : "Create event"}
          </button>
        </div>
      </form>
    </aside>
  );
}
