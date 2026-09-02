import {
  CalendarBlock,
  CalendarCategory,
  CalendarStatus,
  GoogleAccount,
  GoogleCalendar,
} from "./calendar";

export type CalendarView = "day" | "threeDay" | "week" | "next7" | "month";
export type CalendarPaneWidthClass = "narrow" | "medium" | "wide";

export const calendarPaneBreakpoints = {
  medium: 560,
  wide: 840,
} as const;

export function calendarPaneWidthClass(width: number): CalendarPaneWidthClass {
  if (width >= calendarPaneBreakpoints.wide) return "wide";
  if (width >= calendarPaneBreakpoints.medium) return "medium";
  return "narrow";
}

export function recommendedCalendarView(
  widthClass: CalendarPaneWidthClass,
): CalendarView {
  if (widthClass === "wide") return "week";
  if (widthClass === "medium") return "threeDay";
  return "day";
}

export type CalendarRange = {
  start: string;
  end: string;
  days: string[];
  label: string;
  compactLabel: string;
};

export type RecurrenceContext = "single" | "occurrence" | "exception";

export type CalendarOccurrence = {
  key: string;
  block: CalendarBlock;
  calendar: GoogleCalendar;
  account: GoogleAccount | null;
  allDay: boolean;
  startDate: string | null;
  endDate: string | null;
  start: Date | null;
  end: Date | null;
  recurrenceContext: RecurrenceContext;
};

export type CalendarProjection = {
  occurrences: CalendarOccurrence[];
  limited: boolean;
};

export type CalendarProjectionIndex = {
  calendars: Map<string, GoogleCalendar>;
  accounts: Map<string, GoogleAccount>;
  blocks: CalendarBlock[];
  suppressed: Set<string>;
  /**
   * Exception block ids whose immutable original start is no longer produced by
   * their master's confirmed recurrence rule. They are stale local overrides
   * awaiting read-sync reconciliation, not renderable occurrences.
   */
  unanchoredExceptions: Set<string>;
  cache: Map<string, CalendarProjection>;
};

export type TimedSegment = {
  occurrence: CalendarOccurrence;
  startMinute: number;
  endMinute: number;
  column: number;
  columnCount: number;
};

export type CalendarGap = { startMinute: number; endMinute: number };

export type CalendarColor = {
  accent: string;
  fill: string;
  strongFill: string;
  text: string;
};

type ZonedParts = {
  date: string;
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
};

type ParsedRule = {
  frequency: "DAILY" | "WEEKLY" | "MONTHLY" | "YEARLY";
  interval: number;
  count: number | null;
  until: string | null;
  byDay: string[];
  byMonthDay: number[];
  byMonth: number[];
  weekStart: string;
};

const DAY_MS = 86_400_000;
const MAX_SCAN_DAYS = 50_000;
const MAX_OCCURRENCES = 2_000;
const weekdayCodes = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"];
const sourcePalette: CalendarColor[] = [
  {
    accent: "#9b87f5",
    fill: "rgb(90 67 149 / 30%)",
    strongFill: "rgb(112 82 185 / 72%)",
    text: "#f3efff",
  },
  {
    accent: "#7f91ed",
    fill: "rgb(73 88 153 / 32%)",
    strongFill: "rgb(78 95 173 / 74%)",
    text: "#f0f2ff",
  },
  {
    accent: "#55b8ad",
    fill: "rgb(45 115 108 / 30%)",
    strongFill: "rgb(41 125 116 / 70%)",
    text: "#eafffc",
  },
  {
    accent: "#b49bd8",
    fill: "rgb(107 83 137 / 30%)",
    strongFill: "rgb(119 91 154 / 72%)",
    text: "#f8f0ff",
  },
  {
    accent: "#6e76c7",
    fill: "rgb(61 66 128 / 32%)",
    strongFill: "rgb(69 76 145 / 74%)",
    text: "#eff0ff",
  },
  {
    accent: "#67a5cf",
    fill: "rgb(55 99 130 / 30%)",
    strongFill: "rgb(58 108 143 / 72%)",
    text: "#edf8ff",
  },
];

const uncategorizedColor: CalendarColor = {
  accent: "#8d8798",
  fill: "rgb(82 78 91 / 28%)",
  strongFill: "rgb(96 90 108 / 52%)",
  text: "#f0edf3",
};

const categoryPalette: Record<CalendarCategory, CalendarColor> = {
  academic: {
    accent: "#9b87e8",
    fill: "rgb(92 72 146 / 30%)",
    strongFill: "rgb(111 84 179 / 58%)",
    text: "#f7f2ff",
  },
  career: {
    accent: "#718dd2",
    fill: "rgb(54 71 119 / 30%)",
    strongFill: "rgb(66 87 148 / 58%)",
    text: "#f0f5ff",
  },
  personal_project: {
    accent: "#b29acb",
    fill: "rgb(87 70 111 / 29%)",
    strongFill: "rgb(105 83 136 / 55%)",
    text: "#fbf3ff",
  },
  routine_physical: {
    accent: "#55b8ad",
    fill: "rgb(39 99 94 / 28%)",
    strongFill: "rgb(45 119 111 / 52%)",
    text: "#ecfffc",
  },
  personal: {
    accent: "#a986ad",
    fill: "rgb(88 65 92 / 29%)",
    strongFill: "rgb(107 77 112 / 54%)",
    text: "#fff3ff",
  },
  fun: {
    accent: "#8c8d94",
    fill: "rgb(38 39 44 / 34%)",
    strongFill: "rgb(54 55 62 / 72%)",
    text: "#f4f4f6",
  },
  ion_focus: {
    accent: "#a77cff",
    fill: "rgb(91 58 153 / 33%)",
    strongFill: "rgb(116 74 195 / 64%)",
    text: "#f8f1ff",
  },
};

