"""Typed contracts for the Phase 2C-R0 direct-human write foundation.

The renderer supplies **Ion identifiers and desired values only**. Provider
authority -- account, calendar, provider event id, and the exact ETag a
conditional write is conditioned on -- is derived server-side from the confirmed
link. There is deliberately no field through which a renderer could supply one.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ion_api.calendar_write_model import ChangedField


class ProviderDateTime(BaseModel):
    """A civil all-day date or an instant with its IANA zone, never both."""

    model_config = ConfigDict(extra="forbid")

    date: str | None = None
    date_time: str | None = None
    time_zone: str | None = None

    @model_validator(mode="after")
    def exactly_one_shape(self) -> ProviderDateTime:
        if self.date is not None:
            if self.date_time is not None or self.time_zone is not None:
                raise ValueError("all-day value carries no instant or zone")
        elif self.date_time is None or self.time_zone is None:
            raise ValueError("timed value requires an instant and a zone")
        return self


class DirectHumanEditDraft(BaseModel):
    """The bounded desired mutation. Only allowlisted fields exist here."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=1024)
    start: ProviderDateTime | None = None
    end: ProviderDateTime | None = None


class DirectHumanIntentInput(BaseModel):
    """A direct human Calendar action. The action itself is the authorization.

    There is no approval, review, or confirmation field, and adding one would be
    a product regression rather than a hardening measure: see
    docs/CALENDAR_BEHAVIOR.md, "Direct human action is authorization".
    """

    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=36, max_length=36)
    operation: Literal["patch"]
    recurrence_scope: Literal["single"] = "single"
    expected_revision: int = Field(ge=1)
    changed_fields: list[ChangedField] = Field(min_length=1, max_length=3)
    draft: DirectHumanEditDraft
    provenance: Literal["direct_human"] = "direct_human"

    @model_validator(mode="after")
    def draft_matches_changed_fields(self) -> DirectHumanIntentInput:
        declared = set(self.changed_fields)
        if len(declared) != len(self.changed_fields):
            raise ValueError("changed_fields must not repeat")
        supplied = {
            name
            for name in ("title", "start", "end")
            if getattr(self.draft, name) is not None
        }
        if declared != supplied:
            raise ValueError("changed_fields must describe exactly the draft")
        return self


class DirectHumanIntentReceipt(BaseModel):
    """Safe acknowledgement that the human's action is durably accepted.

    Carries no provider identifier, ETag, account email, or raw provider value.
    """

    model_config = ConfigDict(extra="forbid")

    intent_id: str
    block_id: str
    sequence: int
    state: Literal["queued", "ready"]
    accepted: Literal[True] = True
    awaiting_predecessor: bool


class ProviderWritePlan(BaseModel):
    """One serialized unit of provider work, for the Rust owner only.

    Never returned on a renderer-facing route.
    """

    model_config = ConfigDict(extra="forbid")

    intent_id: str
    block_id: str
    account_id: str
    calendar_id: str
    provider_event_id: str
    operation: str
    recurrence_scope: str
    changed_fields: list[str]
    desired: DirectHumanEditDraft
    expected_provider_etag: str | None
    attempt_count: int
    dispatchable: bool


class ProviderWorkOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plans: list[ProviderWritePlan]
    #: True while any target has provider work in flight. It is reported so the
    #: dispatcher can serialize -- never so a human action can be refused.
    provider_busy: bool


class ProviderAttemptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_id: str


class ProviderOutcomeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_id: str
    failure_class: str
    safe_reason: str | None = Field(default=None, max_length=128)


class RecoveryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_id: str
    block_id: str
    state: str
    #: Exactly one member of the closed recovery taxonomy, or null when nothing
    #: needs recovering. There is no generic member by construction.
    recovery: str | None
    automatic: bool
    owner_action: bool


class RecoveryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[RecoveryEntry]
    repaired_in_flight: int
