from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ion_api.task_contracts import TaskOutput

GoalKind = Literal["outcome", "skill", "habit", "project", "academic", "personal"]
GoalState = Literal["active", "paused", "achieved", "retired"]
ProjectState = Literal[
    "idea",
    "exploring",
    "planned",
    "active",
    "paused",
    "completed",
    "archived",
    "abandoned",
]
MilestoneState = Literal["planned", "in_progress", "achieved", "skipped"]
ListView = Literal["active", "archived", "trash", "all"]


class RevisionInput(BaseModel):
    expected_revision: int = Field(ge=1)


class AreaCreateInput(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None


class AreaUpdateInput(RevisionInput):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None


class AreaOutput(BaseModel):
    id: str
    name: str
    description: str | None
    archived_at: str | None
    created_at: str
    updated_at: str
    revision: int
    trashed_at: str | None


class GoalCreateInput(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    kind: GoalKind
    area_id: str | None = None


class GoalUpdateInput(RevisionInput):
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    kind: GoalKind | None = None


class GoalStateInput(RevisionInput):
    state: GoalState


class GoalAreaInput(RevisionInput):
    area_id: str | None = None


class GoalOutput(BaseModel):
    id: str
    area_id: str | None
    title: str
    description: str | None
    kind: GoalKind
    state: GoalState
    archived_at: str | None
    created_at: str
    updated_at: str
    revision: int
    trashed_at: str | None


class AreaDetail(BaseModel):
    area: AreaOutput
    goals: list[GoalOutput]


class MilestoneCreateInput(BaseModel):
    title: str = Field(min_length=1)
    target_date: str | None = None

    @field_validator("target_date")
    @classmethod
    def date_only(cls, value: str | None) -> str | None:
        if value is not None:
            date.fromisoformat(value)
        return value


class MilestoneUpdateInput(RevisionInput):
    title: str | None = Field(default=None, min_length=1)
    target_date: str | None = None

    @field_validator("target_date")
    @classmethod
    def date_only(cls, value: str | None) -> str | None:
        if value is not None:
            date.fromisoformat(value)
        return value


class MilestoneStateInput(RevisionInput):
    state: MilestoneState


class ReorderMilestoneItem(BaseModel):
    id: str
    expected_revision: int = Field(ge=1)


class ReorderMilestonesInput(BaseModel):
    items: list[ReorderMilestoneItem]


class MilestoneOutput(BaseModel):
    id: str
    title: str
    state: MilestoneState
    target_date: str | None
    achieved_at: str | None
    position: int
    created_at: str
    updated_at: str
    revision: int
    trashed_at: str | None


class GoalMilestoneOutput(MilestoneOutput):
    goal_id: str


class ProjectMilestoneOutput(MilestoneOutput):
    project_id: str


class GoalSummary(BaseModel):
    milestone_total: int
    milestone_achieved: int
    project_total: int
    task_total: int
    task_completed: int


class GoalDetail(BaseModel):
    goal: GoalOutput
    summary: GoalSummary
    milestones: list[GoalMilestoneOutput]
    projects: list[ProjectOutput]
    direct_tasks: list[TaskOutput]
    project_tasks: list[TaskOutput]


class ProjectCreateInput(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    state: ProjectState = "idea"
    goal_id: str | None = None


class ProjectUpdateInput(RevisionInput):
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None


class ProjectStateInput(RevisionInput):
    state: ProjectState


class ProjectGoalInput(RevisionInput):
    goal_id: str | None = None


class ProjectOutput(BaseModel):
    id: str
    goal_id: str | None
    title: str
    description: str | None
    state: ProjectState
    completed_at: str | None
    archived_at: str | None
    created_at: str
    updated_at: str
    revision: int
    trashed_at: str | None


class ProjectSummary(BaseModel):
    milestone_total: int
    milestone_achieved: int
    task_total: int
    task_completed: int


class ActivityOutput(BaseModel):
    event_id: str
    occurred_at: str
    entity_type: str
    entity_id: str
    action: str
    from_revision: int | None
    to_revision: int | None
    command_id: str


RecoveryEntityType = Literal[
    "area",
    "goal",
    "goal_milestone",
    "project",
    "project_milestone",
    "task",
]


class RecoveryItemOutput(BaseModel):
    entity_type: RecoveryEntityType
    entity_id: str
    label: str
    lifecycle: str
    revision: int
    trashed_at: str
    owner_label: str | None


class RecoveryActivityOutput(BaseModel):
    event_id: str
    occurred_at: str
    entity_type: RecoveryEntityType
    entity_id: str
    label: str
    action: str
    authority: Literal["direct"]


class RecoveryOutput(BaseModel):
    trash: list[RecoveryItemOutput]
    recent_activity: list[RecoveryActivityOutput]


class ProjectDetail(BaseModel):
    project: ProjectOutput
    summary: ProjectSummary
    milestones: list[ProjectMilestoneOutput]
    current_milestone: ProjectMilestoneOutput | None
    tasks: list[TaskOutput]
    next_actions: list[TaskOutput]
    recent_activity: list[ActivityOutput]


class BlockerOutput(BaseModel):
    entity: str
    count: int


class ProductErrorOutput(BaseModel):
    code: Literal[
        "not_found",
        "revision_conflict",
        "validation",
        "assignment_unavailable",
        "trash_blocked",
        "unavailable",
    ]
    blockers: list[BlockerOutput] = Field(default_factory=list)


GoalDetail.model_rebuild()
