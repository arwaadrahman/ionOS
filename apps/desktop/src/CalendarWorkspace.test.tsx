import "@testing-library/jest-dom/vitest";
import { invoke } from "@tauri-apps/api/core";
import { useState } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { CalendarWorkspace } from "./CalendarWorkspace";
import { CalendarStatus, emptyCalendarStatus } from "./calendar";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

const account = {
  id: "11111111-1111-4111-8111-111111111111",
  provider_account_id: "synthetic@example.invalid",
  display_name: "Synthetic Google Account",
  granted_scopes: [
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.events.readonly",
  ],
  auth_state: "connected" as const,
  last_auth_at: "2030-01-01T00:00:00Z",
  created_at: "2030-01-01T00:00:00Z",
  updated_at: "2030-01-01T00:00:00Z",
  revision: 1,
};

const calendar = {
  id: "22222222-2222-4222-8222-222222222222",
  account_id: account.id,
  provider_calendar_id: "synthetic@example.invalid",
  summary: "Synthetic Primary Calendar",
  description: null,
  location: null,
  timezone: "America/Los_Angeles",
  access_role: "owner",
  is_primary: true,
  provider_selected: true,
  provider_hidden: false,
  enabled_in_ion: true,
  provider_deleted: false,
  has_sync_token: true,
  sync_state: "idle" as const,
  last_synced_at: "2030-01-01T01:00:00Z",
  last_error_code: null,
  retry_count: 0,
  next_retry_at: null,
  revision: 1,
};

const connected: CalendarStatus = {
  configured: true,
  configuration_path: "/synthetic/google-oauth.json",
  accounts: [account],
  calendars: [calendar],
  blocks: [],
};

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

test("explains missing local configuration without enabling OAuth", () => {
  const status = {
    ...emptyCalendarStatus(),
    configuration_path:
      "/Users/synthetic/Library/Application Support/com.ionos.desktop/google-oauth.json",
  };
  render(<CalendarWorkspace status={status} onStatus={() => undefined} />);
  expect(
    screen.getByText("Local OAuth configuration required."),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Connect Google account" }),
  ).toBeDisabled();
  expect(screen.getByText(/calendarlist.readonly/)).toBeInTheDocument();
  expect(screen.getByText(/events.readonly/)).toBeInTheDocument();
});

test("connects in the system flow then requests the first read sync", async () => {
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "connect_google_calendar") return connected;
    if (command === "sync_google_calendars") return connected;
    throw new Error(`Unexpected command: ${command}`);
  });
  const onStatus = vi.fn();
  render(
    <CalendarWorkspace
      status={{ ...emptyCalendarStatus(), configured: true }}
      onStatus={onStatus}
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Connect Google account" }),
  );
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("connect_google_calendar"),
  );
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("sync_google_calendars"),
  );
  expect(onStatus).toHaveBeenCalledTimes(2);
});

test("Sync Now replaces Never synced with the returned successful projection", async () => {
  const neverSynced: CalendarStatus = {
    ...connected,
    calendars: [
      {
        ...calendar,
        has_sync_token: false,
        last_synced_at: null,
      },
    ],
  };
  const synced: CalendarStatus = {
    ...connected,
    blocks: [
      {
        id: "33333333-3333-4333-8333-333333333333",
        calendar_id: calendar.id,
        provider_event_id: "synthetic-event",
        ical_uid: "synthetic-event@example.invalid",
        title: "Synthetic Calendar Event",
        temporal_kind: "timed",
        start_date: null,
        end_date: null,
        start_at: "2030-01-01T09:00:00-08:00",
        end_at: "2030-01-01T10:00:00-08:00",
        start_timezone: "America/Los_Angeles",
        end_timezone: "America/Los_Angeles",
        status: "confirmed",
        recurrence_kind: "single",
        flexibility: "locked",
        provider_deleted_at: null,
        revision: 1,
      },
    ],
  };
  vi.mocked(invoke).mockResolvedValue(synced);

  function Harness() {
    const [status, setStatus] = useState(neverSynced);
    return <CalendarWorkspace status={status} onStatus={setStatus} />;
  }

  render(<Harness />);
  expect(screen.getByText(/Never synced/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Sync now" }));

  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("sync_google_calendars"),
  );
  await waitFor(() =>
    expect(screen.queryByText(/Never synced/)).not.toBeInTheDocument(),
  );
  expect(screen.getByText("1 cached canonical block")).toBeInTheDocument();
});

test("renders only the safe provider rejection classification", () => {
  render(
    <CalendarWorkspace
      status={{
        ...connected,
        calendars: [
          {
            ...calendar,
            has_sync_token: false,
            sync_state: "failed",
            last_synced_at: null,
            last_error_code: "provider_not_found",
          },
        ],
      }}
      onStatus={() => undefined}
    />,
  );
  expect(screen.getByText("provider not found")).toBeInTheDocument();
  expect(screen.getByText(/Never synced/)).toBeInTheDocument();
});

test("changes only Ion selection and disconnects through fixed commands", async () => {
  const disabled = {
    ...connected,
    calendars: [{ ...calendar, enabled_in_ion: false, revision: 2 }],
  };
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "set_google_calendar_enabled") return disabled;
    if (command === "disconnect_google_calendar")
      return {
        ...connected,
        accounts: [{ ...account, auth_state: "disconnected" }],
      };
    throw new Error(`Unexpected command: ${command}`);
  });
  const onStatus = vi.fn();
  render(<CalendarWorkspace status={connected} onStatus={onStatus} />);
  fireEvent.click(screen.getByRole("checkbox", { name: "Enabled in Ion" }));
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("set_google_calendar_enabled", {
      calendarId: calendar.id,
      enabled: false,
      expectedRevision: 1,
    }),
  );
  expect(screen.getByText("owner · America/Los_Angeles")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Disconnect & revoke" }));
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("disconnect_google_calendar", {
      accountId: account.id,
    }),
  );
});
