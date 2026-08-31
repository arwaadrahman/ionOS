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
            if self.end_date is None or self.end_time is None or not self.timezone:
                raise ValueError(
                    "timed resize requires end date, end time, and timezone"
                )
            if (
                self.title is not None
                or self.start_date is not None
                or self.start_time is not None
            ):
                raise ValueError("resize accepts only a target end")
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
                raise ValueError("edit requires a title or temporal value")
        return self


class BeginWriteAttemptInput(CalendarModel):
    expected_state: Literal["ready", "ambiguous"]
    executor_provenance: Literal["direct_human", "recovery"]


class RecordProviderWriteResultInput(CalendarModel):
    expected_state: Literal["attempting"] = "attempting"
    stage: Literal["insert", "patch", "identity_lookup"]
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


class RecoveryResultOutput(CalendarModel):
    attempting_to_ambiguous: int
    retry_wait_to_ready: int
    reauth_required_to_ready: int


class PruneResultOutput(CalendarModel):
    pruned: int