const subtypePalette: Partial<
  Record<CalendarCategory, Partial<Record<string, CalendarColor>>>
> = {
  academic: {
    class_section: {
      accent: "#9480d9",
      fill: "rgb(84 66 132 / 29%)",
      strongFill: "rgb(100 78 159 / 55%)",
      text: "#f6f1ff",
    },
    homework_study: {
      accent: "#b3a2ec",
      fill: "rgb(98 82 145 / 27%)",
      strongFill: "rgb(118 98 175 / 52%)",
      text: "#faf7ff",
    },
    quiz_exam: {
      accent: "#c09aff",
      fill: "rgb(111 70 174 / 38%)",
      strongFill: "rgb(139 86 220 / 68%)",
      text: "#fff8ff",
    },
  },
  career: {
    internship_recruiting: {
      accent: "#6685cd",
      fill: "rgb(50 67 114 / 30%)",
      strongFill: "rgb(60 82 144 / 58%)",
      text: "#eef4ff",
    },
    application_admin: {
      accent: "#879bd4",
      fill: "rgb(63 74 112 / 27%)",
      strongFill: "rgb(76 91 139 / 52%)",
      text: "#f2f6ff",
    },
    interview_networking: {
      accent: "#7da8e6",
      fill: "rgb(55 82 127 / 34%)",
      strongFill: "rgb(65 100 158 / 62%)",
      text: "#f2f8ff",
    },
  },
  personal_project: {
    build: {
      accent: "#aa8fc4",
      fill: "rgb(82 65 104 / 29%)",
      strongFill: "rgb(99 77 128 / 55%)",
      text: "#faf3ff",
    },
    research: {
      accent: "#c1a9d5",
      fill: "rgb(94 77 112 / 27%)",
      strongFill: "rgb(113 92 137 / 52%)",
      text: "#fff6ff",
    },
    creative: {
      accent: "#cab0e0",
      fill: "rgb(101 79 124 / 30%)",
      strongFill: "rgb(122 94 151 / 57%)",
      text: "#fff7ff",
    },
  },
  fun: {
    social: {
      accent: "#9a9ba2",
      fill: "rgb(44 45 50 / 34%)",
      strongFill: "rgb(61 62 69 / 72%)",
      text: "#f6f6f7",
    },
    entertainment: {
      accent: "#81828a",
      fill: "rgb(34 35 40 / 36%)",
      strongFill: "rgb(49 50 57 / 74%)",
      text: "#f2f2f4",
    },
    gaming_media: {
      accent: "#a4a5aa",
      fill: "rgb(47 48 53 / 35%)",
      strongFill: "rgb(65 66 72 / 73%)",
      text: "#f7f7f8",
    },
    leisure: {
      accent: "#74757c",
      fill: "rgb(30 31 36 / 34%)",
      strongFill: "rgb(44 45 51 / 70%)",
      text: "#efeff1",
    },
  },
};

