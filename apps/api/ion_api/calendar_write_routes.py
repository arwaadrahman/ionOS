"""Fixed local-only Phase 2C-R0 Calendar write-foundation routes.

Two lanes, deliberately separated at the transport boundary as well as in the
domain:

* ``/blocks/{id}/intent`` is the **human lane**. It accepts an authorized direct
  human action durably. It never reports provider lifecycle state, so a renderer
  built on it cannot render "pending", "syncing", or "not saved yet".
* ``/internal/*`` is the **provider lane**, for the Rust owner only. It carries
  provider identifiers and the exact ETag a conditional write is conditioned on,
  and is never called by the renderer.

R0 dispatches nothing: no route here reaches Google.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ion_api.calendar_write_contracts import (
    DirectHumanIntentInput,
    DirectHumanIntentReceipt,
    ProviderAttemptInput,
    ProviderOutcomeInput,
    ProviderOutcomeResult,
    ProviderWorkOutput,
    RecoveryOutput,
    WriteConsentInput,
    WriteConsentOutput,
)
from ion_api.calendar_write_coordinator import (
    CalendarWriteCoordinator,
    CalendarWriteError,
    CalendarWriteIneligible,
    CalendarWriteNotFound,
    CalendarWriteRevisionConflict,
)
from ion_api.calendar_write_model import CalendarWriteVocabularyError


def _raise_safe(error: Exception) -> None:
    if isinstance(error, CalendarWriteNotFound):
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "blockers": []}
        ) from error
    if isinstance(error, CalendarWriteRevisionConflict):
        raise HTTPException(
            status_code=409, detail={"code": "revision_conflict", "blockers": []}
        ) from error
    if isinstance(error, CalendarWriteIneligible):
        raise HTTPException(
            status_code=422, detail={"code": "write_ineligible", "blockers": []}
        ) from error
    raise HTTPException(
        status_code=422, detail={"code": "validation", "blockers": []}
    ) from error


def calendar_write_router(coordinator: CalendarWriteCoordinator) -> APIRouter:
    router = APIRouter(prefix="/v1/calendar/writes", tags=["calendar-writes"])

    @router.post("/blocks/{block_id}/intent", response_model=DirectHumanIntentReceipt)
    def accept_intent(
        block_id: str, input: DirectHumanIntentInput
    ) -> DirectHumanIntentReceipt:
        """Accept a direct human Calendar action.

        There is no approval step here and no provider precondition. The only
        refusals are validity refusals.
        """

        try:
            return coordinator.accept_direct_human_intent(block_id, input)
        except (
            CalendarWriteError,
            CalendarWriteVocabularyError,
        ) as error:
            _raise_safe(error)

    @router.post("/internal/work", response_model=ProviderWorkOutput)
    def provider_work(account_id: str | None = None) -> ProviderWorkOutput:
        return coordinator.select_provider_work(account_id)

    @router.post("/internal/attempt", response_model=dict[str, str])
    def begin_attempt(input: ProviderAttemptInput) -> dict[str, str]:
        try:
            coordinator.begin_attempt(input.intent_id)
        except (CalendarWriteError, CalendarWriteVocabularyError) as error:
            _raise_safe(error)
        return {"status": "attempting"}

    @router.post("/internal/outcome", response_model=ProviderOutcomeResult)
    def record_outcome(input: ProviderOutcomeInput) -> ProviderOutcomeResult:
        try:
            return coordinator.record_outcome(
                input.intent_id,
                input.failure_class,
                input.safe_reason,
                input.confirmed,
            )
        except (CalendarWriteError, CalendarWriteVocabularyError) as error:
            _raise_safe(error)

    @router.post("/internal/consent", response_model=WriteConsentOutput)
    def grant_consent(input: WriteConsentInput) -> WriteConsentOutput:
        """Record the one-time Google write capability grant.

        Called by Rust after a successful re-consent flow. It records a
        *capability*, never approval of any individual Calendar action, and
        resumes edits the owner already made so they never retype one.
        """

        try:
            return coordinator.grant_write_capability(input.account_id)
        except (CalendarWriteError, CalendarWriteVocabularyError) as error:
            _raise_safe(error)

    @router.post("/internal/recover", response_model=RecoveryOutput)
    def recover() -> RecoveryOutput:
        return coordinator.recover()

    return router
