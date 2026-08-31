import { describe, expect, test } from "vitest";
import {
  CalendarBlock,
  CalendarStatus,
  calendarCategories,
  calendarSubtypeDefinitions,
} from "./calendar";
import {
  buildCalendarProjectionIndex,
  calendarFreeGaps,
  calendarPaneBreakpoints,
  calendarPaneWidthClass,
  calendarRange,
  categoryColor,
  navigateCalendarAnchor,
  projectCalendar,
  projectCalendarIndex,
  sourceCalendarColor,
  startOfMondayWeek,
  timedSegmentsForDay,
  recommendedCalendarView,
} from "./calendarProjection";

const account = {
  id: "11111111-1111-4111-8111-111111111111",
  provider_account_id: "synthetic@example.invalid",
  display_name: "Synthetic Account",
  granted_scopes: [],
  auth_state: "connected" as const,
  calendar_write_scope_state: "read_only" as const,
  last_auth_at: "2030-01-01T00:00:00Z",
  created_at: "2030-01-01T00:00:00Z",
  updated_at: "2030-01-01T00:00:00Z",
  revision: 1,
};

const calendar = {
  id: "22222222-2222-4222-8222-222222222222",
  account_id: account.id,
  provider_calendar_id: "synthetic@example.invalid",
  summary: "Synthetic Calendar",
  description: null,
  location: null,
  timezone: "America/Los_Angeles",
  access_role: "owner",
  is_primary: true,
  provider_selected: true,
  provider_hidden: false,
  enabled_in_ion: true,
  hidden_in_ion: false,
  provider_deleted: false,
  has_sync_token: true,
  sync_state: "idle" as const,
  last_synced_at: "2030-01-01T00:00:00Z",
  last_error_code: null,
  retry_count: 0,
  next_retry_at: null,
  revision: 1,
  provider_write_eligible: false,
  provider_write_reason: "account_read_only",
};

function block(
  id: string,
  overrides: Partial<CalendarBlock> = {},
): CalendarBlock {
  return {
    id,
    calendar_id: calendar.id,
    provider_event_id: `provider-${id}`,
    ical_uid: null,
    title: `Synthetic ${id}`,
    description: null,
    location: null,
    temporal_kind: "timed",
    start_date: null,
    end_date: null,
    start_at: "2030-01-07T17:00:00Z",
    end_at: "2030-01-07T18:00:00Z",
    start_timezone: "America/Los_Angeles",
    end_timezone: "America/Los_Angeles",
    status: "confirmed",
    transparency: "opaque",
    recurrence_kind: "single",
    recurrence_rules: [],
    recurrence_master_block_id: null,
    recurring_event_id: null,
    original_start_kind: "none",
    original_start_date: null,
    original_start_at: null,
    original_start_timezone: null,
    flexibility: "locked",
    notes: null,
    category: null,
    category_subtype: null,
    ion_metadata_revision: 1,
    provider_deleted_at: null,
    revision: 1,
    provider_write_capability: {
      eligible: false,
      reason: "account_read_only",
    },
    ...overrides,
  };
}

function status(blocks: CalendarBlock[], enabled = true): CalendarStatus {
  return {
    configured: true,
    configuration_path: "/synthetic/google-oauth.json",
    accounts: [account],
    calendars: [{ ...calendar, enabled_in_ion: enabled }],
    blocks,
  };
}

