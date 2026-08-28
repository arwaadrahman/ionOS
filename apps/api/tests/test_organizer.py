from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from ion_api.db import create_database_engine
from ion_api.migrations import upgrade_to_head
from ion_api.organizer import (
    AssignmentUnavailableError,
    OrganizerConflictError,
    OrganizerService,
    OrganizerValidationError,
    TrashBlockedError,
)
from ion_api.organizer_contracts import (
    AreaCreateInput,
    GoalAreaInput,
    GoalCreateInput,
    MilestoneCreateInput,
    MilestoneStateInput,
    ProjectCreateInput,
    ProjectStateInput,
    ReorderMilestoneItem,
    ReorderMilestonesInput,
)
from ion_api.schema import audit_events, goals
from ion_api.task_contracts import (
    CreateTaskInput,
    SetTaskRelationshipsInput,
    UpdateTaskInput,
)
from ion_api.tasks import TaskAssignmentUnavailableError, TaskService


def command_id() -> str:
    return str(uuid4())


@pytest.fixture
def services(tmp_path):
    database_path = tmp_path / "organizer.sqlite3"
    upgrade_to_head(database_path)
    engine = create_database_engine(database_path)
    return OrganizerService(engine), TaskService(engine)


def test_area_archive_is_local_and_trash_uses_direct_goal_blockers(services):
    organizer, _ = services
    area = organizer.create_area(AreaCreateInput(name="Synthetic Area"), command_id())
    goal = organizer.create_goal(
        GoalCreateInput(title="Synthetic Goal", kind="outcome", area_id=area.id),
        command_id(),
    )

    archived = organizer.archive_area(area.id, area.revision, command_id())
    same_archive = organizer.archive_area(area.id, archived.revision, command_id())
    assert same_archive.revision == archived.revision
    assert organizer.get_goal_detail(goal.id).goal.area_id == area.id
    with pytest.raises(AssignmentUnavailableError):
        organizer.create_goal(
            GoalCreateInput(title="Rejected", kind="outcome", area_id=area.id),
            command_id(),
        )

    active = organizer.unarchive_area(area.id, archived.revision, command_id())
    with organizer.engine.connect() as connection:
        audit_count = connection.scalar(select(func.count()).select_from(audit_events))
    with pytest.raises(TrashBlockedError) as blocked:
        organizer.trash_area(area.id, active.revision, command_id())
    assert blocked.value.blockers == {"goal": 1}
    assert organizer.get_area(area.id).revision == active.revision
    with organizer.engine.connect() as connection:
        assert (
            connection.scalar(select(func.count()).select_from(audit_events))
            == audit_count
        )

    unassigned = organizer.set_goal_area(
        goal.id,
        GoalAreaInput(expected_revision=goal.revision, area_id=None),
        command_id(),
    )
    trashed = organizer.trash_area(area.id, active.revision, command_id())
    restored = organizer.restore_area(area.id, trashed.revision, command_id())
    assert restored.trashed_at is None
    assert unassigned.area_id is None


