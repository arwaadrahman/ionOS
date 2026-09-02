import "@testing-library/jest-dom/vitest";
import { invoke } from "@tauri-apps/api/core";
import { readFileSync } from "node:fs";
import { useState } from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { CalendarWorkspace } from "./CalendarWorkspace";
import {
  CalendarBlock,
  CalendarStatus,
  GoogleAccount,
  GoogleCalendar,
  emptyCalendarStatus,
} from "./calendar";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

// Ion emits settled Calendar state when it advances a write on its own. The
// test harness captures those listeners so a self-progression can be driven.
const statusListeners = new Set<(event: { payload: CalendarStatus }) => void>();
vi.mock("@tauri-apps/api/event", () => ({
  listen: (event: string, handler: (event: { payload: unknown }) => void) => {
    if (event === "ion:calendar-status") {
      statusListeners.add(
        handler as (event: { payload: CalendarStatus }) => void,
      );
    }
    return Promise.resolve(() => {
      statusListeners.delete(
        handler as (event: { payload: CalendarStatus }) => void,
      );
    });
  },
}));

async function emitCalendarStatus(payload: CalendarStatus) {
  await waitFor(() => expect(statusListeners.size).toBeGreaterThan(0));
  await act(async () => {
    statusListeners.forEach((handler) => handler({ payload }));
  });
}

/**
 * Commands issued by user actions, excluding the Calendar's own background
 * refresh. Google -> Ion convergence runs on its own and is asserted directly
 * elsewhere; it should not appear in assertions about what a click did.
 */
function userInvokedCommands() {
  return vi
    .mocked(invoke)
    .mock.calls.map(([command]) => command)
    .filter((command) => command !== "sync_google_calendars");
}

const account = {
  id: "11111111-1111-4111-8111-111111111111",
  provider_account_id: "synthetic@example.invalid",
  display_name: "Synthetic Google Account",
  granted_scopes: [
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.events.readonly",
  ],
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
  summary: "Synthetic Primary Calendar",
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
  last_synced_at: "2030-01-01T01:00:00Z",
  last_error_code: null,
  retry_count: 0,
  next_retry_at: null,
  revision: 1,
  provider_write_eligible: false,
  provider_write_reason: "account_read_only",
};

const connected: CalendarStatus = {
  configured: true,
  configuration_path: "/synthetic/google-oauth.json",
  accounts: [account],
  calendars: [calendar],
  blocks: [],
};

const now = new Date("2030-01-02T18:30:00Z");
const calendarStyles = readFileSync("src/styles.css", "utf8");
const tauriConfig = JSON.parse(
  readFileSync("src-tauri/tauri.conf.json", "utf8"),
) as {
  app: { windows: { label: string; minWidth?: number; minHeight?: number }[] };
};

function block(
  id: string,
  title: string,
  overrides: Partial<CalendarBlock> = {},
): CalendarBlock {
  return {
    id,
    calendar_id: calendar.id,
    provider_event_id: `provider-${id}`,
    ical_uid: `ical-${id}@example.invalid`,
    title,
    description: null,
    location: null,
    temporal_kind: "timed",
    start_date: null,
    end_date: null,
    start_at: "2030-01-02T09:00:00Z",
    end_at: "2030-01-02T10:00:00Z",
    start_timezone: "UTC",
    end_timezone: "UTC",
    status: "confirmed",
    transparency: "opaque",
    recurrence_kind: "single",
    recurrence_rules: [],
    recurrence_preset: "none",
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
    provider_delete_capability: {
      eligible: false,
      mode: null,
      reason: "account_read_only",
    },
    provider_write_operation: null,
    provider_write_recurrence_scope: null,
    provider_write_original_start: null,
    provider_write_overlay: null,
    provider_write_state: "synced",
    provider_write_detail: "confirmed",
    provider_write_failure_class: null,
    provider_write_failure_reason: null,
    provider_recovery_kind: null,
    ...overrides,
  };
}

function mockTimeColumnRects(container: HTMLElement) {
  const columns = Array.from(
    container.querySelectorAll<HTMLElement>("[data-calendar-date]"),
  );
  const byDate = new Map<string, { x: number }>();
  columns.forEach((column, index) => {
    const left = index * 100;
    vi.spyOn(column, "getBoundingClientRect").mockReturnValue({
      top: 0,
      bottom: 1440,
      left,
      right: left + 100,
      width: 100,
      height: 1440,
      x: left,
      y: 0,
      toJSON: () => ({}),
    });
    byDate.set(column.dataset.calendarDate!, { x: left + 50 });
  });
  return (date: string) => byDate.get(date)!;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("PointerEvent", MouseEvent);
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.sessionStorage.setItem("ion.calendar-sidebar.v1", "calendars");
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

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
        description: null,
        location: null,
        temporal_kind: "timed",
        start_date: null,
        end_date: null,
        start_at: "2030-01-01T09:00:00-08:00",
        end_at: "2030-01-01T10:00:00-08:00",
        start_timezone: "America/Los_Angeles",
        end_timezone: "America/Los_Angeles",
        status: "confirmed",
        transparency: "opaque",
        recurrence_kind: "single",
        recurrence_rules: [],
        recurrence_preset: "none",
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
        provider_delete_capability: {
          eligible: false,
          mode: null,
          reason: "account_read_only",
        },
        provider_write_operation: null,
        provider_write_recurrence_scope: null,
        provider_write_original_start: null,
        provider_write_overlay: null,
        provider_write_state: "synced",
        provider_write_detail: "confirmed",
        provider_write_failure_class: null,
        provider_write_failure_reason: null,
        provider_recovery_kind: null,
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
  fireEvent.click(screen.getByRole("button", { name: "Sync calendars" }));

  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("sync_google_calendars"),
  );
  await waitFor(() =>
    expect(screen.queryByText(/Never synced/)).not.toBeInTheDocument(),
  );
  expect(
    screen.getByText(
      (_, node) =>
        node?.tagName === "SMALL" &&
        node.textContent === "connected · 1 cached canonical block",
    ),
  ).toBeInTheDocument();
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
        blocks: [
          block("33333333-3333-4333-8333-333333333333", "Saved provider event"),
        ],
      }}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  expect(screen.getByText("provider not found")).toBeInTheDocument();
  expect(screen.getByText(/Never synced/)).toBeInTheDocument();
  expect(
    screen.getByText("Some calendars couldn't refresh. Showing saved events."),
  ).toBeInTheDocument();
  expect(screen.queryByText(/CalendarBlocks/)).not.toBeInTheDocument();
});

test("keeps a local category mutation failure distinct from provider refresh copy", async () => {
  const item = block(
    "33333333-3333-4333-8333-333333333334",
    "Local category failure",
    { category: "academic", category_subtype: "class_section" },
  );
  vi.mocked(invoke).mockRejectedValue({ code: "local_state_invalid" });
  render(
    <CalendarWorkspace
      status={{ ...connected, blocks: [item] }}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: /Local category failure/ }),
  );
  fireEvent.change(
    screen.getByLabelText("Local category failure Ion category subtype"),
    {
      target: { value: "homework_study" },
    },
  );
  fireEvent.click(screen.getByRole("button", { name: "Save category" }));
  expect(
    await screen.findByText("That calendar change couldn't be saved."),
  ).toBeInTheDocument();
  expect(screen.queryByText(/local calendar service/i)).not.toBeInTheDocument();
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
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "Synthetic Primary Calendar enabled in Ion",
    }),
  );
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

