import "@testing-library/jest-dom/vitest";
import { invoke } from "@tauri-apps/api/core";
import { readFileSync } from "node:fs";
import { useState } from "react";
import {
  act,
  cleanup,
  createEvent,
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
    provider_write_state: "synced",
    provider_write_detail: "confirmed",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
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
        provider_write_state: "synced",
        provider_write_detail: "confirmed",
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
  expect(vi.mocked(invoke).mock.calls.map(([command]) => command)).toEqual([
    "set_google_calendar_hidden",
  ]);
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
  expect(vi.mocked(invoke).mock.calls.map(([command]) => command)).toEqual([
    "set_calendar_block_category",
  ]);

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
      },
    }),
  );
  expect(
    await screen.findByText(/saved locally and pending Google confirmation/i),
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

test("edits an eligible title through explicit save and preserves locked confirmation", async () => {
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
  expect(save).toBeDisabled();
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: /confirm changing this Ion-locked event/i,
    }),
  );
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
        locked_confirmed: true,
      },
    }),
  );
  expect(
    await screen.findByText(/saved locally and pending Google confirmation/i),
  ).toBeInTheDocument();
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
        locked_confirmed: true,
      },
    }),
  );
});

test("drag move and end resize open a review surface without pointer-time provider calls", () => {
  const editable = block(
    "66666666-6666-4666-8666-666666666666",
    "Synthetic draggable event",
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
  const transfer = {
    effectAllowed: "none",
    dropEffect: "none",
    setData: vi.fn(),
  };
  const eventButton = screen.getByRole("button", {
    name: /^Synthetic draggable event,/,
  });
  const target = container.querySelector<HTMLElement>(
    '.calendar-time-column[data-calendar-date="2030-01-03"]',
  )!;
  vi.spyOn(target, "getBoundingClientRect").mockReturnValue({
    top: 0,
    bottom: 1440,
    left: 0,
    right: 100,
    width: 100,
    height: 1440,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
  fireEvent.dragStart(eventButton, { dataTransfer: transfer });
  const moveDrop = createEvent.drop(target, { dataTransfer: transfer });
  Object.defineProperty(moveDrop, "clientY", { value: 13 * 60 });
  fireEvent(target, moveDrop);
  expect(screen.getByText(/Review the moved start/i)).toBeInTheDocument();
  expect(invoke).not.toHaveBeenCalledWith(
    "edit_google_calendar_event",
    expect.anything(),
  );
  expect(screen.getByLabelText("Starts")).toHaveValue("2030-01-03");
  expect(screen.getByLabelText("Start time")).toHaveValue("13:00");

  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  fireEvent.click(
    screen.getByRole("button", { name: /^Synthetic draggable event,/ }),
  );
  const resize = screen.getByRole("button", {
    name: "Resize Synthetic draggable event",
  });
  const sameDay = container.querySelector<HTMLElement>(
    '.calendar-time-column[data-calendar-date="2030-01-02"]',
  )!;
  vi.spyOn(sameDay, "getBoundingClientRect").mockReturnValue({
    top: 0,
    bottom: 1440,
    left: 0,
    right: 100,
    width: 100,
    height: 1440,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
  fireEvent.dragStart(resize, { dataTransfer: transfer });
  const resizeDrop = createEvent.drop(sameDay, { dataTransfer: transfer });
  Object.defineProperty(resizeDrop, "clientY", { value: 11 * 60 });
  fireEvent(sameDay, resizeDrop);
  expect(screen.getByText(/Review the resized end/i)).toBeInTheDocument();
  expect(screen.getByLabelText("End time")).toHaveValue("11:00");
  expect(invoke).not.toHaveBeenCalledWith(
    "edit_google_calendar_event",
    expect.anything(),
  );
});

test("keeps attendee and recurring events visibly read-only", () => {
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
