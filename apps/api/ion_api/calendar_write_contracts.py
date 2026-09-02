"""Bounded Phase 2C-1 Calendar provider-write contracts."""

from __future__ import annotations

from datetime import date, time
from typing import Literal

from pydantic import Field, model_validator

from ion_api.calendar_contracts import (
    CalendarModel,
    CalendarStatusOutput,
    ProviderDateTime,
    ProviderEventInput,
)

WriteOperation = Literal[
    "create", "patch", "cancel_occurrence", "delete_event", "delete_series"
]
# Stored outbox scope. A `this_and_following` split is *stored* as its two
# constituent bounded operations (a series-scoped master trim, plus a
# series-scoped create for the new master), so the durable vocabulary is
# unchanged.
WriteRecurrenceScope = Literal["single", "occurrence", "series"]
# Scope a human may request. `this_and_following` is a Google-parity series
# split the domain translates into the bounded operations above.
RequestedRecurrenceScope = Literal[
    "single", "occurrence", "series", "this_and_following"
]
RecurrencePreset = Literal["none", "daily", "weekdays", "weekly", "monthly", "yearly"]
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
WriteField = Literal[
    "title",
    "description",
    "location",
    "transparency",
    "temporal",
    "recurrence",
    "status",
]
ProviderResultClass = Literal[
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


class ProviderRecurrenceIdentity(CalendarModel):
    master_provider_event_id: str = Field(min_length=1, max_length=2048)
    master_provider_etag: str = Field(min_length=1, max_length=4096)
    original_start: ProviderDateTime
    exception_calendar_block_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    )

    @model_validator(mode="after")
    def valid_identity(self):
        if self.master_provider_etag == "*":
            raise ValueError("recurrence identity requires an exact master ETag")
        return self


class ProviderWriteValues(CalendarModel):
    schema_version: Literal[1] = 1
    title: str | None = Field(default=None, max_length=65_536)
    description: str | None = Field(default=None, max_length=262_144)
    location: str | None = Field(default=None, max_length=65_536)
    transparency: Literal["opaque", "transparent"] | None = None
    start: ProviderDateTime | None = None
    end: ProviderDateTime | None = None
    recurrence: list[str] | None = Field(default=None, max_length=128)
    status: Literal["confirmed", "tentative", "cancelled"] | None = None
    recurrence_identity: ProviderRecurrenceIdentity | None = None

    @model_validator(mode="after")
    def valid_temporal_pair(self):
        if (self.start is None) != (self.end is None):
            raise ValueError("provider write start and end must be supplied together")
        if self.start and ((self.start.date is None) != (self.end.date is None)):
            raise ValueError("provider write start and end kinds must match")
        if self.recurrence is not None:
            if any(not item or len(item) > 4096 for item in self.recurrence):
                raise ValueError("provider write recurrence values must be bounded")
        return self


class QueueProviderWriteIntentInput(CalendarModel):
    command_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    calendar_block_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    operation: WriteOperation
    recurrence_scope: WriteRecurrenceScope
    changed_fields: list[WriteField] = Field(min_length=1, max_length=7)
    base_values: ProviderWriteValues | None = None
    desired_values: ProviderWriteValues | None = None
    expected_block_revision: int = Field(ge=1)
    provenance: Literal["direct_human"] = "direct_human"

    @model_validator(mode="after")
    def valid_intent_shape(self):
        if len(self.changed_fields) != len(set(self.changed_fields)):
            raise ValueError("provider write changed fields must be unique")
        if self.operation in ("create", "patch", "cancel_occurrence"):
            if self.desired_values is None:
                raise ValueError(
                    "provider write values are required for this operation"
                )
        if (
            self.operation == "cancel_occurrence"
            and self.recurrence_scope != "occurrence"
        ):
            raise ValueError("occurrence cancellation requires occurrence scope")
        if self.operation == "delete_series" and self.recurrence_scope != "series":
            raise ValueError("series deletion requires series scope")
        if self.operation == "delete_event" and self.recurrence_scope != "single":
            raise ValueError("event deletion requires single scope")
        supplied = (
            set(self.desired_values.model_fields_set) if self.desired_values else set()
        )
        supplied.discard("schema_version")
        expanded_fields = (
            {"start", "end"} if "temporal" in self.changed_fields else set()
        )
        expected_fields = {
            "recurrence" if item == "recurrence" else item
            for item in self.changed_fields
            if item != "temporal"
        } | expanded_fields
        if self.desired_values and expected_fields != supplied:
            raise ValueError("desired values must exactly match changed fields")
        return self