function civilUtc(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

function civilFromUtc(value: Date) {
  return value.toISOString().slice(0, 10);
}

export function addDays(value: string, amount: number) {
  const date = civilUtc(value);
  date.setUTCDate(date.getUTCDate() + amount);
  return civilFromUtc(date);
}

export function differenceInDays(start: string, end: string) {
  return Math.round(
    (civilUtc(end).valueOf() - civilUtc(start).valueOf()) / DAY_MS,
  );
}

export function startOfMondayWeek(value: string) {
  const weekday = civilUtc(value).getUTCDay();
  return addDays(value, -(weekday === 0 ? 6 : weekday - 1));
}

export function monthGridStart(value: string) {
  return startOfMondayWeek(`${value.slice(0, 7)}-01`);
}

export function localCivilDate(timeZone: string, now = new Date()) {
  return zonedParts(now, timeZone).date;
}

function civilDays(start: string, end: string) {
  const values: string[] = [];
  for (let day = start; day < end; day = addDays(day, 1)) values.push(day);
  return values;
}

function formatCivil(value: string, options: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat(undefined, {
    ...options,
    timeZone: "UTC",
  }).format(new Date(`${value}T12:00:00Z`));
}

function rangeLabel(
  view: CalendarView,
  start: string,
  end: string,
  anchor: string,
) {
  if (view === "day") {
    return formatCivil(start, {
      weekday: "long",
      month: "long",
      day: "numeric",
      year: "numeric",
    });
  }
  if (view === "month") {
    return formatCivil(`${anchor.slice(0, 7)}-01`, {
      month: "long",
      year: "numeric",
    });
  }
  const last = addDays(end, -1);
  const startYear = start.slice(0, 4);
  const endYear = last.slice(0, 4);
  const startLabel = formatCivil(start, {
    month: "short",
    day: "numeric",
    ...(startYear !== endYear ? { year: "numeric" } : {}),
  });
  const endLabel = formatCivil(last, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  return `${startLabel} – ${endLabel}`;
}

function compactRangeLabel(
  view: CalendarView,
  start: string,
  end: string,
  anchor: string,
) {
  if (view === "day")
    return `${start.slice(5).replace("-", "/")}/${start.slice(0, 4)}`;
  if (view === "month") return `${anchor.slice(5, 7)}/${anchor.slice(0, 4)}`;
  const last = addDays(end, -1);
  return `${start.slice(5).replace("-", "/")}–${last.slice(5).replace("-", "/")}`;
}

export function calendarRange(
  view: CalendarView,
  anchor: string,
): CalendarRange {
  if (view === "day") {
    const end = addDays(anchor, 1);
    return {
      start: anchor,
      end,
      days: [anchor],
      label: rangeLabel(view, anchor, end, anchor),
      compactLabel: compactRangeLabel(view, anchor, end, anchor),
    };
  }
  if (view === "threeDay") {
    const end = addDays(anchor, 3);
    return {
      start: anchor,
      end,
      days: civilDays(anchor, end),
      label: rangeLabel(view, anchor, end, anchor),
      compactLabel: compactRangeLabel(view, anchor, end, anchor),
    };
  }
  if (view === "week") {
    const start = startOfMondayWeek(anchor);
    const end = addDays(start, 7);
    return {
      start,
      end,
      days: civilDays(start, end),
      label: rangeLabel(view, start, end, anchor),
      compactLabel: compactRangeLabel(view, start, end, anchor),
    };
  }
  if (view === "next7") {
    const end = addDays(anchor, 7);
    return {
      start: anchor,
      end,
      days: civilDays(anchor, end),
      label: rangeLabel(view, anchor, end, anchor),
      compactLabel: compactRangeLabel(view, anchor, end, anchor),
    };
  }
  const monthStart = `${anchor.slice(0, 7)}-01`;
  const nextMonth = civilUtc(monthStart);
  nextMonth.setUTCMonth(nextMonth.getUTCMonth() + 1);
  const start = monthGridStart(anchor);
  const nextMonthDate = civilFromUtc(nextMonth);
  const partialFinalWeek = startOfMondayWeek(nextMonthDate);
  const end =
    partialFinalWeek === nextMonthDate
      ? nextMonthDate
      : addDays(partialFinalWeek, 7);
  return {
    start,
    end,
    days: civilDays(start, end),
    label: rangeLabel(view, start, end, anchor),
    compactLabel: compactRangeLabel(view, start, end, anchor),
  };
}

export function navigateCalendarAnchor(
  view: CalendarView,
  anchor: string,
  direction: -1 | 1,
) {
  if (view === "day") return addDays(anchor, direction);
  if (view === "threeDay") return addDays(anchor, direction * 3);
  if (view === "week" || view === "next7")
    return addDays(anchor, direction * 7);
  const date = civilUtc(`${anchor.slice(0, 7)}-01`);
  date.setUTCMonth(date.getUTCMonth() + direction);
  return civilFromUtc(date);
}

export function sourceCalendarColor(calendarId: string): CalendarColor {
  let hash = 2_166_136_261;
  for (const character of calendarId) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16_777_619);
  }
  return sourcePalette[(hash >>> 0) % sourcePalette.length];
}

export function categoryColor(
  category: CalendarCategory | null,
  subtype: string | null = null,
): CalendarColor {
  if (!category) return uncategorizedColor;
  return subtypePalette[category]?.[subtype ?? ""] ?? categoryPalette[category];
}

function zonedParts(value: Date, timeZone: string): ZonedParts {
  const parts = new Intl.DateTimeFormat("en-US-u-ca-gregory-nu-latn", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(value);
  const read = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((part) => part.type === type)?.value ?? 0);
  const year = read("year");
  const month = read("month");
  const day = read("day");
  return {
    date: `${year.toString().padStart(4, "0")}-${month.toString().padStart(2, "0")}-${day.toString().padStart(2, "0")}`,
    year,
    month,
    day,
    hour: read("hour"),
    minute: read("minute"),
    second: read("second"),
  };
}

function zonedInstant(
  date: string,
  time: Pick<ZonedParts, "hour" | "minute" | "second">,
  timeZone: string,
) {
  const [year, month, day] = date.split("-").map(Number);
  const target = Date.UTC(
    year,
    month - 1,
    day,
    time.hour,
    time.minute,
    time.second,
  );
  let value = target;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const rendered = zonedParts(new Date(value), timeZone);
    const renderedAsUtc = Date.UTC(
      rendered.year,
      rendered.month - 1,
      rendered.day,
      rendered.hour,
      rendered.minute,
      rendered.second,
    );
    value += target - renderedAsUtc;
  }
  return new Date(value);
}

function dayBounds(date: string, timeZone: string) {
  const midnight = { hour: 0, minute: 0, second: 0 };
  return [
    zonedInstant(date, midnight, timeZone),
    zonedInstant(addDays(date, 1), midnight, timeZone),
  ] as const;
}

function intersectsRange(
  start: Date,
  end: Date,
  bounds: readonly [Date, Date],
) {
  return start < bounds[1] && end > bounds[0];
}

function parseRule(lines: string[]): ParsedRule | null {
  const line = lines.find((value) => value.startsWith("RRULE:"));
  if (!line) return null;
  const values = new Map(
    line
      .slice(6)
      .split(";")
      .map((part) => {
        const [key, value = ""] = part.split("=", 2);
        return [key, value];
      }),
  );
  const frequency = values.get("FREQ");
  if (
    !frequency ||
    !["DAILY", "WEEKLY", "MONTHLY", "YEARLY"].includes(frequency)
  ) {
    return null;
  }
  const positive = (value: string | undefined, fallback: number) => {
    const parsed = Number(value);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
  };
  return {
    frequency: frequency as ParsedRule["frequency"],
    interval: positive(values.get("INTERVAL"), 1),
    count: values.has("COUNT") ? positive(values.get("COUNT"), 1) : null,
    until: values.get("UNTIL") || null,
    byDay: values.get("BYDAY")?.split(",").filter(Boolean) ?? [],
    byMonthDay:
      values
        .get("BYMONTHDAY")
        ?.split(",")
        .map(Number)
        .filter((value) => Number.isInteger(value) && value !== 0) ?? [],
    byMonth:
      values
        .get("BYMONTH")
        ?.split(",")
        .map(Number)
        .filter((value) => value >= 1 && value <= 12) ?? [],
    weekStart: values.get("WKST") || "MO",
  };
}

