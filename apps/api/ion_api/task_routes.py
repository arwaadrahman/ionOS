from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from ion_api.task_contracts import (
    CreateTaskInput,
    RevisionInput,
    SetTaskRelationshipsInput,
    TaskOutput,
    UpdateTaskInput,
)
from ion_api.tasks import (
    TaskAssignmentUnavailableError,
    TaskConflictError,
    TaskNotFoundError,
    TaskService,
)


def task_router(service: TaskService) -> APIRouter:
    router = APIRouter(prefix="/v1/tasks", tags=["tasks"])

    @router.get("", response_model=list[TaskOutput])
    def list_tasks() -> list[TaskOutput]:
        return service.list()

    @router.get("/trash", response_model=list[TaskOutput])
    def list_trashed_tasks() -> list[TaskOutput]:
        return service.list(trashed=True)

    @router.post("", response_model=TaskOutput, status_code=status.HTTP_201_CREATED)
    def create_task(input: CreateTaskInput) -> TaskOutput:
        return _mutate(lambda: service.create(input, str(uuid4())))

    @router.patch("/{task_id}", response_model=TaskOutput)
    def update_task(task_id: str, input: UpdateTaskInput) -> TaskOutput:
        return _mutate(lambda: service.update(task_id, input, str(uuid4())))

    @router.put("/{task_id}/relationships", response_model=TaskOutput)
    def set_task_relationships(
        task_id: str, input: SetTaskRelationshipsInput
    ) -> TaskOutput:
        return _mutate(lambda: service.set_relationships(task_id, input, str(uuid4())))

    @router.post("/{task_id}/complete", response_model=TaskOutput)
    def complete_task(task_id: str, input: RevisionInput) -> TaskOutput:
        return _mutate(
            lambda: service.complete(task_id, input.expected_revision, str(uuid4()))
        )

    @router.post("/{task_id}/reopen", response_model=TaskOutput)
    def reopen_task(task_id: str, input: RevisionInput) -> TaskOutput:
        return _mutate(
            lambda: service.reopen(task_id, input.expected_revision, str(uuid4()))
        )

    @router.post("/{task_id}/trash", response_model=TaskOutput)
    def trash_task(task_id: str, input: RevisionInput) -> TaskOutput:
        return _mutate(
            lambda: service.trash(task_id, input.expected_revision, str(uuid4()))
        )

    @router.post("/{task_id}/restore", response_model=TaskOutput)
    def restore_task(task_id: str, input: RevisionInput) -> TaskOutput:
        return _mutate(
            lambda: service.restore(task_id, input.expected_revision, str(uuid4()))
        )

    return router


def _mutate(operation) -> TaskOutput:
    try:
        return operation()
    except TaskNotFoundError as error:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "blockers": []}
        ) from error
    except TaskConflictError as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "revision_conflict", "blockers": []},
        ) from error
    except TaskAssignmentUnavailableError as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "assignment_unavailable", "blockers": []},
        ) from error
    except IntegrityError as error:
        raise HTTPException(
            status_code=422, detail={"code": "validation", "blockers": []}
        ) from error
