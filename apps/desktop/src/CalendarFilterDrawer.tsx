import {
  CalendarCategorySubtype,
  CalendarFilterCategory,
  calendarFilterCategories,
  calendarFilterCategoryLabels,
  calendarSubtypeDefinitions,
} from "./calendar";
import { categoryColor } from "./calendarProjection";

export function CalendarFilterDrawer({
  visibleCategories,
  visibleSubtypes,
  onCategory,
  onSubtype,
}: {
  visibleCategories: CalendarFilterCategory[];
  visibleSubtypes: CalendarCategorySubtype[];
  onCategory(category: CalendarFilterCategory, visible: boolean): void;
  onSubtype(subtype: CalendarCategorySubtype, visible: boolean): void;
}) {
  return (
    <div className="calendar-sidebar-management calendar-filter-drawer">
      <div className="calendar-filter-heading">
        <p className="eyebrow">Presentation only</p>
        <h2>Filters</h2>
        <p>Choose the Ion categories and subtypes shown in this calendar.</p>
      </div>
      <fieldset className="calendar-filter-list">
        <legend>Category and subtype</legend>
        {calendarFilterCategories.map((category) => {
          const broad = category === "uncategorized" ? null : category;
          const color = categoryColor(broad);
          const subtypes = calendarSubtypeDefinitions.filter(
            (item) => item.category === broad,
          );
          return (
            <div className="calendar-filter-family" key={category}>
              <label>
                <input
                  type="checkbox"
                  checked={visibleCategories.includes(category)}
                  onChange={(event) =>
                    onCategory(category, event.currentTarget.checked)
                  }
                />
                <span
                  className="calendar-filter-dot"
                  style={{ background: color.accent }}
                  aria-hidden="true"
                />
                <strong>{calendarFilterCategoryLabels[category]}</strong>
              </label>
              {subtypes.map((subtype) => {
                const subtypeColor = categoryColor(
                  subtype.category,
                  subtype.value,
                );
                return (
                  <label
                    className="calendar-filter-subtype"
                    key={subtype.value}
                  >
                    <input
                      type="checkbox"
                      checked={visibleSubtypes.includes(subtype.value)}
                      onChange={(event) =>
                        onSubtype(subtype.value, event.currentTarget.checked)
                      }
                    />
                    <span
                      className="calendar-filter-dot"
                      style={{ background: subtypeColor.accent }}
                      aria-hidden="true"
                    />
                    {subtype.label}
                  </label>
                );
              })}
            </div>
          );
        })}
      </fieldset>
    </div>
  );
}