function monthDifference(start: string, candidate: string) {
  const initial = civilUtc(start);
  const current = civilUtc(candidate);
  return (
    (current.getUTCFullYear() - initial.getUTCFullYear()) * 12 +
    current.getUTCMonth() -
    initial.getUTCMonth()
  );
}

function daysInMonth(date: string) {
  const value = civilUtc(date);
  return new Date(
    Date.UTC(value.getUTCFullYear(), value.getUTCMonth() + 1, 0),
  ).getUTCDate();
}

function matchesByDay(date: string, tokens: string[]) {
  if (tokens.length === 0) return true;
  const value = civilUtc(date);
  const weekday = weekdayCodes[value.getUTCDay()];
  return tokens.some((token) => {
    const match = token.match(/^([+-]?\d+)?([A-Z]{2})$/);
    if (!match || match[2] !== weekday) return false;
    if (!match[1]) return true;
    const ordinal = Number(match[1]);
    const day = value.getUTCDate();
    if (ordinal > 0) return Math.floor((day - 1) / 7) + 1 === ordinal;
    return Math.floor((daysInMonth(date) - day) / 7) + 1 === Math.abs(ordinal);
  });
}

function weekIndex(start: string, candidate: string, weekStart: string) {
  const requested = weekdayCodes.indexOf(weekStart);
  const index = requested >= 0 ? requested : 1;
  const align = (date: string) => {
    const weekday = civilUtc(date).getUTCDay();
    return addDays(date, -((weekday - index + 7) % 7));
  };
  return Math.floor(differenceInDays(align(start), align(candidate)) / 7);
}

function matchesRule(date: string, start: string, rule: ParsedRule) {
  const elapsed = differenceInDays(start, date);
  if (elapsed < 0) return false;
  const value = civilUtc(date);
  const initial = civilUtc(start);
  if (
    rule.byMonth.length > 0 &&
    !rule.byMonth.includes(value.getUTCMonth() + 1)
  )
    return false;
  if (
    rule.byMonthDay.length > 0 &&
    !rule.byMonthDay.some((day) =>
      day > 0
        ? value.getUTCDate() === day
        : value.getUTCDate() === daysInMonth(date) + day + 1,
    )
  ) {
    return false;
  }
  if (!matchesByDay(date, rule.byDay)) return false;
  if (rule.frequency === "DAILY") return elapsed % rule.interval === 0;
  if (rule.frequency === "WEEKLY") {
    const days =
      rule.byDay.length > 0 ? rule.byDay : [weekdayCodes[initial.getUTCDay()]];
    return (
      weekIndex(start, date, rule.weekStart) % rule.interval === 0 &&
      matchesByDay(date, days)
    );
  }
  if (rule.frequency === "MONTHLY") {
    if (monthDifference(start, date) % rule.interval !== 0) return false;
    if (rule.byMonthDay.length === 0 && rule.byDay.length === 0) {
      return value.getUTCDate() === initial.getUTCDate();
    }
    return true;
  }
  const years = value.getUTCFullYear() - initial.getUTCFullYear();
  if (years % rule.interval !== 0) return false;
  if (
    rule.byMonth.length === 0 &&
    value.getUTCMonth() !== initial.getUTCMonth()
  )
    return false;
  if (rule.byMonthDay.length === 0 && rule.byDay.length === 0) {
    return value.getUTCDate() === initial.getUTCDate();
  }
  return true;
}

function compactDateTime(value: string, timeZone: string) {
  if (/^\d{8}$/.test(value)) {
    return {
      kind: "date" as const,
      date: `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`,
    };
  }
  const match = value.match(
    /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z?)$/,
  );
  if (!match) return null;
  const date = `${match[1]}-${match[2]}-${match[3]}`;
  const time = {
    hour: Number(match[4]),
    minute: Number(match[5]),
    second: Number(match[6]),
  };
  return {
    kind: "instant" as const,
    instant: match[7]
      ? new Date(`${date}T${match[4]}:${match[5]}:${match[6]}Z`)
      : zonedInstant(date, time, timeZone),
  };
}

function untilAllows(
  candidateDate: string,
  candidateStart: Date | null,
  until: string | null,
  timeZone: string,
) {
  if (!until) return true;
  const parsed = compactDateTime(until, timeZone);
  if (!parsed) return true;
  return parsed.kind === "date"
    ? candidateDate <= parsed.date
    : candidateStart !== null
      ? candidateStart <= parsed.instant
      : candidateDate <= zonedParts(parsed.instant, timeZone).date;
}

function recurrenceValues(
  lines: string[],
  name: "EXDATE" | "RDATE",
  timeZone: string,
) {
  return lines
    .filter(
      (line) => line.startsWith(`${name}:`) || line.startsWith(`${name};`),
    )
    .flatMap((line) => line.slice(line.indexOf(":") + 1).split(","))
    .map((value) => compactDateTime(value, timeZone))
    .filter((value): value is NonNullable<typeof value> => value !== null);
}