def test_goal_summary_and_trash_blockers_are_direct_only(services):
    organizer, task_service = services
    goal = organizer.create_goal(
        GoalCreateInput(title="Synthetic Goal", kind="skill"), command_id()
    )
    achieved = organizer.create_goal_milestone(
        goal.id, MilestoneCreateInput(title="Achieved"), command_id()
    )
    achieved = organizer.set_goal_milestone_state(
        achieved.id,
        MilestoneStateInput(expected_revision=achieved.revision, state="achieved"),
        command_id(),
    )
    assert achieved.achieved_at is not None
    reopened_milestone = organizer.set_goal_milestone_state(
        achieved.id,
        MilestoneStateInput(expected_revision=achieved.revision, state="planned"),
        command_id(),
    )
    assert reopened_milestone.achieved_at is None
    organizer.set_goal_milestone_state(
        achieved.id,
        MilestoneStateInput(
            expected_revision=reopened_milestone.revision, state="achieved"
        ),
        command_id(),
    )
    skipped = organizer.create_goal_milestone(
        goal.id, MilestoneCreateInput(title="Skipped"), command_id()
    )
    organizer.set_goal_milestone_state(
        skipped.id,
        MilestoneStateInput(expected_revision=skipped.revision, state="skipped"),
        command_id(),
    )
    project = organizer.create_project(
        ProjectCreateInput(title="Child Project", goal_id=goal.id), command_id()
    )
    direct_task = task_service.create(
        CreateTaskInput(title="Direct Task", goal_id=goal.id), command_id()
    )
    task_service.create(
        CreateTaskInput(title="Project-only Task", project_id=project.id), command_id()
    )

    detail = organizer.get_goal_detail(goal.id)
    assert detail.summary.milestone_total == 1
    assert detail.summary.milestone_achieved == 1
    assert detail.summary.project_total == 1
    assert [task.id for task in detail.direct_tasks] == [direct_task.id]
    assert [task.title for task in detail.project_tasks] == ["Project-only Task"]

    with pytest.raises(TrashBlockedError) as blocked:
        organizer.trash_goal(goal.id, goal.revision, command_id())
    assert blocked.value.blockers == {"milestone": 2, "project": 1, "task": 1}


def test_project_lifecycle_projection_and_activity_attribution(services):
    organizer, task_service = services
    project = organizer.create_project(
        ProjectCreateInput(title="Synthetic Project", state="active"), command_id()
    )
    planned = organizer.create_project_milestone(
        project.id, MilestoneCreateInput(title="Planned"), command_id()
    )
    current = organizer.create_project_milestone(
        project.id, MilestoneCreateInput(title="Current"), command_id()
    )
    current = organizer.set_project_milestone_state(
        current.id,
        MilestoneStateInput(expected_revision=current.revision, state="in_progress"),
        command_id(),
    )
    task = task_service.create(
        CreateTaskInput(title="Next action", project_id=project.id), command_id()
    )
    task_service.update(
        task.id,
        UpdateTaskInput(expected_revision=task.revision, details="Edited"),
        command_id(),
    )

    detail = organizer.get_project_detail(project.id)
    assert detail.current_milestone.id == current.id
    assert [item.id for item in detail.next_actions] == [task.id]
    assert {event.entity_type for event in detail.recent_activity} == {
        "project",
        "project_milestone",
    }
    assert "task" not in {event.entity_type for event in detail.recent_activity}

    planned = organizer.set_project_milestone_state(
        planned.id,
        MilestoneStateInput(expected_revision=planned.revision, state="in_progress"),
        command_id(),
    )
    assert organizer.get_project_detail(project.id).current_milestone.id == planned.id
    same_state = organizer.set_project_milestone_state(
        planned.id,
        MilestoneStateInput(expected_revision=planned.revision, state="in_progress"),
        command_id(),
    )
    assert same_state.revision == planned.revision

    completed = organizer.set_project_state(
        project.id,
        ProjectStateInput(expected_revision=project.revision, state="completed"),
        command_id(),
    )
    assert completed.completed_at is not None
    archived = organizer.archive_project(project.id, completed.revision, command_id())
    assert archived.state == "archived"
    assert archived.archived_at is not None
    assert archived.completed_at == completed.completed_at
    unarchived = organizer.unarchive_project(
        project.id, archived.revision, command_id()
    )
    assert unarchived.state == "completed"
    assert unarchived.completed_at == completed.completed_at
    reopened = organizer.set_project_state(
        project.id,
        ProjectStateInput(expected_revision=unarchived.revision, state="active"),
        command_id(),
    )
    assert reopened.completed_at is None
    with pytest.raises(OrganizerValidationError):
        organizer.archive_project(project.id, reopened.revision, command_id())

    with pytest.raises(TrashBlockedError) as blocked:
        organizer.trash_project(project.id, reopened.revision, command_id())
    assert blocked.value.blockers == {"project_milestone": 2, "task": 1}

    assert planned.position == 0


