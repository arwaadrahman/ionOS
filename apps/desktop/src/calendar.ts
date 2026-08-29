import { invoke } from "@tauri-apps/api/core";

export type GoogleAccount = {
  id: string;
  provider_account_id: string;
  display_name: string;
  granted_scopes: string[];
  auth_state: "connected" | "reauth_required" | "disconnected";
  last_auth_at: string | null;
  created_at: string;
  updated_at: string;
  revision: number;
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
};

export type CalendarBlock = {
  id: string;
  calendar_id: string;
  provider_event_id: string;
  ical_uid: string | null;
  title: string;
  temporal_kind: "all_day" | "timed";
  start_date: string | null;
  end_date: string | null;
  start_at: string | null;
  end_at: string | null;
  start_timezone: string | null;
  end_timezone: string | null;
  status: "confirmed" | "tentative" | "cancelled";
  recurrence_kind: "single" | "master" | "exception";
  flexibility: "locked" | "flexible" | "ion_controlled";
  provider_deleted_at: string | null;
  revision: number;
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
  connect: () => invoke<CalendarStatus>("connect_google_calendar"),
  setEnabled: (calendar: GoogleCalendar, enabled: boolean) =>
    invoke<CalendarStatus>("set_google_calendar_enabled", {
      calendarId: calendar.id,
      enabled,
      expectedRevision: calendar.revision,
    }),
  sync: () => invoke<CalendarStatus>("sync_google_calendars"),
  disconnect: (account: GoogleAccount) =>
    invoke<CalendarStatus>("disconnect_google_calendar", {
      accountId: account.id,
    }),
};
