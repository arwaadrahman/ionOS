import { invoke } from "@tauri-apps/api/core";

export const calendarCategories = [
  "academic",
  "career",
  "personal_project",
  "routine_physical",
  "personal",
  "fun",
  "ion_focus",
] as const;

export type CalendarCategory = (typeof calendarCategories)[number];
export type CalendarFilterCategory = CalendarCategory | "uncategorized";
export type CalendarDensity = "compact" | "default" | "expanded";
export type CalendarDrawerMode = "calendars" | "filters" | null;

export const calendarDensityHeights: Record<CalendarDensity, number> = {
  compact: 36,
  default: 56,
  expanded: 72,
};

export const calendarFilterCategories: CalendarFilterCategory[] = [
  "uncategorized",
  ...calendarCategories,
];

export const calendarCategoryLabels: Record<CalendarCategory, string> = {
  academic: "Academic",
  career: "Career",
  personal_project: "Personal project",
  routine_physical: "Routine / physical",
  personal: "Personal",
  fun: "Fun",
  ion_focus: "Ion focus",
};

export const calendarSubtypeDefinitions = [
  { value: "class_section", category: "academic", label: "Class / section" },
  {
    value: "homework_study",
    category: "academic",
    label: "Homework / study",
  },
  { value: "quiz_exam", category: "academic", label: "Quiz / exam" },
  {
    value: "internship_recruiting",
    category: "career",
    label: "Internship / recruiting",
  },
  {
    value: "application_admin",
    category: "career",
    label: "Application / admin",
  },
  {
    value: "interview_networking",
    category: "career",
    label: "Interview / networking",
  },
  {
    value: "build",
    category: "personal_project",
    label: "Build",
  },
  {
    value: "research",
    category: "personal_project",
    label: "Research",
  },
  { value: "creative", category: "personal_project", label: "Creative" },
  {
    value: "work_shift",
    category: "routine_physical",
    label: "Work / shift",
  },
  { value: "meal", category: "routine_physical", label: "Meal" },
  { value: "gym", category: "routine_physical", label: "Gym" },
  { value: "hygiene", category: "routine_physical", label: "Hygiene" },
  {
    value: "chores_errands",
    category: "routine_physical",
    label: "Chores / errands",
  },
  { value: "appointment", category: "personal", label: "Appointment" },
  { value: "family", category: "personal", label: "Family" },
  { value: "travel", category: "personal", label: "Travel" },
  {
    value: "personal_admin",
    category: "personal",
    label: "Personal admin",
  },
  { value: "social", category: "fun", label: "Social" },
  { value: "entertainment", category: "fun", label: "Entertainment" },
  {
    value: "gaming_media",
    category: "fun",
    label: "Gaming / media",
  },
  { value: "leisure", category: "fun", label: "Leisure" },
] as const satisfies readonly {
  value: string;
  category: CalendarCategory;
  label: string;
}[];

export type CalendarCategorySubtype =
  (typeof calendarSubtypeDefinitions)[number]["value"];

export function calendarSubtypesFor(category: CalendarCategory | null) {
  return category
    ? calendarSubtypeDefinitions.filter((item) => item.category === category)
    : [];
}

export function calendarSubtypeLabel(subtype: string) {
  return (
    calendarSubtypeDefinitions.find((item) => item.value === subtype)?.label ??
    subtype
      .split("_")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ")
  );
}

export function calendarCategoryDisplay(
  category: CalendarCategory | null,
  subtype: string | null,
) {
  if (!category) return "Uncategorized";
  const broad = calendarCategoryLabels[category];
  return subtype ? `${broad} · ${calendarSubtypeLabel(subtype)}` : broad;
}

export const calendarFilterCategoryLabels: Record<
  CalendarFilterCategory,
  string
> = {
  uncategorized: "Uncategorized",
  ...calendarCategoryLabels,
};

export type GoogleAccount = {
  id: string;
  provider_account_id: string;
  display_name: string;
  granted_scopes: string[];
  auth_state: "connected" | "reauth_required" | "disconnected";
  calendar_write_scope_state: "read_only" | "write_granted" | "reauth_required";
  last_auth_at: string | null;
  created_at: string;
  updated_at: string;
  revision: number;
};

export type ProviderWriteCapability = {
  eligible: boolean;
  reason:
    | "eligible"
    | "account_read_only"
    | "reauth_required"
    | "calendar_disabled"
    | "calendar_deleted"
    | "access_role_read_only"
    | "special_event"
    | "provider_locked"
    | "attendees_present"
    | "provider_deleted"
    | "provider_unconfirmed"
    | "recurrence_unsupported"
    | "write_pending";
};

export type GoogleCalendar = {
  id: string;
  account_id: string;
  provider_calendar_id: string;
  summary: string;
  description: string | null;
  location: string | null;
  timezone: string | null;
  access_role: string;
  is_primary: boolean;
  provider_selected: boolean;
  provider_hidden: boolean;
  enabled_in_ion: boolean;
  hidden_in_ion: boolean;
  provider_deleted: boolean;
  has_sync_token: boolean;
  sync_state:
    | "idle"
    | "syncing"
    | "retry_wait"
    | "failed"
    | "reauth_required"
    | "disconnected";
  last_synced_at: string | null;
  last_error_code: string | null;
  retry_count: number;
  next_retry_at: string | null;
  revision: number;
  provider_write_eligible: boolean;
  provider_write_reason: string;
};