def test_milestone_order_reserves_trash_slots_and_reorder_is_atomic(services):
    organizer, _ = services
    project = organizer.create_project(
        ProjectCreateInput(title="Ordered Project"), command_id()
    )
    first = organizer.create_project_milestone(
        project.id, MilestoneCreateInput(title="First"), command_id()
    )
    reserved = organizer.create_project_milestone(
        project.id, MilestoneCreateInput(title="Reserved"), command_id()
    )
    third = organizer.create_project_milestone(
        project.id, MilestoneCreateInput(title="Third"), command_id()
    )
    reserved = organizer.trash_project_milestone(
        reserved.id, reserved.revision, command_id()
    )

    reordered = organizer.reorder_project_milestones(
        project.id,
        ReorderMilestonesInput(
            items=[
                ReorderMilestoneItem(id=third.id, expected_revision=third.revision),
                ReorderMilestoneItem(id=first.id, expected_revision=first.revision),
            ]
        ),
        "11111111-1111-4111-8111-111111111111",
    )
    assert [(item.title, item.position) for item in reordered] == [
        ("Third", 0),
        ("First", 2),
    ]
    restored = organizer.restore_project_milestone(
        reserved.id, reserved.revision, command_id()
    )
    assert restored.position == 1
    appended = organizer.create_project_milestone(
        project.id, MilestoneCreateInput(title="Appended"), command_id()
    )
    assert appended.position == 3

    with organizer.engine.connect() as connection:
        reorder_events = connection.execute(
            select(audit_events).where(audit_events.c.action == "reordered")
        ).all()
    assert len(reorder_events) == 2
    assert {event.command_id for event in reorder_events} == {
        "11111111-1111-4111-8111-111111111111"
    }

    before = organizer.list_project_milestones(project.id)
    with pytest.raises(OrganizerConflictError):
        organizer.reorder_project_milestones(
            project.id,
            ReorderMilestonesInput(
                items=[
                    ReorderMilestoneItem(
                        id=appended.id, expected_revision=appended.revision
                    ),
                    ReorderMilestoneItem(id=third.id, expected_revision=1),
                    ReorderMilestoneItem(
                        id=first.id, expected_revision=reordered[1].revision
                    ),
                ]
            ),
            command_id(),
        )
    assert organizer.list_project_milestones(project.id) == before


def test_task_relationships_are_explicit_independent_and_noop_safe(services):
    organizer, task_service = services
    goal = organizer.create_goal(
        GoalCreateInput(title="Relationship Goal", kind="outcome"), command_id()
    )
    project = organizer.create_project(
        ProjectCreateInput(title="Relationship Project"), command_id()
    )
    task = task_service.create(CreateTaskInput(title="Task"), command_id())
    linked = task_service.set_relationships(
        task.id,
        SetTaskRelationshipsInput(
            expected_revision=task.revision,
            goal_id=goal.id,
            project_id=project.id,
        ),
        command_id(),
    )
    edited = task_service.update(
        task.id,
        UpdateTaskInput(expected_revision=linked.revision, title="Edited Task"),
        command_id(),
    )
    assert (edited.goal_id, edited.project_id) == (goal.id, project.id)

    with task_service.engine.connect() as connection:
        audit_count = connection.scalar(select(func.count()).select_from(audit_events))
    unchanged = task_service.set_relationships(
        task.id,
        SetTaskRelationshipsInput(
            expected_revision=edited.revision,
            goal_id=goal.id,
            project_id=project.id,
        ),
        command_id(),
    )
    with task_service.engine.connect() as connection:
        after_noop = connection.scalar(select(func.count()).select_from(audit_events))
    assert unchanged.revision == edited.revision
    assert after_noop == audit_count

    archived_goal = organizer.archive_goal(goal.id, goal.revision, command_id())
    with pytest.raises(TaskAssignmentUnavailableError):
        task_service.set_relationships(
            task.id,
            SetTaskRelationshipsInput(
                expected_revision=unchanged.revision,
                goal_id=archived_goal.id,
                project_id=None,
            ),
            command_id(),
        )
    with organizer.engine.connect() as connection:
        stored_goal = connection.scalar(
            select(goals.c.id).where(goals.c.id == archived_goal.id)
        )
    assert stored_goal == archived_goal.id
