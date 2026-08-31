"""Bounded Phase 2C-1 Calendar provider-write contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from ion_api.calendar_contracts import CalendarModel, ProviderDateTime

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
    now: str = Field(max_length=128)
    limit: int = Field(default=50, ge=1, le=100)


class RecoverWriteIntentsInput(CalendarModel):
    now: str = Field(max_length=128)
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


class RecoveryResultOutput(CalendarModel):
    attempting_to_ambiguous: int
    retry_wait_to_ready: int


class PruneResultOutput(CalendarModel):
    pruned: int
