import { useEffect, useState } from "react";
import {
  addDays,
  CalendarOccurrence,
  formatOccurrenceTime,
  localCivilDate,
} from "./calendarProjection";
import { CalendarEditForm, type CalendarEditDraft } from "./CalendarEditForm";
import {
  CalendarCategory,
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

export function CalendarInspector({
  occurrence,
  localTimeZone,
  categoryPending,
  editable,
  onCategory,
  onEdit,
  onClose,
}: {
  occurrence: CalendarOccurrence;
  localTimeZone: string;
  categoryPending: boolean;
  editable: boolean;
  onCategory(category: CalendarCategory | null, subtype: string | null): void;
  onEdit(draft: CalendarEditDraft): void;
  onClose(): void;
}) {
  const sourceTimeZone = occurrence.block.start_timezone;
  const differentTimeZone =
    !occurrence.allDay && sourceTimeZone && sourceTimeZone !== localTimeZone;
  const category = occurrence.block.category;
  const currentSubtype = occurrence.block.category_subtype;
  const [draftCategory, setDraftCategory] = useState<CalendarCategory | null>(
    category,
  );
  const [draftSubtype, setDraftSubtype] = useState<string | null>(
    categoryDraftSubtype(category, currentSubtype),
  );
  useEffect(() => {
    setDraftCategory(category);
    setDraftSubtype(categoryDraftSubtype(category, currentSubtype));
  }, [category, currentSubtype, occurrence.block.id]);
  const draftSubtypes = calendarSubtypesFor(draftCategory);
  const hasCustomDraftSubtype =
    draftSubtype !== null &&
    !draftSubtypes.some((item) => item.value === draftSubtype);
  const categoryChanged =
    draftCategory !== category || draftSubtype !== currentSubtype;
  return (
    <aside className="calendar-inspector" aria-label="Event details">
      <div className="calendar-inspector-heading">
        <p className="eyebrow">{editable ? "Event" : "Read-only event"}</p>
        <button
          className="quiet-button"
          type="button"
          aria-label="Close event details"
          autoFocus
          onClick={onClose}
        >
          Close
        </button>
      </div>
      <h2>{occurrence.block.title}</h2>
      {editable ? (
        <CalendarEditForm
          occurrence={occurrence}
          localTimeZone={localTimeZone}
          onSubmit={onEdit}
        />
      ) : null}
      <label className="calendar-category-editor">
        <span>Ion category</span>
        <select
          aria-label={`${occurrence.block.title} Ion category`}
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
            aria-label={`${occurrence.block.title} Ion category subtype`}
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
        {occurrence.block.location ? (
          <div>
            <dt>Location</dt>
            <dd>{occurrence.block.location}</dd>
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
            {occurrence.block.status}
            {occurrence.block.transparency === "transparent"
              ? " · does not mark time busy"
              : " · occupies calendar time"}
          </dd>
        </div>
      </dl>
      {occurrence.block.description ? (
        <section>
          <h3>Description</h3>
          <p>{occurrence.block.description}</p>
        </section>
      ) : null}
      <p className="context-note">
        Provider event fields are view-only. This inspector cannot edit, move,
        resize, or delete them; only Ion-owned category metadata can change.
      </p>
    </aside>
  );
}
