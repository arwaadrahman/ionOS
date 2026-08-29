from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select

from ion_api.db import create_database_engine
from ion_api.home import HomeService
from ion_api.migrations import upgrade_to_head
from ion_api.organizer import OrganizerService
from ion_api.organizer_contracts import (
    AreaCreateInput,
    GoalCreateInput,
    MilestoneCreateInput,
    ProjectCreateInput,
)
from ion_api.schema import audit_events
from ion_api.task_contracts import CreateTaskInput, DeadlineInput
from ion_api.tasks import TaskService
from ion_api.today import TodayService
from ion_api.today_contracts import AddTaskToTodayInput, TodayContext

NOW = datetime(2030, 3, 10, 9, 30, tzinfo=UTC)
CONTEXT = TodayContext(planning_date="2030-03-10", timezone="America/Los_Angeles")


def command() -> str:
    return str(uuid4())


def test_home_projection_is_deterministic_read_only_and_reuses_today(tmp_path):
    database_path = tmp_path / "home.sqlite3"
    upgrade_to_head(database_path)
    engine = create_database_engine(database_path)
    organizer = OrganizerService(engine)
    task_service = TaskService(engine)
    today_service = TodayService(engine, lambda: NOW)
    home_service = HomeService(engine, lambda: NOW)

    area = organizer.create_area(AreaCreateInput(name="Synthetic Area"), command())
    goal = organizer.create_goal(
        GoalCreateInput(title="Synthetic Goal", kind="outcome", area_id=area.id),
        command(),
    )
    goal_milestone = organizer.create_goal_milestone(
        goal.id, MilestoneCreateInput(title="Goal checkpoint"), command()
    )
    project = organizer.create_project(
        ProjectCreateInput(title="Synthetic Project", state="active", goal_id=goal.id),
        command(),
    )
    project_milestone = organizer.create_project_milestone(
        project.id, MilestoneCreateInput(title="Project checkpoint"), command()
    )
    focus = task_service.create(
        CreateTaskInput(title="Focus", goal_id=goal.id, project_id=project.id),
        command(),
    )
    attention = task_service.create(
        CreateTaskInput(
            title="Attention",
            deadline=DeadlineInput(kind="date", date="2030-03-09"),
        ),
        command(),
    )
    upcoming = task_service.create(
        CreateTaskInput(
            title="Upcoming",
            deadline=DeadlineInput(kind="date", date="2030-03-10"),
        ),
        command(),
    )
    today_service.add_task(
        AddTaskToTodayInput(**CONTEXT.model_dump(), task_id=focus.id, role="priority"),
        command(),
    )
    today_service.add_task(
        AddTaskToTodayInput(
            **CONTEXT.model_dump(), task_id=upcoming.id, role="planned"
        ),
        command(),
    )
    trashed = task_service.create(CreateTaskInput(title="Trashed"), command())
    task_service.trash(trashed.id, trashed.revision, command())

    with engine.connect() as connection:
        audit_count = connection.scalar(select(func.count()).select_from(audit_events))
    first = home_service.get_home(CONTEXT)
    second = home_service.get_home(CONTEXT)
    with engine.connect() as connection:
        assert (
            connection.scalar(select(func.count()).select_from(audit_events))
            == audit_count
        )

    assert first == second
    assert first.focus is not None and first.focus.id == focus.id
    assert [item.id for item in first.needs_attention] == [attention.id]
    assert [item.id for item in first.upcoming] == [upcoming.id]
    node_by_id = {node.id: node for node in first.core.nodes}
    assert trashed.id not in node_by_id
    assert node_by_id[focus.id].today_role == "priority"
    assert node_by_id[attention.id].attention_reason == "overdue"
    assert {node.entity_type for node in first.core.nodes} == {
        "area",
        "goal",
        "goal_milestone",
        "project",
        "project_milestone",
        "task",
    }
    assert {
        (edge.source_id, edge.target_id, edge.relationship_type)
        for edge in first.core.edges
    } >= {
        (goal.id, area.id, "goal_area"),
        (project.id, goal.id, "project_goal"),
        (goal_milestone.id, goal.id, "goal_milestone_goal"),
        (
            project_milestone.id,
            project.id,
            "project_milestone_project",
        ),
        (focus.id, goal.id, "task_goal"),
        (focus.id, project.id, "task_project"),
    }
    assert first.core.nodes == sorted(
        first.core.nodes,
        key=lambda node: (
            [
                "area",
                "goal",
                "project",
                "goal_milestone",
                "project_milestone",
                "task",
            ].index(node.entity_type),
            node.id,
        ),
    )


def test_home_empty_database_has_explicit_empty_projection(tmp_path):
    database_path = tmp_path / "empty-home.sqlite3"
    upgrade_to_head(database_path)
    engine = create_database_engine(database_path)
    output = HomeService(engine, lambda: NOW).get_home(CONTEXT)
    assert output.core.nodes == []
    assert output.core.edges == []
    assert output.focus is None
    assert output.needs_attention == []
    assert output.upcoming == []