test("defaults to a Monday-through-Sunday week and navigates every locked view", () => {
  render(
    <CalendarWorkspace
      status={connected}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );

  expect(screen.getByRole("button", { name: "Week view" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByText("Mon, Dec 31")).toBeInTheDocument();
  expect(screen.getByText("Sun, Jan 6")).toBeInTheDocument();
  expect(screen.getByText("Wed, Jan 2").parentElement).toHaveClass("is-today");

  fireEvent.click(screen.getByRole("button", { name: "Previous period" }));
  expect(screen.getByText("Mon, Dec 24")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Today" }));
  expect(screen.getByText("Mon, Dec 31")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Day view" }));
  expect(
    screen.getByRole("heading", { name: "Wednesday, January 2, 2030" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Next period" }));
  expect(
    screen.getByRole("heading", { name: "Thursday, January 3, 2030" }),
  ).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "3 Day view" }));
  fireEvent.click(screen.getByRole("button", { name: "Today" }));
  expect(screen.getByText("Wed, Jan 2")).toBeInTheDocument();
  expect(screen.getByText("Fri, Jan 4")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Next period" }));
  expect(screen.getByText("Sat, Jan 5")).toBeInTheDocument();
  expect(screen.getByText("Mon, Jan 7")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Next 7 Days view" }));
  fireEvent.click(screen.getByRole("button", { name: "Today" }));
  expect(screen.getByText("Wed, Jan 2")).toBeInTheDocument();
  expect(screen.getByText("Tue, Jan 8")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Month view" }));
  expect(
    screen.getByRole("heading", { name: "January 2030" }),
  ).toBeInTheDocument();
  expect(screen.getAllByText("Mon").length).toBeGreaterThan(0);
  expect(screen.getByLabelText("2030-01-02")).toHaveClass("is-today");
});

test("renders unified multi-account timed, all-day, and overlapping events while filtering disabled calendars", () => {
  const schoolAccount: GoogleAccount = {
    ...account,
    id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    provider_account_id: "school@example.invalid",
    display_name: "Synthetic School Account",
  };
  const schoolCalendar: GoogleCalendar = {
    ...calendar,
    id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    account_id: schoolAccount.id,
    provider_calendar_id: "school-calendar@example.invalid",
    summary: "Synthetic School Calendar",
    is_primary: false,
  };
  const disabledCalendar: GoogleCalendar = {
    ...calendar,
    id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    provider_calendar_id: "disabled-calendar@example.invalid",
    summary: "Disabled Calendar",
    enabled_in_ion: false,
    is_primary: false,
  };
  const personalEvent = block(
    "33333333-3333-4333-8333-333333333333",
    "Personal focus",
  );
  const schoolEvent = block(
    "44444444-4444-4444-8444-444444444444",
    "School seminar",
    {
      calendar_id: schoolCalendar.id,
      start_at: "2030-01-02T09:30:00Z",
      end_at: "2030-01-02T10:30:00Z",
    },
  );
  const allDayEvent = block(
    "55555555-5555-4555-8555-555555555555",
    "All-day marker",
    {
      calendar_id: schoolCalendar.id,
      temporal_kind: "all_day",
      start_date: "2030-01-02",
      end_date: "2030-01-03",
      start_at: null,
      end_at: null,
      start_timezone: null,
      end_timezone: null,
    },
  );
  const hiddenEvent = block(
    "66666666-6666-4666-8666-666666666666",
    "Must stay hidden",
    { calendar_id: disabledCalendar.id },
  );

  const { container } = render(
    <CalendarWorkspace
      status={{
        ...connected,
        accounts: [account, schoolAccount],
        calendars: [calendar, schoolCalendar, disabledCalendar],
        blocks: [personalEvent, schoolEvent, allDayEvent, hiddenEvent],
      }}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );

  expect(screen.getByText("Synthetic School Account")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /Personal focus/ }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /School seminar/ }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /All-day marker/ }),
  ).toBeInTheDocument();
  expect(screen.queryByText("Must stay hidden")).not.toBeInTheDocument();
  const positioned = container.querySelectorAll<HTMLElement>(
    ".calendar-timed-position",
  );
  expect(positioned).toHaveLength(2);
  expect(positioned[0].style.width).toBe("50%");
  expect(positioned[1].style.width).toBe("50%");
});

test("bounds month density and opens a useful read-only inspector without technical identifiers", () => {
  const items = Array.from({ length: 5 }, (_, index) =>
    block(
      `77777777-7777-4777-8777-77777777777${index}`,
      `Month event ${index + 1}`,
      index === 0
        ? {
            description: "Synthetic description",
            location: "Synthetic room",
            start_timezone: "America/New_York",
            end_timezone: "America/New_York",
          }
        : {},
    ),
  );
  render(
    <CalendarWorkspace
      status={{ ...connected, blocks: items }}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Month view" }));
  expect(screen.getByText("+2 more")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Month event 1/ }));

  const inspector = screen.getByRole("complementary", {
    name: "Event details",
  });
  expect(
    within(inspector).getByText("Synthetic description"),
  ).toBeInTheDocument();
  expect(within(inspector).getByText("Synthetic room")).toBeInTheDocument();
  expect(within(inspector).getByText("America/New_York")).toBeInTheDocument();
  expect(
    within(inspector).getByText("Synthetic Primary Calendar"),
  ).toBeInTheDocument();
  expect(
    within(inspector).queryByText(items[0].provider_event_id),
  ).not.toBeInTheDocument();
  expect(within(inspector).queryByText(items[0].id)).not.toBeInTheDocument();
  expect(
    within(inspector).queryByRole("button", {
      name: /edit|delete|move|resize/i,
    }),
  ).not.toBeInTheDocument();
});

test("keeps cached events visible when the provider account is offline", () => {
  render(
    <CalendarWorkspace
      status={{
        ...connected,
        accounts: [{ ...account, auth_state: "disconnected" }],
        calendars: [
          {
            ...calendar,
            sync_state: "disconnected",
            last_error_code: "reauth_required",
          },
        ],
        blocks: [
          block("88888888-8888-4888-8888-888888888888", "Cached offline event"),
        ],
      }}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  expect(
    screen.getByRole("button", { name: /Cached offline event/ }),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Google Calendar isn't connected. Showing saved events."),
  ).toBeInTheDocument();
  const sync = screen.getByRole("button", { name: "Sync calendars" });
  expect(sync).toBeEnabled();
  fireEvent.click(sync);
  expect(
    screen.getByText("Connect Google Calendar before syncing."),
  ).toBeInTheDocument();
  expect(invoke).not.toHaveBeenCalled();
});

test("starts closed and reopens the shared drawer in Filter mode", () => {
  window.sessionStorage.clear();
  const { unmount } = render(
    <CalendarWorkspace status={connected} onStatus={() => undefined} />,
  );
  const trigger = screen.getByRole("button", {
    name: "Toggle calendar sidebar",
  });
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByText(account.display_name)).not.toBeInTheDocument();

  fireEvent.click(trigger);
  expect(
    screen.getByRole("button", { name: "Toggle calendar sidebar" }),
  ).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("tab", { name: "Filter" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  expect(screen.queryByText(account.display_name)).not.toBeInTheDocument();
  expect(window.sessionStorage.getItem("ion.calendar-sidebar.v1")).toBe("open");
  fireEvent.click(screen.getByRole("tab", { name: "Calendars" }));
  expect(screen.getByText(account.display_name)).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Toggle calendar sidebar" }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Toggle calendar sidebar" }),
  );
  expect(screen.getByRole("tab", { name: "Filter" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  unmount();

  render(<CalendarWorkspace status={connected} onStatus={() => undefined} />);
  expect(
    screen.getByRole("button", { name: "Toggle calendar sidebar" }),
  ).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("tab", { name: "Filter" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
});

test("hides and restores calendars only through the fixed Ion-local command", async () => {
  vi.mocked(invoke).mockResolvedValue(connected);
  const { rerender } = render(
    <CalendarWorkspace status={connected} onStatus={() => undefined} />,
  );
  fireEvent.click(
    screen.getByRole("button", {
      name: `Hide ${calendar.summary} from Ion`,
    }),
  );
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("set_google_calendar_hidden", {
      calendarId: calendar.id,
      hidden: true,
      expectedRevision: 1,
    }),
  );

  vi.mocked(invoke).mockClear();
  const hiddenCalendar = { ...calendar, hidden_in_ion: true, revision: 2 };
  rerender(
    <CalendarWorkspace
      status={{ ...connected, calendars: [hiddenCalendar] }}
      onStatus={() => undefined}
    />,
  );
  fireEvent.click(screen.getByText("Hidden calendars · 1"));
  fireEvent.click(screen.getByRole("button", { name: "Restore to Ion" }));
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("set_google_calendar_hidden", {
      calendarId: calendar.id,
      hidden: false,
      expectedRevision: 2,
    }),
  );
  expect(userInvokedCommands()).toEqual(["set_google_calendar_hidden"]);
});

test("persists density and adapts title detail to rendered event height", async () => {
  const short = block("99999999-9999-4999-8999-999999999991", "Short event", {
    start_at: "2030-01-02T09:00:00Z",
    end_at: "2030-01-02T09:20:00Z",
  });
  const roomy = block("99999999-9999-4999-8999-999999999992", "Roomy event", {
    start_at: "2030-01-02T11:00:00Z",
    end_at: "2030-01-02T13:00:00Z",
    category: "routine_physical",
    category_subtype: "gym",
    location: "Synthetic clinic",
  });
  const medium = block(
    "99999999-9999-4999-8999-999999999993",
    "Medium event with a useful second title line",
    {
      start_at: "2030-01-02T14:00:00Z",
      end_at: "2030-01-02T14:35:00Z",
    },
  );
  const { container } = render(
    <CalendarWorkspace
      status={{ ...connected, blocks: [short, roomy, medium] }}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  expect(screen.getByRole("button", { name: /Short event/ })).toHaveClass(
    "calendar-event--title",
  );
  expect(screen.getByRole("button", { name: /Roomy event/ })).toHaveClass(
    "calendar-event--full",
  );
  expect(screen.getByRole("button", { name: /Medium event/ })).toHaveClass(
    "calendar-event--title-two-line",
  );
  const roomyEvent = screen.getByRole("button", { name: /Roomy event/ });
  expect(roomyEvent).not.toHaveTextContent("Routine");
  expect(roomyEvent).not.toHaveTextContent("Synthetic clinic");

  fireEvent.click(screen.getByRole("button", { name: "Calendar density" }));
  const densityPopover = screen.getByRole("dialog", {
    name: "Calendar density options",
  });
  expect(densityPopover).toHaveAttribute(
    "data-portal-layer",
    "calendar-toolbar",
  );
  expect(densityPopover.parentElement).toBe(document.body);
  fireEvent.click(
    within(densityPopover).getByRole("button", { name: "Expanded" }),
  );
  expect(
    container
      .querySelector<HTMLElement>(".calendar-time-view")
      ?.style.getPropertyValue("--calendar-hours-height"),
  ).toBe("1728px");
  await waitFor(() =>
    expect(window.localStorage.getItem("ion.calendar-density.v1")).toBe(
      "expanded",
    ),
  );
});

test("filters by Ion category and edits only local category metadata", async () => {
  const categorized = block(
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaab",
    "Categorized event",
    {
      category: "academic",
      category_subtype: "class_section",
      ion_metadata_revision: 4,
    },
  );
  vi.mocked(invoke).mockResolvedValue(connected);
  render(
    <CalendarWorkspace
      status={{ ...connected, blocks: [categorized] }}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: /Categorized event/ }));
  fireEvent.change(screen.getByLabelText("Categorized event Ion category"), {
    target: { value: "career" },
  });
  expect(
    screen.queryByRole("option", { name: "No subtype" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Save category" }));
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("set_calendar_block_category", {
      blockId: categorized.id,
      category: "career",
      categorySubtype: "internship_recruiting",
      expectedRevision: 4,
    }),
  );
  expect(userInvokedCommands()).toEqual(["set_calendar_block_category"]);

  fireEvent.click(screen.getByRole("button", { name: "Close event details" }));
  fireEvent.click(screen.getByRole("tab", { name: "Filter" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Academic" }));
  expect(
    screen.queryByRole("button", { name: /Categorized event/ }),
  ).not.toBeInTheDocument();
});

test("edits and filters subtype within its broad semantic color family", async () => {
  const academicClass = block(
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaac",
    "Synthetic class",
    {
      category: "academic",
      category_subtype: "class_section",
      ion_metadata_revision: 7,
    },
  );
  vi.mocked(invoke).mockResolvedValue(connected);
  render(
    <CalendarWorkspace
      status={{ ...connected, blocks: [academicClass] }}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );

  const event = screen.getByRole("button", { name: /Synthetic class/ });
  expect(event).not.toHaveTextContent("Academic");
  expect(event).not.toHaveTextContent("Uncategorized");
  expect(event).not.toHaveTextContent(calendar.summary);
  fireEvent.click(event);
  expect(screen.getByText("Academic · Class / section")).toBeInTheDocument();
  fireEvent.change(
    screen.getByLabelText("Synthetic class Ion category subtype"),
    { target: { value: "quiz_exam" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Save category" }));
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("set_calendar_block_category", {
      blockId: academicClass.id,
      category: "academic",
      categorySubtype: "quiz_exam",
      expectedRevision: 7,
    }),
  );

  fireEvent.click(screen.getByRole("button", { name: "Close event details" }));
  fireEvent.click(screen.getByRole("tab", { name: "Filter" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Class / section" }));
  expect(
    screen.queryByRole("button", { name: /Synthetic class/ }),
  ).not.toBeInTheDocument();
});

test("requires an explicit starter subtype without offering a null choice", async () => {
  const legacyBroadOnly = block(
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaad",
    "Broad-only academic event",
    { category: "academic", category_subtype: null, ion_metadata_revision: 3 },
  );
  vi.mocked(invoke).mockResolvedValue(connected);
  render(
    <CalendarWorkspace
      status={{ ...connected, blocks: [legacyBroadOnly] }}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: /Broad-only academic event/ }),
  );
  expect(
    screen.getByLabelText("Broad-only academic event Ion category subtype"),
  ).toHaveValue("class_section");
  expect(
    screen.queryByRole("option", { name: "No subtype" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Save category" }));
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("set_calendar_block_category", {
      blockId: legacyBroadOnly.id,
      category: "academic",
      categorySubtype: "class_section",
      expectedRevision: 3,
    }),
  );
});

test("keeps compact controls named and separates drawer scrolling from its pinned footer", () => {
  const { container } = render(
    <CalendarWorkspace
      status={connected}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  expect(screen.getByRole("button", { name: "Week view" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByRole("heading")).toHaveTextContent("12/31–01/06");
  expect(
    screen.getByRole("button", { name: "Toggle calendar sidebar" }),
  ).toHaveAttribute("title", "Calendar sidebar");
  const footer = container.querySelector(".calendar-sidebar-footer");
  expect(footer).not.toBeNull();
  const sidebar = container.querySelector(".calendar-sidebar");
  const management = container.querySelector(".calendar-sidebar-management");
  expect(footer?.parentElement).toBe(sidebar);
  expect(management?.parentElement).toBe(sidebar);
  expect(sidebar?.lastElementChild).toBe(footer);
  expect(
    within(footer as HTMLElement).getByRole("button", {
      name: "Connect another account",
    }),
  ).toBeInTheDocument();
  expect(
    within(footer as HTMLElement).queryByRole("button", {
      name: "Sync calendars",
    }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Sync calendars" }),
  ).toBeInTheDocument();
  expect(calendarStyles).toMatch(
    /\.calendar-sidebar-management \{[\s\S]*?overflow-y: auto;/,
  );
  expect(calendarStyles).toMatch(
    /\.calendar-sidebar-footer \{[\s\S]*?flex: 0 0 auto;/,
  );
  const pane = screen.getByRole("region", { name: "Calendar pane" });
  expect(sidebar?.nextElementSibling).toBe(pane);
  fireEvent.click(
    screen.getByRole("button", { name: "Toggle calendar sidebar" }),
  );
  expect(
    screen.queryByRole("complementary", { name: "Calendar sidebar" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Calendar pane" })).toBe(pane);
});

test("uses one mutually exclusive drawer region for calendars and filters", () => {
  render(
    <CalendarWorkspace
      status={connected}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  expect(screen.getByText(account.display_name)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Filter" }));
  expect(screen.queryByText(account.display_name)).not.toBeInTheDocument();
  expect(
    screen.getByRole("complementary", { name: "Calendar sidebar" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Filter" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Toggle calendar sidebar" }),
  );
  expect(
    screen.queryByRole("complementary", { name: "Calendar sidebar" }),
  ).not.toBeInTheDocument();
});

test("does not present provider-deleted calendar tombstones as active sources", () => {
  render(
    <CalendarWorkspace
      status={{
        ...connected,
        calendars: [
          calendar,
          {
            ...calendar,
            id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            provider_calendar_id: "removed-calendar@example.invalid",
            summary: "Untitled Google Calendar",
            is_primary: false,
            enabled_in_ion: false,
            provider_deleted: true,
          },
        ],
      }}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  expect(
    screen.queryByText("Untitled Google Calendar"),
  ).not.toBeInTheDocument();
  expect(screen.getByText(calendar.summary)).toBeInTheDocument();
});

test("keeps one fixed toolbar row above one attached calendar scroll surface", () => {
  const { container } = render(
    <CalendarWorkspace
      status={connected}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  const toolbar = screen.getByLabelText("Calendar controls");
  expect(toolbar).toHaveAttribute("data-layout", "single-row");
  expect(calendarStyles).toContain("height: 3.15rem;");
  expect(calendarStyles).not.toContain("grid-template-rows: auto auto");

  const navigation = screen.getByLabelText("Date navigation");
  expect(
    within(navigation)
      .getAllByRole("button")
      .map((button) => button.getAttribute("aria-label") ?? button.textContent),
  ).toEqual(["Previous period", "Today", "Next period", "Sync calendars"]);
  const previous = screen.getByRole("button", { name: "Previous period" });
  const next = screen.getByRole("button", { name: "Next period" });
  expect(previous).toHaveClass("calendar-nav-arrow");
  expect(next).toHaveClass("calendar-nav-arrow");
  expect(previous.className).toBe(next.className);
  expect(
    screen.getByRole("button", { name: "Sync calendars" }),
  ).not.toHaveTextContent("Sync");

  expect(
    screen
      .getAllByLabelText(/^(Day|3 Day|Week|Next 7 Days|Month) view$/)
      .map((button) => button.textContent),
  ).toEqual(["D", "3", "W", "7", "M"]);
  expect(screen.getByLabelText("Choose calendar view")).toBeInTheDocument();
  expect(screen.queryByText(/^View$/)).not.toBeInTheDocument();

  fireEvent.click(screen.getByLabelText("Choose calendar view"));
  const viewPopover = screen.getByRole("dialog", {
    name: "Choose calendar view options",
  });
  expect(viewPopover.parentElement).toBe(document.body);
  expect(viewPopover.closest(".calendar-workspace")).toBeNull();

  const surface = container.querySelector(".calendar-content-surface");
  const header = container.querySelector(".calendar-grid-header");
  const body = container.querySelector<HTMLElement>(".calendar-time-canvas");
  const timeView = container.querySelector<HTMLElement>(".calendar-time-view");
  const headings = container.querySelector<HTMLElement>(
    ".calendar-day-headings",
  );
  const allDay = container.querySelector<HTMLElement>(".calendar-all-day-row");
  expect(header?.closest(".calendar-content-surface")).toBe(surface);
  expect(body?.closest(".calendar-content-surface")).toBe(surface);
  expect(timeView?.style.getPropertyValue("--calendar-columns")).toBe(
    "var(--calendar-time-gutter) repeat(7, minmax(0, 1fr))",
  );
  expect(timeView?.style.getPropertyValue("--calendar-min-width")).toBe("");
  for (const owner of [headings, allDay, body]) {
    expect(owner?.style.gridTemplateColumns).toBe("");
    expect(owner?.style.minWidth).toBe("");
    expect(owner?.closest(".calendar-time-view")).toBe(timeView);
  }
  expect(calendarStyles).toMatch(
    /\.calendar-day-headings,[\s\S]*?\.calendar-all-day-row,[\s\S]*?\.calendar-time-canvas \{[\s\S]*?grid-template-columns: var\(--calendar-columns\);[\s\S]*?min-width: 0;/,
  );
  expect(calendarStyles).not.toContain(
    ".calendar-grid-header {\n  position: sticky;",
  );
  expect(calendarStyles).not.toContain(
    ".calendar-month-weekdays {\n  position: sticky;",
  );
  expect(calendarStyles).toMatch(
    /\.app-shell\.is-calendar-active \{[\s\S]*?overflow: hidden;/,
  );
  expect(calendarStyles).toMatch(
    /\.calendar-toolbar h2 \{[\s\S]*?pointer-events: none;/,
  );
  expect(calendarStyles).toMatch(
    /\.calendar-stage \{[\s\S]*?overflow-x: hidden;[\s\S]*?overflow-y: auto;/,
  );
  expect(calendarStyles).toMatch(
    /\.calendar-time-scroll \{[\s\S]*?overflow: visible;/,
  );
  expect(calendarStyles).toMatch(
    /\.calendar-interface \{[\s\S]*?gap: 0\.65rem;/,
  );
  expect(calendarStyles).toMatch(
    /\.calendar-pane \{[\s\S]*?border: 1px solid #29262f;/,
  );
  expect(calendarStyles).not.toContain("left: -2.55rem;");
  expect(calendarStyles).toMatch(
    /@container calendar-pane \(max-width: 46rem\)[\s\S]*?\.calendar-view-inline \{[\s\S]*?display: none;[\s\S]*?\.calendar-view-menu \{[\s\S]*?display: block;/,
  );
  expect(calendarStyles).toMatch(
    /@container calendar-workspace \(max-width: 43rem\)[\s\S]*?\.calendar-sidebar \{[\s\S]*?position: absolute;/,
  );

  expect(container.querySelectorAll(".calendar-stage")).toHaveLength(1);
  expect(
    container.querySelectorAll(".calendar-sidebar-management"),
  ).toHaveLength(1);
  expect(container.querySelectorAll(".calendar-drawer-tabs")).toHaveLength(1);
  expect(
    within(container.querySelector(".calendar-drawer-tabs") as HTMLElement)
      .getAllByRole("tab")
      .map((tab) => tab.textContent),
  ).toEqual(["Filter", "Calendars"]);
  const sidebar = screen.getByRole("complementary", {
    name: "Calendar sidebar",
  });
  const pane = screen.getByRole("region", { name: "Calendar pane" });
  const paneHeader = container.querySelector(".calendar-pane-header");
  expect(sidebar.nextElementSibling).toBe(pane);
  expect(toolbar.parentElement).toBe(paneHeader);
  expect(
    screen.getByLabelText("Date navigation").closest(".calendar-pane"),
  ).toBe(pane);
  expect(container.querySelectorAll('[data-icon="sidebar"]')).toHaveLength(1);
  expect(
    container.querySelectorAll('[data-icon="density-spacing"]'),
  ).toHaveLength(1);
  expect(
    screen.getByRole("button", { name: "Toggle calendar sidebar" })
      .nextElementSibling,
  ).toHaveClass("calendar-drawer-tabs");
  expect(
    screen.getByRole("button", { name: "Toggle calendar sidebar" })
      .parentElement,
  ).toHaveClass("calendar-drawer-header");
});

test("keeps reauthentication truthful and routes sync to a reachable reconnect action", async () => {
  window.sessionStorage.clear();
  const reauthentication: CalendarStatus = {
    ...connected,
    accounts: [{ ...account, auth_state: "reauth_required" }],
    calendars: [
      {
        ...calendar,
        sync_state: "reauth_required",
        last_error_code: "reauth_required",
      },
    ],
    blocks: [
      block("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbc", "Saved reauth event"),
    ],
  };
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "connect_google_calendar") return connected;
    if (command === "sync_google_calendars") return connected;
    throw new Error(`Unexpected command: ${command}`);
  });
  render(
    <CalendarWorkspace
      status={reauthentication}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );

  expect(
    screen.getByText(/Google Calendar needs to reconnect/),
  ).toBeInTheDocument();
  const sync = screen.getByRole("button", { name: "Sync calendars" });
  expect(sync).toBeEnabled();
  fireEvent.click(sync);
  expect(invoke).not.toHaveBeenCalled();
  expect(
    screen.getByRole("complementary", { name: "Calendar sidebar" }),
  ).toBeInTheDocument();
  expect(
    screen.getAllByRole("button", { name: "Reconnect Google account" }),
  ).not.toHaveLength(0);

  fireEvent.click(
    screen.getAllByRole("button", { name: "Reconnect Google account" })[0],
  );
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("connect_google_calendar"),
  );
});

test("selects responsive views from the calendar canvas width and closes drawers only across breakpoints", () => {
  let resize: ResizeObserverCallback | undefined;
  class MockResizeObserver implements ResizeObserver {
    constructor(callback: ResizeObserverCallback) {
      resize = callback;
    }
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", MockResizeObserver);
  window.sessionStorage.clear();
  const { container } = render(
    <CalendarWorkspace
      status={connected}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  const canvas = screen.getByRole("main", { name: "Calendar canvas" });
  const reportWidth = (width: number) => {
    act(() => {
      resize?.(
        [
          {
            target: canvas,
            contentRect: { width },
          } as unknown as ResizeObserverEntry,
        ],
        {} as ResizeObserver,
      );
    });
  };

  reportWidth(900);
  expect(screen.getByRole("button", { name: "Week view" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByRole("region", { name: "Calendar pane" })).toHaveAttribute(
    "data-pane-width-class",
    "wide",
  );

  fireEvent.click(screen.getByRole("button", { name: "Month view" }));
  reportWidth(900);
  expect(screen.getByRole("button", { name: "Month view" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  fireEvent.click(
    screen.getByRole("button", { name: "Toggle calendar sidebar" }),
  );
  expect(screen.getByRole("tab", { name: "Filter" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  reportWidth(700);
  expect(screen.getByRole("button", { name: "3 Day view" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(
    screen.queryByRole("complementary", { name: "Calendar sidebar" }),
  ).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Toggle calendar sidebar" }),
  );
  expect(screen.getByRole("tab", { name: "Filter" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Toggle calendar sidebar" }),
  );

  reportWidth(500);
  expect(screen.getByRole("button", { name: "Day view" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  reportWidth(900);
  expect(screen.getByRole("button", { name: "Week view" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(
    screen.queryByRole("complementary", { name: "Calendar sidebar" }),
  ).not.toBeInTheDocument();
  expect(container.querySelectorAll('[data-icon="sidebar"]')).toHaveLength(1);
});

test("removes calendar zoom and keeps every active view inside one vertical scroll surface", () => {
  const { container } = render(
    <CalendarWorkspace
      status={connected}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  const canvas = screen.getByRole("main", { name: "Calendar canvas" });
  const geometry = container.querySelector<HTMLElement>(".calendar-time-view")!;
  const sharedColumns = geometry.style.getPropertyValue("--calendar-columns");
  expect(sharedColumns).toBe(
    "var(--calendar-time-gutter) repeat(7, minmax(0, 1fr))",
  );
  expect(screen.queryByLabelText(/calendar zoom/i)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /zoom calendar/i })).toBeNull();
  expect(container.querySelector(".calendar-content-scale")).toBeNull();
  expect(window.localStorage.getItem("ion.calendar-zoom.v1")).toBeNull();
  const shortcut = new KeyboardEvent("keydown", {
    key: "+",
    metaKey: true,
    bubbles: true,
    cancelable: true,
  });
  canvas.dispatchEvent(shortcut);
  expect(shortcut.defaultPrevented).toBe(false);
  const change = new Event("gesturechange", {
    bubbles: true,
    cancelable: true,
  });
  Object.defineProperty(change, "scale", { value: 1.2 });
  canvas.dispatchEvent(change);
  expect(change.defaultPrevented).toBe(false);
  expect(geometry.style.getPropertyValue("--calendar-columns")).toBe(
    sharedColumns,
  );
  expect(document.documentElement.style.getPropertyValue("zoom")).toBe("");
  expect(calendarStyles).not.toContain("calendar-zoom-control");
  expect(calendarStyles).not.toContain("--calendar-min-width");
  expect(calendarStyles).toMatch(/\.calendar-month \{[\s\S]*?min-width: 0;/);
});

test("requires an explicit account-scoped step before Google create is available", async () => {
  const writeEnabled: CalendarStatus = {
    ...connected,
    accounts: [
      {
        ...account,
        granted_scopes: [
          "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
          "https://www.googleapis.com/auth/calendar.events",
        ],
        calendar_write_scope_state: "write_granted",
      },
    ],
    calendars: [
      {
        ...calendar,
        provider_write_eligible: true,
        provider_write_reason: "eligible",
      },
    ],
  };
  vi.mocked(invoke).mockResolvedValue(writeEnabled);
  render(
    <CalendarWorkspace
      status={connected}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );

  expect(screen.getByText("Read only")).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Enable Calendar writing" }),
  );
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("enable_google_calendar_writes", {
      accountId: account.id,
    }),
  );
});

test("confirms a local-first attendee-free timed create with an eligible calendar", async () => {
  const writableCalendar: GoogleCalendar = {
    ...calendar,
    provider_write_eligible: true,
    provider_write_reason: "eligible",
  };
  const writable: CalendarStatus = {
    ...connected,
    accounts: [
      {
        ...account,
        calendar_write_scope_state: "write_granted",
      },
    ],
    calendars: [writableCalendar],
  };
  const pendingBlock = block(
    "44444444-4444-4444-8444-444444444444",
    "Synthetic harmless event",
    {
      calendar_id: writableCalendar.id,
      provider_event_id: "ion2c2syntheticidentity",
      start_at: "2030-01-02T09:00:00Z",
      end_at: "2030-01-02T10:00:00Z",
      provider_write_capability: { eligible: true, reason: "eligible" },
      provider_write_state: "pending",
      provider_write_detail: "ready",
    },
  );
  vi.mocked(invoke).mockResolvedValue({ ...writable, blocks: [pendingBlock] });
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );

  fireEvent.keyDown(
    screen.getByRole("button", {
      name: "Create timed event on 2030-01-02",
    }),
    { key: "Enter" },
  );
  fireEvent.change(screen.getByLabelText("Title"), {
    target: { value: "Synthetic harmless event" },
  });
  fireEvent.change(screen.getByLabelText("Repeat"), {
    target: { value: "weekly" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create event" }));

  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("create_google_calendar_event", {
      draft: {
        command_id: expect.stringMatching(
          /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
        ),
        calendar_id: writableCalendar.id,
        title: "Synthetic harmless event",
        date: "2030-01-02",
        all_day: false,
        start_time: "09:00",
        end_time: "10:00",
        timezone: "America/Los_Angeles",
        recurrence: "weekly",
      },
    }),
  );
  // Lightweight confirmation: the Calendar itself is the primary feedback.
  expect(
    await screen.findByText(/Event created · saving…/i),
  ).toBeInTheDocument();
});

function writableStatus(blocks: CalendarBlock[]): CalendarStatus {
  return {
    ...connected,
    accounts: [
      {
        ...account,
        calendar_write_scope_state: "write_granted",
      },
    ],
    calendars: [
      {
        ...calendar,
        timezone: "UTC",
        provider_write_eligible: true,
        provider_write_reason: "eligible",
      },
    ],
    blocks,
  };
}

test("edits an eligible title through explicit save with lightweight feedback", async () => {
  const editable = block(
    "55555555-5555-4555-8555-555555555555",
    "Synthetic editable event",
    {
      provider_write_capability: { eligible: true, reason: "eligible" },
    },
  );
  const writable = writableStatus([editable]);
  vi.mocked(invoke).mockResolvedValue({
    ...writable,
    blocks: [
      {
        ...editable,
        title: "Synthetic revised event",
        provider_write_capability: {
          eligible: false,
          reason: "write_pending",
        },
        provider_write_state: "pending",
        provider_write_detail: "ready",
      },
    ],
  });
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );

  fireEvent.click(
    screen.getByRole("button", { name: /^Synthetic editable event,/ }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Edit event" }));
  fireEvent.change(screen.getByLabelText("Title"), {
    target: { value: "Synthetic revised event" },
  });
  const save = screen.getByRole("button", { name: "Save change" });
  expect(save).toBeEnabled();
  fireEvent.click(save);

  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("edit_google_calendar_event", {
      draft: {
        command_id: expect.stringMatching(/^[0-9a-f-]{36}$/),
        calendar_block_id: editable.id,
        edit_kind: "edit",
        expected_block_revision: 1,
        title: "Synthetic revised event",
        start_date: "2030-01-02",
        end_date: "2030-01-02",
        start_time: "09:00",
        end_time: "10:00",
        timezone: "UTC",
        recurrence_scope: "single",
        occurrence_original_start: null,
        recurrence: null,
        recurrence_risk_confirmed: false,
        locked_confirmed: false,
      },
    }),
  );
  // Lightweight confirmation: the Calendar itself is the primary feedback.
  expect(
    await screen.findByText(/Event updated · saving…/i),
  ).toBeInTheDocument();
});

test("surfaces a safe write-pending rejection truthfully instead of generic local-state copy", async () => {
  const editable = block(
    "55555555-5555-4555-8555-555555555556",
    "Synthetic serialized event",
    {
      flexibility: "flexible",
      provider_write_capability: { eligible: true, reason: "eligible" },
    },
  );
  vi.mocked(invoke).mockRejectedValue({ code: "write_pending" });
  render(
    <CalendarWorkspace
      status={writableStatus([editable])}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );

  fireEvent.click(
    screen.getByRole("button", { name: /^Synthetic serialized event,/ }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Edit event" }));
  fireEvent.change(screen.getByLabelText("Title"), {
    target: { value: "Synthetic second change" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save change" }));

  expect(
    await screen.findByText(
      /Another change to this recurring series is still syncing/i,
    ),
  ).toBeInTheDocument();
  expect(
    screen.queryByText("That calendar change couldn't be saved."),
  ).not.toBeInTheDocument();
});

test("surfaces a safe timezone-change rejection truthfully instead of generic local-state copy", async () => {
  const editable = block(
    "55555555-5555-4555-8555-555555555557",
    "Synthetic asymmetric-timezone event",
    {
      flexibility: "flexible",
      provider_write_capability: { eligible: true, reason: "eligible" },
    },
  );
  vi.mocked(invoke).mockRejectedValue({ code: "timezone_change_unsupported" });
  render(
    <CalendarWorkspace
      status={writableStatus([editable])}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );

  fireEvent.click(
    screen.getByRole("button", {
      name: /^Synthetic asymmetric-timezone event,/,
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Edit event" }));
  fireEvent.change(screen.getByLabelText("Title"), {
    target: { value: "Synthetic asymmetric-timezone change" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save change" }));

  expect(
    await screen.findByText(/different start and end time zones/i),
  ).toBeInTheDocument();
  expect(
    screen.queryByText("That calendar change couldn't be saved."),
  ).not.toBeInTheDocument();
});

test("requires explicit confirmation before a bounded single-event delete", async () => {
  const deletable = block(
    "88888888-8888-4888-8888-888888888888",
    "Synthetic deletable event",
    {
      provider_write_capability: { eligible: true, reason: "eligible" },
      provider_delete_capability: {
        eligible: true,
        mode: "provider_delete",
        reason: "eligible",
      },
    },
  );
  const writable = writableStatus([deletable]);
  vi.mocked(invoke).mockResolvedValue({ ...writable, blocks: [] });
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: /^Synthetic deletable event,/ }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Delete event" }));
  expect(screen.getByText(/Scope: this event only/i)).toBeInTheDocument();
  expect(screen.getByText(/cannot be undone in Ion/i)).toBeInTheDocument();
  const confirm = screen.getByRole("button", { name: "Delete event" });
  expect(confirm).toBeDisabled();
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: /confirm deleting this Ion-locked event/i,
    }),
  );
  fireEvent.click(confirm);
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("delete_google_calendar_event", {
      draft: {
        command_id: expect.stringMatching(/^[0-9a-f-]{36}$/),
        calendar_block_id: deletable.id,
        expected_block_revision: 1,
        recurrence_scope: "single",
        occurrence_original_start: null,
        series_confirmed: false,
        locked_confirmed: true,
      },
    }),
  );
});

test("omits this-and-following at the first occurrence and confirms whole-series delete", async () => {
  const recurring = block(
    "99999999-9999-4999-8999-999999999999",
    "Synthetic recurring event",
    {
      recurrence_kind: "master",
      recurrence_rules: ["RRULE:FREQ=WEEKLY"],
      recurrence_preset: "weekly",
      flexibility: "flexible",
      provider_write_capability: { eligible: true, reason: "eligible" },
      provider_delete_capability: {
        eligible: true,
        mode: "provider_delete",
        reason: "eligible",
      },
    },
  );
  const writable = writableStatus([recurring]);
  vi.mocked(invoke).mockResolvedValue({ ...writable, blocks: [] });
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );

  fireEvent.click(
    screen.getByRole("button", { name: /^Synthetic recurring event,/ }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Delete event" }));
  // Google's order: choose scope, and that is the whole decision. "This and
  // following" is truthfully unavailable at the first occurrence.
  const scopeDialog = screen.getByRole("dialog", {
    name: "Delete recurring event",
  });
  // First occurrence: splitting here would mean exactly "All events", so
  // Google omits the option and so does Ion -- with no misleading note.
  expect(
    within(scopeDialog).queryByRole("radio", { name: /following/i }),
  ).toBeNull();
  expect(within(scopeDialog).queryByText(/can.t split safely/i)).toBeNull();
  expect(invoke).not.toHaveBeenCalledWith(
    "delete_google_calendar_event",
    expect.anything(),
  );
  fireEvent.click(
    within(scopeDialog).getByRole("radio", { name: /All events/ }),
  );
  expect(
    within(scopeDialog).getByText(
      /whole recurring series\. These may not be recoverable/i,
    ),
  ).toBeInTheDocument();
  fireEvent.click(within(scopeDialog).getByRole("button", { name: "Delete" }));
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("delete_google_calendar_event", {
      draft: {
        command_id: expect.stringMatching(/^[0-9a-f-]{36}$/),
        calendar_block_id: recurring.id,
        expected_block_revision: 1,
        recurrence_scope: "series",
        occurrence_original_start: null,
        series_confirmed: true,
        locked_confirmed: false,
      },
    }),
  );
});

/**
 * A drag is a complete statement of intent, so it commits at drop the way
 * Google's does. For a recurring event the only thing the gesture did not say
 * is scope, so that -- and nothing after it -- is the last action required.
 */
test("one pointer move previews movement, then commits at drop after the scope choice", async () => {
  const editable = block(
    "66666666-6666-4666-8666-666666666666",
    "Synthetic draggable event",
    {
      recurrence_kind: "master",
      recurrence_rules: ["RRULE:FREQ=WEEKLY"],
      recurrence_preset: "weekly",
      flexibility: "flexible",
      provider_write_capability: { eligible: true, reason: "eligible" },
    },
  );
  const writable = writableStatus([editable]);
  vi.mocked(invoke).mockResolvedValue(writable);
  const { container } = render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  const point = mockTimeColumnRects(container);
  const eventButton = screen.getByRole("button", {
    name: /^Synthetic draggable event,/,
  });
  fireEvent.pointerDown(eventButton, {
    button: 0,
    pointerId: 7,
    clientX: point("2030-01-02").x,
    clientY: 9 * 60 + 15,
  });
  fireEvent.pointerMove(eventButton, {
    pointerId: 7,
    clientX: point("2030-01-03").x,
    clientY: 13 * 60 + 15,
  });
  expect(
    container.querySelector('[data-calendar-preview="move"]'),
  ).toBeInTheDocument();
  expect(editable.start_at).toBe("2030-01-02T09:00:00Z");
  expect(invoke).not.toHaveBeenCalledWith(
    "edit_google_calendar_event",
    expect.anything(),
  );

  fireEvent.pointerUp(eventButton, {
    pointerId: 7,
    clientX: point("2030-01-03").x,
    clientY: 13 * 60 + 15,
  });

  // The drop asks for scope directly -- there is no review step and no Save.
  expect(
    screen.queryByRole("button", { name: "Save change" }),
  ).not.toBeInTheDocument();
  const scopeDialog = screen.getByRole("dialog", {
    name: "Save recurring event",
  });
  expect(
    within(scopeDialog).queryByRole("radio", { name: /following/i }),
  ).toBeNull();
  fireEvent.click(
    within(scopeDialog).getByRole("radio", { name: /This event/ }),
  );
  fireEvent.click(within(scopeDialog).getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("edit_google_calendar_event", {
      draft: expect.objectContaining({
        calendar_block_id: editable.id,
        edit_kind: "move",
        start_date: "2030-01-03",
        start_time: "13:00",
        end_date: null,
        end_time: null,
        recurrence_scope: "occurrence",
        occurrence_original_start: {
          date: null,
          date_time: "2030-01-02T09:00:00.000Z",
          timezone: "UTC",
        },
      }),
    }),
  );
  expect(
    vi
      .mocked(invoke)
      .mock.calls.filter(
        ([command]) => command === "edit_google_calendar_event",
      ),
  ).toHaveLength(1);
});

test("top-edge pointer resize commits the proposed start at release", async () => {
  const editable = block(
    "66666666-6666-4666-8666-666666666667",
    "Synthetic top resize",
    {
      flexibility: "flexible",
      provider_write_capability: { eligible: true, reason: "eligible" },
    },
  );
  const { container } = render(
    <CalendarWorkspace
      status={writableStatus([editable])}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  const point = mockTimeColumnRects(container);
  const handle = screen.getByRole("button", {
    name: "Resize start of Synthetic top resize",
  });
  fireEvent.pointerDown(handle, {
    button: 0,
    pointerId: 8,
    clientX: point("2030-01-02").x,
    clientY: 9 * 60,
  });
  fireEvent.pointerMove(handle, {
    pointerId: 8,
    clientX: point("2030-01-02").x,
    clientY: 8 * 60,
  });
  expect(
    container.querySelector('[data-calendar-preview="resize-start"]'),
  ).toBeInTheDocument();
  // A gesture in flight writes nothing; it commits at release.
  expect(userInvokedCommands()).toEqual([]);
  fireEvent.pointerUp(handle, {
    pointerId: 8,
    clientX: point("2030-01-02").x,
    clientY: 8 * 60,
  });
  // Release is the commit. A resize edits only the edge it grabbed.
  expect(
    screen.queryByRole("button", { name: "Save change" }),
  ).not.toBeInTheDocument();
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("edit_google_calendar_event", {
      draft: expect.objectContaining({
        calendar_block_id: editable.id,
        edit_kind: "resize",
        start_time: "08:00",
        end_time: null,
        recurrence_scope: "single",
      }),
    }),
  );
});

test("bottom-edge pointer resize commits the proposed end at release", async () => {
  const editable = block(
    "66666666-6666-4666-8666-666666666668",
    "Synthetic bottom resize",
    {
      flexibility: "flexible",
      provider_write_capability: { eligible: true, reason: "eligible" },
    },
  );
  const { container } = render(
    <CalendarWorkspace
      status={writableStatus([editable])}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  const point = mockTimeColumnRects(container);
  const handle = screen.getByRole("button", {
    name: "Resize end of Synthetic bottom resize",
  });
  fireEvent.pointerDown(handle, {
    button: 0,
    pointerId: 9,
    clientX: point("2030-01-02").x,
    clientY: 10 * 60,
  });
  fireEvent.pointerMove(handle, {
    pointerId: 9,
    clientX: point("2030-01-02").x,
    clientY: 11 * 60,
  });
  expect(
    container.querySelector('[data-calendar-preview="resize-end"]'),
  ).toBeInTheDocument();
  // A gesture in flight writes nothing; it commits at release.
  expect(userInvokedCommands()).toEqual([]);
  fireEvent.pointerUp(handle, {
    pointerId: 9,
    clientX: point("2030-01-02").x,
    clientY: 11 * 60,
  });
  expect(
    screen.queryByRole("button", { name: "Save change" }),
  ).not.toBeInTheDocument();
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("edit_google_calendar_event", {
      draft: expect.objectContaining({
        calendar_block_id: editable.id,
        edit_kind: "resize",
        end_time: "11:00",
        start_date: null,
        recurrence_scope: "single",
      }),
    }),
  );
});

test("Escape cancels an active drag before pointerup, committing no write", () => {
  const editable = block(
    "66666666-6666-4666-8666-666666666669",
    "Synthetic escape event",
    {
      flexibility: "flexible",
      provider_write_capability: { eligible: true, reason: "eligible" },
    },
  );
  const writable = writableStatus([editable]);
  vi.mocked(invoke).mockResolvedValue(writable);
  const { container } = render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  const point = mockTimeColumnRects(container);
  const eventButton = screen.getByRole("button", {
    name: /^Synthetic escape event,/,
  });
  fireEvent.pointerDown(eventButton, {
    button: 0,
    pointerId: 9,
    clientX: point("2030-01-02").x,
    clientY: 9 * 60 + 15,
  });
  fireEvent.pointerMove(eventButton, {
    pointerId: 9,
    clientX: point("2030-01-03").x,
    clientY: 13 * 60 + 15,
  });
  expect(
    container.querySelector('[data-calendar-preview="move"]'),
  ).toBeInTheDocument();

  fireEvent.keyDown(window, { key: "Escape" });
  expect(
    container.querySelector('[data-calendar-preview="move"]'),
  ).not.toBeInTheDocument();

  fireEvent.pointerUp(eventButton, {
    pointerId: 9,
    clientX: point("2030-01-03").x,
    clientY: 13 * 60 + 15,
  });
  expect(screen.queryByText(/Review the moved start/i)).toBeNull();
  expect(invoke).not.toHaveBeenCalledWith(
    "edit_google_calendar_event",
    expect.anything(),
  );
});

test("the occurrence open in the inspector shows a restrained selected state in the grid", () => {
  const first = block(
    "aaaaaaaa-1111-4111-8111-111111111111",
    "Synthetic first event",
  );
  const second = block(
    "bbbbbbbb-2222-4222-8222-222222222222",
    "Synthetic second event",
    {
      start_at: "2030-01-02T13:00:00Z",
      end_at: "2030-01-02T14:00:00Z",
    },
  );
  const writable = writableStatus([first, second]);
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  const firstButton = screen.getByRole("button", {
    name: /^Synthetic first event,/,
  });
  const secondButton = screen.getByRole("button", {
    name: /^Synthetic second event,/,
  });
  expect(firstButton).not.toHaveAttribute("data-selected");
  fireEvent.click(firstButton);
  expect(firstButton).toHaveAttribute("data-selected", "true");
  expect(secondButton).not.toHaveAttribute("data-selected");
});

test("recovery actions invoke only their fixed Tauri commands with bounded Ion identifiers", async () => {
  const conflicted = block(
    "77777777-7777-4777-8777-777777777771",
    "Synthetic conflicted event",
    {
      provider_write_state: "conflict",
      provider_write_failure_class: "provider_not_found",
      provider_recovery_kind: "provider_deleted",
      provider_write_capability: { eligible: false, reason: "write_pending" },
    },
  );
  const writable = writableStatus([conflicted]);
  vi.mocked(invoke).mockResolvedValue(writable);
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: /^Synthetic conflicted event,/ }),
  );
  // The condition is named, and only a truthful action is offered: Google
  // deleted the event, so there is nothing to "keep" and nothing to re-apply.
  expect(screen.getByText(/Google deleted this event/i)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "Discard my change" }));
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("keep_google_calendar_version", {
      draft: expect.objectContaining({
        calendar_block_id: conflicted.id,
        expected_block_revision: conflicted.revision,
      }),
    }),
  );
  // The generic version-comparison surface is gone from ordinary Calendar use.
  expect(invoke).not.toHaveBeenCalledWith(
    "review_google_calendar_differences",
    expect.anything(),
  );
});

test("a terminally failed write offers a human exit instead of locking the event", async () => {
  const failed = block(
    "77777777-7777-4777-8777-777777777772",
    "Synthetic failed event",
    {
      provider_write_state: "failed",
      provider_write_detail: "failed",
      provider_write_failure_class: "terminal_provider_rejection",
      provider_write_failure_reason: "access_role_read_only",
      provider_recovery_kind: "provider_rejected",
      provider_write_capability: { eligible: false, reason: "write_pending" },
    },
  );
  const writable = writableStatus([failed]);
  vi.mocked(invoke).mockResolvedValue(writable);
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: /^Synthetic failed event,/ }),
  );
  // Truthful failure guidance, plus a reachable way out of the failure.
  expect(
    screen.getByText(/Google permanently rejected this change/i),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Google rejected this change and will not accept it/i),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Discard my change" }));
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("keep_google_calendar_version", {
      draft: expect.objectContaining({ calendar_block_id: failed.id }),
    }),
  );
  // Retrying a change Google will not accept as written would be a lie.
  expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
});

test("Try again reports the real outcome instead of staying in applying", async () => {
  const conflicted = block(
    "77777777-7777-4777-8777-777777777773",
    "Synthetic applied event",
    {
      provider_write_state: "conflict",
      provider_write_failure_class: "stale_precondition",
      provider_write_failure_reason: "automatic_rebase_exhausted",
      provider_recovery_kind: "retry_available",
      provider_write_capability: { eligible: false, reason: "write_pending" },
    },
  );
  const confirmed = writableStatus([
    {
      ...conflicted,
      provider_write_state: "synced",
      provider_write_detail: "confirmed",
      provider_write_capability: { eligible: true, reason: "eligible" },
    },
  ]);
  const writable = writableStatus([conflicted]);
  vi.mocked(invoke).mockResolvedValue(confirmed);
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: /^Synthetic applied event,/ }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await waitFor(() =>
    expect(
      screen.getByText("Your Ion change is now confirmed by Google."),
    ).toBeInTheDocument(),
  );
  expect(screen.queryByText(/Applying your Ion change/i)).toBeNull();
});

function recurringWritable(
  id: string,
  title: string,
  rule: { rules: string[]; preset: CalendarBlock["recurrence_preset"] } = {
    rules: ["RRULE:FREQ=WEEKLY"],
    preset: "weekly",
  },
) {
  return block(id, title, {
    recurrence_kind: "master",
    recurrence_rules: rule.rules,
    recurrence_preset: rule.preset,
    flexibility: "flexible",
    provider_write_capability: { eligible: true, reason: "eligible" },
    provider_delete_capability: {
      eligible: true,
      mode: "provider_delete",
      reason: "eligible",
    },
  });
}

function openRecurringEdit(recurring: CalendarBlock) {
  const writable = writableStatus([recurring]);
  vi.mocked(invoke).mockResolvedValue(writable);
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: new RegExp(`^${recurring.title},`) }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Edit event" }));
  fireEvent.change(screen.getByLabelText("Title"), {
    target: { value: "Renamed by the owner" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save change" }));
}

test("a recurring Save asks for scope before dispatching anything", () => {
  openRecurringEdit(
    recurringWritable(
      "12121212-1212-4121-8121-121212121212",
      "Synthetic scoped event",
    ),
  );
  // Save alone must not reach the provider.
  expect(invoke).not.toHaveBeenCalledWith(
    "edit_google_calendar_event",
    expect.anything(),
  );
  const dialog = screen.getByRole("dialog", { name: "Save recurring event" });
  expect(
    within(dialog).getByRole("radio", { name: /This event/ }),
  ).toBeInTheDocument();
  expect(
    within(dialog).getByRole("radio", { name: /All events/ }),
  ).toBeInTheDocument();
  expect(
    within(dialog).queryByRole("radio", { name: /following/i }),
  ).toBeNull();
});

test("choosing This event dispatches one occurrence-scoped write", async () => {
  const recurring = recurringWritable(
    "13131313-1313-4131-8131-131313131313",
    "Synthetic occurrence scope",
  );
  openRecurringEdit(recurring);
  const dialog = screen.getByRole("dialog", { name: "Save recurring event" });
  fireEvent.click(within(dialog).getByRole("radio", { name: /This event/ }));
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("edit_google_calendar_event", {
      draft: expect.objectContaining({
        calendar_block_id: recurring.id,
        recurrence_scope: "occurrence",
        title: "Renamed by the owner",
      }),
    }),
  );
});

test("choosing All events dispatches the master write without extra friction", async () => {
  const recurring = recurringWritable(
    "14141414-1414-4141-8141-141414141414",
    "Synthetic series scope",
  );
  openRecurringEdit(recurring);
  const dialog = screen.getByRole("dialog", { name: "Save recurring event" });
  fireEvent.click(within(dialog).getByRole("radio", { name: /All events/ }));
  // A series-wide edit leaves every occurrence in place and stays reversible,
  // so it commits on Save. Only occurrence-removing operations confirm.
  expect(within(dialog).getByRole("button", { name: "Save" })).toBeEnabled();
  expect(within(dialog).queryByRole("checkbox")).toBeNull();
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("edit_google_calendar_event", {
      draft: expect.objectContaining({
        calendar_block_id: recurring.id,
        recurrence_scope: "series",
      }),
    }),
  );
});

test("cancelling the scope chooser makes no canonical or provider mutation", () => {
  openRecurringEdit(
    recurringWritable(
      "15151515-1515-4151-8151-151515151515",
      "Synthetic cancelled scope",
    ),
  );
  const dialog = screen.getByRole("dialog", { name: "Save recurring event" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
  expect(
    screen.queryByRole("dialog", { name: "Save recurring event" }),
  ).toBeNull();
  expect(invoke).not.toHaveBeenCalledWith(
    "edit_google_calendar_event",
    expect.anything(),
  );
  expect(invoke).not.toHaveBeenCalledWith(
    "delete_google_calendar_event",
    expect.anything(),
  );
});

test("a non-recurring Save bypasses the scope chooser entirely", async () => {
  const single = block(
    "16161616-1616-4161-8161-161616161616",
    "Synthetic single event",
    {
      flexibility: "flexible",
      provider_write_capability: { eligible: true, reason: "eligible" },
    },
  );
  const writable = writableStatus([single]);
  vi.mocked(invoke).mockResolvedValue(writable);
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: /^Synthetic single event,/ }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Edit event" }));
  fireEvent.change(screen.getByLabelText("Title"), {
    target: { value: "Renamed single" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save change" }));
  expect(screen.queryByRole("dialog", { name: /recurring event/ })).toBeNull();
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("edit_google_calendar_event", {
      draft: expect.objectContaining({
        calendar_block_id: single.id,
        recurrence_scope: "single",
      }),
    }),
  );
});

test("a recurring resize asks for scope at release, and that choice is the last action", async () => {
  const recurring = recurringWritable(
    "17171717-1717-4171-8171-171717171717",
    "Synthetic resized series",
  );
  const writable = writableStatus([recurring]);
  vi.mocked(invoke).mockResolvedValue(writable);
  const { container } = render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  const point = mockTimeColumnRects(container);
  const handle = screen.getByRole("button", {
    name: "Resize end of Synthetic resized series",
  });
  fireEvent.pointerDown(handle, {
    button: 0,
    pointerId: 11,
    clientX: point("2030-01-02").x,
    clientY: 10 * 60,
  });
  fireEvent.pointerMove(handle, {
    pointerId: 11,
    clientX: point("2030-01-02").x,
    clientY: 11 * 60,
  });
  fireEvent.pointerUp(handle, {
    pointerId: 11,
    clientX: point("2030-01-02").x,
    clientY: 11 * 60,
  });
  // The gesture itself never writes -- it asks for the one thing it could not
  // express, with no intervening Save.
  expect(invoke).not.toHaveBeenCalledWith(
    "edit_google_calendar_event",
    expect.anything(),
  );
  expect(
    screen.queryByRole("button", { name: "Save change" }),
  ).not.toBeInTheDocument();
  const dialog = screen.getByRole("dialog", { name: "Save recurring event" });

  fireEvent.click(within(dialog).getByRole("radio", { name: /This event/ }));
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  // Choosing scope dispatches. Nothing else is asked of the user.
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("edit_google_calendar_event", {
      draft: expect.objectContaining({
        calendar_block_id: recurring.id,
        edit_kind: "resize",
        end_time: "11:00",
        recurrence_scope: "occurrence",
      }),
    }),
  );
  expect(
    screen.queryByRole("dialog", { name: "Save recurring event" }),
  ).toBeNull();
  expect(screen.queryByRole("button", { name: "Save change" })).toBeNull();
  expect(screen.queryByRole("button", { name: /Apply my Ion/i })).toBeNull();
});

function laterOccurrenceButton(title: string) {
  // The second rendered occurrence of a weekly series is a middle occurrence,
  // where a split is genuinely distinct from "All events".
  const matches = screen.getAllByRole("button", {
    name: new RegExp(`^${title},`),
  });
  return matches[1];
}

test("offers This and following on a middle occurrence and splits the series", async () => {
  const recurring = recurringWritable(
    "18181818-1818-4181-8181-181818181818",
    "Synthetic splittable series",
    { rules: ["RRULE:FREQ=DAILY"], preset: "daily" },
  );
  const writable = writableStatus([recurring]);
  vi.mocked(invoke).mockResolvedValue(writable);
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(laterOccurrenceButton("Synthetic splittable series"));
  fireEvent.click(screen.getByRole("button", { name: "Edit event" }));
  fireEvent.change(screen.getByLabelText("Title"), {
    target: { value: "Renamed from here on" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save change" }));

  const dialog = screen.getByRole("dialog", { name: "Save recurring event" });
  const following = within(dialog).getByRole("radio", {
    name: /This and following events/,
  });
  expect(following).toBeInTheDocument();
  expect(invoke).not.toHaveBeenCalledWith(
    "edit_google_calendar_event",
    expect.anything(),
  );
  fireEvent.click(following);
  // A non-destructive split preserves every occurrence, so it commits without
  // an extra acknowledgement.
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("edit_google_calendar_event", {
      draft: expect.objectContaining({
        calendar_block_id: recurring.id,
        recurrence_scope: "this_and_following",
        title: "Renamed from here on",
        occurrence_original_start: expect.objectContaining({
          date_time: expect.any(String),
        }),
      }),
    }),
  );
});

test("withholds This and following for a recurrence pattern Ion cannot split", () => {
  const custom = block(
    "19191919-1919-4191-8191-191919191919",
    "Synthetic custom series",
    {
      recurrence_kind: "master",
      recurrence_rules: ["RRULE:FREQ=DAILY;INTERVAL=3"],
      recurrence_preset: "custom",
      flexibility: "flexible",
      provider_write_capability: { eligible: true, reason: "eligible" },
    },
  );
  const writable = writableStatus([custom]);
  vi.mocked(invoke).mockResolvedValue(writable);
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(laterOccurrenceButton("Synthetic custom series"));
  fireEvent.click(screen.getByRole("button", { name: "Edit event" }));
  fireEvent.click(screen.getByRole("button", { name: "Save change" }));
  const dialog = screen.getByRole("dialog", { name: "Save recurring event" });
  // Truthfully withheld and explained -- never approximated.
  expect(
    within(dialog).queryByRole("radio", { name: /This and following/ }),
  ).toBeNull();
  expect(
    within(dialog).getByText(/can.t split safely yet/i),
  ).toBeInTheDocument();
  expect(
    within(dialog).getByRole("radio", { name: /All events/ }),
  ).toBeInTheDocument();
});

test("7: recurring delete dispatches from the scope choice, with the warning in the dialog", async () => {
  const recurring = recurringWritable(
    "20202020-2020-4202-8202-202020202020",
    "Synthetic trimmable series",
    { rules: ["RRULE:FREQ=DAILY"], preset: "daily" },
  );
  const writable = writableStatus([recurring]);
  vi.mocked(invoke).mockResolvedValue(writable);
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(laterOccurrenceButton("Synthetic trimmable series"));
  fireEvent.click(screen.getByRole("button", { name: "Delete event" }));
  const dialog = screen.getByRole("dialog", { name: "Delete recurring event" });
  fireEvent.click(
    within(dialog).getByRole("radio", { name: /This and following events/ }),
  );
  // The consequence is stated beside the choice that causes it...
  expect(
    within(dialog).getByText(/every later one\. These may not be recoverable/i),
  ).toBeInTheDocument();
  // ...and there is no checkbox to tick.
  expect(within(dialog).queryByRole("checkbox")).toBeNull();

  fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));

  // The scope choice is the whole decision: nothing follows it.
  expect(
    screen.queryByRole("button", { name: "Delete this and following" }),
  ).toBeNull();
  expect(
    screen.queryByRole("region", { name: "Confirm event deletion" }),
  ).toBeNull();
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("delete_google_calendar_event", {
      draft: expect.objectContaining({
        calendar_block_id: recurring.id,
        recurrence_scope: "this_and_following",
        series_confirmed: true,
      }),
    }),
  );
});

/**
 * Every event synced from Google carries Ion metadata whose flexibility
 * defaults to `locked`, so a confirmation gate there would sit in front of
 * essentially every real edit. An edit is reversible and ETag-conditional, so
 * it commits on Save alone.
 */
/**
 * Undo is what makes removing the confirmation friction honest: an ordinary
 * edit is reversible because Ion offers the reverse of it, aimed at the
 * revision the change produced.
 */
/**
 * The owner reported pressing Save, then Sync, then Apply, unsure which one
 * would make a change take. These assert the healthy path exposes none of that
 * machinery: one gesture, one dispatch, and no recovery control in sight.
 */
test("a non-recurring drag commits once, with no Save, Sync, or Apply anywhere in the flow", async () => {
  const editable = block(
    "36363636-3636-4363-8363-363636363636",
    "Synthetic direct event",
    {
      flexibility: "flexible",
      provider_write_capability: { eligible: true, reason: "eligible" },
    },
  );
  const writable = writableStatus([editable]);
  vi.mocked(invoke).mockResolvedValue(writable);
  const { container } = render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  const point = mockTimeColumnRects(container);
  const eventButton = screen.getByRole("button", {
    name: /^Synthetic direct event,/,
  });
  fireEvent.pointerDown(eventButton, {
    button: 0,
    pointerId: 21,
    clientX: point("2030-01-02").x,
    clientY: 9 * 60 + 15,
  });
  fireEvent.pointerMove(eventButton, {
    pointerId: 21,
    clientX: point("2030-01-02").x,
    clientY: 13 * 60 + 15,
  });
  fireEvent.pointerUp(eventButton, {
    pointerId: 21,
    clientX: point("2030-01-02").x,
    clientY: 13 * 60 + 15,
  });

  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("edit_google_calendar_event", {
      draft: expect.objectContaining({
        calendar_block_id: editable.id,
        edit_kind: "move",
        start_time: "13:00",
        recurrence_scope: "single",
      }),
    }),
  );
  // Exactly one durable mutation, dispatched automatically.
  expect(
    vi
      .mocked(invoke)
      .mock.calls.filter(
        ([command]) => command === "edit_google_calendar_event",
      ),
  ).toHaveLength(1);
  expect(invoke).not.toHaveBeenCalledWith(
    "sync_google_calendars",
    expect.anything(),
  );
  expect(screen.queryByRole("button", { name: "Save change" })).toBeNull();
  expect(
    screen.queryByRole("dialog", { name: "Save recurring event" }),
  ).toBeNull();
  expect(screen.queryByRole("button", { name: /Apply my Ion/i })).toBeNull();
  // The reversible action is offered back instead of being confirmed up front.
  expect(
    await screen.findByRole("button", { name: "Undo" }),
  ).toBeInTheDocument();
});

test("cancelling a recurring gesture's scope choice writes nothing at all", () => {
  const recurring = recurringWritable(
    "37373737-3737-4373-8373-373737373737",
    "Synthetic cancelled gesture",
  );
  const writable = writableStatus([recurring]);
  vi.mocked(invoke).mockResolvedValue(writable);
  const { container } = render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  const point = mockTimeColumnRects(container);
  const handle = screen.getByRole("button", {
    name: "Resize end of Synthetic cancelled gesture",
  });
  fireEvent.pointerDown(handle, {
    button: 0,
    pointerId: 22,
    clientX: point("2030-01-02").x,
    clientY: 10 * 60,
  });
  fireEvent.pointerMove(handle, {
    pointerId: 22,
    clientX: point("2030-01-02").x,
    clientY: 11 * 60,
  });
  fireEvent.pointerUp(handle, {
    pointerId: 22,
    clientX: point("2030-01-02").x,
    clientY: 11 * 60,
  });
  const dialog = screen.getByRole("dialog", { name: "Save recurring event" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));

  expect(
    screen.queryByRole("dialog", { name: "Save recurring event" }),
  ).toBeNull();
  expect(invoke).not.toHaveBeenCalledWith(
    "edit_google_calendar_event",
    expect.anything(),
  );
});

test("an automatically advanced write settles the projection without a manual sync", async () => {
  const editable = block(
    "38383838-3838-4383-8383-383838383838",
    "Synthetic settling event",
    { provider_write_capability: { eligible: true, reason: "eligible" } },
  );
  const onStatus = vi.fn();
  render(
    <CalendarWorkspace
      status={writableStatus([editable])}
      onStatus={onStatus}
      now={now}
      localTimeZone="UTC"
    />,
  );
  const settled = writableStatus([{ ...editable, title: "Settled by Ion" }]);
  // Ion drains a waiting write on its own and announces the settled state.
  await emitCalendarStatus(settled);
  expect(onStatus).toHaveBeenCalledWith(settled);
});

/**
 * The owner reached Apply during ordinary edits and could not tell whether it
 * was required. Every non-conflict write state must keep the recovery surface
 * out of sight -- pending progression is Ion's job, not a decision to present.
 */
test.each([
  ["synced", "confirmed"],
  ["pending", "queued"],
  ["pending", "syncing"],
  ["pending", "retry_wait"],
] as const)(
  "a %s/%s write exposes no conflict-recovery controls",
  (writeState, detail) => {
    const settling = block(
      "39393939-3939-4393-8393-393939393939",
      "Synthetic uncontested event",
      {
        provider_write_state: writeState,
        provider_write_detail: detail,
        provider_write_capability: { eligible: true, reason: "eligible" },
      },
    );
    render(
      <CalendarWorkspace
        status={writableStatus([settling])}
        onStatus={() => undefined}
        now={now}
        localTimeZone="UTC"
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /^Synthetic uncontested event,/ }),
    );
    expect(screen.queryByRole("button", { name: /Apply my Ion/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /Keep Google/i })).toBeNull();
    expect(
      screen.queryByRole("button", { name: /Review differences/i }),
    ).toBeNull();
  },
);

/**
 * H: Google -> Ion convergence. A change made in Google must reach Ion without
 * the owner reaching for Sync Now, so the Calendar refreshes itself whenever it
 * is on screen.
 */
test("the Calendar refreshes itself from Google without any user action", async () => {
  const existing = block(
    "41414141-4141-4141-8141-414141414141",
    "Synthetic remote event",
  );
  const changedInGoogle = writableStatus([
    { ...existing, title: "Renamed in Google" },
  ]);
  vi.mocked(invoke).mockResolvedValue(changedInGoogle);
  const onStatus = vi.fn();
  render(
    <CalendarWorkspace
      status={writableStatus([existing])}
      onStatus={onStatus}
      now={now}
      localTimeZone="UTC"
    />,
  );

  // No click, no Sync Now: the Calendar reaches for Google on its own.
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("sync_google_calendars"),
  );
  await waitFor(() => expect(onStatus).toHaveBeenCalledWith(changedInGoogle));
});

test("the automatic refresh stops while the Calendar is not on screen", async () => {
  const existing = block(
    "42424242-4242-4242-8242-424242424242",
    "Synthetic background event",
  );
  vi.mocked(invoke).mockResolvedValue(writableStatus([existing]));
  const visibility = vi
    .spyOn(document, "visibilityState", "get")
    .mockReturnValue("hidden");
  try {
    render(
      <CalendarWorkspace
        status={writableStatus([existing])}
        onStatus={() => undefined}
        now={now}
        localTimeZone="UTC"
      />,
    );
    // Background work costs the user battery for nothing they can see.
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(invoke).not.toHaveBeenCalledWith("sync_google_calendars");
  } finally {
    visibility.mockRestore();
  }
});

/**
 * The owner's acceptance failure was a permanent "Needs Review" with a
 * Keep Google / Apply Ion chooser. Ordinary drift is now absorbed before it can
 * reach the renderer, and every in-flight state must prove it stays silent.
 */
test.each([
  ["pending", "queued"],
  ["pending", "syncing"],
  ["pending", "ambiguous"],
  ["pending", "retry_wait"],
  ["synced", "confirmed"],
] as const)(
  "a %s/%s write never shows Needs Review or a conflict chooser",
  (writeState, detail) => {
    const converging = block(
      "43434343-4343-4343-8343-434343434343",
      "Synthetic converging event",
      {
        provider_write_state: writeState,
        provider_write_detail: detail,
        provider_write_capability: { eligible: true, reason: "eligible" },
      },
    );
    render(
      <CalendarWorkspace
        status={writableStatus([converging])}
        onStatus={() => undefined}
        now={now}
        localTimeZone="UTC"
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /^Synthetic converging event,/ }),
    );
    expect(screen.queryByText(/needs review/i)).toBeNull();
    expect(
      screen.queryByRole("button", { name: /Review differences/i }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: /Keep Google/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /Apply my Ion/i })).toBeNull();
  },
);

test("exhausted automatic recovery offers a retry, not a choice between versions", () => {
  const exhausted = block(
    "44444444-4444-4444-8444-444444444444",
    "Synthetic exhausted event",
    {
      provider_write_state: "conflict",
      provider_write_detail: "conflict",
      provider_write_failure_class: "stale_precondition",
      provider_write_failure_reason: "automatic_rebase_exhausted",
      provider_recovery_kind: "retry_available",
      provider_write_capability: { eligible: false, reason: "write_pending" },
    },
  );
  render(
    <CalendarWorkspace
      status={writableStatus([exhausted])}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: /^Synthetic exhausted event,/ }),
  );

  // Nothing here is contradictory -- the write just never found a stable
  // version to land on -- so the recovery is one honest retry.
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Keep Google/i })).toBeNull();
  expect(
    screen.queryByRole("button", { name: /Review differences/i }),
  ).toBeNull();
  expect(screen.queryByText(/needs review/i)).toBeNull();
});

test("a genuinely unmergeable condition names itself instead of offering a chooser", () => {
  const unmergeable = block(
    "45454545-4545-4545-8454-454545454545",
    "Synthetic unmergeable event",
    {
      provider_write_state: "conflict",
      provider_write_detail: "conflict",
      provider_write_failure_class: "provider_not_found",
      provider_write_failure_reason: "provider_event_absent_during_refresh",
      provider_recovery_kind: "provider_deleted",
      provider_write_capability: { eligible: false, reason: "write_pending" },
    },
  );
  render(
    <CalendarWorkspace
      status={writableStatus([unmergeable])}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: /^Synthetic unmergeable event,/ }),
  );
  // The actual condition, and only actions that are truthful for it.
  expect(screen.getByText(/Google deleted this event/i)).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Discard my change" }),
  ).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  // No generic chooser exists anywhere in the ordinary Calendar surface.
  expect(screen.queryByRole("button", { name: /Keep Google/i })).toBeNull();
  expect(
    screen.queryByRole("button", { name: /Review differences/i }),
  ).toBeNull();
  expect(screen.queryByRole("button", { name: /Apply my Ion/i })).toBeNull();
});

/**
 * The owner drags the same event twice without waiting. Provider settlement is
 * Ion's problem, not theirs: the second gesture must be accepted and dispatched
 * like any other, with no "still syncing" refusal anywhere.
 */
/**
 * The literal form of "you cannot edit yet": while a write was unsettled the
 * event was projected ineligible, which removed the Edit button and the drag
 * handles outright. The owner could not even attempt a second change.
 */
test("an event with an unsettled write keeps its edit and drag affordances", () => {
  const pending = block(
    "47474747-4747-4747-8474-474747474747",
    "Synthetic settling event",
    {
      flexibility: "flexible",
      provider_write_state: "pending",
      provider_write_detail: "syncing",
      provider_write_capability: { eligible: true, reason: "eligible" },
    },
  );
  render(
    <CalendarWorkspace
      status={writableStatus([pending])}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );

  // Drag and resize handles survive an in-flight write...
  expect(
    screen.getByRole("button", {
      name: "Resize start of Synthetic settling event",
    }),
  ).toBeInTheDocument();

  // ...and so does the Inspector's Edit affordance.
  fireEvent.click(
    screen.getByRole("button", { name: /^Synthetic settling event,/ }),
  );
  expect(
    screen.getByRole("button", { name: "Edit event" }),
  ).toBeInTheDocument();
  expect(screen.queryByText(/Wait for it to finish/i)).toBeNull();
});

/**
 * 3: three rapid drags while commands are genuinely outstanding.
 *
 * The renderer used to drop any gesture arriving while a Tauri invoke had not
 * returned, so the owner's *most recent* action -- the one they meant -- was
 * the one most likely to be lost, silently.
 */
test("a fast third drag is not discarded while an earlier command is in flight", async () => {
  const editable = block(
    "48484848-4848-4848-8484-484848484848",
    "Synthetic triple drag",
    {
      flexibility: "flexible",
      provider_write_capability: { eligible: true, reason: "eligible" },
    },
  );
  const writable = writableStatus([editable]);

  // Hold every command open until we choose to settle it, so the second and
  // third gestures genuinely land mid-flight.
  const release: Array<() => void> = [];
  vi.mocked(invoke).mockImplementation(
    () =>
      new Promise((resolve) => {
        release.push(() => resolve(writable));
      }),
  );

  const { container } = render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  const point = mockTimeColumnRects(container);

  const drag = (pointerId: number, hour: number) => {
    const target = screen.getByRole("button", {
      name: /^Synthetic triple drag,/,
    });
    fireEvent.pointerDown(target, {
      button: 0,
      pointerId,
      clientX: point("2030-01-02").x,
      clientY: 9 * 60 + 15,
    });
    fireEvent.pointerMove(target, {
      pointerId,
      clientX: point("2030-01-02").x,
      clientY: hour * 60 + 15,
    });
    fireEvent.pointerUp(target, {
      pointerId,
      clientX: point("2030-01-02").x,
      clientY: hour * 60 + 15,
    });
  };

  drag(41, 15);
  drag(42, 16);
  drag(43, 17);

  const edits = () =>
    vi
      .mocked(invoke)
      .mock.calls.filter(
        ([command]) => command === "edit_google_calendar_event",
      );

  // Only the first is in flight; the later gestures are held, not lost.
  await waitFor(() => expect(edits()).toHaveLength(1));

  await act(async () => {
    release.forEach((resolve) => resolve());
    release.length = 0;
  });

  // The owner's final position is what actually reaches the provider seam.
  await waitFor(() => expect(edits().length).toBeGreaterThan(1));
  const last = edits().at(-1)?.[1] as { draft: { start_time: string } };
  expect(last.draft.start_time).toBe("17:00");
  expect(screen.queryByText(/still syncing/i)).toBeNull();
});

test("a second drag before the first settles is accepted, not refused", async () => {
  const editable = block(
    "46464646-4646-4646-8464-464646464646",
    "Synthetic rapid event",
    {
      flexibility: "flexible",
      provider_write_capability: { eligible: true, reason: "eligible" },
    },
  );
  const writable = writableStatus([editable]);
  vi.mocked(invoke).mockResolvedValue(writable);
  const { container } = render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  const point = mockTimeColumnRects(container);

  const drag = async (pointerId: number, hour: number) => {
    const button = screen.getByRole("button", {
      name: /^Synthetic rapid event,/,
    });
    fireEvent.pointerDown(button, {
      button: 0,
      pointerId,
      clientX: point("2030-01-02").x,
      clientY: 9 * 60 + 15,
    });
    fireEvent.pointerMove(button, {
      pointerId,
      clientX: point("2030-01-02").x,
      clientY: hour * 60 + 15,
    });
    fireEvent.pointerUp(button, {
      pointerId,
      clientX: point("2030-01-02").x,
      clientY: hour * 60 + 15,
    });
  };

  await drag(31, 15);
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith(
      "edit_google_calendar_event",
      expect.objectContaining({
        draft: expect.objectContaining({ start_time: "15:00" }),
      }),
    ),
  );

  await drag(32, 16);
  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith(
      "edit_google_calendar_event",
      expect.objectContaining({
        draft: expect.objectContaining({ start_time: "16:00" }),
      }),
    ),
  );

  // Both gestures reached the provider seam, and the owner was never told to
  // wait for synchronization.
  expect(
    vi
      .mocked(invoke)
      .mock.calls.filter(
        ([command]) => command === "edit_google_calendar_event",
      ),
  ).toHaveLength(2);
  expect(screen.queryByText(/still syncing/i)).toBeNull();
  expect(screen.queryByText(/Wait for it to finish/i)).toBeNull();
  expect(screen.queryByRole("button", { name: /Apply my Ion/i })).toBeNull();
});

test("a confirmed edit offers an Undo that writes the previous value back", async () => {
  const editable = block(
    "34343434-3434-4343-8343-343434343434",
    "Synthetic undoable event",
    { provider_write_capability: { eligible: true, reason: "eligible" } },
  );
  const writable = writableStatus([editable]);
  vi.mocked(invoke).mockResolvedValue(
    writableStatus([{ ...editable, revision: 2, title: "Renamed by mistake" }]),
  );
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: /^Synthetic undoable event,/ }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Edit event" }));
  fireEvent.change(screen.getByLabelText("Title"), {
    target: { value: "Renamed by mistake" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save change" }));

  const undo = await screen.findByRole("button", { name: "Undo" });
  fireEvent.click(undo);

  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith("edit_google_calendar_event", {
      draft: expect.objectContaining({
        calendar_block_id: editable.id,
        // The value before the edit, against the revision the edit produced.
        title: "Synthetic undoable event",
        expected_block_revision: 2,
      }),
    }),
  );
  // Undo is offered once, not as a repeatable toggle.
  expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
});

test("a series split offers no Undo, because reversing it would split again", async () => {
  const recurring = recurringWritable(
    "35353535-3535-4353-8353-353535353535",
    "Synthetic split series",
    { rules: ["RRULE:FREQ=DAILY"], preset: "daily" },
  );
  const writable = writableStatus([recurring]);
  vi.mocked(invoke).mockResolvedValue(writable);
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(laterOccurrenceButton("Synthetic split series"));
  fireEvent.click(screen.getByRole("button", { name: "Edit event" }));
  fireEvent.change(screen.getByLabelText("Title"), {
    target: { value: "Renamed from here" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save change" }));
  const dialog = screen.getByRole("dialog", { name: "Save recurring event" });
  fireEvent.click(
    within(dialog).getByRole("radio", { name: /This and following events/ }),
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  await waitFor(() =>
    expect(invoke).toHaveBeenCalledWith(
      "edit_google_calendar_event",
      expect.anything(),
    ),
  );
  expect(screen.queryByRole("button", { name: "Undo" })).toBeNull();
});

test("an ordinary edit of a synced Google event needs no confirmation checkbox", () => {
  const locked = block(
    "31313131-3131-4131-8131-313131313131",
    "Synthetic locked event",
    {
      flexibility: "locked",
      provider_write_capability: { eligible: true, reason: "eligible" },
    },
  );
  const writable = writableStatus([locked]);
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: /^Synthetic locked event,/ }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Edit event" }));
  fireEvent.change(screen.getByLabelText("Title"), {
    target: { value: "Renamed once" },
  });

  expect(screen.queryByText(/Ion-locked event/i)).toBeNull();
  expect(screen.getByRole("button", { name: "Save change" })).toBeEnabled();
});

/**
 * The three scopes must stay independently routable: a regression that made one
 * unreachable is invisible unless each is exercised end to end.
 */
test.each([
  ["This event", "occurrence", true],
  ["This and following events", "this_and_following", true],
  ["All events", "series", false],
] as const)(
  "routes %s to recurrence_scope %s",
  async (optionLabel, expectedScope, carriesIdentity) => {
    const recurring = recurringWritable(
      "32323232-3232-4232-8232-323232323232",
      "Synthetic routable series",
      { rules: ["RRULE:FREQ=DAILY"], preset: "daily" },
    );
    const writable = writableStatus([recurring]);
    vi.mocked(invoke).mockResolvedValue(writable);
    render(
      <CalendarWorkspace
        status={writable}
        onStatus={() => undefined}
        now={now}
        localTimeZone="UTC"
      />,
    );
    fireEvent.click(laterOccurrenceButton("Synthetic routable series"));
    fireEvent.click(screen.getByRole("button", { name: "Edit event" }));
    fireEvent.change(screen.getByLabelText("Title"), {
      target: { value: "Renamed" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save change" }));

    const dialog = screen.getByRole("dialog", { name: "Save recurring event" });
    fireEvent.click(
      within(dialog).getByRole("radio", { name: new RegExp(optionLabel) }),
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(invoke).toHaveBeenCalledWith("edit_google_calendar_event", {
        draft: expect.objectContaining({
          calendar_block_id: recurring.id,
          recurrence_scope: expectedScope,
          title: "Renamed",
          occurrence_original_start: carriesIdentity
            ? expect.objectContaining({ date_time: expect.any(String) })
            : null,
        }),
      }),
    );
  },
);

test("the scope chooser is a modal over the whole window, not an Inspector panel", () => {
  const recurring = recurringWritable(
    "33333333-3333-4333-8333-333333333333",
    "Synthetic modal series",
    { rules: ["RRULE:FREQ=DAILY"], preset: "daily" },
  );
  const writable = writableStatus([recurring]);
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(laterOccurrenceButton("Synthetic modal series"));
  fireEvent.click(screen.getByRole("button", { name: "Edit event" }));
  fireEvent.click(screen.getByRole("button", { name: "Save change" }));

  const dialog = screen.getByRole("dialog", { name: "Save recurring event" });
  expect(dialog.closest("aside")).toBeNull();
  expect(dialog.closest(".calendar-modal-overlay")).not.toBeNull();

  // Escape is the same no-op cancel as the Cancel button.
  fireEvent.keyDown(dialog, { key: "Escape" });
  expect(
    screen.queryByRole("dialog", { name: "Save recurring event" }),
  ).toBeNull();
  expect(invoke).not.toHaveBeenCalledWith(
    "edit_google_calendar_event",
    expect.anything(),
  );
});

test("recurrence_unsupported reason renders specific safe copy, not the generic fallback", () => {
  const unsupported = block(
    "88888888-8888-4888-8888-888888888888",
    "Synthetic recurring event",
    {
      recurrence_kind: "master",
      recurrence_rules: ["RRULE:FREQ=WEEKLY"],
      recurrence_preset: "weekly",
      provider_write_capability: {
        eligible: false,
        reason: "recurrence_unsupported",
      },
    },
  );
  const writable = writableStatus([unsupported]);
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: /^Synthetic recurring event,/ }),
  );
  expect(
    screen.getByText(/recurring-event change isn't supported yet/i),
  ).toBeInTheDocument();
  expect(
    screen.queryByText("This event is not eligible for provider changes."),
  ).toBeNull();
});

test("a provider failure class produces specific safe guidance beyond the generic state", () => {
  const failing = block(
    "99999999-9999-4999-8999-999999999999",
    "Synthetic quota-limited event",
    {
      provider_write_state: "pending",
      provider_write_detail: "retry_wait",
      provider_write_failure_class: "retryable_quota",
      provider_write_failure_reason: "provider_rate_limited",
      provider_write_capability: { eligible: false, reason: "write_pending" },
    },
  );
  const writable = writableStatus([failing]);
  render(
    <CalendarWorkspace
      status={writable}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: /^Synthetic quota-limited event,/ }),
  );
  expect(
    screen.getByText(/Google asked Ion to slow down \(rate limit\)/i),
  ).toBeInTheDocument();
});

test("keeps attendee-bearing events visibly read-only", () => {
  const attendee = block(
    "77777777-7777-4777-8777-777777777770",
    "Synthetic attendee event",
    {
      provider_write_capability: {
        eligible: false,
        reason: "attendees_present",
      },
    },
  );
  render(
    <CalendarWorkspace
      status={writableStatus([attendee])}
      onStatus={() => undefined}
      now={now}
      localTimeZone="UTC"
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: /Synthetic attendee event/ }),
  );
  expect(
    screen.queryByRole("button", { name: "Edit event" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByText(/Events with attendees remain read-only/i),
  ).toBeInTheDocument();
});

test("sets a compact minimum desktop window that preserves a usable Day view", () => {
  const mainWindow = tauriConfig.app.windows.find(
    (window) => window.label === "main",
  );
  expect(mainWindow?.minWidth).toBe(540);
  expect(mainWindow?.minHeight).toBe(560);
});