export type ProviderWriteIntentSummary = {
  id: string;
  calendar_block_id: string;
  operation:
    "create" | "patch" | "cancel_occurrence" | "delete_event" | "delete_series";
  recurrence_scope: "single" | "occurrence" | "series";
  changed_fields: string[];
  state:
    | "queued"
    | "ready"
    | "attempting"
    | "retry_wait"
    | "reauth_required"
    | "conflict"
    | "ambiguous"
    | "failed"
    | "completed"
    | "cancelled";
  attempt_count: number;
  next_attempt_at: string | null;
  failure_class: string | null;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  provenance: "direct_human";
};

export type CalendarWriteFoundation = {
  accounts: {
    account_id: string;
    state: "read_only" | "write_granted" | "reauth_required";
    write_capable: boolean;
  }[];
  calendars: { calendar_id: string; eligible: boolean; reason: string }[];
  blocks: {
    calendar_block_id: string;
    eligible: boolean;
    reason: string;
  }[];
  pending: ProviderWriteIntentSummary[];
};

export type CalendarCreateSeed = {
  date: string;
  allDay: boolean;
  startTime: string | null;
  endTime: string | null;
};

export type CalendarCreateDraft = {
  command_id: string;
  calendar_id: string;
  title: string;
  date: string;
  all_day: boolean;
  start_time: string | null;
  end_time: string | null;
  timezone: string | null;
};

export type CalendarEditKind = "edit" | "move" | "resize";

export type CalendarEditSeed = {
  editKind: CalendarEditKind;
  startDate?: string;
  startTime?: string;
  endDate?: string;
  endTime?: string;
};

export type CalendarEditDraft = {
  command_id: string;
  calendar_block_id: string;
  edit_kind: CalendarEditKind;
  expected_block_revision: number;
  title: string | null;
  start_date: string | null;
  end_date: string | null;
  start_time: string | null;
  end_time: string | null;
  timezone: string | null;
  locked_confirmed: boolean;
};

export type CalendarBlock = {
  id: string;
  calendar_id: string;
  provider_event_id: string;
  ical_uid: string | null;
  title: string;
  description: string | null;
  location: string | null;
  temporal_kind: "all_day" | "timed";
  start_date: string | null;
  end_date: string | null;
  start_at: string | null;
  end_at: string | null;
  start_timezone: string | null;
  end_timezone: string | null;
  status: "confirmed" | "tentative" | "cancelled";
  transparency: "opaque" | "transparent";
  recurrence_kind: "single" | "master" | "exception";
  recurrence_rules: string[];
  recurrence_master_block_id: string | null;
  recurring_event_id: string | null;
  original_start_kind: "none" | "date" | "instant";
  original_start_date: string | null;
  original_start_at: string | null;
  original_start_timezone: string | null;
  flexibility: "locked" | "flexible" | "ion_controlled";
  notes: string | null;
  category: CalendarCategory | null;
  category_subtype: string | null;
  ion_metadata_revision: number;
  provider_deleted_at: string | null;
  revision: number;
  provider_write_capability: ProviderWriteCapability;
  provider_write_state: "pending" | "synced" | "failed" | "conflict";
  provider_write_detail:
    | "queued"
    | "ready"
    | "syncing"
    | "retry_wait"
    | "reauth_required"
    | "ambiguous"
    | "failed"
    | "conflict"
    | "confirmed";
};

export type CalendarStatus = {
  configured: boolean;
  configuration_path: string;
  accounts: GoogleAccount[];
  calendars: GoogleCalendar[];
  blocks: CalendarBlock[];
};

export type GoogleCommandError = { code: string };

export function asGoogleError(reason: unknown): GoogleCommandError {
  if (
    typeof reason === "object" &&
    reason !== null &&
    "code" in reason &&
    typeof reason.code === "string"
  ) {
    return { code: reason.code };
  }
  return { code: "unavailable" };
}

export const emptyCalendarStatus = (): CalendarStatus => ({
  configured: false,
  configuration_path: "",
  accounts: [],
  calendars: [],
  blocks: [],
});

export const googleCalendarClient = {
  status: () => invoke<CalendarStatus>("get_google_calendar_status"),
  writeFoundation: () =>
    invoke<CalendarWriteFoundation>("get_calendar_write_foundation"),
  connect: () => invoke<CalendarStatus>("connect_google_calendar"),
  enableWrites: (account: GoogleAccount) =>
    invoke<CalendarStatus>("enable_google_calendar_writes", {
      accountId: account.id,
    }),
  create: (draft: CalendarCreateDraft) =>
    invoke<CalendarStatus>("create_google_calendar_event", { draft }),
  edit: (draft: CalendarEditDraft) =>
    invoke<CalendarStatus>("edit_google_calendar_event", { draft }),
  setEnabled: (calendar: GoogleCalendar, enabled: boolean) =>
    invoke<CalendarStatus>("set_google_calendar_enabled", {
      calendarId: calendar.id,
      enabled,
      expectedRevision: calendar.revision,
    }),
  setHidden: (calendar: GoogleCalendar, hidden: boolean) =>
    invoke<CalendarStatus>("set_google_calendar_hidden", {
      calendarId: calendar.id,
      hidden,
      expectedRevision: calendar.revision,
    }),
  setCategory: (
    block: CalendarBlock,
    category: CalendarCategory | null,
    categorySubtype: string | null,
  ) =>
    invoke<CalendarStatus>("set_calendar_block_category", {
      blockId: block.id,
      category,
      categorySubtype,
      expectedRevision: block.ion_metadata_revision,
    }),
  sync: () => invoke<CalendarStatus>("sync_google_calendars"),
  disconnect: (account: GoogleAccount) =>
    invoke<CalendarStatus>("disconnect_google_calendar", {
      accountId: account.id,
    }),
};