describe("calendar range semantics", () => {
  test("uses Monday weeks and deterministic day/week/rolling/month navigation", () => {
    expect(startOfMondayWeek("2030-01-09")).toBe("2030-01-07");
    expect(calendarRange("week", "2030-01-09").days).toEqual([
      "2030-01-07",
      "2030-01-08",
      "2030-01-09",
      "2030-01-10",
      "2030-01-11",
      "2030-01-12",
      "2030-01-13",
    ]);
    expect(calendarRange("threeDay", "2030-01-09").days).toEqual([
      "2030-01-09",
      "2030-01-10",
      "2030-01-11",
    ]);
    expect(calendarRange("next7", "2030-01-09").days[0]).toBe("2030-01-09");
    expect(calendarRange("day", "2030-01-09").end).toBe("2030-01-10");
    expect(calendarRange("week", "2026-08-26").compactLabel).toBe(
      "08/24–08/30",
    );
    expect(navigateCalendarAnchor("week", "2030-01-09", 1)).toBe("2030-01-16");
    expect(navigateCalendarAnchor("next7", "2030-01-09", -1)).toBe(
      "2030-01-02",
    );
    expect(navigateCalendarAnchor("day", "2030-01-09", 1)).toBe("2030-01-10");
    expect(navigateCalendarAnchor("threeDay", "2030-01-09", 1)).toBe(
      "2030-01-12",
    );
    const month = calendarRange("month", "2030-05-15");
    expect(month.start).toBe("2030-04-29");
    expect(month.days.length % 7).toBe(0);
    expect(month.days.length).toBeGreaterThanOrEqual(35);
  });

  test("assigns stable restrained source markers and category event colors", () => {
    expect(sourceCalendarColor(calendar.id)).toEqual(
      sourceCalendarColor(calendar.id),
    );
    expect(
      new Set(
        ["calendar-a", "calendar-b", "calendar-c"].map(
          (id) => sourceCalendarColor(id).accent,
        ),
      ).size,
    ).toBeGreaterThan(1);
    expect(categoryColor("academic")).not.toEqual(
      categoryColor("routine_physical"),
    );
    expect(categoryColor("academic", "class_section")).not.toEqual(
      categoryColor("academic", "homework_study"),
    );
    expect(categoryColor("academic", "quiz_exam")).not.toEqual(
      categoryColor("academic", "class_section"),
    );
    expect(categoryColor("routine_physical", "meal")).toEqual(
      categoryColor("routine_physical", "gym"),
    );
    expect(categoryColor("fun", "social").accent).toBe("#9a9ba2");
    expect(categoryColor("fun", "social")).not.toEqual(
      categoryColor("personal_project", "build"),
    );
    expect(categoryColor("fun", "social")).not.toEqual(categoryColor(null));
    expect(categoryColor("career", "class_section")).toEqual(
      categoryColor("career"),
    );
    expect(categoryColor(null)).toEqual(categoryColor(null));
  });

  test("exposes the accepted extensible starter taxonomy without empty subtypes", () => {
    expect(calendarCategories).toEqual([
      "academic",
      "career",
      "personal_project",
      "routine_physical",
      "personal",
      "fun",
      "ion_focus",
    ]);
    expect(
      calendarSubtypeDefinitions.map(({ category, value }) => [
        category,
        value,
      ]),
    ).toEqual([
      ["academic", "class_section"],
      ["academic", "homework_study"],
      ["academic", "quiz_exam"],
      ["career", "internship_recruiting"],
      ["career", "application_admin"],
      ["career", "interview_networking"],
      ["personal_project", "build"],
      ["personal_project", "research"],
      ["personal_project", "creative"],
      ["routine_physical", "work_shift"],
      ["routine_physical", "meal"],
      ["routine_physical", "gym"],
      ["routine_physical", "hygiene"],
      ["routine_physical", "chores_errands"],
      ["personal", "appointment"],
      ["personal", "family"],
      ["personal", "travel"],
      ["personal", "personal_admin"],
      ["fun", "social"],
      ["fun", "entertainment"],
      ["fun", "gaming_media"],
      ["fun", "leisure"],
    ]);
    expect(
      calendarSubtypeDefinitions.every((item) => item.value.length > 0),
    ).toBe(true);
  });

  test("recommends views only at documented calendar-pane breakpoints", () => {
    expect(calendarPaneWidthClass(calendarPaneBreakpoints.wide)).toBe("wide");
    expect(calendarPaneWidthClass(calendarPaneBreakpoints.wide - 1)).toBe(
      "medium",
    );
    expect(calendarPaneWidthClass(calendarPaneBreakpoints.medium)).toBe(
      "medium",
    );
    expect(calendarPaneWidthClass(calendarPaneBreakpoints.medium - 1)).toBe(
      "narrow",
    );
    expect(recommendedCalendarView("wide")).toBe("week");
    expect(recommendedCalendarView("medium")).toBe("threeDay");
    expect(recommendedCalendarView("narrow")).toBe("day");
  });
});

