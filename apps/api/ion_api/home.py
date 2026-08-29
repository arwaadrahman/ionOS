"""Read-only Phase 1D Home projection."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import Engine, select

from ion_api.home_contracts import (
    CoreEdge,
    CoreGraph,
    CoreLifecycle,
    CoreNode,
    HomeAttentionSummary,
    HomeOutput,
    HomeTaskSummary,
)
from ion_api.schema import (
    areas,
    goals,
    milestones,
    project_milestones,
    projects,
    task_day_plans,
    tasks,
)
from ion_api.today import TodayService
from ion_api.today_contracts import TodayContext, TodayTaskOutput

ENTITY_ORDER = {
    "area": 0,
    "goal": 1,
    "project": 2,
    "goal_milestone": 3,
    "project_milestone": 4,
    "task": 5,
}
RELATIONSHIP_ORDER = {
    "goal_area": 0,
    "project_goal": 1,
    "goal_milestone_goal": 2,
    "project_milestone_project": 3,
    "task_goal": 4,
    "task_project": 5,
}


def _summary(item: TodayTaskOutput) -> HomeTaskSummary:
    return HomeTaskSummary(
        id=item.task.id,
        title=item.task.title,
        state=item.task.state,
        deadline=item.task.deadline,
        goal=item.goal,
        project=item.project,
    )


def _goal_lifecycle(row) -> CoreLifecycle:
    if row.archived_at is not None:
        return "archived"
    return {"active": "active", "paused": "paused", "achieved": "completed"}.get(
        row.state, "inactive"
    )


def _project_lifecycle(row) -> CoreLifecycle:
    if row.archived_at is not None or row.state == "archived":
        return "archived"
    if row.state == "paused":
        return "paused"
    if row.state == "completed":
        return "completed"
    if row.state == "abandoned":
        return "inactive"
    return "active"


def _milestone_lifecycle(row) -> CoreLifecycle:
    return {"achieved": "completed", "skipped": "inactive"}.get(row.state, "active")


def _task_lifecycle(row) -> CoreLifecycle:
    return {
        "open": "active",
        "in_progress": "active",
        "paused": "paused",
        "completed": "completed",
        "canceled": "inactive",
    }[row.state]


class HomeService:
    def __init__(
        self,
        engine: Engine,
        clock: Callable[[], datetime] | None = None,
    ):
        self.engine = engine
        self.today = TodayService(engine, clock)

    def get_home(self, context: TodayContext) -> HomeOutput:
        with self.engine.connect() as connection:
            today = self.today.project(connection, context)
            core = self._core(connection, context, today)

        focus_item = today.plan.priorities[0] if today.plan.priorities else None
        focus = _summary(focus_item) if focus_item is not None else None
        attention = [
            HomeAttentionSummary(**_summary(item).model_dump(), reason=item.reason)
            for item in today.needs_attention[:3]
        ]
        used_ids = {item.id for item in attention}
        if focus is not None:
            used_ids.add(focus.id)
        upcoming: list[HomeTaskSummary] = []
        for item in [*today.deadlines.due_today, *today.deadlines.approaching]:
            if item.task.id in used_ids:
                continue
            upcoming.append(_summary(item))
            used_ids.add(item.task.id)
            if len(upcoming) == 3:
                break
        return HomeOutput(
            planning_date=today.planning_date,
            timezone=today.timezone,
            generated_at=today.generated_at,
            core=core,
            focus=focus,
            needs_attention=attention,
            upcoming=upcoming,
        )

    @staticmethod
    def _core(connection, context: TodayContext, today) -> CoreGraph:
        area_rows = connection.execute(
            select(areas).where(areas.c.trashed_at.is_(None))
        ).all()
        goal_rows = connection.execute(
            select(goals).where(goals.c.trashed_at.is_(None))
        ).all()
        project_rows = connection.execute(
            select(projects).where(projects.c.trashed_at.is_(None))
        ).all()
        goal_milestone_rows = connection.execute(
            select(milestones).where(milestones.c.trashed_at.is_(None))
        ).all()
        project_milestone_rows = connection.execute(
            select(project_milestones).where(project_milestones.c.trashed_at.is_(None))
        ).all()
        task_rows = connection.execute(
            select(tasks).where(tasks.c.trashed_at.is_(None))
        ).all()
        plan_rows = connection.execute(
            select(task_day_plans).where(
                task_day_plans.c.planning_date == context.planning_date.isoformat()
            )
        ).all()
        today_roles = {row.task_id: row.role for row in plan_rows}
        attention = {item.task.id: item.reason for item in today.needs_attention}

        nodes = [
            *[
                CoreNode(
                    id=row.id,
                    entity_type="area",
                    label=row.name,
                    lifecycle="archived" if row.archived_at else "active",
                )
                for row in area_rows
            ],
            *[
                CoreNode(
                    id=row.id,
                    entity_type="goal",
                    label=row.title,
                    lifecycle=_goal_lifecycle(row),
                )
                for row in goal_rows
            ],
            *[
                CoreNode(
                    id=row.id,
                    entity_type="project",
                    label=row.title,
                    lifecycle=_project_lifecycle(row),
                )
                for row in project_rows
            ],
            *[
                CoreNode(
                    id=row.id,
                    entity_type="goal_milestone",
                    label=row.title,
                    lifecycle=_milestone_lifecycle(row),
                )
                for row in goal_milestone_rows
            ],
            *[
                CoreNode(
                    id=row.id,
                    entity_type="project_milestone",
                    label=row.title,
                    lifecycle=_milestone_lifecycle(row),
                )
                for row in project_milestone_rows
            ],
            *[
                CoreNode(
                    id=row.id,
                    entity_type="task",
                    label=row.title,
                    lifecycle=_task_lifecycle(row),
                    today_role=today_roles.get(row.id),
                    attention_reason=attention.get(row.id),
                )
                for row in task_rows
            ],
        ]
        node_ids = {node.id for node in nodes}
        edges: list[CoreEdge] = []

        def add(source_id, target_id, relationship_type):
            if source_id in node_ids and target_id in node_ids:
                edges.append(
                    CoreEdge(
                        source_id=source_id,
                        target_id=target_id,
                        relationship_type=relationship_type,
                    )
                )

        for row in goal_rows:
            if row.area_id is not None:
                add(row.id, row.area_id, "goal_area")
        for row in project_rows:
            if row.goal_id is not None:
                add(row.id, row.goal_id, "project_goal")
        for row in goal_milestone_rows:
            add(row.id, row.goal_id, "goal_milestone_goal")
        for row in project_milestone_rows:
            add(row.id, row.project_id, "project_milestone_project")
        for row in task_rows:
            if row.goal_id is not None:
                add(row.id, row.goal_id, "task_goal")
            if row.project_id is not None:
                add(row.id, row.project_id, "task_project")

        nodes.sort(key=lambda node: (ENTITY_ORDER[node.entity_type], node.id))
        edges.sort(
            key=lambda edge: (
                RELATIONSHIP_ORDER[edge.relationship_type],
                edge.source_id,
                edge.target_id,
            )
        )
        return CoreGraph(nodes=nodes, edges=edges)
