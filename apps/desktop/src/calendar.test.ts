import { invoke } from "@tauri-apps/api/core";
import { beforeEach, expect, test, vi } from "vitest";
import { CalendarWriteFoundation, googleCalendarClient } from "./calendar";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

beforeEach(() => vi.clearAllMocks());

test("reads only backend-derived write capability through one fixed command", async () => {
  const foundation: CalendarWriteFoundation = {
    accounts: [
      {
        account_id: "11111111-1111-4111-8111-111111111111",
        state: "read_only",
        write_capable: false,
      },
    ],
    calendars: [
      {
        calendar_id: "22222222-2222-4222-8222-222222222222",
        eligible: false,
        reason: "account_read_only",
      },
    ],
    blocks: [
      {
        calendar_block_id: "33333333-3333-4333-8333-333333333333",
        eligible: false,
        reason: "attendees_present",
      },
    ],
    pending: [],
  };
  vi.mocked(invoke).mockResolvedValue(foundation);

  await expect(googleCalendarClient.writeFoundation()).resolves.toEqual(
    foundation,
  );
  expect(invoke).toHaveBeenCalledWith("get_calendar_write_foundation");
  expect(invoke).not.toHaveBeenCalledWith(
    expect.stringMatching(/insert|patch|delete|transition|enqueue/i),
    expect.anything(),
  );
});