describe("bounded recurrence and exception projection", () => {
  test("expands a master, replaces its original slot with a moved exception, and avoids duplicates", () => {
    const master = block("master", {
      provider_event_id: "series",
      recurrence_kind: "master",
      recurrence_rules: ["RRULE:FREQ=WEEKLY;BYDAY=MO,WE"],
    });
    const moved = block("moved", {
      provider_event_id: "exception-moved",
      title: "Moved class",
      recurrence_kind: "exception",
      recurrence_master_block_id: master.id,
      recurring_event_id: "series",
      original_start_kind: "instant",
      original_start_at: "2030-01-09T17:00:00Z",
      original_start_timezone: "America/Los_Angeles",
      start_at: "2030-01-10T19:00:00Z",
      end_at: "2030-01-10T20:00:00Z",
    });
    const projection = projectCalendar(
      status([master, moved]),
      calendarRange("week", "2030-01-07"),
      "America/Los_Angeles",
    );
    expect(projection.occurrences.map((item) => item.key)).toEqual([
      `${master.id}|instant:2030-01-07T17:00:00.000Z`,
      moved.id,
    ]);
    expect(projection.occurrences[1].recurrenceContext).toBe("exception");
  });

  test("retains a cancelled exception only as suppression metadata", () => {
    const master = block("master", {
      provider_event_id: "series",
      recurrence_kind: "master",
      recurrence_rules: ["RRULE:FREQ=WEEKLY;BYDAY=MO"],
    });
    const cancelled = block("cancelled", {
      recurrence_kind: "exception",
      recurrence_master_block_id: master.id,
      recurring_event_id: "series",
      original_start_kind: "instant",
      original_start_at: "2030-01-14T17:00:00Z",
      original_start_timezone: "America/Los_Angeles",
      start_at: "2030-01-14T17:00:00Z",
      end_at: "2030-01-14T18:00:00Z",
      status: "cancelled",
      provider_deleted_at: "2030-01-01T00:00:00Z",
    });
    const projection = projectCalendar(
      status([master, cancelled]),
      calendarRange("week", "2030-01-14"),
      "America/Los_Angeles",
    );
    expect(projection.occurrences).toHaveLength(0);
  });

  test("preserves local wall time across DST and keeps all-day dates date-only", () => {
    const dstMaster = block("dst", {
      start_at: "2030-03-04T17:00:00Z",
      end_at: "2030-03-04T18:00:00Z",
      recurrence_kind: "master",
      recurrence_rules: ["RRULE:FREQ=WEEKLY;BYDAY=MO"],
    });
    const allDay = block("all-day", {
      temporal_kind: "all_day",
      start_date: "2030-03-04",
      end_date: "2030-03-05",
      start_at: null,
      end_at: null,
      start_timezone: null,
      end_timezone: null,
      recurrence_kind: "master",
      recurrence_rules: ["RRULE:FREQ=WEEKLY;BYDAY=MO"],
    });
    const projection = projectCalendar(
      status([dstMaster, allDay]),
      calendarRange("week", "2030-03-11"),
      "America/Los_Angeles",
    );
    const timed = projection.occurrences.find(
      (item) => item.block.id === "dst",
    )!;
    const dateOnly = projection.occurrences.find(
      (item) => item.block.id === "all-day",
    )!;
    expect(timed.start?.toISOString()).toBe("2030-03-11T16:00:00.000Z");
    expect(dateOnly.startDate).toBe("2030-03-11");
    expect(dateOnly.start).toBeNull();
  });

  test("filters disabled calendars and bounds pathological COUNT scans", () => {
    const ancient = block("ancient", {
      start_at: "1800-01-06T17:00:00Z",
      end_at: "1800-01-06T18:00:00Z",
      recurrence_kind: "master",
      recurrence_rules: ["RRULE:FREQ=DAILY;COUNT=100000"],
    });
    const range = calendarRange("week", "2030-01-07");
    expect(
      projectCalendar(status([ancient], false), range, "UTC").occurrences,
    ).toEqual([]);
    expect(projectCalendar(status([ancient]), range, "UTC").limited).toBe(true);
  });
});

