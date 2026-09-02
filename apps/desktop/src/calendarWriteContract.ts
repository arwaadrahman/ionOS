/**
 * Phase 2C-R0 renderer-side contract for direct-human Calendar writes.
 *
 * Nothing in the Calendar UI imports this yet, and that is deliberate: R0
 * establishes the foundation R1 will build the first write capability on, and
 * exposes no write affordance of its own.
 *
 * Two properties are enforced by types here and asserted against the canonical
 * cross-layer manifest by the accompanying tests:
 *
 * 1. The renderer can name only Ion identifiers and desired values. There is no
 *    field for a provider event id, ETag, HTTP method, URL, header, or raw
 *    body, so provider authority cannot originate here.
 * 2. There is no approval, confirmation, or review field. A direct human action
 *    is itself the authorization (docs/CALENDAR_BEHAVIOR.md); adding a second
 *    step would be the Phase 2C v1 regression, not a safety improvement.
 */

/** Operations the renderer may name in R0. Widened only across every layer. */
export const ACCEPTED_OPERATIONS = ["patch"] as const;
export const ACCEPTED_RECURRENCE_SCOPES = ["single"] as const;
export const CHANGED_FIELDS = ["title", "start", "end"] as const;

/**
 * The closed recovery taxonomy, with deliberately no generic member. Ordinary
 * provider version drift is `automatic` and never reaches the owner.
 */
export const AUTOMATIC_RECOVERY = [
  "provider_version_drift",
  "transient_transport",
  "transient_backend",
  "transient_quota",
  "reconcilable_ambiguity",
] as const;

export const OWNER_ACTION_RECOVERY = [
  "reauthentication_required",
  "write_permission_lost",
  "provider_target_deleted",
  "recurrence_identity_lost",
  "unsupported_provider_transformation",
  "deterministic_id_collision",
  "provider_rejected_terminally",
  "automatic_recovery_exhausted",
] as const;

export type WriteOperation = (typeof ACCEPTED_OPERATIONS)[number];
export type WriteRecurrenceScope = (typeof ACCEPTED_RECURRENCE_SCOPES)[number];
export type ChangedField = (typeof CHANGED_FIELDS)[number];
export type RecoveryKind =
  (typeof AUTOMATIC_RECOVERY)[number] | (typeof OWNER_ACTION_RECOVERY)[number];

/** A civil all-day date or an instant with its IANA zone, never both. */
export type ProviderDateTime =
  | { date: string; date_time?: never; time_zone?: never }
  | { date?: never; date_time: string; time_zone: string };

export type DirectHumanEditDraft = {
  title?: string;
  start?: ProviderDateTime;
  end?: ProviderDateTime;
};

export type DirectHumanIntentDraft = {
  command_id: string;
  operation: WriteOperation;
  recurrence_scope: WriteRecurrenceScope;
  expected_revision: number;
  changed_fields: ChangedField[];
  draft: DirectHumanEditDraft;
};

export type DirectHumanIntentReceipt = {
  intent_id: string;
  block_id: string;
  sequence: number;
  state: "queued" | "ready";
  accepted: true;
  awaiting_predecessor: boolean;
};

export function isAutomaticRecovery(kind: RecoveryKind): boolean {
  return (AUTOMATIC_RECOVERY as readonly string[]).includes(kind);
}

export function requiresOwnerAction(kind: RecoveryKind): boolean {
  return (OWNER_ACTION_RECOVERY as readonly string[]).includes(kind);
}

/**
 * Every field the renderer declares must be exactly the field it supplies.
 * The same rule is enforced independently in Rust and in the local API, so a
 * layer that forgets it fails a test rather than producing a generic error.
 */
export function draftMatchesChangedFields(
  intent: DirectHumanIntentDraft,
): boolean {
  const declared = [...new Set(intent.changed_fields)].sort();
  if (declared.length !== intent.changed_fields.length) return false;
  const supplied = CHANGED_FIELDS.filter(
    (field) => intent.draft[field] !== undefined,
  ).sort();
  return declared.join("|") === supplied.join("|");
}
