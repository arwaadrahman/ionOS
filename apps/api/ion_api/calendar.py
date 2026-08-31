"""Canonical Phase 2A account, calendar, and duplicate-safe read-sync service."""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import Engine, insert, select, update

from ion_api.calendar_contracts import (
    WRITE_GOOGLE_SCOPES,
    CalendarBlockOutput,
    CalendarCategoryInput,
    CalendarStatusOutput,
    CalendarVisibilityInput,
    GoogleAccountConnectInput,
    GoogleAccountOutput,
    GoogleCalendarOutput,
    InternalCalendarStateOutput,
    InternalGoogleAccountOutput,
    InternalGoogleCalendarOutput,
    ProviderDateTime,
    ProviderDeleteCapabilityOutput,
    ProviderEventInput,
    ProviderWriteCapabilityOutput,
    SelectionInput,
    SyncBeginInput,
    SyncCompleteInput,
    SyncFailureInput,
    SyncPageInput,
)
from ion_api.schema import (
    audit_events,
    calendar_block_ion_metadata,
    calendar_blocks,
    calendar_provider_write_audit,
    calendar_provider_write_intents,
    google_accounts,
    google_calendars,
    google_event_links,
)

logger = logging.getLogger("ion")
UNTITLED_GOOGLE_CALENDAR = "Untitled Google Calendar"


class CalendarNotFoundError(LookupError):
    pass


class CalendarConflictError(RuntimeError):
    pass


class CalendarValidationError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _audit(
    connection,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_kind: str,
    authority: str,
    source: str,
    from_revision: int | None,
    to_revision: int | None,
    command_id: str,
) -> None:
    connection.execute(
        insert(audit_events).values(
            event_id=str(uuid4()),
            occurred_at=utc_now(),
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_kind=actor_kind,
            authority=authority,
            source=source,
            from_revision=from_revision,
            to_revision=to_revision,
            command_id=command_id,
        )
    )


def _write_conflict_audit(
    connection, row, occurred_at: str, *, reason: str, reason_class: str
) -> None:
    connection.execute(
        insert(calendar_provider_write_audit).values(
            id=str(uuid4()),
            intent_id=row.id,
            calendar_block_id=row.calendar_block_id,
            action="write_conflict_detected",
            operation=row.operation,
            changed_fields_json=row.changed_fields_json,
            attempt_count=row.attempt_count,
            safe_reason_class=reason_class,
            safe_reason=reason,
            from_state=row.state,
            to_state="conflict",
            source_revision=row.source_block_revision,
            resulting_revision=None,
            occurred_at=occurred_at,
            executor_provenance="recovery",
        )
    )


def _event_matches_write_intent(row, event: ProviderEventInput) -> bool:
    desired = json.loads(row.desired_values_json or "{}")
    changed = set(json.loads(row.changed_fields_json))
    if "title" in changed and (event.title or "Untitled event") != desired.get("title"):
        return False
    if "temporal" in changed:
        if event.start is None or event.end is None:
            return False
        expected_start = desired.get("start", {})
        expected_end = desired.get("end", {})
        if event.start.date is not None:
            return event.start.date == expected_start.get(
                "date"
            ) and event.end.date == expected_end.get("date")
        try:
            actual_start = datetime.fromisoformat(event.start.date_time)
            actual_end = datetime.fromisoformat(event.end.date_time)
            desired_start = datetime.fromisoformat(expected_start["date_time"])
            desired_end = datetime.fromisoformat(expected_end["date_time"])
        except (KeyError, TypeError, ValueError):
            return False
        return (
            actual_start == desired_start
            and actual_end == desired_end
            and event.start.timezone == expected_start.get("timezone")
            and event.end.timezone == expected_end.get("timezone")
        )
    return True


def _write_completed_audit(
    connection, row, occurred_at: str, resulting_revision: int
) -> None:
    connection.execute(
        insert(calendar_provider_write_audit).values(
            id=str(uuid4()),
            intent_id=row.id,
            calendar_block_id=row.calendar_block_id,
            action="write_completed",
            operation=row.operation,
            changed_fields_json=row.changed_fields_json,
            attempt_count=row.attempt_count,
            safe_reason_class="success",
            safe_reason="provider_confirmed_during_refresh",
            from_state=row.state,
            to_state="completed",
            source_revision=row.source_block_revision,
            resulting_revision=resulting_revision,
            occurred_at=occurred_at,
            executor_provenance="recovery",
        )
    )


def _account_output(row, *, internal: bool = False):
    model = InternalGoogleAccountOutput if internal else GoogleAccountOutput
    values = {
        "id": row.id,
        "provider_account_id": row.provider_account_id,
        "display_name": row.display_name,
        "granted_scopes": json.loads(row.granted_scopes),
        "auth_state": row.auth_state,
        "calendar_write_scope_state": row.calendar_write_scope_state,
        "last_auth_at": row.last_auth_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "revision": row.revision,
    }
    if internal:
        values["keychain_locator"] = row.keychain_locator
    return model.model_validate(values)


def _calendar_output(row, *, account=None, internal: bool = False):
    model = InternalGoogleCalendarOutput if internal else GoogleCalendarOutput
    values = {
        "id": row.id,
        "account_id": row.account_id,
        "provider_calendar_id": row.provider_calendar_id,
        "summary": row.summary,
        "description": row.description,
        "location": row.location,
        "timezone": row.timezone,
        "access_role": row.access_role,
        "is_primary": bool(row.is_primary),
        "provider_selected": bool(row.provider_selected),
        "provider_hidden": bool(row.provider_hidden),
        "enabled_in_ion": bool(row.enabled_in_ion),
        "hidden_in_ion": bool(row.hidden_in_ion),
        "provider_deleted": bool(row.provider_deleted),
        "has_sync_token": row.next_sync_token is not None,
        "sync_state": row.sync_state,
        "last_synced_at": row.last_synced_at,
        "last_error_code": row.last_error_code,
        "retry_count": row.retry_count,
        "next_retry_at": row.next_retry_at,
        "revision": row.revision,
        "provider_write_eligible": bool(
            account
            and account.auth_state == "connected"
            and account.calendar_write_scope_state == "write_granted"
            and row.enabled_in_ion
            and not row.provider_deleted
            and row.access_role in ("writer", "owner")
        ),
        "provider_write_reason": (
            "reauth_required"
            if account
            and (
                account.auth_state != "connected"
                or account.calendar_write_scope_state == "reauth_required"
            )
            else "account_read_only"
            if not account or account.calendar_write_scope_state != "write_granted"
            else "calendar_deleted"
            if row.provider_deleted
            else "calendar_disabled"
            if not row.enabled_in_ion
            else "access_role_read_only"
            if row.access_role not in ("writer", "owner")
            else "eligible"
        ),
    }
    if internal:
        values["next_sync_token"] = row.next_sync_token
    return model.model_validate(values)


