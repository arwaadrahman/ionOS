import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";
import {
  ACCEPTED_OPERATIONS,
  ACCEPTED_RECURRENCE_SCOPES,
  AUTOMATIC_RECOVERY,
  CHANGED_FIELDS,
  OWNER_ACTION_RECOVERY,
  draftMatchesChangedFields,
  isAutomaticRecovery,
  requiresOwnerAction,
  type DirectHumanIntentDraft,
} from "./calendarWriteContract";

// Read from disk rather than imported, so the renderer asserts against the same
// bytes Rust `include_str!`s and Python loads -- not against a bundled copy.
const manifest = JSON.parse(
  readFileSync(
    resolve(__dirname, "../../../contracts/calendar-write-vocabulary.json"),
    "utf8",
  ),
);

describe("cross-layer vocabulary parity", () => {
  // The test Phase 2C v1 did not have. `this and following` was implemented end
  // to end in the Python domain, with passing tests, while the Tauri scope
  // allowlist still read single | occurrence | series. Every real attempt failed
  // as local_state_invalid. Rust and Python assert against this same file.
  test("renderer vocabularies match the canonical manifest", () => {
    expect([...ACCEPTED_OPERATIONS]).toEqual(
      manifest.coordinator.accepted_operations,
    );
    expect([...ACCEPTED_RECURRENCE_SCOPES]).toEqual(
      manifest.coordinator.accepted_recurrence_scopes,
    );
    expect([...CHANGED_FIELDS]).toEqual(manifest.coordinator.changed_fields);
    expect([...AUTOMATIC_RECOVERY]).toEqual(manifest.recovery.automatic);
    expect([...OWNER_ACTION_RECOVERY]).toEqual(manifest.recovery.owner_action);
  });

  test("no recovery kind is a generic review decision", () => {
    const known: string[] = [...AUTOMATIC_RECOVERY, ...OWNER_ACTION_RECOVERY];
    for (const forbidden of manifest.recovery.forbidden) {
      expect(known).not.toContain(forbidden);
    }
  });

  test("ordinary provider drift is automatic, never an owner decision", () => {
    expect(isAutomaticRecovery("provider_version_drift")).toBe(true);
    expect(requiresOwnerAction("provider_version_drift")).toBe(false);
    // Exhausting the budget is a named condition, not a disagreement about facts.
    expect(requiresOwnerAction("automatic_recovery_exhausted")).toBe(true);
  });

  test("R0 dispatches nothing", () => {
    expect(manifest.coordinator.dispatchable_operations).toEqual([]);
  });
});

describe("renderer contract shape", () => {
  const base: DirectHumanIntentDraft = {
    command_id: "11111111-1111-4111-8111-111111111111",
    operation: "patch",
    recurrence_scope: "single",
    expected_revision: 3,
    changed_fields: ["title"],
    draft: { title: "Study" },
  };

  test("declared fields must equal supplied fields", () => {
    expect(draftMatchesChangedFields(base)).toBe(true);
    expect(
      draftMatchesChangedFields({ ...base, changed_fields: ["start"] }),
    ).toBe(false);
    expect(
      draftMatchesChangedFields({
        ...base,
        changed_fields: ["title", "title"] as never,
      }),
    ).toBe(false);
  });

  test("carries no provider authority and no second authorization step", () => {
    const serialized = JSON.stringify(base);
    for (const forbidden of [
      "etag",
      "if_match",
      "provider_event_id",
      "calendar_id",
      "account_id",
      "method",
      "url",
      "headers",
      "access_token",
      "approved",
      "confirmed",
      "reviewed",
    ]) {
      expect(serialized).not.toContain(forbidden);
    }
    expect(Object.keys(base).sort()).toEqual([
      "changed_fields",
      "command_id",
      "draft",
      "expected_revision",
      "operation",
      "recurrence_scope",
    ]);
  });
});
