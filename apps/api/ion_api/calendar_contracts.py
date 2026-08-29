"""Validated Phase 2A Google Calendar read-sync contracts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator

CALENDAR_LIST_SCOPE = "https://www.googleapis.com/auth/calendar.calendarlist.readonly"
EVENTS_READ_SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"
REQUIRED_GOOGLE_SCOPES = frozenset((CALENDAR_LIST_SCOPE, EVENTS_READ_SCOPE))


class CalendarModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderCalendarInput(CalendarModel):
    provider_calendar_id: str = Field(min_length=1, max_length=2048)
    summary: str = Field(min_length=1, max_length=4096)
    description: str | None = Field(default=None, max_length=65536)
    location: str | None = Field(default=None, max_length=4096)
    timezone: str | None = Field(default=None, max_length=255)
    access_role: Literal[
        "none",
        "freeBusyReader",
        "reader",
        "writerWithoutPrivateAccess",
        "writer",
        "owner",
    ]
    provider_etag: str | None = Field(default=None, max_length=4096)
    is_primary: bool = False
    provider_selected: bool = False
    provider_hidden: bool = False
    provider_deleted: bool = False

    @model_validator(mode="after")
    def valid_timezone(self):
        if self.timezone:
            try:
                ZoneInfo(self.timezone)
            except ZoneInfoNotFoundError as error:
                raise ValueError(
                    "calendar timezone must be an IANA timezone"
                ) from error
        return self


class GoogleAccountConnectInput(CalendarModel):
    provider_account_id: str = Field(min_length=1, max_length=2048)
    display_name: str = Field(min_length=1, max_length=4096)
    granted_scopes: list[str] = Field(min_length=1, max_length=8)
    keychain_locator: str = Field(min_length=16, max_length=255)
    calendars: list[ProviderCalendarInput] = Field(max_length=10_000)

    @model_validator(mode="after")
    def has_exact_phase_scopes(self):
        if set(self.granted_scopes) != REQUIRED_GOOGLE_SCOPES:
            raise ValueError("the exact Phase 2A read-only scopes are required")
        if not any(item.is_primary for item in self.calendars):
            raise ValueError("calendar discovery must include the primary calendar")
        return self


class SelectionInput(CalendarModel):
    enabled: bool
    expected_revision: int = Field(ge=1)


class SyncBeginInput(CalendarModel):
    generation: str = Field(pattern=r"^[0-9a-f-]{36}$")
    mode: Literal["full", "incremental"]


class ProviderDateTime(CalendarModel):
    date: str | None = None
    date_time: str | None = None
    timezone: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def explicit_union(self):
        if (self.date is None) == (self.date_time is None):
            raise ValueError(
                "provider time must contain exactly one of date or date_time"
            )
        if self.date is not None:
            date.fromisoformat(self.date)
            if self.timezone is not None:
                raise ValueError("date-only provider time must not carry a timezone")
        else:
            parsed = datetime.fromisoformat(self.date_time.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("timed provider value must include an offset")
            if not self.timezone:
                raise ValueError("timed provider value must preserve an IANA timezone")
            try:
                ZoneInfo(self.timezone)
            except ZoneInfoNotFoundError as error:
                raise ValueError(
                    "timed provider value must use an IANA timezone"
                ) from error
        return self


class ProviderEventInput(CalendarModel):
    provider_event_id: str = Field(min_length=1, max_length=2048)
    ical_uid: str | None = Field(default=None, max_length=4096)
    provider_etag: str | None = Field(default=None, max_length=4096)
    provider_updated_at: str | None = Field(default=None, max_length=128)
    title: str | None = Field(default=None, max_length=65536)
    description: str | None = Field(default=None, max_length=262144)
    location: str | None = Field(default=None, max_length=65536)
    status: Literal["confirmed", "tentative", "cancelled"] = "confirmed"
    transparency: Literal["opaque", "transparent"] = "opaque"
    start: ProviderDateTime | None = None
    end: ProviderDateTime | None = None
    recurrence: list[str] = Field(default_factory=list, max_length=1024)
    recurring_event_id: str | None = Field(default=None, max_length=2048)
    original_start: ProviderDateTime | None = None

    @model_validator(mode="after")
    def valid_event_shape(self):
        tombstone = self.status == "cancelled"
        if not tombstone and (self.start is None or self.end is None):
            raise ValueError("active provider events require start and end")
        if (self.start is None) != (self.end is None):
            raise ValueError("provider start and end must be supplied together")
        if self.start and ((self.start.date is None) != (self.end.date is None)):
            raise ValueError("provider start and end must have the same temporal kind")
        if self.recurring_event_id and self.original_start is None:
            raise ValueError("recurrence exceptions require original_start")
        if self.original_start and not self.recurring_event_id:
            raise ValueError("original_start is valid only for an exception")
        if self.recurrence and self.recurring_event_id:
            raise ValueError("an exception cannot also be a recurrence master")
        return self


class SyncPageInput(CalendarModel):
    generation: str = Field(pattern=r"^[0-9a-f-]{36}$")
    events: list[ProviderEventInput] = Field(max_length=2500)


class SyncCompleteInput(CalendarModel):
    generation: str = Field(pattern=r"^[0-9a-f-]{36}$")
    next_sync_token: str = Field(min_length=1, max_length=16384)


class SyncFailureInput(CalendarModel):
    error_code: Literal[
        "network",
        "rate_limited",
        "provider_unavailable",
        "provider_rejected",
        "provider_bad_request",
        "provider_forbidden",
        "provider_not_found",
        "provider_insufficient_permissions",
        "provider_api_disabled",
        "reauth_required",
        "invalid_response",
    ]
    retry_count: int = Field(ge=0, le=32)
    next_retry_at: str | None = Field(default=None, max_length=128)


class GoogleAccountOutput(CalendarModel):
    id: str
    provider_account_id: str
    display_name: str
    granted_scopes: list[str]
    auth_state: Literal["connected", "reauth_required", "disconnected"]
    last_auth_at: str | None
    created_at: str
    updated_at: str
    revision: int


class InternalGoogleAccountOutput(GoogleAccountOutput):
    keychain_locator: str


class GoogleCalendarOutput(CalendarModel):
    id: str
    account_id: str
    provider_calendar_id: str
    summary: str
    description: str | None
    location: str | None
    timezone: str | None
    access_role: str
    is_primary: bool
    provider_selected: bool
    provider_hidden: bool
    enabled_in_ion: bool
    provider_deleted: bool
    has_sync_token: bool
    sync_state: str
    last_synced_at: str | None
    last_error_code: str | None
    retry_count: int
    next_retry_at: str | None
    revision: int


class InternalGoogleCalendarOutput(GoogleCalendarOutput):
    next_sync_token: str | None


class CalendarBlockOutput(CalendarModel):
    id: str
    calendar_id: str
    provider_event_id: str
    ical_uid: str | None
    title: str
    description: str | None
    location: str | None
    temporal_kind: Literal["all_day", "timed"]
    start_date: str | None
    end_date: str | None
    start_at: str | None
    end_at: str | None
    start_timezone: str | None
    end_timezone: str | None
    status: str
    transparency: str
    recurrence_kind: str
    recurrence_rules: list[str]
    recurrence_master_block_id: str | None
    recurring_event_id: str | None
    flexibility: str
    notes: str | None
    provider_deleted_at: str | None
    revision: int


class CalendarStatusOutput(CalendarModel):
    configured: bool = True
    accounts: list[GoogleAccountOutput]
    calendars: list[GoogleCalendarOutput]
    blocks: list[CalendarBlockOutput]


class InternalCalendarStateOutput(CalendarModel):
    accounts: list[InternalGoogleAccountOutput]
    calendars: list[InternalGoogleCalendarOutput]
