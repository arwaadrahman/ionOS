from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from ion_api.db import create_database_engine
from ion_api.migrations import upgrade_to_head
from ion_api.schema import audit_events, goals, projects, task_day_plans, tasks
from ion_api.task_contracts import CreateTaskInput, DeadlineInput
from ion_api.tasks import TaskService
from ion_api.today import TodayConflictError, TodayService, TodayValidationError
from ion_api.today_contracts import (
    AddTaskToTodayInput,
    ReorderTodayItem,
    ReorderTodayTasksInput,
    SetTodayRoleInput,
    TodayContext,
)

NOW = datetime(2030, 3, 10, 9, 30, tzinfo=UTC)
CONTEXT = TodayContext(planning_date="2030-03-10", timezone="America/Los_Angeles")


@pytest.fixture
def services(tmp_path):
    database_path = tmp_path / "today.sqlite3"
    upgrade_to_head(database_path)
    engine = create_database_engine(database_path)
    return TaskService(engine), TodayService(engine, lambda: NOW)


def command(index: int) -> str:
    return f"00000000-0000-4000-8000-{index:012d}"


def add(today, task_id, role="planned", index=1):
    return today.add_task(
        AddTaskToTodayInput(**CONTEXT.model_dump(), task_id=task_id, role=role),
        command(index),
    )


def test_today_membership_roles_revisions_and_task_independence(services):
    task_service, today = services
    task = task_service.create(CreateTaskInput(title="Synthetic"), command(1))
    added = add(today, task.id, "priority", 2)
    plan = added.plan.priorities[0].plan
    assert task_service.list()[0].revision == task.revision

    moved = today.set_role(
        plan.id,
        SetTodayRoleInput(
            **CONTEXT.model_dump(), expected_revision=plan.revision, role="backup"
        ),
        command(3),
    )
    moved_plan = moved.plan.backups[0].plan
    assert moved_plan.position == 0
    assert moved_plan.revision == 2
    assert task_service.list()[0].revision == task.revision

    with pytest.raises(IntegrityError):
        add(today, task.id, "planned", 4)
    removed = today.remove_task(
        moved_plan.id,
        SetTodayRoleInput(
            **CONTEXT.model_dump(),
            expected_revision=moved_plan.revision,
            role="backup",
        ),
        command(5),
    )
    assert removed.plan.backups == []
    readded = add(today, task.id, "backup", 6)
    assert readded.plan.backups[0].plan.id != moved_plan.id
    with today.engine.connect() as connection:
        events = connection.execute(
            select(audit_events).where(audit_events.c.entity_type == "task_day_plan")
        ).all()
    assert sorted(event.action for event in events) == sorted(
        [
            "added_to_today",
            "added_to_today",
            "today_role_changed",
            "removed_from_today",
        ]
    )
    added_events = [event for event in events if event.action == "added_to_today"]
    removed_event = next(
        event for event in events if event.action == "removed_from_today"
    )
    assert all(
        event.from_revision is None and event.to_revision == 1 for event in added_events
    )
    assert removed_event.from_revision == 2 and removed_event.to_revision is None


def test_reorder_reserves_completed_slots_and_is_atomic(services):
    task_service, today = services
    first = task_service.create(CreateTaskInput(title="First"), command(1))
    hidden = task_service.create(CreateTaskInput(title="Hidden"), command(2))
    third = task_service.create(CreateTaskInput(title="Third"), command(3))
    response = add(today, first.id, "priority", 4)
    response = add(today, hidden.id, "priority", 5)
    response = add(today, third.id, "priority", 6)
    plans = {item.task.id: item.plan for item in response.plan.priorities}
    with today.engine.begin() as connection:
        connection.execute(
            update(tasks)
            .where(tasks.c.id == hidden.id)
            .values(
                state="completed",
                completed_at="2030-03-10T10:00:00Z",
                revision=hidden.revision + 1,
            )
        )
    current = today.get_today(CONTEXT)
    assert [item.plan.position for item in current.plan.priorities] == [0, 2]
    reordered = today.reorder(
        ReorderTodayTasksInput(
            **CONTEXT.model_dump(),
            role="priority",
            items=[
                ReorderTodayItem(
                    id=plans[third.id].id,
                    expected_revision=plans[third.id].revision,
                ),
                ReorderTodayItem(
                    id=plans[first.id].id,
                    expected_revision=plans[first.id].revision,
                ),
            ],
        ),
        command(7),
    )
    assert [
        (item.task.title, item.plan.position) for item in reordered.plan.priorities
    ] == [
        ("Third", 0),
        ("First", 2),
    ]
    assert reordered.completed_today[0].plan.position == 1
    with today.engine.connect() as connection:
        reorder_events = connection.execute(
            select(audit_events).where(audit_events.c.action == "today_reordered")
        ).all()
    assert len(reorder_events) == 2
    assert len({event.command_id for event in reorder_events}) == 1
    with pytest.raises(TodayConflictError):
        today.reorder(
            ReorderTodayTasksInput(
                **CONTEXT.model_dump(),
                role="priority",
                items=[ReorderTodayItem(id=plans[first.id].id, expected_revision=1)],
            ),
            command(8),
        )
    assert today.get_today(CONTEXT) == reordered