function originalKey(masterId: string, block: CalendarBlock) {
  if (block.original_start_kind === "date" && block.original_start_date) {
    return `${masterId}|date:${block.original_start_date}`;
  }
  if (block.original_start_kind === "instant" && block.original_start_at) {
    return `${masterId}|instant:${new Date(block.original_start_at).toISOString()}`;
  }
  return null;
}

function occurrenceKey(masterId: string, date: string, instant: Date | null) {
  return instant
    ? `${masterId}|instant:${instant.toISOString()}`
    : `${masterId}|date:${date}`;
}

/**
 * An explicit exception overrides exactly one generated occurrence, identified
 * by its immutable original start. After a confirmed whole-series change moves
 * or re-rules the master, an older exception can be left anchored to a slot the
 * confirmed rule no longer produces -- Google resets instance exceptions in that
 * case. Such a row is a stale local override, not a legitimate provider
 * exception: it must neither suppress a generated occurrence nor render itself
 * as a phantom event at the old time, until read sync reconciles it.
 *
 * Anchoring is only denied when it can be positively determined. Anything
 * uncertain (missing master, unparseable rule, absent original start) keeps the
 * previous behaviour, so genuine data is never hidden.
 */
function exceptionIsAnchored(
  master: CalendarBlock,
  exception: CalendarBlock,
  localTimeZone: string,
): boolean {
  const rule = parseRule(master.recurrence_rules);
  if (!rule || master.status === "cancelled" || master.provider_deleted_at) {
    return true;
  }
  const allDay = master.temporal_kind === "all_day";
  if (allDay) {
    if (!master.start_date || exception.original_start_kind !== "date") {
      return true;
    }
    const originalDate = exception.original_start_date;
    if (!originalDate) return true;
    return (
      matchesRule(originalDate, master.start_date, rule) &&
      untilAllows(originalDate, null, rule.until, localTimeZone)
    );
  }
  if (!master.start_at || exception.original_start_kind !== "instant") {
    return true;
  }
  const originalAt = exception.original_start_at;
  if (!originalAt) return true;
  const zone = master.start_timezone ?? localTimeZone;
  const masterParts = zonedParts(new Date(master.start_at), zone);
  const originalInstant = new Date(originalAt);
  const originalParts = zonedParts(originalInstant, zone);
  // The slot must exist in the confirmed rule *and* carry the series' current
  // time of day: a moved series leaves old exceptions on the previous clock
  // time, which is exactly the stale-override case.
  if (!matchesRule(originalParts.date, masterParts.date, rule)) return false;
  if (!untilAllows(originalParts.date, originalInstant, rule.until, zone)) {
    return false;
  }
  return (
    zonedInstant(originalParts.date, masterParts, zone).valueOf() ===
    originalInstant.valueOf()
  );
}

function directOccurrence(
  block: CalendarBlock,
  calendar: GoogleCalendar,
  account: GoogleAccount | null,
): CalendarOccurrence | null {
  if (block.status === "cancelled" || block.provider_deleted_at) return null;
  if (block.temporal_kind === "all_day") {
    if (!block.start_date || !block.end_date) return null;
    return {
      key: block.id,
      block,
      calendar,
      account,
      allDay: true,
      startDate: block.start_date,
      endDate: block.end_date,
      start: null,
      end: null,
      recurrenceContext:
        block.recurrence_kind === "exception"
          ? "exception"
          : block.recurrence_kind === "master"
            ? "occurrence"
            : "single",
    };
  }
  if (!block.start_at || !block.end_at) return null;
  const start = new Date(block.start_at);
  const end = new Date(block.end_at);
  if (
    Number.isNaN(start.valueOf()) ||
    Number.isNaN(end.valueOf()) ||
    end <= start
  )
    return null;
  return {
    key: block.id,
    block,
    calendar,
    account,
    allDay: false,
    startDate: null,
    endDate: null,
    start,
    end,
    recurrenceContext:
      block.recurrence_kind === "exception"
        ? "exception"
        : block.recurrence_kind === "master"
          ? "occurrence"
          : "single",
  };
}

function occurrenceIntersects(
  occurrence: CalendarOccurrence,
  range: CalendarRange,
  bounds: readonly [Date, Date],
) {
  if (occurrence.allDay) {
    return (
      occurrence.startDate! < range.end && occurrence.endDate! > range.start
    );
  }
  return intersectsRange(occurrence.start!, occurrence.end!, bounds);
}

function occurrenceMatchesPendingIdentity(occurrence: CalendarOccurrence) {
  const identity = occurrence.block.provider_write_original_start;
  if (!identity) return false;
  if (occurrence.allDay) return identity.date === occurrence.startDate;
  return (
    Boolean(identity.date_time) &&
    Boolean(occurrence.start) &&
    new Date(identity.date_time!).valueOf() === occurrence.start!.valueOf()
  );
}