class CalendarService:
    def __init__(self, engine: Engine):
        self.engine = engine

    @staticmethod
    def _row(connection, table, identifier: str, column=None):
        key = column if column is not None else table.c.id
        row = connection.execute(select(table).where(key == identifier)).one_or_none()
        if row is None:
            raise CalendarNotFoundError(identifier)
        return row

    def connect_account(self, input: GoogleAccountConnectInput) -> CalendarStatusOutput:
        now = utc_now()
        command_id = str(uuid4())
        with self.engine.begin() as connection:
            existing = connection.execute(
                select(google_accounts).where(
                    google_accounts.c.provider_account_id == input.provider_account_id
                )
            ).one_or_none()
            scopes = json.dumps(sorted(input.granted_scopes), separators=(",", ":"))
            write_scope_state = (
                "write_granted"
                if frozenset(input.granted_scopes) == WRITE_GOOGLE_SCOPES
                else "read_only"
            )
            if existing is None:
                account_id = str(uuid4())
                connection.execute(
                    insert(google_accounts).values(
                        id=account_id,
                        provider_account_id=input.provider_account_id,
                        display_name=input.display_name,
                        granted_scopes=scopes,
                        keychain_locator=input.keychain_locator,
                        auth_state="connected",
                        calendar_write_scope_state=write_scope_state,
                        last_auth_at=now,
                        created_at=now,
                        updated_at=now,
                        revision=1,
                    )
                )
                _audit(
                    connection,
                    entity_type="google_account",
                    entity_id=account_id,
                    action="connected",
                    actor_kind="integration",
                    authority="approved",
                    source="google_calendar",
                    from_revision=None,
                    to_revision=1,
                    command_id=command_id,
                )
            else:
                account_id = existing.id
                revision = existing.revision + 1
                connection.execute(
                    update(google_accounts)
                    .where(google_accounts.c.id == account_id)
                    .values(
                        display_name=input.display_name,
                        granted_scopes=scopes,
                        keychain_locator=input.keychain_locator,
                        auth_state="connected",
                        calendar_write_scope_state=write_scope_state,
                        last_auth_at=now,
                        updated_at=now,
                        revision=revision,
                    )
                )
                _audit(
                    connection,
                    entity_type="google_account",
                    entity_id=account_id,
                    action="reauthenticated",
                    actor_kind="integration",
                    authority="approved",
                    source="google_calendar",
                    from_revision=existing.revision,
                    to_revision=revision,
                    command_id=command_id,
                )

            discovered_ids: set[str] = set()
            for item in input.calendars:
                discovered_ids.add(item.provider_calendar_id)
                row = connection.execute(
                    select(google_calendars).where(
                        google_calendars.c.account_id == account_id,
                        google_calendars.c.provider_calendar_id
                        == item.provider_calendar_id,
                    )
                ).one_or_none()
                if row is None and item.provider_deleted:
                    # A provider tombstone with no local state has nothing to
                    # preserve and must not become a new anonymous calendar.
                    continue
                provider_values = {
                    "description": item.description,
                    "location": item.location,
                    "timezone": item.timezone,
                    "access_role": item.access_role,
                    "provider_etag": item.provider_etag,
                    "is_primary": item.is_primary,
                    "provider_selected": item.provider_selected,
                    "provider_hidden": item.provider_hidden,
                    "provider_deleted": item.provider_deleted,
                    "updated_at": now,
                }
                if item.summary is not None:
                    provider_values["summary"] = item.summary
                elif not item.provider_deleted:
                    # Only a genuinely active unnamed CalendarList entry gets
                    # a presentation fallback. Tombstones retain local titles.
                    provider_values["summary"] = UNTITLED_GOOGLE_CALENDAR
                readable = item.access_role not in ("none", "freeBusyReader")
                if row is None:
                    connection.execute(
                        insert(google_calendars).values(
                            id=str(uuid4()),
                            account_id=account_id,
                            provider_calendar_id=item.provider_calendar_id,
                            enabled_in_ion=(
                                readable
                                and not item.provider_deleted
                                and (item.is_primary or item.provider_selected)
                            ),
                            hidden_in_ion=False,
                            next_sync_token=None,
                            sync_state="idle",
                            active_sync_generation=None,
                            active_sync_mode=None,
                            last_synced_at=None,
                            last_error_code=None,
                            retry_count=0,
                            next_retry_at=None,
                            created_at=now,
                            revision=1,
                            summary=provider_values.pop("summary"),
                            **provider_values,
                        )
                    )
                else:
                    connection.execute(
                        update(google_calendars)
                        .where(google_calendars.c.id == row.id)
                        .values(
                            **provider_values,
                            enabled_in_ion=(
                                bool(row.enabled_in_ion)
                                and readable
                                and not item.provider_deleted
                            ),
                            sync_state="idle",
                            last_error_code=None,
                            next_retry_at=None,
                            revision=row.revision + 1,
                        )
                    )

            existing_calendars = connection.execute(
                select(google_calendars).where(
                    google_calendars.c.account_id == account_id
                )
            ).all()
            for row in existing_calendars:
                if row.provider_calendar_id not in discovered_ids:
                    connection.execute(
                        update(google_calendars)
                        .where(google_calendars.c.id == row.id)
                        .values(
                            provider_deleted=True,
                            enabled_in_ion=False,
                            sync_state="idle",
                            updated_at=now,
                            revision=row.revision + 1,
                        )
                    )
        return self.status()

    def status(self) -> CalendarStatusOutput:
        with self.engine.connect() as connection:
            account_rows = connection.execute(
                select(google_accounts).order_by(google_accounts.c.created_at)
            ).all()
            calendar_rows = connection.execute(
                select(google_calendars).order_by(
                    google_calendars.c.account_id,
                    google_calendars.c.is_primary.desc(),
                    google_calendars.c.summary,
                )
            ).all()
            accounts_by_id = {row.id: row for row in account_rows}
            latest_write_state = (
                select(calendar_provider_write_intents.c.state)
                .where(
                    calendar_provider_write_intents.c.calendar_block_id
                    == calendar_blocks.c.id
                )
                .order_by(calendar_provider_write_intents.c.sequence.desc())
                .limit(1)
                .correlate(calendar_blocks)
                .scalar_subquery()
            )
            latest_write_desired_values = (
                select(calendar_provider_write_intents.c.desired_values_json)
                .where(
                    calendar_provider_write_intents.c.calendar_block_id
                    == calendar_blocks.c.id
                )
                .order_by(calendar_provider_write_intents.c.sequence.desc())
                .limit(1)
                .correlate(calendar_blocks)
                .scalar_subquery()
            )
            latest_write_operation = (
                select(calendar_provider_write_intents.c.operation)
                .where(
                    calendar_provider_write_intents.c.calendar_block_id
                    == calendar_blocks.c.id
                )
                .order_by(calendar_provider_write_intents.c.sequence.desc())
                .limit(1)
                .correlate(calendar_blocks)
                .scalar_subquery()
            )
            latest_write_attempt_count = (
                select(calendar_provider_write_intents.c.attempt_count)
                .where(
                    calendar_provider_write_intents.c.calendar_block_id
                    == calendar_blocks.c.id
                )
                .order_by(calendar_provider_write_intents.c.sequence.desc())
                .limit(1)
                .correlate(calendar_blocks)
                .scalar_subquery()
            )
            latest_write_changed_fields = (
                select(calendar_provider_write_intents.c.changed_fields_json)
                .where(
                    calendar_provider_write_intents.c.calendar_block_id
                    == calendar_blocks.c.id
                )
                .order_by(calendar_provider_write_intents.c.sequence.desc())
                .limit(1)
                .correlate(calendar_blocks)
                .scalar_subquery()
            )
            block_rows = connection.execute(
                select(
                    calendar_blocks,
                    latest_write_state.label("latest_write_state"),
                    latest_write_operation.label("latest_write_operation"),
                    latest_write_attempt_count.label("latest_write_attempt_count"),
                    latest_write_desired_values.label("latest_write_desired_values"),
                    latest_write_changed_fields.label("latest_write_changed_fields"),
                    calendar_block_ion_metadata.c.flexibility,
                    calendar_block_ion_metadata.c.notes,
                    calendar_block_ion_metadata.c.category,
                    calendar_block_ion_metadata.c.category_subtype,
                    calendar_block_ion_metadata.c.revision.label(
                        "ion_metadata_revision"
                    ),
                    google_event_links.c.calendar_id,
                    google_event_links.c.provider_event_id,
                    google_event_links.c.ical_uid,
                    google_event_links.c.recurring_event_id,
                    google_event_links.c.original_start_kind,
                    google_event_links.c.original_start_date,
                    google_event_links.c.original_start_at,
                    google_event_links.c.original_start_timezone,
                    google_event_links.c.link_state,
                    google_event_links.c.provider_etag,
                    google_event_links.c.provider_event_type,
                    google_event_links.c.provider_locked,
                    google_event_links.c.has_attendees,
                    google_accounts.c.auth_state.label("account_auth_state"),
                    google_accounts.c.calendar_write_scope_state,
                    google_calendars.c.enabled_in_ion,
                    google_calendars.c.provider_deleted,
                    google_calendars.c.access_role,
                )
                .join(
                    calendar_block_ion_metadata,
                    calendar_block_ion_metadata.c.calendar_block_id
                    == calendar_blocks.c.id,
                )
                .join(
                    google_event_links,
                    google_event_links.c.calendar_block_id == calendar_blocks.c.id,
                )
                .join(
                    google_accounts,
                    google_accounts.c.id == google_event_links.c.account_id,
                )
                .join(
                    google_calendars,
                    google_calendars.c.id == google_event_links.c.calendar_id,
                )
                .order_by(
                    calendar_blocks.c.start_date,
                    calendar_blocks.c.start_at,
                    calendar_blocks.c.id,
                )
                .limit(10_000)
            ).all()
        return CalendarStatusOutput(
            accounts=[_account_output(row) for row in account_rows],
            calendars=[
                _calendar_output(row, account=accounts_by_id[row.account_id])
                for row in calendar_rows
            ],
            blocks=[self._block_output(row) for row in block_rows],
        )

    def internal_state(self) -> InternalCalendarStateOutput:
        with self.engine.connect() as connection:
            accounts = connection.execute(
                select(google_accounts).order_by(google_accounts.c.created_at)
            ).all()
            calendars = connection.execute(
                select(google_calendars).order_by(google_calendars.c.created_at)
            ).all()
            accounts_by_id = {row.id: row for row in accounts}
        return InternalCalendarStateOutput(
            accounts=[_account_output(row, internal=True) for row in accounts],
            calendars=[
                _calendar_output(
                    row, account=accounts_by_id[row.account_id], internal=True
                )
                for row in calendars
            ],
        )

    @staticmethod
    def _block_output(row) -> CalendarBlockOutput:
        write_state = row.latest_write_state
        provider_write_state = (
            "failed"
            if write_state == "failed"
            else "conflict"
            if write_state == "conflict"
            else "pending"
            if write_state
            in (
                "queued",
                "ready",
                "attempting",
                "retry_wait",
                "reauth_required",
                "ambiguous",
            )
            or row.link_state == "pending_create"
            else "synced"
        )
        provider_write_detail = {
            "attempting": "syncing",
            "completed": "confirmed",
            "cancelled": "confirmed",
            None: "confirmed",
        }.get(write_state, write_state)
        if provider_write_detail == "confirmed" and row.link_state == "pending_create":
            provider_write_detail = "queued"
        local_create_cancel = (
            row.latest_write_operation == "create"
            and row.latest_write_state in ("queued", "ready")
            and row.latest_write_attempt_count == 0
            and row.link_state == "pending_create"
        )
        provider_delete_eligible = (
            row.account_auth_state == "connected"
            and row.calendar_write_scope_state == "write_granted"
            and bool(row.enabled_in_ion)
            and not bool(row.provider_deleted)
            and row.access_role in ("writer", "owner")
            and row.link_state == "confirmed"
            and bool(row.provider_etag)
            and row.provider_etag != "*"
            and row.provider_event_type == "default"
            and not bool(row.provider_locked)
            and not bool(row.has_attendees)
            and row.status != "cancelled"
            and row.provider_deleted_at is None
            and row.recurrence_kind == "single"
            and provider_write_state == "synced"
        )
        values = {
            "title": row.title,
            "temporal_kind": row.temporal_kind,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "start_at": row.start_at,
            "end_at": row.end_at,
            "start_timezone": row.start_timezone,
            "end_timezone": row.end_timezone,
        }
        if (
            write_state
            in (
                "queued",
                "ready",
                "attempting",
                "retry_wait",
                "reauth_required",
                "ambiguous",
                "failed",
            )
            and row.latest_write_desired_values
            and row.latest_write_changed_fields
        ):
            desired = json.loads(row.latest_write_desired_values)
            changed_fields = set(json.loads(row.latest_write_changed_fields))
            if "title" in changed_fields:
                values["title"] = desired["title"]
            if "temporal" in changed_fields:
                start = desired["start"]
                end = desired["end"]
                if start.get("date") is not None:
                    values.update(
                        temporal_kind="all_day",
                        start_date=start["date"],
                        end_date=end["date"],
                        start_at=None,
                        end_at=None,
                        start_timezone=None,
                        end_timezone=None,
                    )
                else:
                    values.update(
                        temporal_kind="timed",
                        start_date=None,
                        end_date=None,
                        start_at=start["date_time"],
                        end_at=end["date_time"],
                        start_timezone=start["timezone"],
                        end_timezone=end["timezone"],
                    )
        return CalendarBlockOutput(
            id=row.id,
            calendar_id=row.calendar_id,
            provider_event_id=row.provider_event_id,
            ical_uid=row.ical_uid,
            title=values["title"],
            description=row.description,
            location=row.location,
            temporal_kind=values["temporal_kind"],
            start_date=values["start_date"],
            end_date=values["end_date"],
            start_at=values["start_at"],
            end_at=values["end_at"],
            start_timezone=values["start_timezone"],
            end_timezone=values["end_timezone"],
            status=row.status,
            transparency=row.transparency,
            recurrence_kind=row.recurrence_kind,
            recurrence_rules=json.loads(row.recurrence_rules or "[]"),
            recurrence_master_block_id=row.recurrence_master_block_id,
            recurring_event_id=row.recurring_event_id,
            original_start_kind=row.original_start_kind,
            original_start_date=row.original_start_date,
            original_start_at=row.original_start_at,
            original_start_timezone=row.original_start_timezone,
            flexibility=row.flexibility,
            notes=row.notes,
            category=row.category,
            category_subtype=row.category_subtype,
            ion_metadata_revision=row.ion_metadata_revision,
            provider_deleted_at=row.provider_deleted_at,
            revision=row.revision,
            provider_write_capability=ProviderWriteCapabilityOutput(
                eligible=(
                    row.account_auth_state == "connected"
                    and row.calendar_write_scope_state == "write_granted"
                    and bool(row.enabled_in_ion)
                    and not bool(row.provider_deleted)
                    and row.access_role in ("writer", "owner")
                    and row.link_state == "confirmed"
                    and bool(row.provider_etag)
                    and row.provider_etag != "*"
                    and row.provider_event_type == "default"
                    and not bool(row.provider_locked)
                    and not bool(row.has_attendees)
                    and row.status != "cancelled"
                    and row.provider_deleted_at is None
                    and row.recurrence_kind == "single"
                    and provider_write_state == "synced"
                ),
                reason=(
                    "reauth_required"
                    if row.account_auth_state != "connected"
                    or row.calendar_write_scope_state == "reauth_required"
                    else "account_read_only"
                    if row.calendar_write_scope_state != "write_granted"
                    else "calendar_deleted"
                    if bool(row.provider_deleted)
                    else "calendar_disabled"
                    if not bool(row.enabled_in_ion)
                    else "access_role_read_only"
                    if row.access_role not in ("writer", "owner")
                    else "special_event"
                    if row.provider_event_type != "default"
                    else "provider_locked"
                    if bool(row.provider_locked)
                    else "attendees_present"
                    if bool(row.has_attendees)
                    else "provider_deleted"
                    if row.status == "cancelled" or row.provider_deleted_at is not None
                    else "provider_unconfirmed"
                    if row.link_state != "confirmed"
                    or not row.provider_etag
                    or row.provider_etag == "*"
                    else "recurrence_unsupported"
                    if row.recurrence_kind != "single"
                    else "write_pending"
                    if provider_write_state != "synced"
                    else "eligible"
                ),
            ),
            provider_delete_capability=ProviderDeleteCapabilityOutput(
                eligible=local_create_cancel or provider_delete_eligible,
                mode=(
                    "local_create_cancel"
                    if local_create_cancel
                    else "provider_delete"
                    if provider_delete_eligible
                    else None
                ),
                reason=(
                    "eligible"
                    if local_create_cancel or provider_delete_eligible
                    else "reauth_required"
                    if row.account_auth_state != "connected"
                    or row.calendar_write_scope_state == "reauth_required"
                    else "account_read_only"
                    if row.calendar_write_scope_state != "write_granted"
                    else "calendar_deleted"
                    if bool(row.provider_deleted)
                    else "calendar_disabled"
                    if not bool(row.enabled_in_ion)
                    else "access_role_read_only"
                    if row.access_role not in ("writer", "owner")
                    else "special_event"
                    if row.provider_event_type != "default"
                    else "provider_locked"
                    if bool(row.provider_locked)
                    else "attendees_present"
                    if bool(row.has_attendees)
                    else "provider_deleted"
                    if row.status == "cancelled" or row.provider_deleted_at is not None
                    else "create_reconciliation_required"
                    if row.latest_write_operation == "create"
                    and row.latest_write_state
                    in (
                        "attempting",
                        "ambiguous",
                        "retry_wait",
                        "reauth_required",
                        "failed",
                        "conflict",
                    )
                    else "recurrence_unsupported"
                    if row.recurrence_kind != "single"
                    else "write_pending"
                    if provider_write_state != "synced"
                    else "provider_unconfirmed"
                    if row.link_state != "confirmed"
                    or not row.provider_etag
                    or row.provider_etag == "*"
                    else "provider_unconfirmed"
                ),
            ),
            provider_write_operation=row.latest_write_operation,
            provider_write_state=provider_write_state,
            provider_write_detail=provider_write_detail,
        )

    def set_selection(
        self, calendar_id: str, input: SelectionInput
    ) -> CalendarStatusOutput:
        now = utc_now()
        command_id = str(uuid4())
        with self.engine.begin() as connection:
            row = self._row(connection, google_calendars, calendar_id)
            if row.revision != input.expected_revision:
                raise CalendarConflictError(calendar_id)
            if input.enabled and (
                row.provider_deleted or row.access_role in ("none", "freeBusyReader")
            ):
                raise CalendarValidationError("calendar is not event-readable")
            if bool(row.enabled_in_ion) != input.enabled:
                revision = row.revision + 1
                connection.execute(
                    update(google_calendars)
                    .where(
                        google_calendars.c.id == calendar_id,
                        google_calendars.c.revision == row.revision,
                    )
                    .values(
                        enabled_in_ion=input.enabled,
                        sync_state="idle",
                        updated_at=now,
                        revision=revision,
                    )
                )
                _audit(
                    connection,
                    entity_type="google_calendar",
                    entity_id=calendar_id,
                    action="enabled" if input.enabled else "disabled",
                    actor_kind="human",
                    authority="direct",
                    source="desktop",
                    from_revision=row.revision,
                    to_revision=revision,
                    command_id=command_id,
                )
        return self.status()

    def set_visibility(
        self, calendar_id: str, input: CalendarVisibilityInput
    ) -> CalendarStatusOutput:
        now = utc_now()
        command_id = str(uuid4())
        with self.engine.begin() as connection:
            row = self._row(connection, google_calendars, calendar_id)
            if row.revision != input.expected_revision:
                raise CalendarConflictError(calendar_id)
            if bool(row.hidden_in_ion) != input.hidden:
                revision = row.revision + 1
                connection.execute(
                    update(google_calendars)
                    .where(
                        google_calendars.c.id == calendar_id,
                        google_calendars.c.revision == row.revision,
                    )
                    .values(
                        hidden_in_ion=input.hidden,
                        updated_at=now,
                        revision=revision,
                    )
                )
                _audit(
                    connection,
                    entity_type="google_calendar",
                    entity_id=calendar_id,
                    action="hidden_from_ion" if input.hidden else "restored_to_ion",
                    actor_kind="human",
                    authority="direct",
                    source="desktop",
                    from_revision=row.revision,
                    to_revision=revision,
                    command_id=command_id,
                )
        return self.status()

    def set_category(
        self, block_id: str, input: CalendarCategoryInput
    ) -> CalendarStatusOutput:
        now = utc_now()
        command_id = str(uuid4())
        with self.engine.begin() as connection:
            block = self._row(connection, calendar_blocks, block_id)
            metadata_row = self._row(
                connection,
                calendar_block_ion_metadata,
                block_id,
                calendar_block_ion_metadata.c.calendar_block_id,
            )
            if metadata_row.revision != input.expected_revision:
                raise CalendarConflictError(block_id)
            if (
                metadata_row.category != input.category
                or metadata_row.category_subtype != input.category_subtype
            ):
                revision = metadata_row.revision + 1
                connection.execute(
                    update(calendar_block_ion_metadata)
                    .where(
                        calendar_block_ion_metadata.c.calendar_block_id == block_id,
                        calendar_block_ion_metadata.c.revision == metadata_row.revision,
                    )
                    .values(
                        category=input.category,
                        category_subtype=input.category_subtype,
                        updated_at=now,
                        revision=revision,
                    )
                )
                _audit(
                    connection,
                    entity_type="calendar_block",
                    entity_id=block.id,
                    action="category_changed",
                    actor_kind="human",
                    authority="direct",
                    source="desktop",
                    from_revision=metadata_row.revision,
                    to_revision=revision,
                    command_id=command_id,
                )
        return self.status()

    def begin_sync(self, calendar_id: str, input: SyncBeginInput) -> None:
        with self.engine.begin() as connection:
            row = self._row(connection, google_calendars, calendar_id)
            account = self._row(connection, google_accounts, row.account_id)
            if not row.enabled_in_ion or row.provider_deleted:
                raise CalendarValidationError("calendar is not enabled")
            if account.auth_state != "connected":
                raise CalendarValidationError("account is not connected")
            if input.mode == "incremental" and not row.next_sync_token:
                raise CalendarValidationError("incremental sync requires a sync token")
            connection.execute(
                update(google_calendars)
                .where(google_calendars.c.id == calendar_id)
                .values(
                    sync_state="syncing",
                    active_sync_generation=input.generation,
                    active_sync_mode=input.mode,
                    last_error_code=None,
                    next_retry_at=None,
                    updated_at=utc_now(),
                    revision=row.revision + 1,
                )
            )
        logger.info("Calendar sync began id=%s mode=%s", calendar_id, input.mode)

    def apply_sync_page(self, calendar_id: str, input: SyncPageInput) -> None:
        with self.engine.begin() as connection:
            calendar = self._active_sync(connection, calendar_id, input.generation)
            for event in input.events:
                self._reconcile_event(connection, calendar, input.generation, event)
            self._resolve_recurrence_masters(connection, calendar_id)

    def complete_sync(self, calendar_id: str, input: SyncCompleteInput) -> None:
        now = utc_now()
        with self.engine.begin() as connection:
            calendar = self._active_sync(connection, calendar_id, input.generation)
            if calendar.active_sync_mode == "full":
                unseen = connection.execute(
                    select(calendar_blocks, google_event_links.c.provider_event_id)
                    .join(
                        google_event_links,
                        google_event_links.c.calendar_block_id == calendar_blocks.c.id,
                    )
                    .where(
                        google_event_links.c.calendar_id == calendar_id,
                        google_event_links.c.last_seen_sync_generation
                        != input.generation,
                        calendar_blocks.c.status != "cancelled",
                    )
                ).all()
                for row in unseen:
                    pending_write = connection.execute(
                        select(calendar_provider_write_intents)
                        .where(
                            calendar_provider_write_intents.c.calendar_block_id
                            == row.id,
                            calendar_provider_write_intents.c.operation.in_(
                                ("patch", "delete_event")
                            ),
                            calendar_provider_write_intents.c.state.in_(
                                (
                                    "queued",
                                    "ready",
                                    "attempting",
                                    "retry_wait",
                                    "reauth_required",
                                    "ambiguous",
                                )
                            ),
                        )
                        .order_by(calendar_provider_write_intents.c.sequence.desc())
                        .limit(1)
                    ).one_or_none()
                    if (
                        pending_write is not None
                        and pending_write.operation == "delete_event"
                    ):
                        prune_after = (
                            (datetime.now(UTC) + timedelta(days=30))
                            .isoformat(timespec="microseconds")
                            .replace("+00:00", "Z")
                        )
                        connection.execute(
                            update(calendar_provider_write_intents)
                            .where(
                                calendar_provider_write_intents.c.id == pending_write.id
                            )
                            .values(
                                state="completed",
                                failure_class="success",
                                failure_reason="provider_already_absent_during_refresh",
                                next_attempt_at=None,
                                updated_at=now,
                                resolved_at=now,
                                prune_after=prune_after,
                            )
                        )
                        _write_completed_audit(
                            connection, pending_write, now, row.revision + 1
                        )
                    elif pending_write is not None:
                        connection.execute(
                            update(calendar_provider_write_intents)
                            .where(
                                calendar_provider_write_intents.c.id == pending_write.id
                            )
                            .values(
                                state="conflict",
                                failure_class="provider_not_found",
                                failure_reason="provider_event_absent_during_refresh",
                                updated_at=now,
                            )
                        )
                        _write_conflict_audit(
                            connection,
                            pending_write,
                            now,
                            reason="provider_event_absent_during_refresh",
                            reason_class="provider_not_found",
                        )
                    revision = row.revision + 1
                    connection.execute(
                        update(calendar_blocks)
                        .where(calendar_blocks.c.id == row.id)
                        .values(
                            status="cancelled",
                            provider_deleted_at=now,
                            updated_at=now,
                            revision=revision,
                        )
                    )
                    _audit(
                        connection,
                        entity_type="calendar_block",
                        entity_id=row.id,
                        action="sync_cancelled",
                        actor_kind="integration",
                        authority="automated",
                        source="google_calendar",
                        from_revision=row.revision,
                        to_revision=revision,
                        command_id=input.generation,
                    )
            self._resolve_recurrence_masters(connection, calendar_id)
            connection.execute(
                update(google_calendars)
                .where(google_calendars.c.id == calendar_id)
                .values(
                    next_sync_token=input.next_sync_token,
                    sync_state="idle",
                    active_sync_generation=None,
                    active_sync_mode=None,
                    last_synced_at=now,
                    last_error_code=None,
                    retry_count=0,
                    next_retry_at=None,
                    updated_at=now,
                    revision=calendar.revision + 1,
                )
            )
        logger.info("Calendar sync completed id=%s", calendar_id)

    def fail_sync(self, calendar_id: str, input: SyncFailureInput) -> None:
        now = utc_now()
        retryable = input.error_code in (
            "network",
            "rate_limited",
            "provider_unavailable",
        )
        next_retry_at = input.next_retry_at
        if retryable and input.retry_count > 0 and next_retry_at is None:
            delay = min(30 * (2 ** min(input.retry_count - 1, 5)), 900)
            next_retry_at = (
                (datetime.now(UTC) + timedelta(seconds=delay))
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z")
            )
        with self.engine.begin() as connection:
            calendar = self._row(connection, google_calendars, calendar_id)
            state = (
                "reauth_required"
                if input.error_code == "reauth_required"
                else "retry_wait"
                if next_retry_at
                else "failed"
            )
            connection.execute(
                update(google_calendars)
                .where(google_calendars.c.id == calendar_id)
                .values(
                    sync_state=state,
                    active_sync_generation=None,
                    active_sync_mode=None,
                    last_error_code=input.error_code,
                    retry_count=input.retry_count,
                    next_retry_at=next_retry_at,
                    updated_at=now,
                    revision=calendar.revision + 1,
                )
            )
            if input.error_code == "reauth_required":
                account = self._row(connection, google_accounts, calendar.account_id)
                connection.execute(
                    update(google_accounts)
                    .where(google_accounts.c.id == account.id)
                    .values(
                        auth_state="reauth_required",
                        calendar_write_scope_state="reauth_required",
                        updated_at=now,
                        revision=account.revision + 1,
                    )
                )
                connection.execute(
                    update(google_calendars)
                    .where(google_calendars.c.account_id == account.id)
                    .values(sync_state="reauth_required", updated_at=now)
                )
        logger.warning(
            "Calendar sync failed id=%s code=%s state=%s",
            calendar_id,
            input.error_code,
            state,
        )

    def disconnect_account(self, account_id: str) -> CalendarStatusOutput:
        now = utc_now()
        command_id = str(uuid4())
        with self.engine.begin() as connection:
            account = self._row(connection, google_accounts, account_id)
            if account.auth_state != "disconnected":
                revision = account.revision + 1
                connection.execute(
                    update(google_accounts)
                    .where(google_accounts.c.id == account_id)
                    .values(
                        auth_state="disconnected",
                        updated_at=now,
                        revision=revision,
                    )
                )
                connection.execute(
                    update(google_calendars)
                    .where(google_calendars.c.account_id == account_id)
                    .values(
                        sync_state="disconnected",
                        active_sync_generation=None,
                        active_sync_mode=None,
                        updated_at=now,
                    )
                )
                _audit(
                    connection,
                    entity_type="google_account",
                    entity_id=account_id,
                    action="disconnected",
                    actor_kind="human",
                    authority="direct",
                    source="desktop",
                    from_revision=account.revision,
                    to_revision=revision,
                    command_id=command_id,
                )
        return self.status()

    @staticmethod
    def _active_sync(connection, calendar_id: str, generation: str):
        row = connection.execute(
            select(google_calendars).where(google_calendars.c.id == calendar_id)
        ).one_or_none()
        if row is None:
            raise CalendarNotFoundError(calendar_id)
        if row.sync_state != "syncing" or row.active_sync_generation != generation:
            raise CalendarConflictError(calendar_id)
        return row

    @staticmethod
    def _temporal_values(value: ProviderDateTime, end: ProviderDateTime | None = None):
        if value.date is not None:
            end_date = end.date if end and end.date else None
            if end_date is None:
                end_date = (
                    date.fromisoformat(value.date) + timedelta(days=1)
                ).isoformat()
            return {
                "temporal_kind": "all_day",
                "start_date": value.date,
                "end_date": end_date,
                "start_at": None,
                "end_at": None,
                "start_timezone": None,
                "end_timezone": None,
            }
        return {
            "temporal_kind": "timed",
            "start_date": None,
            "end_date": None,
            "start_at": value.date_time,
            "end_at": end.date_time if end else value.date_time,
            "start_timezone": value.timezone,
            "end_timezone": end.timezone if end else value.timezone,
        }

    def _reconcile_event(
        self, connection, calendar, generation: str, event: ProviderEventInput
    ):
        existing = connection.execute(
            select(calendar_blocks, google_event_links)
            .join(
                google_event_links,
                google_event_links.c.calendar_block_id == calendar_blocks.c.id,
            )
            .where(
                google_event_links.c.calendar_id == calendar.id,
                google_event_links.c.provider_event_id == event.provider_event_id,
            )
        ).one_or_none()
        if (
            existing is None
            and event.status == "cancelled"
            and not event.recurring_event_id
        ):
            return

        recurrence_kind = (
            "exception"
            if event.recurring_event_id
            else "master"
            if event.recurrence
            else "single"
        )
        time_source = event.start or event.original_start
        if time_source is None:
            if existing is None:
                return
            temporal = {
                key: getattr(existing, key)
                for key in (
                    "temporal_kind",
                    "start_date",
                    "end_date",
                    "start_at",
                    "end_at",
                    "start_timezone",
                    "end_timezone",
                )
            }
        else:
            temporal = self._temporal_values(time_source, event.end)
        now = utc_now()
        provider_deleted_at = (
            existing.provider_deleted_at
            if existing is not None
            and event.status == "cancelled"
            and existing.provider_deleted_at is not None
            else now
            if event.status == "cancelled"
            else None
        )
        block_values = {
            "title": (
                event.title or "Cancelled occurrence"
                if event.status == "cancelled"
                else event.title or "Untitled event"
            ),
            "description": event.description,
            "location": event.location,
            "status": event.status,
            "transparency": event.transparency,
            "recurrence_kind": recurrence_kind,
            "recurrence_rules": (
                json.dumps(event.recurrence, separators=(",", ":"))
                if event.recurrence
                else None
            ),
            "provider_deleted_at": provider_deleted_at,
            **temporal,
        }
        original = event.original_start
        original_values = {
            "original_start_kind": (
                "date"
                if original and original.date is not None
                else "instant"
                if original
                else "none"
            ),
            "original_start_date": original.date if original else None,
            "original_start_at": original.date_time if original else None,
            "original_start_timezone": original.timezone if original else None,
        }
        if existing is None:
            block_id = str(uuid4())
            connection.execute(
                insert(calendar_blocks).values(
                    id=block_id,
                    source_kind="google",
                    recurrence_master_block_id=None,
                    created_at=now,
                    updated_at=now,
                    revision=1,
                    trashed_at=None,
                    **block_values,
                )
            )
            connection.execute(
                insert(calendar_block_ion_metadata).values(
                    calendar_block_id=block_id,
                    flexibility="locked",
                    notes=None,
                    category=None,
                    category_subtype=None,
                    created_at=now,
                    updated_at=now,
                    revision=1,
                )
            )
            connection.execute(
                insert(google_event_links).values(
                    calendar_block_id=block_id,
                    account_id=calendar.account_id,
                    calendar_id=calendar.id,
                    provider_event_id=event.provider_event_id,
                    ical_uid=event.ical_uid,
                    provider_etag=event.provider_etag,
                    provider_updated_at=event.provider_updated_at,
                    recurring_event_id=event.recurring_event_id,
                    last_seen_sync_generation=generation,
                    link_state="confirmed",
                    provider_event_type=event.provider_event_type,
                    provider_locked=event.provider_locked,
                    has_attendees=event.has_attendees,
                    **original_values,
                )
            )
            _audit(
                connection,
                entity_type="calendar_block",
                entity_id=block_id,
                action="sync_created",
                actor_kind="integration",
                authority="automated",
                source="google_calendar",
                from_revision=None,
                to_revision=1,
                command_id=generation,
            )
            return

        pending_patch = connection.execute(
            select(calendar_provider_write_intents)
            .where(
                calendar_provider_write_intents.c.calendar_block_id == existing.id,
                calendar_provider_write_intents.c.operation == "patch",
                calendar_provider_write_intents.c.state.in_(
                    (
                        "queued",
                        "ready",
                        "attempting",
                        "retry_wait",
                        "reauth_required",
                        "ambiguous",
                    )
                ),
            )
            .order_by(calendar_provider_write_intents.c.sequence.desc())
            .limit(1)
        ).one_or_none()
        pending_delete = connection.execute(
            select(calendar_provider_write_intents)
            .where(
                calendar_provider_write_intents.c.calendar_block_id == existing.id,
                calendar_provider_write_intents.c.operation == "delete_event",
                calendar_provider_write_intents.c.state.in_(
                    (
                        "queued",
                        "ready",
                        "attempting",
                        "retry_wait",
                        "reauth_required",
                        "ambiguous",
                    )
                ),
            )
            .order_by(calendar_provider_write_intents.c.sequence.desc())
            .limit(1)
        ).one_or_none()
        confirmed_patch = None
        if (
            pending_patch is not None
            and event.provider_etag
            and event.provider_etag != pending_patch.expected_provider_etag
        ):
            if pending_patch.state in ("attempting", "ambiguous") and (
                _event_matches_write_intent(pending_patch, event)
            ):
                confirmed_patch = pending_patch
            else:
                connection.execute(
                    update(calendar_provider_write_intents)
                    .where(calendar_provider_write_intents.c.id == pending_patch.id)
                    .values(
                        state="conflict",
                        failure_class="stale_precondition",
                        failure_reason="provider_etag_changed_during_refresh",
                        updated_at=now,
                    )
                )
                _write_conflict_audit(
                    connection,
                    pending_patch,
                    now,
                    reason="provider_etag_changed_during_refresh",
                    reason_class="stale_precondition",
                )
        if pending_delete is not None:
            if event.status == "cancelled":
                prune_after = (
                    (datetime.now(UTC) + timedelta(days=30))
                    .isoformat(timespec="microseconds")
                    .replace("+00:00", "Z")
                )
                connection.execute(
                    update(calendar_provider_write_intents)
                    .where(calendar_provider_write_intents.c.id == pending_delete.id)
                    .values(
                        state="completed",
                        failure_class="success",
                        failure_reason="provider_already_absent_during_refresh",
                        next_attempt_at=None,
                        updated_at=now,
                        resolved_at=now,
                        prune_after=prune_after,
                    )
                )
            elif event.provider_etag != pending_delete.expected_provider_etag:
                connection.execute(
                    update(calendar_provider_write_intents)
                    .where(calendar_provider_write_intents.c.id == pending_delete.id)
                    .values(
                        state="conflict",
                        failure_class="stale_precondition",
                        failure_reason="provider_etag_changed_during_refresh",
                        updated_at=now,
                    )
                )
                _write_conflict_audit(
                    connection,
                    pending_delete,
                    now,
                    reason="provider_etag_changed_during_refresh",
                    reason_class="stale_precondition",
                )

        connection.execute(
            update(google_event_links)
            .where(google_event_links.c.calendar_block_id == existing.id)
            .values(
                ical_uid=event.ical_uid,
                provider_etag=event.provider_etag,
                provider_updated_at=event.provider_updated_at,
                recurring_event_id=event.recurring_event_id,
                last_seen_sync_generation=generation,
                link_state="confirmed",
                provider_event_type=event.provider_event_type,
                provider_locked=event.provider_locked,
                has_attendees=event.has_attendees,
                **original_values,
            )
        )
        changes = {
            key: value
            for key, value in block_values.items()
            if getattr(existing, key) != value
        }
        revision = existing.revision
        if changes:
            revision += 1
            connection.execute(
                update(calendar_blocks)
                .where(calendar_blocks.c.id == existing.id)
                .values(**changes, updated_at=now, revision=revision)
            )
            _audit(
                connection,
                entity_type="calendar_block",
                entity_id=existing.id,
                action="sync_cancelled"
                if event.status == "cancelled"
                else "sync_updated",
                actor_kind="integration",
                authority="automated",
                source="google_calendar",
                from_revision=existing.revision,
                to_revision=revision,
                command_id=generation,
            )
        if confirmed_patch is not None:
            prune_after = (
                (datetime.now(UTC) + timedelta(days=30))
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z")
            )
            connection.execute(
                update(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.id == confirmed_patch.id)
                .values(
                    state="completed",
                    failure_class="success",
                    failure_reason="provider_confirmed_during_refresh",
                    next_attempt_at=None,
                    updated_at=now,
                    resolved_at=now,
                    prune_after=prune_after,
                )
            )
            _write_completed_audit(connection, confirmed_patch, now, revision)
        if pending_delete is not None and event.status == "cancelled":
            _write_completed_audit(connection, pending_delete, now, revision)

    @staticmethod
    def _resolve_recurrence_masters(connection, calendar_id: str):
        exceptions = connection.execute(
            select(
                google_event_links.c.calendar_block_id,
                google_event_links.c.recurring_event_id,
            ).where(
                google_event_links.c.calendar_id == calendar_id,
                google_event_links.c.recurring_event_id.is_not(None),
            )
        ).all()
        for exception in exceptions:
            master = connection.execute(
                select(google_event_links.c.calendar_block_id).where(
                    google_event_links.c.calendar_id == calendar_id,
                    google_event_links.c.provider_event_id
                    == exception.recurring_event_id,
                )
            ).one_or_none()
            if master:
                connection.execute(
                    update(calendar_blocks)
                    .where(calendar_blocks.c.id == exception.calendar_block_id)
                    .values(recurrence_master_block_id=master.calendar_block_id)
                )