def test_deadlines_attention_yesterday_and_related_context(services):
    task_service, today = services
    with today.engine.begin() as connection:
        connection.execute(
            insert(goals).values(
                id="11111111-1111-4111-8111-111111111111",
                title="Archived Goal",
                kind="outcome",
                state="active",
                archived_at=None,
                created_at="2030-01-01T00:00:00Z",
                updated_at="2030-01-01T00:00:00Z",
                revision=1,
            )
        )
        connection.execute(
            insert(projects).values(
                id="22222222-2222-4222-8222-222222222222",
                title="Archived Project",
                state="active",
                archived_at=None,
                created_at="2030-01-01T00:00:00Z",
                updated_at="2030-01-01T00:00:00Z",
                revision=1,
            )
        )
    overdue = task_service.create(
        CreateTaskInput(
            title="Overdue",
            deadline=DeadlineInput(kind="date", date="2030-03-09"),
            goal_id="11111111-1111-4111-8111-111111111111",
            project_id="22222222-2222-4222-8222-222222222222",
        ),
        command(1),
    )
    due = task_service.create(
        CreateTaskInput(
            title="Due exact",
            deadline=DeadlineInput(
                kind="instant",
                at="2030-03-10T10:30:00Z",
                timezone="UTC",
            ),
        ),
        command(2),
    )
    approaching = task_service.create(
        CreateTaskInput(
            title="Approaching high",
            importance="high",
            deadline=DeadlineInput(kind="date", date="2030-03-17"),
        ),
        command(3),
    )
    in_progress = task_service.create(CreateTaskInput(title="In progress"), command(4))
    ignored = task_service.create(
        CreateTaskInput(title="High without date", importance="high"), command(5)
    )
    with today.engine.begin() as connection:
        connection.execute(
            update(goals)
            .where(goals.c.id == overdue.goal_id)
            .values(archived_at="2030-01-01T00:00:00Z")
        )
        connection.execute(
            update(projects)
            .where(projects.c.id == overdue.project_id)
            .values(state="archived", archived_at="2030-01-01T00:00:00Z")
        )
        connection.execute(
            update(tasks)
            .where(tasks.c.id == in_progress.id)
            .values(state="in_progress")
        )
        connection.execute(
            insert(task_day_plans).values(
                id="33333333-3333-4333-8333-333333333333",
                task_id=ignored.id,
                planning_date="2030-03-09",
                role="backup",
                position=0,
                created_at="2030-03-09T08:00:00Z",
                updated_at="2030-03-09T08:00:00Z",
                revision=1,
            )
        )
    output = today.get_today(CONTEXT)
    assert [item.task.id for item in output.deadlines.overdue] == [overdue.id]
    assert [item.task.id for item in output.deadlines.due_today] == [due.id]
    assert [item.task.id for item in output.deadlines.approaching] == [approaching.id]
    assert [item.reason for item in output.needs_attention] == [
        "overdue",
        "due_today",
        "high_importance_approaching",
        "in_progress_not_planned",
    ]
    assert output.deadlines.overdue[0].goal.archived_at is not None
    assert output.deadlines.overdue[0].project.archived_at is not None
    assert output.unfinished_from_yesterday[0].task.id == ignored.id


def test_visibility_eligibility_and_context_validation(services):
    task_service, today = services
    paused = task_service.create(CreateTaskInput(title="Paused"), command(1))
    completed = task_service.create(CreateTaskInput(title="Completed"), command(2))
    canceled = task_service.create(CreateTaskInput(title="Canceled"), command(3))
    trashed = task_service.create(CreateTaskInput(title="Trashed"), command(4))
    with today.engine.begin() as connection:
        connection.execute(
            update(tasks).where(tasks.c.id == paused.id).values(state="paused")
        )
        connection.execute(
            update(tasks)
            .where(tasks.c.id == completed.id)
            .values(state="completed", completed_at="2030-03-10T10:00:00Z")
        )
        connection.execute(
            update(tasks).where(tasks.c.id == canceled.id).values(state="canceled")
        )
        connection.execute(
            update(tasks)
            .where(tasks.c.id == trashed.id)
            .values(trashed_at="2030-03-10T10:00:00Z")
        )
    assert add(today, paused.id).plan.planned[0].task.state == "paused"
    for task in (completed, canceled, trashed):
        with pytest.raises(TodayValidationError):
            add(today, task.id)
    with pytest.raises(TodayValidationError):
        today.get_today(
            TodayContext(planning_date="2030-03-09", timezone=CONTEXT.timezone)
        )
    with pytest.raises(TodayValidationError):
        today.get_today(TodayContext(planning_date="2030-03-10", timezone="Mars/Base"))
    with pytest.raises(ValueError):
        TodayContext(planning_date="2030-02-30", timezone="UTC")


