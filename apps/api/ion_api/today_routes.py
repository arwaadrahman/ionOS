from __future__ import annotations

from collections.abc import Callable
from datetime import date
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from ion_api.today import (
    TodayConflictError,
    TodayNotFoundError,
    TodayService,
    TodayValidationError,
)
from ion_api.today_contracts import (
    AddTaskToTodayInput,
    RemoveTaskFromTodayInput,
    ReorderTodayTasksInput,
    SetTodayRoleInput,
    TodayContext,
    TodayOutput,
)


def _call(operation: Callable):
    try:
        return operation()
    except TodayNotFoundError as error:
        raise HTTPException(
            404, detail={"code": "not_found", "blockers": []}
        ) from error
    except TodayConflictError as error:
        raise HTTPException(
            409, detail={"code": "revision_conflict", "blockers": []}
        ) from error
    except (TodayValidationError, IntegrityError) as error:
        raise HTTPException(
            422, detail={"code": "validation", "blockers": []}
        ) from error


def today_router(service: TodayService) -> APIRouter:
    router = APIRouter(prefix="/v1/today", tags=["today"])

    @router.get("", response_model=TodayOutput)
    def get_today(planning_date: date, timezone: str):
        context = TodayContext(planning_date=planning_date, timezone=timezone)
        return _call(lambda: service.get_today(context))

    @router.post(
        "/plans", response_model=TodayOutput, status_code=status.HTTP_201_CREATED
    )
    def add_task_to_today(input: AddTaskToTodayInput):
        return _call(lambda: service.add_task(input, str(uuid4())))

    @router.put("/plans/{plan_id}/role", response_model=TodayOutput)
    def set_today_role(plan_id: str, input: SetTodayRoleInput):
        return _call(lambda: service.set_role(plan_id, input, str(uuid4())))

    @router.post("/plans/{plan_id}/remove", response_model=TodayOutput)
    def remove_task_from_today(plan_id: str, input: RemoveTaskFromTodayInput):
        return _call(lambda: service.remove_task(plan_id, input, str(uuid4())))

    @router.put("/plans/order", response_model=TodayOutput)
    def reorder_today_tasks(input: ReorderTodayTasksInput):
        return _call(lambda: service.reorder(input, str(uuid4())))

    return router
