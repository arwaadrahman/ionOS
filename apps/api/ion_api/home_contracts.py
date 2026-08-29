from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ion_api.task_contracts import DeadlineInput, TaskState
from ion_api.today_contracts import (
    AttentionReason,
    GoalContextOutput,
    ProjectContextOutput,
    TodayContext,
    TodayRole,
)

CoreEntityType = Literal[
    "area",
    "goal",
    "goal_milestone",
    "project",
    "project_milestone",
    "task",
]
CoreLifecycle = Literal["active", "paused", "completed", "archived", "inactive"]
CoreRelationshipType = Literal[
    "goal_area",
    "project_goal",
    "goal_milestone_goal",
    "project_milestone_project",
    "task_goal",
    "task_project",
]


class CoreNode(BaseModel):
    id: str
    entity_type: CoreEntityType
    label: str
    lifecycle: CoreLifecycle
    today_role: TodayRole | None = None
    attention_reason: AttentionReason | None = None


class CoreEdge(BaseModel):
    source_id: str
    target_id: str
    relationship_type: CoreRelationshipType


class CoreGraph(BaseModel):
    nodes: list[CoreNode]
    edges: list[CoreEdge]


class HomeTaskSummary(BaseModel):
    id: str
    title: str
    state: TaskState
    deadline: DeadlineInput
    goal: GoalContextOutput | None
    project: ProjectContextOutput | None


class HomeAttentionSummary(HomeTaskSummary):
    reason: AttentionReason


class HomeOutput(TodayContext):
    generated_at: str
    core: CoreGraph
    focus: HomeTaskSummary | None
    needs_attention: list[HomeAttentionSummary]
    upcoming: list[HomeTaskSummary]