describe("timeline layout and truthful free gaps", () => {
  test("lays overlapping events side by side without obscuring them", () => {
    const blocks = [
      block("a"),
      block("b", {
        start_at: "2030-01-07T17:30:00Z",
        end_at: "2030-01-07T19:00:00Z",
      }),
      block("c", {
        start_at: "2030-01-07T18:00:00Z",
        end_at: "2030-01-07T19:00:00Z",
      }),
    ];
    const occurrences = projectCalendar(
      status(blocks),
      calendarRange("day", "2030-01-07"),
      "America/Los_Angeles",
    ).occurrences;
    const segments = timedSegmentsForDay(
      occurrences,
      "2030-01-07",
      "America/Los_Angeles",
    );
    expect(
      segments.map(({ column, columnCount }) => [column, columnCount]),
    ).toEqual([
      [0, 2],
      [1, 2],
      [0, 2],
    ]);
  });

  test("computes gaps only from opaque real calendar occupancy", () => {
    const events = [
      block("occupied", {
        start_at: "2030-01-07T17:00:00Z",
        end_at: "2030-01-07T18:00:00Z",
      }),
      block("transparent", {
        start_at: "2030-01-07T19:00:00Z",
        end_at: "2030-01-07T20:00:00Z",
        transparency: "transparent",
      }),
    ];
    const occurrences = projectCalendar(
      status(events),
      calendarRange("day", "2030-01-07"),
      "America/Los_Angeles",
    ).occurrences;
    expect(
      calendarFreeGaps(
        occurrences,
        "2030-01-07",
        "America/Los_Angeles",
        480,
        720,
      ),
    ).toEqual([
      { startMinute: 480, endMinute: 540 },
      { startMinute: 600, endMinute: 720 },
    ]);
  });
});

describe("indexed projection performance shape", () => {
  test("indexes roughly two thousand blocks once and bounds range memoization", () => {
    const blocks = Array.from({ length: 2_048 }, (_, index) =>
      block(`bulk-${index}`, {
        title: `Synthetic bulk event ${index}`,
        start_at: "2030-01-07T17:00:00Z",
        end_at: "2030-01-07T17:30:00Z",
      }),
    );
    const index = buildCalendarProjectionIndex(status(blocks));
    expect(index.blocks).toHaveLength(2_048);

    const range = calendarRange("day", "2030-01-07");
    const first = projectCalendarIndex(index, range, "UTC");
    expect(first.occurrences).toHaveLength(2_048);
    expect(projectCalendarIndex(index, range, "UTC")).toBe(first);

    for (let day = 8; day <= 22; day += 1) {
      projectCalendarIndex(
        index,
        calendarRange("day", `2030-01-${day.toString().padStart(2, "0")}`),
        "UTC",
      );
    }
    expect(index.cache.size).toBeLessThanOrEqual(12);
  });

  test("omits an Ion-hidden calendar without discarding its cached blocks", () => {
    const hiddenStatus = status([block("cached")]);
    hiddenStatus.calendars[0].hidden_in_ion = true;
    const index = buildCalendarProjectionIndex(hiddenStatus);
    expect(index.blocks).toEqual([]);
    expect(hiddenStatus.blocks).toHaveLength(1);
  });
});