function scopedOccurrenceWrite(
  occurrence: CalendarOccurrence,
): CalendarOccurrence {
  const block = occurrence.block;
  if (block.provider_write_recurrence_scope !== "occurrence") return occurrence;
  const targeted =
    occurrence.recurrenceContext === "exception" ||
    occurrenceMatchesPendingIdentity(occurrence);
  // The master's row also stands in for every not-yet-materialized sibling
  // occurrence, so only a write that is genuinely still in flight may
  // serialize them. A resolved write -- confirmed, cancelled, conflicted, or
  // terminally failed -- belongs to exactly one occurrence; every other
  // occurrence must not keep inheriting it.
  const stillInFlight = block.provider_write_state === "pending";
  if (!targeted) {
    if (!stillInFlight) {
      if (block.provider_write_capability.reason !== "write_pending") {
        // Something unrelated to this write already makes it ineligible
        // (reauth, a disabled calendar, etc.); leave that reason intact.
        return occurrence;
      }
      return {
        ...occurrence,
        block: {
          ...block,
          provider_write_capability: { eligible: true, reason: "eligible" },
          provider_delete_capability: {
            eligible: true,
            mode: "provider_delete",
            reason: "eligible",
          },
          provider_write_operation: null,
          provider_write_recurrence_scope: null,
          provider_write_original_start: null,
          provider_write_overlay: null,
          provider_write_state: "synced",
          provider_write_detail: "confirmed",
        },
      };
    }
    return {
      ...occurrence,
      block: {
        ...block,
        // The overlay is scoped to one original-start identity, but the durable
        // outbox is serialized on the canonical master. Sibling occurrences
        // stay visually confirmed while correctly refusing a second write.
        provider_write_capability: {
          eligible: false,
          reason: "write_pending",
        },
        provider_delete_capability: {
          eligible: false,
          mode: null,
          reason: "write_pending",
        },
        provider_write_operation: null,
        provider_write_recurrence_scope: null,
        provider_write_original_start: null,
        provider_write_overlay: null,
        provider_write_state: "synced",
        provider_write_detail: "confirmed",
      },
    };
  }
  if (!stillInFlight) return occurrence;
  const overlay = block.provider_write_overlay;
  if (!overlay) return occurrence;
  const nextBlock = {
    ...block,
    title: overlay.title ?? block.title,
  };
  if (overlay.start?.date && overlay.end?.date) {
    return {
      ...occurrence,
      block: nextBlock,
      allDay: true,
      startDate: overlay.start.date,
      endDate: overlay.end.date,
      start: null,
      end: null,
    };
  }
  if (overlay.start?.date_time && overlay.end?.date_time) {
    return {
      ...occurrence,
      block: nextBlock,
      allDay: false,
      startDate: null,
      endDate: null,
      start: new Date(overlay.start.date_time),
      end: new Date(overlay.end.date_time),
    };
  }
  return { ...occurrence, block: nextBlock };
}

function projectMaster(
  master: CalendarBlock,
  calendar: GoogleCalendar,
  account: GoogleAccount | null,
  range: CalendarRange,
  localTimeZone: string,
  suppressed: Set<string>,
  bounds: readonly [Date, Date],
): CalendarProjection {
  const rule = parseRule(master.recurrence_rules);
  if (!rule || master.status === "cancelled" || master.provider_deleted_at) {
    const direct = directOccurrence(master, calendar, account);
    return {
      occurrences:
        direct && occurrenceIntersects(direct, range, bounds) ? [direct] : [],
      limited: false,
    };
  }
  const allDay = master.temporal_kind === "all_day";
  if (allDay && (!master.start_date || !master.end_date))
    return { occurrences: [], limited: false };
  if (
    !allDay &&
    (!master.start_at || !master.end_at || !master.start_timezone)
  ) {
    return { occurrences: [], limited: false };
  }
  const startInstant = allDay ? null : new Date(master.start_at!);
  const endInstant = allDay ? null : new Date(master.end_at!);
  const zone = master.start_timezone ?? localTimeZone;
  const initialParts = allDay ? null : zonedParts(startInstant!, zone);
  const initialDate = allDay ? master.start_date! : initialParts!.date;
  const durationDays = allDay
    ? Math.max(1, differenceInDays(master.start_date!, master.end_date!))
    : 0;
  const durationMs = allDay
    ? 0
    : Math.max(1, endInstant!.valueOf() - startInstant!.valueOf());
  const exdates = new Set(
    recurrenceValues(master.recurrence_rules, "EXDATE", zone).map((value) =>
      value.kind === "date"
        ? occurrenceKey(master.id, value.date, null)
        : occurrenceKey(master.id, "", value.instant),
    ),
  );
  const occurrences: CalendarOccurrence[] = [];
  let matched = 0;
  let scanned = 0;
  let limited = false;
  const lookback = allDay ? durationDays : 1;
  let candidate = rule.count
    ? initialDate
    : initialDate > addDays(range.start, -lookback)
      ? initialDate
      : addDays(range.start, -lookback);
  const earliestVisibleCandidate = addDays(range.start, -lookback);

  while (candidate < range.end) {
    if (scanned >= MAX_SCAN_DAYS || occurrences.length >= MAX_OCCURRENCES) {
      limited = true;
      break;
    }
    scanned += 1;
    if (matchesRule(candidate, initialDate, rule)) {
      const candidateMayIntersect = candidate >= earliestVisibleCandidate;
      const candidateStart =
        allDay || (!candidateMayIntersect && !rule.until?.includes("T"))
          ? null
          : zonedInstant(candidate, initialParts!, zone);
      if (!untilAllows(candidate, candidateStart, rule.until, zone)) break;
      matched += 1;
      if (rule.count !== null && matched > rule.count) break;
      if (candidateMayIntersect) {
        const visibleStart =
          allDay || candidateStart
            ? candidateStart
            : zonedInstant(candidate, initialParts!, zone);
        const key = occurrenceKey(master.id, candidate, visibleStart);
        if (!suppressed.has(key) && !exdates.has(key)) {
          const occurrence = scopedOccurrenceWrite(
            allDay
              ? {
                  key,
                  block: master,
                  calendar,
                  account,
                  allDay: true,
                  startDate: candidate,
                  endDate: addDays(candidate, durationDays),
                  start: null,
                  end: null,
                  recurrenceContext: "occurrence",
                }
              : {
                  key,
                  block: master,
                  calendar,
                  account,
                  allDay: false,
                  startDate: null,
                  endDate: null,
                  start: visibleStart,
                  end: new Date(visibleStart!.valueOf() + durationMs),
                  recurrenceContext: "occurrence",
                },
          );
          if (occurrenceIntersects(occurrence, range, bounds)) {
            occurrences.push(occurrence);
          }
        }
      }
    }
    candidate = addDays(candidate, 1);
  }

  for (const value of recurrenceValues(
    master.recurrence_rules,
    "RDATE",
    zone,
  )) {
    const key =
      value.kind === "date"
        ? occurrenceKey(master.id, value.date, null)
        : occurrenceKey(master.id, "", value.instant);
    if (
      suppressed.has(key) ||
      exdates.has(key) ||
      occurrences.some((item) => item.key === key)
    )
      continue;
    const occurrence = scopedOccurrenceWrite(
      value.kind === "date"
        ? {
            key,
            block: master,
            calendar,
            account,
            allDay: true,
            startDate: value.date,
            endDate: addDays(value.date, durationDays || 1),
            start: null,
            end: null,
            recurrenceContext: "occurrence",
          }
        : {
            key,
            block: master,
            calendar,
            account,
            allDay: false,
            startDate: null,
            endDate: null,
            start: value.instant,
            end: new Date(value.instant.valueOf() + durationMs),
            recurrenceContext: "occurrence",
          },
    );
    if (occurrenceIntersects(occurrence, range, bounds))
      occurrences.push(occurrence);
  }
  return { occurrences, limited };
}