class CreateProviderEventInput(CalendarModel):
    command_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    calendar_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    title: str = Field(min_length=1, max_length=512)
    date: str
    all_day: bool = False
    start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    timezone: str | None = Field(default=None, min_length=1, max_length=255)
    recurrence: RecurrencePreset = "none"
    provenance: Literal["direct_human"] = "direct_human"

    @model_validator(mode="after")
    def valid_create_shape(self):
        date.fromisoformat(self.date)
        if self.all_day:
            if self.start_time is not None or self.end_time is not None:
                raise ValueError("all-day create must not include clock times")
            if self.timezone is not None:
                raise ValueError("all-day create must preserve civil dates only")
        else:
            if self.start_time is None or self.end_time is None or not self.timezone:
                raise ValueError("timed create requires start, end, and timezone")
            time.fromisoformat(self.start_time)
            time.fromisoformat(self.end_time)
        return self


class EditProviderEventInput(CalendarModel):
    command_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    calendar_block_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    edit_kind: Literal["edit", "move", "resize"]
    expected_block_revision: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=512)
    start_date: str | None = None
    end_date: str | None = None
    start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    timezone: str | None = Field(default=None, min_length=1, max_length=255)
    recurrence_scope: RequestedRecurrenceScope = "single"
    occurrence_original_start: ProviderDateTime | None = None
    recurrence: RecurrencePreset | None = None
    recurrence_risk_confirmed: bool = False
    locked_confirmed: bool = False
    provenance: Literal["direct_human"] = "direct_human"

    @model_validator(mode="after")
    def valid_edit_shape(self):
        for value in (self.start_date, self.end_date):
            if value is not None:
                date.fromisoformat(value)
        for value in (self.start_time, self.end_time):
            if value is not None:
                time.fromisoformat(value)
        if self.recurrence_scope == "single":
            if (
                self.occurrence_original_start is not None
                or self.recurrence is not None
            ):
                raise ValueError("single-event edits cannot carry recurrence authority")
        elif self.recurrence_scope == "occurrence":
            if self.occurrence_original_start is None:
                raise ValueError("occurrence edits require original-start identity")
            if self.recurrence is not None:
                raise ValueError("one occurrence cannot change the recurrence rule")
        elif self.recurrence_scope == "this_and_following":
            # A split is anchored on the selected occurrence and continues the
            # series' existing preset forward; the renderer never supplies the
            # replacement rule.
            if self.occurrence_original_start is None:
                raise ValueError("this-and-following requires original-start identity")
            if self.recurrence is not None:
                raise ValueError(
                    "this-and-following continues the existing recurrence preset"
                )
        else:
            if self.occurrence_original_start is not None:
                raise ValueError("series edits target the canonical master")
            if self.recurrence == "none":
                raise ValueError("stopping a series is outside the bounded surface")
        if self.edit_kind == "move":
            if self.start_date is None or self.start_time is None or not self.timezone:
                raise ValueError("timed move requires date, start time, and timezone")
            if (
                self.title is not None
                or self.end_date is not None
                or self.end_time is not None
            ):
                raise ValueError("move accepts only a target start")
        elif self.edit_kind == "resize":
            has_start = self.start_date is not None or self.start_time is not None
            has_end = self.end_date is not None or self.end_time is not None
            if not self.timezone or has_start == has_end:
                raise ValueError("timed resize requires exactly one boundary")
            if has_start and (self.start_date is None or self.start_time is None):
                raise ValueError("start resize requires date and time")
            if has_end and (self.end_date is None or self.end_time is None):
                raise ValueError("end resize requires date and time")
            if self.title is not None:
                raise ValueError("resize cannot change title")
        else:
            timed_fields = (self.start_time, self.end_time, self.timezone)
            has_timed = any(value is not None for value in timed_fields)
            if has_timed and not all(value is not None for value in timed_fields):
                raise ValueError("timed edit requires start, end, and timezone")
            if has_timed and (self.start_date is None or self.end_date is None):
                raise ValueError("timed edit requires start and end dates")
            if not has_timed and (self.start_date is None) != (self.end_date is None):
                raise ValueError("all-day edit requires both civil-date boundaries")
            if self.title is None and self.start_date is None:
                if self.recurrence is None:
                    raise ValueError(
                        "edit requires a title, temporal value, or recurrence"
                    )
        if self.recurrence is not None and self.edit_kind != "edit":
            raise ValueError("recurrence rules change only through explicit edit")
        # A series-wide edit is reversible and leaves every occurrence in place, so
        # Ion does not require a risk acknowledgement to make one. `recurrence_risk_
        # confirmed` stays on the contract as a caller-supplied signal; only
        # occurrence-removing operations still require an explicit confirmation.
        return self


