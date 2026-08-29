from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from ion_api.db import create_database_engine
from ion_api.migrations import upgrade_to_head
from ion_api.schema import audit_events, goals, projects, tasks
from ion_api.task_contracts import CreateTaskInput, DeadlineInput, UpdateTaskInput
from ion_api.tasks import TaskAssignmentUnavailableError, TaskConflictError, TaskService


@pytest.fixture
def service(tmp_path):
    database_path = tmp_path / "tasks.sqlite3"
    upgrade_to_head(database_path)
    return TaskService(create_database_engine(database_path))


def test_task_vertical_slice_writes_audit_and_preserves_progress(service):
    task = service.create(
        CreateTaskInput(
            title="Calibrate synthetic star map",
            progress_percent=35,
            deadline=DeadlineInput(kind="date", date="2030-01-02"),
        ),
        "11111111-1111-4111-8111-111111111111",
    )
    UUID(task.id)
    assert task.id == task.id.lower()
    assert task.revision == 1

    edited = service.update(
        task.id,
        UpdateTaskInput(expected_revision=1, importance="high"),
        "22222222-2222-4222-8222-222222222222",
    )
    completed = service.complete(
        task.id, edited.revision, "33333333-3333-4333-8333-333333333333"
    )
    reopened = service.reopen(
        task.id, completed.revision, "44444444-4444-4444-8444-444444444444"
    )
    trashed = service.trash(
        task.id, reopened.revision, "55555555-5555-4555-8555-555555555555"
    )
    restored = service.restore(
        task.id, trashed.revision, "66666666-6666-4666-8666-666666666666"
    )

    assert completed.completed_at is not None
    assert completed.progress_percent == 35
    assert reopened.completed_at is None
    assert reopened.progress_percent == 35
    assert service.list() == [restored]
    assert service.list(trashed=True) == []
    with service.engine.connect() as connection:
        actions = (
            connection.execute(
                select(audit_events.c.action).order_by(audit_events.c.occurred_at)
            )
            .scalars()
            .all()
        )
    assert actions == [
        "created",
        "edited",
        "completed",
        "reopened",
        "trashed",
        "restored",
    ]


def test_stale_revision_and_trash_filter_are_safe(service):
    task = service.create(
        CreateTaskInput(title="Synthetic task"), "11111111-1111-4111-8111-111111111111"
    )
    service.update(
        task.id,
        UpdateTaskInput(expected_revision=1, details="Updated"),
        "22222222-2222-4222-8222-222222222222",
    )
    with pytest.raises(TaskConflictError):
        service.trash(task.id, 1, "33333333-3333-4333-8333-333333333333")


def test_same_title_tasks_remain_distinct_canonical_records(service):
    first = service.create(
        CreateTaskInput(title="Synthetic duplicate title"),
        "11111111-1111-4111-8111-111111111111",
    )
    second = service.create(
        CreateTaskInput(title="Synthetic duplicate title"),
        "22222222-2222-4222-8222-222222222222",
    )

    assert first.id != second.id
    assert {task.id for task in service.list()} == {first.id, second.id}
    with service.engine.connect() as connection:
        actions = connection.execute(select(audit_events.c.action)).scalars().all()
    assert actions == ["created", "created"]


def test_task_relationships_are_independently_nullable_and_foreign_keys_enforced(
    service,
):
    now = "2030-01-01T00:00:00.000000Z"
    with service.engine.begin() as connection:
        connection.execute(
            insert(goals).values(
                id="11111111-1111-4111-8111-111111111111",
                title="Synthetic goal",
                kind="outcome",
                state="active",
                created_at=now,
                updated_at=now,
                revision=1,
            )
        )
        connection.execute(
            insert(projects).values(
                id="22222222-2222-4222-8222-222222222222",
                title="Synthetic project",
                state="idea",
                created_at=now,
                updated_at=now,
                revision=1,
            )
        )
    task = service.create(
        CreateTaskInput(
            title="Linked",
            goal_id="11111111-1111-4111-8111-111111111111",
            project_id="22222222-2222-4222-8222-222222222222",
        ),
        "33333333-3333-4333-8333-333333333333",
    )
    assert task.goal_id and task.project_id
    with pytest.raises(TaskAssignmentUnavailableError):
        service.create(
            CreateTaskInput(title="Broken", goal_id="not-a-goal"),
            "44444444-4444-4444-8444-444444444444",
        )


def test_sqlite_constraints_reject_invalid_task_state_and_deadline(service):
    with service.engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                insert(tasks).values(
                    id="11111111-1111-4111-8111-111111111111",
                    title="Bad",
                    state="bad",
                    source_kind="human",
                    deadline_kind="none",
                    created_at="2030-01-01T00:00:00.000000Z",
                    updated_at="2030-01-01T00:00:00.000000Z",
                    revision=1,
                )
            )
    with pytest.raises(ValueError, match="deadline"):
        DeadlineInput(kind="date", date="2030-01-01", timezone="America/Los_Angeles")
