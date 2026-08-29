"""Canonical Phase 2A account, calendar, and duplicate-safe read-sync service."""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import Engine, insert, select, update

from ion_api.calendar_contracts import (
    CalendarBlockOutput,
    CalendarStatusOutput,
    GoogleAccountConnectInput,
    GoogleAccountOutput,
    GoogleCalendarOutput,
    InternalCalendarStateOutput,
    InternalGoogleAccountOutput,
    InternalGoogleCalendarOutput,
    ProviderDateTime,
    ProviderEventInput,
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
    google_accounts,
    google_calendars,
    google_event_links,
)

logger = logging.getLogger("ion")


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


def _account_output(row, *, internal: bool = False):
    model = InternalGoogleAccountOutput if internal else GoogleAccountOutput
    values = {
        "id": row.id,
        "provider_account_id": row.provider_account_id,
        "display_name": row.display_name,
        "granted_scopes": json.loads(row.granted_scopes),
        "auth_state": row.auth_state,
        "last_auth_at": row.last_auth_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "revision": row.revision,
    }
    if internal:
        values["keychain_locator"] = row.keychain_locator
    return model.model_validate(values)


def _calendar_output(row, *, internal: bool = False):
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
        "provider_deleted": bool(row.provider_deleted),
        "has_sync_token": row.next_sync_token is not None,
        "sync_state": row.sync_state,
        "last_synced_at": row.last_synced_at,
        "last_error_code": row.last_error_code,
        "retry_count": row.retry_count,
        "next_retry_at": row.next_retry_at,
        "revision": row.revision,
    }
    if internal:
        values["next_sync_token"] = row.next_sync_token
    return model.model_validate(values)


class CalendarService:
    def __init__(self, engine: Engine):
        self.engine = engine

    @staticmethod
    def _row(connection, table, identifier: str, column=None):
        key = column or table.c.id
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
                provider_values = {
                    "summary": item.summary,
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
            block_rows = connection.execute(
                select(
                    calendar_blocks,
                    calendar_block_ion_metadata.c.flexibility,
                    calendar_block_ion_metadata.c.notes,
                    google_event_links.c.calendar_id,
                    google_event_links.c.provider_event_id,
                    google_event_links.c.ical_uid,
                    google_event_links.c.recurring_event_id,
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
                .order_by(
                    calendar_blocks.c.start_date,
                    calendar_blocks.c.start_at,
                    calendar_blocks.c.id,
                )
                .limit(10_000)
            ).all()
        return CalendarStatusOutput(
            accounts=[_account_output(row) for row in account_rows],
            calendars=[_calendar_output(row) for row in calendar_rows],
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
        return InternalCalendarStateOutput(
            accounts=[_account_output(row, internal=True) for row in accounts],
            calendars=[_calendar_output(row, internal=True) for row in calendars],
        )

    @staticmethod
    def _block_output(row) -> CalendarBlockOutput:
        return CalendarBlockOutput(
            id=row.id,
            calendar_id=row.calendar_id,
            provider_event_id=row.provider_event_id,
            ical_uid=row.ical_uid,
            title=row.title,
            description=row.description,
            location=row.location,
            temporal_kind=row.temporal_kind,
            start_date=row.start_date,
            end_date=row.end_date,
            start_at=row.start_at,
            end_at=row.end_at,
            start_timezone=row.start_timezone,
            end_timezone=row.end_timezone,
            status=row.status,
            transparency=row.transparency,
            recurrence_kind=row.recurrence_kind,
            recurrence_rules=json.loads(row.recurrence_rules or "[]"),
            recurrence_master_block_id=row.recurrence_master_block_id,
            recurring_event_id=row.recurring_event_id,
            flexibility=row.flexibility,
            notes=row.notes,
            provider_deleted_at=row.provider_deleted_at,
            revision=row.revision,
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

        connection.execute(
            update(google_event_links)
            .where(google_event_links.c.calendar_block_id == existing.id)
            .values(
                ical_uid=event.ical_uid,
                provider_etag=event.provider_etag,
                provider_updated_at=event.provider_updated_at,
                recurring_event_id=event.recurring_event_id,
                last_seen_sync_generation=generation,
                **original_values,
            )
        )
        changes = {
            key: value
            for key, value in block_values.items()
            if getattr(existing, key) != value
        }
        if changes:
            revision = existing.revision + 1
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
