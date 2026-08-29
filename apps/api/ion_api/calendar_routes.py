"""Fixed local-only Phase 2A calendar routes used by the Rust owner."""

from fastapi import APIRouter, HTTPException

from ion_api.calendar import (
    CalendarConflictError,
    CalendarNotFoundError,
    CalendarService,
    CalendarValidationError,
)
from ion_api.calendar_contracts import (
    CalendarStatusOutput,
    GoogleAccountConnectInput,
    InternalCalendarStateOutput,
    SelectionInput,
    SyncBeginInput,
    SyncCompleteInput,
    SyncFailureInput,
    SyncPageInput,
)


def _raise_safe(error: Exception) -> None:
    if isinstance(error, CalendarNotFoundError):
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "blockers": []}
        ) from error
    if isinstance(error, CalendarConflictError):
        raise HTTPException(
            status_code=409,
            detail={"code": "revision_conflict", "blockers": []},
        ) from error
    raise HTTPException(
        status_code=422, detail={"code": "validation", "blockers": []}
    ) from error


def calendar_router(service: CalendarService) -> APIRouter:
    router = APIRouter(prefix="/v1/calendar", tags=["calendar"])

    @router.get("/status", response_model=CalendarStatusOutput)
    def status() -> CalendarStatusOutput:
        return service.status()

    @router.post("/internal/state", response_model=InternalCalendarStateOutput)
    def internal_state() -> InternalCalendarStateOutput:
        return service.internal_state()

    @router.post("/accounts/connect", response_model=CalendarStatusOutput)
    def connect(input: GoogleAccountConnectInput) -> CalendarStatusOutput:
        try:
            return service.connect_account(input)
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.post(
        "/accounts/{account_id}/disconnect", response_model=CalendarStatusOutput
    )
    def disconnect(account_id: str) -> CalendarStatusOutput:
        try:
            return service.disconnect_account(account_id)
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.put(
        "/calendars/{calendar_id}/selection", response_model=CalendarStatusOutput
    )
    def selection(calendar_id: str, input: SelectionInput) -> CalendarStatusOutput:
        try:
            return service.set_selection(calendar_id, input)
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.post("/calendars/{calendar_id}/sync/begin")
    def begin_sync(calendar_id: str, input: SyncBeginInput) -> dict[str, str]:
        try:
            service.begin_sync(calendar_id, input)
            return {"status": "ok"}
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.post("/calendars/{calendar_id}/sync/page")
    def sync_page(calendar_id: str, input: SyncPageInput) -> dict[str, str]:
        try:
            service.apply_sync_page(calendar_id, input)
            return {"status": "ok"}
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.post("/calendars/{calendar_id}/sync/complete")
    def complete_sync(calendar_id: str, input: SyncCompleteInput) -> dict[str, str]:
        try:
            service.complete_sync(calendar_id, input)
            return {"status": "ok"}
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.post("/calendars/{calendar_id}/sync/failure")
    def fail_sync(calendar_id: str, input: SyncFailureInput) -> dict[str, str]:
        try:
            service.fail_sync(calendar_id, input)
            return {"status": "ok"}
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    return router