export function buildCalendarProjectionIndex(
  status: CalendarStatus,
  localTimeZone: string = "UTC",
): CalendarProjectionIndex {
  const calendars = new Map(
    status.calendars
      .filter(
        (calendar) =>
          calendar.enabled_in_ion &&
          !calendar.hidden_in_ion &&
          !calendar.provider_deleted,
      )
      .map((calendar) => [calendar.id, calendar]),
  );
  const accounts = new Map(
    status.accounts.map((account) => [account.id, account]),
  );
  const blocks = status.blocks.filter((block) =>
    calendars.has(block.calendar_id),
  );
  const masters = blocks.filter((block) => block.recurrence_kind === "master");
  const mastersById = new Map(masters.map((master) => [master.id, master]));
  const mastersByProvider = new Map(
    masters.map((master) => [
      `${master.calendar_id}|${master.provider_event_id}`,
      master,
    ]),
  );
  const masterFor = (block: CalendarBlock) =>
    block.recurrence_master_block_id
      ? (mastersById.get(block.recurrence_master_block_id) ?? null)
      : block.recurring_event_id
        ? (mastersByProvider.get(
            `${block.calendar_id}|${block.recurring_event_id}`,
          ) ?? null)
        : null;
  const suppressed = new Set<string>();
  const unanchoredExceptions = new Set<string>();
  for (const exception of blocks) {
    if (exception.recurrence_kind !== "exception") continue;
    const master = masterFor(exception);
    if (!master) continue;
    if (!exceptionIsAnchored(master, exception, localTimeZone)) {
      // A confirmed whole-series change re-anchored the rule; this override no
      // longer belongs to any occurrence, so it must not suppress the freshly
      // confirmed generated occurrence or render at its own stale time.
      unanchoredExceptions.add(exception.id);
      continue;
    }
    const key = originalKey(master.id, exception);
    if (key) suppressed.add(key);
  }
  return {
    calendars,
    accounts,
    blocks,
    suppressed,
    unanchoredExceptions,
    cache: new Map(),
  };
}

export function projectCalendarIndex(
  index: CalendarProjectionIndex,
  range: CalendarRange,
  localTimeZone: string,
): CalendarProjection {
  const cacheKey = `${localTimeZone}|${range.start}|${range.end}`;
  const cached = index.cache.get(cacheKey);
  if (cached) return cached;
  const [rangeStart] = dayBounds(range.start, localTimeZone);
  const [rangeEnd] = dayBounds(range.end, localTimeZone);
  const bounds = [rangeStart, rangeEnd] as const;

  const occurrences: CalendarOccurrence[] = [];
  let limited = false;
  for (const block of index.blocks) {
    const calendar = index.calendars.get(block.calendar_id)!;
    const account = index.accounts.get(calendar.account_id) ?? null;
    if (block.recurrence_kind === "master") {
      const projection = projectMaster(
        block,
        calendar,
        account,
        range,
        localTimeZone,
        index.suppressed,
        bounds,
      );
      occurrences.push(...projection.occurrences);
      limited ||= projection.limited;
      continue;
    }
    if (index.unanchoredExceptions.has(block.id)) {
      // Stale override from a confirmed whole-series change: rendering it would
      // show the pre-change state next to the newly confirmed occurrences and
      // hand the Inspector a base that no longer matches anything visible.
      continue;
    }
    const direct = directOccurrence(block, calendar, account);
    const occurrence = direct ? scopedOccurrenceWrite(direct) : null;
    if (occurrence && occurrenceIntersects(occurrence, range, bounds)) {
      occurrences.push(occurrence);
    }
  }
  occurrences.sort((left, right) => {
    const leftValue = left.allDay ? left.startDate! : left.start!.toISOString();
    const rightValue = right.allDay
      ? right.startDate!
      : right.start!.toISOString();
    return (
      leftValue.localeCompare(rightValue) ||
      left.block.title.localeCompare(right.block.title) ||
      left.key.localeCompare(right.key)
    );
  });
  const projection = { occurrences, limited };
  if (index.cache.size >= 12) {
    const oldest = index.cache.keys().next().value;
    if (oldest) index.cache.delete(oldest);
  }
  index.cache.set(cacheKey, projection);
  return projection;
}