class DeleteProviderEventInput(CalendarModel):
    command_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    calendar_block_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    expected_block_revision: int = Field(ge=1)
    locked_confirmed: bool = False
    recurrence_scope: RequestedRecurrenceScope = "single"
    occurrence_original_start: ProviderDateTime | None = None
    series_confirmed: bool = False
    provenance: Literal["direct_human"] = "direct_human"

    @model_validator(mode="after")
    def valid_delete_scope(self):
        if self.recurrence_scope == "single":
            if self.occurrence_original_start is not None or self.series_confirmed:
                raise ValueError(
                    "single-event delete cannot carry recurrence authority"
                )
        elif self.recurrence_scope == "occurrence":
            if self.occurrence_original_start is None or self.series_confirmed:
                raise ValueError(
                    "occurrence cancellation requires original-start identity"
                )
        elif self.recurrence_scope == "this_and_following":
            if self.occurrence_original_start is None or not self.series_confirmed:
                raise ValueError(
                    "this-and-following delete requires identity and confirmation"
                )
        else:
            if self.occurrence_original_start is not None or not self.series_confirmed:
                raise ValueError("whole-series delete requires blocking confirmation")
        return self


class KeepGoogleVersionInput(CalendarModel):
    """Discard the pending provider-field intent for a conflicted block and
    keep the latest confirmed Google values. Ion IDs only -- no provider
    identifiers, ETags, or arbitrary values are accepted as authority."""

    command_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    calendar_block_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    expected_block_revision: int = Field(ge=1)
    provenance: Literal["direct_human"] = "direct_human"


class ApplyIonChangesInput(CalendarModel):
    """Rebase the conflicted intent's field mask onto the freshly confirmed
    provider ETag as a new explicit human write authorization. Ion IDs only;
    Rust/Python derive the fresh ETag from trusted linkage, never from the
    stale conflict row or a renderer-supplied value."""

    command_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    calendar_block_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    expected_block_revision: int = Field(ge=1)
    provenance: Literal["direct_human"] = "direct_human"


class ReviewDifferencesInput(CalendarModel):
    calendar_block_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )


class ReviewDifferencesOutput(CalendarModel):
    """A bounded, normalized comparison between the latest confirmed
    provider-owned values and the preserved Ion desired intent for a
    conflicted block. Only supported provider fields; no raw provider
    object, technical ID, ETag, or payload dump."""

    calendar_block_id: str
    changed_fields: list[WriteField]
    confirmed_title: str | None = None
    desired_title: str | None = None
    confirmed_start: ProviderDateTime | None = None
    confirmed_end: ProviderDateTime | None = None
    desired_start: ProviderDateTime | None = None
    desired_end: ProviderDateTime | None = None
    confirmed_recurrence: list[str] | None = None
    desired_recurrence: list[str] | None = None
    confirmed_status: str | None = None
    desired_status: str | None = None


class BeginWriteAttemptInput(CalendarModel):
    expected_state: Literal["ready", "ambiguous"]
    executor_provenance: Literal["direct_human", "recovery"]


class RecordProviderWriteResultInput(CalendarModel):
    expected_state: Literal["attempting"] = "attempting"
    stage: Literal[
        "insert", "instance_resolution", "patch", "delete", "identity_lookup"
    ]
    result_class: ProviderResultClass
    safe_reason: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def failure_only(self):
        if self.result_class == "success":
            raise ValueError("provider success requires sanitized reconciliation")
        return self


class ReconcileProviderCreateInput(CalendarModel):
    expected_state: Literal["attempting"] = "attempting"
    resolution_kind: Literal["insert_response", "identity_lookup"]
    event: ProviderEventInput


class ReconcileProviderPatchInput(CalendarModel):
    expected_state: Literal["attempting"] = "attempting"
    resolution_kind: Literal["patch_response", "identity_lookup"]
    event: ProviderEventInput


class ReconcileProviderDeleteInput(CalendarModel):
    expected_state: Literal["attempting"] = "attempting"
    resolution_kind: Literal["delete_response", "identity_lookup", "already_absent"]
    event: ProviderEventInput | None = None

    @model_validator(mode="after")
    def valid_resolution(self):
        if (self.resolution_kind == "identity_lookup") != (self.event is not None):
            raise ValueError("delete identity lookup requires exactly one event")
        return self


class ResolveProviderOccurrenceInput(CalendarModel):
    expected_state: Literal["attempting"] = "attempting"
    master: ProviderEventInput
    instance: ProviderEventInput