def test_existing_membership_survives_complete_reopen_trash_restore_and_cancel(
    services,
):
    task_service, today = services
    task = task_service.create(CreateTaskInput(title="Lifecycle"), command(1))
    added = add(today, task.id, "planned", 2)
    original_plan = added.plan.planned[0].plan
    with today.engine.begin() as connection:
        connection.execute(
            update(tasks)
            .where(tasks.c.id == task.id)
            .values(state="completed", completed_at="2030-03-10T10:00:00Z")
        )
    completed = today.get_today(CONTEXT)
    assert completed.plan.planned == []
    assert completed.completed_today[0].plan == original_plan

    with today.engine.begin() as connection:
        connection.execute(
            update(tasks)
            .where(tasks.c.id == task.id)
            .values(state="open", completed_at=None)
        )
    assert today.get_today(CONTEXT).plan.planned[0].plan == original_plan

    with today.engine.begin() as connection:
        connection.execute(
            update(tasks)
            .where(tasks.c.id == task.id)
            .values(trashed_at="2030-03-10T11:00:00Z")
        )
    assert today.get_today(CONTEXT).plan.planned == []
    with today.engine.begin() as connection:
        connection.execute(
            update(tasks).where(tasks.c.id == task.id).values(trashed_at=None)
        )
    assert today.get_today(CONTEXT).plan.planned[0].plan == original_plan

    with today.engine.begin() as connection:
        connection.execute(
            update(tasks).where(tasks.c.id == task.id).values(state="canceled")
        )
    assert today.get_today(CONTEXT).plan.planned == []
    with today.engine.begin() as connection:
        connection.execute(
            update(tasks).where(tasks.c.id == task.id).values(state="open")
        )
        assert (
            connection.execute(
                select(task_day_plans).where(task_day_plans.c.task_id == task.id)
            )
            .one()
            .id
            == original_plan.id
        )
    assert today.get_today(CONTEXT).plan.planned[0].plan == original_plan


def test_exact_approaching_window_excludes_start_of_local_day_eight(services):
    task_service, today = services
    inside = task_service.create(
        CreateTaskInput(
            title="Last second of day seven",
            deadline=DeadlineInput(
                kind="instant",
                at="2030-03-18T06:59:59Z",
                timezone="America/Los_Angeles",
            ),
        ),
        command(1),
    )
    outside = task_service.create(
        CreateTaskInput(
            title="Start of day eight",
            deadline=DeadlineInput(
                kind="instant",
                at="2030-03-18T07:00:00Z",
                timezone="America/Los_Angeles",
            ),
        ),
        command(2),
    )
    approaching_ids = {
        item.task.id for item in today.get_today(CONTEXT).deadlines.approaching
    }
    assert inside.id in approaching_ids
    assert outside.id not in approaching_ids


@pytest.mark.parametrize(
    ("now", "planning_date", "due_at", "outside_at"),
    [
        (
            datetime(2030, 3, 10, 9, 30, tzinfo=UTC),
            "2030-03-10",
            "2030-03-11T06:59:59Z",
            "2030-03-11T07:00:00Z",
        ),
        (
            datetime(2030, 11, 3, 8, 30, tzinfo=UTC),
            "2030-11-03",
            "2030-11-04T07:59:59Z",
            "2030-11-04T08:00:00Z",
        ),
    ],
)
def test_dst_day_boundaries_use_local_midnight(
    tmp_path, now, planning_date, due_at, outside_at
):
    database_path = tmp_path / "dst.sqlite3"
    upgrade_to_head(database_path)
    engine = create_database_engine(database_path)
    tasks_service = TaskService(engine)
    today = TodayService(engine, lambda: now)
    due = tasks_service.create(
        CreateTaskInput(
            title="Inside local day",
            deadline=DeadlineInput(kind="instant", at=due_at, timezone="UTC"),
        ),
        command(1),
    )
    outside = tasks_service.create(
        CreateTaskInput(
            title="Outside local day",
            deadline=DeadlineInput(kind="instant", at=outside_at, timezone="UTC"),
        ),
        command(2),
    )
    output = today.get_today(
        TodayContext(planning_date=planning_date, timezone="America/Los_Angeles")
    )
    assert [item.task.id for item in output.deadlines.due_today] == [due.id]
    assert [item.task.id for item in output.deadlines.approaching] == [outside.id]