export function projectCalendar(
  status: CalendarStatus,
  range: CalendarRange,
  localTimeZone: string,
): CalendarProjection {
  return projectCalendarIndex(
    buildCalendarProjectionIndex(status, localTimeZone),
    range,
    localTimeZone,
  );
}

export function occurrencesForDay(
  occurrences: CalendarOccurrence[],
  date: string,
  localTimeZone: string,
) {
  const [start, end] = dayBounds(date, localTimeZone);
  return occurrences.filter((occurrence) =>
    occurrence.allDay
      ? occurrence.startDate! <= date && occurrence.endDate! > date
      : occurrence.start! < end && occurrence.end! > start,
  );
}

function wallMinute(value: Date, timeZone: string) {
  const parts = zonedParts(value, timeZone);
  return parts.hour * 60 + parts.minute + parts.second / 60;
}

export function minuteOfDay(value: Date, timeZone: string) {
  return wallMinute(value, timeZone);
}

export function timedSegmentsForDay(
  occurrences: CalendarOccurrence[],
  date: string,
  localTimeZone: string,
): TimedSegment[] {
  const [dayStart, dayEnd] = dayBounds(date, localTimeZone);
  const raw = occurrences
    .filter(
      (occurrence) =>
        !occurrence.allDay &&
        occurrence.start! < dayEnd &&
        occurrence.end! > dayStart,
    )
    .map((occurrence) => {
      const clippedStart =
        occurrence.start! < dayStart ? dayStart : occurrence.start!;
      const clippedEnd = occurrence.end! > dayEnd ? dayEnd : occurrence.end!;
      const startMinute =
        clippedStart <= dayStart ? 0 : wallMinute(clippedStart, localTimeZone);
      let endMinute =
        clippedEnd >= dayEnd ? 1_440 : wallMinute(clippedEnd, localTimeZone);
      if (endMinute <= startMinute)
        endMinute = Math.min(1_440, startMinute + 1);
      return { occurrence, startMinute, endMinute, column: 0, columnCount: 1 };
    })
    .sort(
      (left, right) =>
        left.startMinute - right.startMinute ||
        right.endMinute - left.endMinute ||
        left.occurrence.key.localeCompare(right.occurrence.key),
    );

  let cluster: TimedSegment[] = [];
  let clusterEnd = -1;
  const finish = () => {
    if (cluster.length === 0) return;
    const active: TimedSegment[] = [];
    let columns = 1;
    for (const item of cluster) {
      for (let index = active.length - 1; index >= 0; index -= 1) {
        if (active[index].endMinute <= item.startMinute)
          active.splice(index, 1);
      }
      const occupied = new Set(active.map((entry) => entry.column));
      let column = 0;
      while (occupied.has(column)) column += 1;
      item.column = column;
      columns = Math.max(columns, column + 1);
      active.push(item);
    }
    cluster.forEach((item) => (item.columnCount = columns));
    cluster = [];
  };

  for (const item of raw) {
    if (cluster.length > 0 && item.startMinute >= clusterEnd) finish();
    cluster.push(item);
    clusterEnd = Math.max(clusterEnd, item.endMinute);
  }
  finish();
  return raw;
}

export function calendarFreeGaps(
  occurrences: CalendarOccurrence[],
  date: string,
  localTimeZone: string,
  windowStart = 360,
  windowEnd = 1_380,
) {
  const occupied = timedSegmentsForDay(
    occurrences.filter(
      (occurrence) => occurrence.block.transparency === "opaque",
    ),
    date,
    localTimeZone,
  )
    .map((segment) => ({
      startMinute: Math.max(windowStart, segment.startMinute),
      endMinute: Math.min(windowEnd, segment.endMinute),
    }))
    .filter((segment) => segment.endMinute > segment.startMinute)
    .sort((left, right) => left.startMinute - right.startMinute);
  const merged: CalendarGap[] = [];
  for (const interval of occupied) {
    const previous = merged.at(-1);
    if (!previous || interval.startMinute > previous.endMinute)
      merged.push({ ...interval });
    else previous.endMinute = Math.max(previous.endMinute, interval.endMinute);
  }
  const gaps: CalendarGap[] = [];
  let cursor = windowStart;
  for (const interval of merged) {
    if (interval.startMinute - cursor >= 30)
      gaps.push({ startMinute: cursor, endMinute: interval.startMinute });
    cursor = Math.max(cursor, interval.endMinute);
  }
  if (windowEnd - cursor >= 30)
    gaps.push({ startMinute: cursor, endMinute: windowEnd });
  return gaps;
}

export function formatMinutes(value: number) {
  const hour = Math.floor(value / 60);
  const minute = Math.round(value % 60);
  const date = new Date(Date.UTC(2030, 0, 1, hour, minute));
  return new Intl.DateTimeFormat(undefined, {
    timeZone: "UTC",
    hour: "numeric",
    minute: minute === 0 ? undefined : "2-digit",
  }).format(date);
}

export function formatOccurrenceTime(
  occurrence: CalendarOccurrence,
  localTimeZone: string,
) {
  if (occurrence.allDay) return "All day";
  const formatter = new Intl.DateTimeFormat(undefined, {
    timeZone: localTimeZone,
    hour: "numeric",
    minute: "2-digit",
  });
  return `${formatter.format(occurrence.start!)}–${formatter.format(occurrence.end!)}`;
}