class WriteIntentTransitionInput(CalendarModel):
    expected_state: WriteIntentState
    target_state: WriteIntentState
    occurred_at: str = Field(max_length=128)
    executor_provenance: Literal["direct_human", "recovery"]
    result_class: ProviderResultClass | None = None
    safe_reason: str | None = Field(default=None, max_length=128)
    next_attempt_at: str | None = Field(default=None, max_length=128)
    resulting_revision: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def valid_transition_metadata(self):
        if self.target_state == "retry_wait" and self.next_attempt_at is None:
            raise ValueError("retry_wait requires a persisted next attempt")
        if self.target_state != "retry_wait" and self.next_attempt_at is not None:
            raise ValueError("next attempt is valid only for retry_wait")
        if (
            self.target_state
            in (
                "completed",
                "retry_wait",
                "reauth_required",
                "conflict",
                "ambiguous",
                "failed",
            )
            and self.result_class is None
        ):
            raise ValueError("provider result transition requires a safe result class")
        allowed_results = {
            "completed": {"success"},
            "retry_wait": {
                "retryable_transport",
                "retryable_backend",
                "retryable_quota",
            },
            "reauth_required": {"reauthentication_required"},
            "conflict": {"stale_precondition", "provider_not_found"},
            "ambiguous": {
                "duplicate_or_ambiguous_create",
                "retryable_transport",
            },
            "failed": {
                "provider_not_found",
                "invalid_target",
                "terminal_provider_rejection",
            },
        }
        if (
            self.target_state in allowed_results
            and self.result_class not in allowed_results[self.target_state]
        ):
            raise ValueError("provider result class does not match target state")
        return self


class ReadyWriteIntentsInput(CalendarModel):
    now: str | None = Field(default=None, max_length=128)
    limit: int = Field(default=50, ge=1, le=100)


class RecoverWriteIntentsInput(CalendarModel):
    now: str | None = Field(default=None, max_length=128)
    limit: int = Field(default=100, ge=1, le=500)


class PruneWriteIntentsInput(CalendarModel):
    now: str = Field(max_length=128)
    limit: int = Field(default=100, ge=1, le=500)


class ProviderWriteIntentSummaryOutput(CalendarModel):
    id: str
    calendar_block_id: str
    operation: WriteOperation
    recurrence_scope: WriteRecurrenceScope
    changed_fields: list[WriteField]
    state: WriteIntentState
    attempt_count: int
    next_attempt_at: str | None
    failure_class: ProviderResultClass | None
    failure_reason: str | None
    created_at: str
    updated_at: str
    resolved_at: str | None
    provenance: Literal["direct_human"]


class ProviderWritePlanOutput(ProviderWriteIntentSummaryOutput):
    account_id: str
    calendar_id: str
    provider_event_id: str
    expected_provider_etag: str | None
    base_values: ProviderWriteValues | None
    desired_values: ProviderWriteValues | None
    source_block_revision: int
    schema_version: Literal[1]


class AccountWriteCapabilityOutput(CalendarModel):
    account_id: str
    state: Literal["read_only", "write_granted", "reauth_required"]
    write_capable: bool


class CalendarWriteCapabilityOutput(CalendarModel):
    calendar_id: str
    eligible: bool
    reason: str


class BlockWriteCapabilityOutput(CalendarModel):
    calendar_block_id: str
    eligible: bool
    reason: str


class CalendarWriteFoundationOutput(CalendarModel):
    accounts: list[AccountWriteCapabilityOutput]
    calendars: list[CalendarWriteCapabilityOutput]
    blocks: list[BlockWriteCapabilityOutput]
    pending: list[ProviderWriteIntentSummaryOutput]


class CreateProviderEventOutput(CalendarModel):
    intent: ProviderWriteIntentSummaryOutput
    status: CalendarStatusOutput


class EditProviderEventOutput(CalendarModel):
    intent: ProviderWriteIntentSummaryOutput
    status: CalendarStatusOutput


class DeleteProviderEventOutput(CalendarModel):
    intent: ProviderWriteIntentSummaryOutput | None
    status: CalendarStatusOutput
    resolution: Literal["provider_delete_queued", "local_create_cancelled"]


class KeepGoogleVersionOutput(CalendarModel):
    intent: ProviderWriteIntentSummaryOutput
    status: CalendarStatusOutput


class ApplyIonChangesOutput(CalendarModel):
    intent: ProviderWriteIntentSummaryOutput
    status: CalendarStatusOutput


class RecoveryResultOutput(CalendarModel):
    attempting_to_ambiguous: int
    retry_wait_to_ready: int
    reauth_required_to_ready: int
    failed_occurrence_to_conflict: int
    # Rows the superseded conflict policy created for ordinary drift,
    # re-armed against confirmed authority by this pass.
    legacy_conflicts_requeued: int = 0
    # How long until the earliest still-waiting retry becomes due, so the
    # dispatcher can wake itself once instead of stranding the write until an
    # unrelated user action. None when nothing is waiting. Expressed as a delay
    # rather than an instant so the caller needs no clock of its own.
    next_retry_in_seconds: int | None = None


class PruneResultOutput(CalendarModel):
    pruned: int
