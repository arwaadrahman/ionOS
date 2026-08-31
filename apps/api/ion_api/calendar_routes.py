"""Fixed local-only Phase 2A calendar routes used by the Rust owner."""

from fastapi import APIRouter, HTTPException

from ion_api.calendar import (
    CalendarConflictError,
    CalendarNotFoundError,
    CalendarService,
    CalendarValidationError,
)
from ion_api.calendar_contracts import (
    CalendarCategoryInput,
    CalendarStatusOutput,
    CalendarVisibilityInput,
    GoogleAccountConnectInput,
    InternalCalendarStateOutput,
    SelectionInput,
    SyncBeginInput,
    SyncCompleteInput,
    SyncFailureInput,
    SyncPageInput,
)
from ion_api.calendar_write_contracts import (
    BeginWriteAttemptInput,
    CalendarWriteFoundationOutput,
    CreateProviderEventInput,
    CreateProviderEventOutput,
    DeleteProviderEventInput,
    DeleteProviderEventOutput,
    EditProviderEventInput,
    EditProviderEventOutput,
    ProviderWriteIntentSummaryOutput,
    ProviderWritePlanOutput,
    PruneResultOutput,
    PruneWriteIntentsInput,
    QueueProviderWriteIntentInput,
    ReadyWriteIntentsInput,
    ReconcileProviderCreateInput,
    ReconcileProviderDeleteInput,
    ReconcileProviderPatchInput,
    RecordProviderWriteResultInput,
    RecoverWriteIntentsInput,
    RecoveryResultOutput,
    WriteIntentTransitionInput,
)
from ion_api.calendar_writes import CalendarWriteService


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
    writes = CalendarWriteService(service.engine)

    @router.get("/status", response_model=CalendarStatusOutput)
    def status() -> CalendarStatusOutput:
        return service.status()

    @router.post("/internal/state", response_model=InternalCalendarStateOutput)
    def internal_state() -> InternalCalendarStateOutput:
        return service.internal_state()

    @router.get("/write-foundation", response_model=CalendarWriteFoundationOutput)
    def write_foundation() -> CalendarWriteFoundationOutput:
        return writes.foundation()

    @router.post(
        "/internal/write-intents/create",
        response_model=CreateProviderEventOutput,
    )
    def create_write_intent(
        input: CreateProviderEventInput,
    ) -> CreateProviderEventOutput:
        try:
            return CreateProviderEventOutput(
                intent=writes.create(input), status=service.status()
            )
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.post(
        "/internal/write-intents/edit",
        response_model=EditProviderEventOutput,
    )
    def edit_write_intent(
        input: EditProviderEventInput,
    ) -> EditProviderEventOutput:
        try:
            return EditProviderEventOutput(
                intent=writes.edit(input), status=service.status()
            )
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.post(
        "/internal/write-intents/delete",
        response_model=DeleteProviderEventOutput,
    )
    def delete_write_intent(
        input: DeleteProviderEventInput,
    ) -> DeleteProviderEventOutput:
        try:
            intent = writes.delete(input)
            return DeleteProviderEventOutput(
                intent=intent,
                status=service.status(),
                resolution=(
                    "provider_delete_queued"
                    if intent is not None
                    else "local_create_cancelled"
                ),
            )
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.post(
        "/internal/write-intents",
        response_model=ProviderWriteIntentSummaryOutput,
    )
    def queue_write_intent(
        input: QueueProviderWriteIntentInput,
    ) -> ProviderWriteIntentSummaryOutput:
        try:
            return writes.queue(input)
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.post(
        "/internal/write-intents/ready",
        response_model=list[ProviderWritePlanOutput],
    )
    def ready_write_intents(
        input: ReadyWriteIntentsInput,
    ) -> list[ProviderWritePlanOutput]:
        try:
            return writes.ready(input)
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.post(
        "/internal/write-intents/recover",
        response_model=RecoveryResultOutput,
    )
    def recover_write_intents(
        input: RecoverWriteIntentsInput,
    ) -> RecoveryResultOutput:
        try:
            return writes.recover(input)
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.post(
        "/internal/write-intents/prune",
        response_model=PruneResultOutput,
    )
    def prune_write_intents(input: PruneWriteIntentsInput) -> PruneResultOutput:
        try:
            return writes.prune(input)
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.post(
        "/internal/write-intents/{intent_id}/attempt",
        response_model=ProviderWriteIntentSummaryOutput,
    )
    def begin_write_attempt(
        intent_id: str, input: BeginWriteAttemptInput
    ) -> ProviderWriteIntentSummaryOutput:
        try:
            return writes.begin_attempt(intent_id, input)
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.post(
        "/internal/write-intents/{intent_id}/result",
        response_model=ProviderWriteIntentSummaryOutput,
    )
    def record_write_result(
        intent_id: str, input: RecordProviderWriteResultInput
    ) -> ProviderWriteIntentSummaryOutput:
        try:
            return writes.record_result(intent_id, input)
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.post(
        "/internal/write-intents/{intent_id}/reconcile-create",
        response_model=ProviderWriteIntentSummaryOutput,
    )
    def reconcile_write_create(
        intent_id: str, input: ReconcileProviderCreateInput
    ) -> ProviderWriteIntentSummaryOutput:
        try:
            return writes.reconcile_create(intent_id, input)
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.post(
        "/internal/write-intents/{intent_id}/reconcile-patch",
        response_model=ProviderWriteIntentSummaryOutput,
    )
    def reconcile_write_patch(
        intent_id: str, input: ReconcileProviderPatchInput
    ) -> ProviderWriteIntentSummaryOutput:
        try:
            return writes.reconcile_patch(intent_id, input)
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.post(
        "/internal/write-intents/{intent_id}/reconcile-delete",
        response_model=ProviderWriteIntentSummaryOutput,
    )
    def reconcile_write_delete(
        intent_id: str, input: ReconcileProviderDeleteInput
    ) -> ProviderWriteIntentSummaryOutput:
        try:
            return writes.reconcile_delete(intent_id, input)
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.post(
        "/internal/write-intents/{intent_id}/transition",
        response_model=ProviderWriteIntentSummaryOutput,
    )
    def transition_write_intent(
        intent_id: str, input: WriteIntentTransitionInput
    ) -> ProviderWriteIntentSummaryOutput:
        try:
            return writes.transition(intent_id, input)
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

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

    @router.put(
        "/calendars/{calendar_id}/visibility", response_model=CalendarStatusOutput
    )
    def visibility(
        calendar_id: str, input: CalendarVisibilityInput
    ) -> CalendarStatusOutput:
        try:
            return service.set_visibility(calendar_id, input)
        except (
            CalendarNotFoundError,
            CalendarConflictError,
            CalendarValidationError,
        ) as error:
            _raise_safe(error)

    @router.put("/blocks/{block_id}/category", response_model=CalendarStatusOutput)
    def category(block_id: str, input: CalendarCategoryInput) -> CalendarStatusOutput:
        try:
            return service.set_category(block_id, input)
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
