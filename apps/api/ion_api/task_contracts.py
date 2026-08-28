from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

TaskState = Literal["open", "in_progress", "paused", "completed", "canceled"]
Importance = Literal["low", "normal", "high"]


class DeadlineInput(BaseModel):
    kind: Literal["none", "date", "instant"] = "none"
    date: str | None = None
    at: str | None = None
    timezone: str | None = None

    @model_validator(mode="after")
    def valid_union(self) -> DeadlineInput:
        valid = (
            (
                self.kind == "none"
                and self.date is None
                and self.at is None
                and self.timezone is None
            )
            or (
                self.kind == "date"
                and self.date is not None
                and self.at is None
                and self.timezone is None
            )
            or (
                self.kind == "instant"
                and self.date is None
                and self.at is not None
                and self.timezone is not None
            )
        )
        if not valid:
            raise ValueError("deadline fields do not match deadline kind")
        return self


class CreateTaskInput(BaseModel):
    title: str = Field(min_length=1)
    details: str | None = None
    importance: Importance | None = None
    estimated_minutes: int | None = Field(default=None, ge=0)
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    deadline: DeadlineInput = Field(default_factory=DeadlineInput)
    project_id: str | None = None
    goal_id: str | None = None
    completion_evidence: str | None = None


class UpdateTaskInput(BaseModel):
    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1)
    details: str | None = None
    importance: Importance | None = None
    estimated_minutes: int | None = Field(default=None, ge=0)
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    deadline: DeadlineInput | None = None
    project_id: str | None = None
    goal_id: str | None = None
    completion_evidence: str | None = None


class RevisionInput(BaseModel):
    expected_revision: int = Field(ge=1)


class TaskOutput(BaseModel):
    id: str
    title: str
    details: str | None
    state: TaskState
    source_kind: str
    importance: Importance | None
    estimated_minutes: int | None
    progress_percent: int | None
    deadline: DeadlineInput
    project_id: str | None
    goal_id: str | None
    completion_evidence: str | None
    completed_at: str | None
    created_at: str
    updated_at: str
    revision: int
    trashed_at: str | None
