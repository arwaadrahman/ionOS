"""Closed vocabularies and the recovery taxonomy for direct-human Calendar writes.

Phase 2C-R0. This module is deliberately small and has no database, provider, or
transport dependency: it is the vocabulary every other layer is measured against.

Two rules shape everything here.

**Storage vocabulary does not dictate product behavior.** Migration 0007 is
immutable history, so its CHECK constraints fix the values a row may hold. What
the *coordinator* may produce is narrower, and is declared separately.

**The recovery taxonomy is closed and has no generic member.** Phase 2C v1
allowed any unclassified provider disagreement to fall through into a generic
"review this" decision, which is why ordinary edits kept reaching the owner no
matter how many individual routes were repaired. Here every failure class maps
into exactly one named kind, and `classify_failure` is total by construction.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final, Literal, get_args

VOCABULARY_PATH: Final = (
    Path(__file__).resolve().parents[3] / "contracts" / "calendar-write-vocabulary.json"
)

# --- Storage vocabulary: exactly migration 0007's CHECK constraints. ---

WriteOperation = Literal[
    "create", "patch", "cancel_occurrence", "delete_event", "delete_series"
]
WriteRecurrenceScope = Literal["single", "occurrence", "series"]
WriteIntentState = Literal[
    "queued",
    "ready",
    "attempting",
    "retry_wait",
    "reauth_required",
    "conflict",
    "ambiguous",
    "failed",
    "completed",
    "cancelled",
]
WriteFailureClass = Literal[
    "success",
    "retryable_transport",
    "retryable_backend",
    "retryable_quota",
    "reauthentication_required",
    "stale_precondition",
    "duplicate_or_ambiguous_create",
    "provider_not_found",
    "invalid_target",
    "terminal_provider_rejection",
]
WriteAuditAction = Literal[
    "write_intent_queued",
    "write_intent_ready",
    "write_attempt_started",
    "write_retry_scheduled",
    "write_reauthentication_required",
    "write_outcome_ambiguous",
    "write_conflict_detected",
    "write_failed_terminally",
    "write_completed",
    "write_cancelled",
]

#: Storage values the direct-human coordinator never produces. They exist only
#: because 0007 cannot be edited. A test asserts the coordinator cannot emit them.
COORDINATOR_UNUSED_STATES: Final[frozenset[str]] = frozenset({"conflict"})
COORDINATOR_UNUSED_AUDIT_ACTIONS: Final[frozenset[str]] = frozenset(
    {"write_conflict_detected"}
)

# --- Coordinator vocabulary: what R0 actually accepts. ---

#: R0 accepts intent for an ordinary single-event field change. Recurrence
#: operations are R4/R5 and are not accepted here.
ACCEPTED_OPERATIONS: Final[frozenset[str]] = frozenset({"patch"})
ACCEPTED_RECURRENCE_SCOPES: Final[frozenset[str]] = frozenset({"single"})

#: R1 dispatches the bounded ordinary edit and nothing else. Create, delete, and
#: every recurrence operation stay undispatchable until their own subphase and
#: their own real-Google acceptance gate.
DISPATCHABLE_OPERATIONS: Final[frozenset[str]] = frozenset({"patch"})

ChangedField = Literal["title", "start", "end"]
CHANGED_FIELDS: Final[frozenset[str]] = frozenset(get_args(ChangedField))

IntentProvenance = Literal["direct_human"]
AuditExecutorProvenance = Literal["direct_human", "recovery"]

#: Bounded automatic attempt budget. 0007 constrains attempt_count to 0..5.
MAX_ATTEMPTS: Final = 5

# --- The closed recovery taxonomy. ---

AutomaticRecovery = Literal[
    "provider_version_drift",
    "transient_transport",
    "transient_backend",
    "transient_quota",
    "reconcilable_ambiguity",
]
OwnerActionRecovery = Literal[
    # Permission has never been granted for this account. This is a capability
    # transition the owner completes once, not approval of a Calendar action:
    # the edit that surfaced it is already durable and resumes afterwards.
    "write_consent_required",
    "reauthentication_required",
    "write_permission_lost",
    "provider_target_deleted",
    "recurrence_identity_lost",
    "unsupported_provider_transformation",
    "deterministic_id_collision",
    "provider_rejected_terminally",
    "automatic_recovery_exhausted",
]
RecoveryKind = AutomaticRecovery | OwnerActionRecovery

AUTOMATIC_RECOVERY: Final[frozenset[str]] = frozenset(get_args(AutomaticRecovery))
OWNER_ACTION_RECOVERY: Final[frozenset[str]] = frozenset(get_args(OwnerActionRecovery))

#: Vocabulary that must never appear as a recovery kind. Phase 2C v1's generic
#: review surface is withdrawn, not narrowed; see ADR 0022.
FORBIDDEN_RECOVERY: Final[frozenset[str]] = frozenset(
    {"conflict", "needs_review", "apply_ion", "keep_google", "review_differences"}
)

#: Total mapping from provider failure class to recovery kind. Every member of
#: WriteFailureClass except `success` appears exactly once, so classification can
#: never fall through to a generic outcome.
_FAILURE_RECOVERY: Final[dict[str, str]] = {
    "retryable_transport": "transient_transport",
    "retryable_backend": "transient_backend",
    "retryable_quota": "transient_quota",
    "stale_precondition": "provider_version_drift",
    "duplicate_or_ambiguous_create": "reconcilable_ambiguity",
    "reauthentication_required": "reauthentication_required",
    "provider_not_found": "provider_target_deleted",
    "invalid_target": "unsupported_provider_transformation",
    "terminal_provider_rejection": "provider_rejected_terminally",
}


class CalendarWriteVocabularyError(ValueError):
    """A value outside a closed Calendar-write vocabulary."""


#: Recovery kinds that are not provider failures at all. They describe a
#: capability the account is missing, so they are reached before dispatch rather
#: than classified from a provider result.
CAPABILITY_RECOVERY: Final[frozenset[str]] = frozenset(
    {"write_consent_required", "reauthentication_required"}
)


def classify_capability(scope_state: str) -> str | None:
    """Recovery kind for an account that cannot currently be written to.

    Distinguishes *never granted* from *granted then lost*, because the owner
    sees different, truthful copy for each and only the first is a first-time
    capability transition.
    """

    if scope_state == "write_granted":
        return None
    if scope_state == "reauth_required":
        return "reauthentication_required"
    return "write_consent_required"


def classify_failure(failure_class: str, attempt_count: int) -> str | None:
    """Map a provider failure onto exactly one closed recovery kind.

    Returns `None` for `success`. Ordinary provider version drift classifies as
    `provider_version_drift`, which is *automatic* -- it is never a semantic
    conflict and never reaches the owner. An otherwise automatic kind that has
    consumed the whole attempt budget becomes `automatic_recovery_exhausted`,
    which is an owner-action exception naming what actually happened rather than
    borrowing the language of a disagreement about facts.
    """

    if failure_class == "success":
        return None
    kind = _FAILURE_RECOVERY.get(failure_class)
    if kind is None:
        raise CalendarWriteVocabularyError("failure_class")
    if kind in AUTOMATIC_RECOVERY and attempt_count >= MAX_ATTEMPTS:
        return "automatic_recovery_exhausted"
    return kind


def is_automatically_recoverable(kind: str | None) -> bool:
    """True when Ion finishes this itself and the owner is never told."""

    return kind is not None and kind in AUTOMATIC_RECOVERY


def requires_owner_action(kind: str | None) -> bool:
    return kind is not None and kind in OWNER_ACTION_RECOVERY


def load_vocabulary() -> dict:
    """Read the canonical cross-layer vocabulary manifest."""

    return json.loads(VOCABULARY_PATH.read_text())
