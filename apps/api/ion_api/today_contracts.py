from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from ion_api.task_contracts import TaskOutput

TodayRole = Literal["priority", "planned", "backup"]
AttentionReason = Literal[
    "overdue",
    "due_today",
    "high_importance_approaching",
    "in_progress_not_planned",
]


class TodayContext(BaseModel):
    planning_date: date
    timezone: str = Field(min_length=1, max_length=255)


class AddTaskToTodayInput(TodayContext):
    task_id: str = Field(min_length=1, max_length=36)
    role: TodayRole


class RemoveTaskFromTodayInput(TodayContext):
    expected_revision: int = Field(ge=1)


class SetTodayRoleInput(RemoveTaskFromTodayInput):
    role: TodayRole


class ReorderTodayItem(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    expected_revision: int = Field(ge=1)


class ReorderTodayTasksInput(TodayContext):
    role: TodayRole
    items: list[ReorderTodayItem]


class DayPlanOutput(BaseModel):
    id: str
    task_id: str
    planning_date: date
    role: TodayRole
    position: int
    created_at: str
    updated_at: str
    revision: int


class GoalContextOutput(BaseModel):
    id: str
    title: str
    state: str
    archived_at: str | None


class ProjectContextOutput(BaseModel):
    id: str
    title: str
    state: str
    archived_at: str | None


class TodayTaskOutput(BaseModel):
    task: TaskOutput
    goal: GoalContextOutput | None
    project: ProjectContextOutput | None


class TodayPlanItemOutput(TodayTaskOutput):
    plan: DayPlanOutput


class AttentionItemOutput(TodayTaskOutput):
    reason: AttentionReason


class CompletedTodayItemOutput(TodayTaskOutput):
    plan: DayPlanOutput | None


class TodayPlanSections(BaseModel):
    priorities: list[TodayPlanItemOutput]
    planned: list[TodayPlanItemOutput]
    backups: list[TodayPlanItemOutput]


class TodayDeadlineSections(BaseModel):
    overdue: list[TodayTaskOutput]
    due_today: list[TodayTaskOutput]
    approaching: list[TodayTaskOutput]


class TodayOutput(BaseModel):
    planning_date: date
    timezone: str
    generated_at: str
    plan: TodayPlanSections
    deadlines: TodayDeadlineSections
    needs_attention: list[AttentionItemOutput]
    unfinished_from_yesterday: list[TodayPlanItemOutput]
    completed_today: list[CompletedTodayItemOutput]
