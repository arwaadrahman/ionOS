"""Task domain operations backed by SQLAlchemy Core transactions."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Engine, Select, insert, select, update

from ion_api.schema import audit_events, tasks
from ion_api.task_contracts import (
    CreateTaskInput,
    DeadlineInput,
    TaskOutput,
    UpdateTaskInput,
)


class TaskNotFoundError(LookupError):
    pass


class TaskConflictError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _task_output(row) -> TaskOutput:
    return TaskOutput(
        id=row.id,
        title=row.title,
        details=row.details,
        state=row.state,
        source_kind=row.source_kind,
        importance=row.importance,
        estimated_minutes=row.estimated_minutes,
        progress_percent=row.progress_percent,
        deadline=DeadlineInput(
            kind=row.deadline_kind,
            date=row.deadline_date,
            at=row.deadline_at,
            timezone=row.deadline_timezone,
        ),
        project_id=row.project_id,
        goal_id=row.goal_id,
        completion_evidence=row.completion_evidence,
        completed_at=row.completed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        revision=row.revision,
        trashed_at=row.trashed_at,
    )


def _audit(
    connection,
    *,
    entity_id: str,
    action: str,
    from_revision: int | None,
    to_revision: int | None,
    command_id: str,
) -> None:
    connection.execute(
        insert(audit_events).values(
            event_id=str(uuid4()),
            occurred_at=utc_now(),
            entity_type="task",
            entity_id=entity_id,
            action=action,
            actor_kind="human",
            authority="direct",
            source="desktop",
            from_revision=from_revision,
            to_revision=to_revision,
            command_id=command_id,
        )
    )


def _active_query(trashed: bool) -> Select:
    return select(tasks).where(
        tasks.c.trashed_at.is_not(None) if trashed else tasks.c.trashed_at.is_(None)
    )


class TaskService:
    def __init__(self, engine: Engine):
        self.engine = engine

    def list(self, *, trashed: bool = False) -> list[TaskOutput]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                _active_query(trashed).order_by(tasks.c.updated_at.desc(), tasks.c.id)
            ).all()
        return [_task_output(row) for row in rows]

    def create(self, input: CreateTaskInput, command_id: str) -> TaskOutput:
        now = utc_now()
        task_id = str(uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                insert(tasks).values(
                    id=task_id,
                    title=input.title.strip(),
                    details=input.details,
                    state="open",
                    source_kind="human",
                    importance=input.importance,
                    estimated_minutes=input.estimated_minutes,
                    progress_percent=input.progress_percent,
                    deadline_kind=input.deadline.kind,
                    deadline_date=input.deadline.date,
                    deadline_at=input.deadline.at,
                    deadline_timezone=input.deadline.timezone,
                    project_id=input.project_id,
                    goal_id=input.goal_id,
                    completion_evidence=input.completion_evidence,
                    completed_at=None,
                    created_at=now,
                    updated_at=now,
                    revision=1,
                    trashed_at=None,
                )
            )
            _audit(
                connection,
                entity_id=task_id,
                action="created",
                from_revision=None,
                to_revision=1,
                command_id=command_id,
            )
            row = connection.execute(select(tasks).where(tasks.c.id == task_id)).one()
        return _task_output(row)

    def update(
        self, task_id: str, input: UpdateTaskInput, command_id: str
    ) -> TaskOutput:
        changes = input.model_dump(exclude_unset=True)
        changes.pop("expected_revision")
        deadline = changes.pop("deadline", None)
        if not changes and deadline is None:
            return self._get(task_id, trashed=False)
        if deadline is not None:
            changes.update(
                deadline_kind=deadline["kind"],
                deadline_date=deadline.get("date"),
                deadline_at=deadline.get("at"),
                deadline_timezone=deadline.get("timezone"),
            )
        return self._mutate(
            task_id, input.expected_revision, changes, "edited", command_id
        )

    def complete(
        self, task_id: str, expected_revision: int, command_id: str
    ) -> TaskOutput:
        return self._mutate(
            task_id,
            expected_revision,
            {"state": "completed", "completed_at": utc_now()},
            "completed",
            command_id,
        )

    def reopen(
        self, task_id: str, expected_revision: int, command_id: str
    ) -> TaskOutput:
        return self._mutate(
            task_id,
            expected_revision,
            {"state": "open", "completed_at": None},
            "reopened",
            command_id,
        )

    def trash(
        self, task_id: str, expected_revision: int, command_id: str
    ) -> TaskOutput:
        return self._mutate(
            task_id,
            expected_revision,
            {"trashed_at": utc_now()},
            "trashed",
            command_id,
            require_trashed=False,
        )

    def restore(
        self, task_id: str, expected_revision: int, command_id: str
    ) -> TaskOutput:
        return self._mutate(
            task_id,
            expected_revision,
            {"trashed_at": None},
            "restored",
            command_id,
            require_trashed=True,
        )

    def _get(self, task_id: str, *, trashed: bool | None = None) -> TaskOutput:
        query = select(tasks).where(tasks.c.id == task_id)
        if trashed is True:
            query = query.where(tasks.c.trashed_at.is_not(None))
        if trashed is False:
            query = query.where(tasks.c.trashed_at.is_(None))
        with self.engine.connect() as connection:
            row = connection.execute(query).one_or_none()
        if row is None:
            raise TaskNotFoundError(task_id)
        return _task_output(row)

    def _mutate(
        self,
        task_id: str,
        expected_revision: int,
        changes: dict,
        action: str,
        command_id: str,
        require_trashed: bool | None = None,
    ) -> TaskOutput:
        now = utc_now()
        with self.engine.begin() as connection:
            query = select(tasks).where(tasks.c.id == task_id)
            if require_trashed is True:
                query = query.where(tasks.c.trashed_at.is_not(None))
            elif require_trashed is False:
                query = query.where(tasks.c.trashed_at.is_(None))
            row = connection.execute(query).one_or_none()
            if row is None:
                raise TaskNotFoundError(task_id)
            if row.revision != expected_revision:
                raise TaskConflictError(task_id)
            next_revision = row.revision + 1
            connection.execute(
                update(tasks)
                .where(tasks.c.id == task_id)
                .values(**changes, updated_at=now, revision=next_revision)
            )
            _audit(
                connection,
                entity_id=task_id,
                action=action,
                from_revision=row.revision,
                to_revision=next_revision,
                command_id=command_id,
            )
            updated = connection.execute(
                select(tasks).where(tasks.c.id == task_id)
            ).one()
        return _task_output(updated)
