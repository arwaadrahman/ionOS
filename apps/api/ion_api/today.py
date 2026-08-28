"""Deterministic Today planning and projection operations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Engine, delete, func, insert, select, update

from ion_api.schema import (
    audit_events,
    goals,
    projects,
    task_day_plans,
    tasks,
)
from ion_api.tasks import _task_output
from ion_api.today_contracts import (
    AddTaskToTodayInput,
    AttentionItemOutput,
    CompletedTodayItemOutput,
    DayPlanOutput,
    GoalContextOutput,
    ProjectContextOutput,
    ReorderTodayTasksInput,
    SetTodayRoleInput,
    TodayContext,
    TodayDeadlineSections,
    TodayOutput,
    TodayPlanItemOutput,
    TodayPlanSections,
    TodayRole,
    TodayTaskOutput,
)

VISIBLE_STATES = {"open", "in_progress", "paused"}
ROLE_ORDER = {"priority": 0, "planned": 1, "backup": 2}
IMPORTANCE_ORDER = {"high": 0, "normal": 1, "low": 2, None: 3}
ATTENTION_ORDER = {
    "overdue": 0,
    "due_today": 1,
    "high_importance_approaching": 2,
    "in_progress_not_planned": 3,
}


class TodayNotFoundError(LookupError):
    pass


class TodayConflictError(RuntimeError):
    pass


class TodayValidationError(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _parse_instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise TodayValidationError("invalid canonical instant") from error
    if parsed.tzinfo is None:
        raise TodayValidationError("canonical instant must include timezone")
    return parsed.astimezone(UTC)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise TodayValidationError("invalid canonical date") from error


def _plan_output(row) -> DayPlanOutput:
    return DayPlanOutput(
        id=row.id,
        task_id=row.task_id,
        planning_date=date.fromisoformat(row.planning_date),
        role=row.role,
        position=row.position,
        created_at=row.created_at,
        updated_at=row.updated_at,
        revision=row.revision,
    )


def _audit(
    connection,
    *,
    entity_id: str,
    action: str,
    from_revision: int | None,
    to_revision: int | None,
    command_id: str,
    occurred_at: str,
) -> None:
    connection.execute(
        insert(audit_events).values(
            event_id=str(uuid4()),
            occurred_at=occurred_at,
            entity_type="task_day_plan",
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


class TodayService:
    def __init__(
        self,
        engine: Engine,
        clock: Callable[[], datetime] | None = None,
    ):
        self.engine = engine
        self.clock = clock or _utc_now

    def get_today(self, context: TodayContext) -> TodayOutput:
        now, zone = self._validate_context(context)
        with self.engine.connect() as connection:
            return self._project(connection, context, now, zone)

    def add_task(self, input: AddTaskToTodayInput, command_id: str) -> TodayOutput:
        now, zone = self._validate_context(input)
        now_text = _timestamp(now)
        with self.engine.begin() as connection:
            task = connection.execute(
                select(tasks).where(tasks.c.id == input.task_id)
            ).one_or_none()
            if task is None:
                raise TodayNotFoundError(input.task_id)
            if task.trashed_at is not None or task.state not in VISIBLE_STATES:
                raise TodayValidationError("Task is not eligible for Today")
            position = connection.execute(
                select(func.max(task_day_plans.c.position)).where(
                    task_day_plans.c.planning_date == input.planning_date.isoformat(),
                    task_day_plans.c.role == input.role,
                )
            ).scalar_one()
            plan_id = str(uuid4())
            connection.execute(
                insert(task_day_plans).values(
                    id=plan_id,
                    task_id=input.task_id,
                    planning_date=input.planning_date.isoformat(),
                    role=input.role,
                    position=0 if position is None else position + 1,
                    created_at=now_text,
                    updated_at=now_text,
                    revision=1,
                )
            )
            _audit(
                connection,
                entity_id=plan_id,
                action="added_to_today",
                from_revision=None,
                to_revision=1,
                command_id=command_id,
                occurred_at=now_text,
            )
            return self._project(connection, input, now, zone)

    def remove_task(
        self,
        plan_id: str,
        input,
        command_id: str,
    ) -> TodayOutput:
        now, zone = self._validate_context(input)
        now_text = _timestamp(now)
        with self.engine.begin() as connection:
            row = self._current_plan(connection, plan_id, input.planning_date)
            if row.revision != input.expected_revision:
                raise TodayConflictError(plan_id)
            connection.execute(
                delete(task_day_plans).where(task_day_plans.c.id == plan_id)
            )
            _audit(
                connection,
                entity_id=plan_id,
                action="removed_from_today",
                from_revision=row.revision,
                to_revision=None,
                command_id=command_id,
                occurred_at=now_text,
            )
            return self._project(connection, input, now, zone)

    def set_role(
        self,
        plan_id: str,
        input: SetTodayRoleInput,
        command_id: str,
    ) -> TodayOutput:
        now, zone = self._validate_context(input)
        now_text = _timestamp(now)
        with self.engine.begin() as connection:
            row = self._current_plan(connection, plan_id, input.planning_date)
            if row.revision != input.expected_revision:
                raise TodayConflictError(plan_id)
            if row.role == input.role:
                return self._project(connection, input, now, zone)
            position = connection.execute(
                select(func.max(task_day_plans.c.position)).where(
                    task_day_plans.c.planning_date == input.planning_date.isoformat(),
                    task_day_plans.c.role == input.role,
                )
            ).scalar_one()
            next_revision = row.revision + 1
            result = connection.execute(
                update(task_day_plans)
                .where(
                    task_day_plans.c.id == plan_id,
                    task_day_plans.c.revision == row.revision,
                )
                .values(
                    role=input.role,
                    position=0 if position is None else position + 1,
                    updated_at=now_text,
                    revision=next_revision,
                )
            )
            if result.rowcount != 1:
                raise TodayConflictError(plan_id)
            _audit(
                connection,
                entity_id=plan_id,
                action="today_role_changed",
                from_revision=row.revision,
                to_revision=next_revision,
                command_id=command_id,
                occurred_at=now_text,
            )
            return self._project(connection, input, now, zone)

    def reorder(self, input: ReorderTodayTasksInput, command_id: str) -> TodayOutput:
        now, zone = self._validate_context(input)
        now_text = _timestamp(now)
        submitted_ids = [item.id for item in input.items]
        if len(submitted_ids) != len(set(submitted_ids)):
            raise TodayValidationError("duplicate plan item")
        with self.engine.begin() as connection:
            rows = connection.execute(
                select(task_day_plans, tasks.c.state, tasks.c.trashed_at)
                .join(tasks, tasks.c.id == task_day_plans.c.task_id)
                .where(
                    task_day_plans.c.planning_date == input.planning_date.isoformat(),
                    task_day_plans.c.role == input.role,
                )
                .order_by(task_day_plans.c.position, task_day_plans.c.id)
            ).all()
            visible = [
                row
                for row in rows
                if row.trashed_at is None and row.state in VISIBLE_STATES
            ]
            if set(submitted_ids) != {row.id for row in visible}:
                raise TodayConflictError(input.planning_date.isoformat())
            by_id = {row.id: row for row in visible}
            for item in input.items:
                if by_id[item.id].revision != item.expected_revision:
                    raise TodayConflictError(item.id)

            slots = sorted(row.position for row in visible)
            changes = [
                (by_id[item.id], slot)
                for item, slot in zip(input.items, slots, strict=True)
                if by_id[item.id].position != slot
            ]
            if changes:
                max_position = max(row.position for row in rows)
                for offset, row in enumerate(visible, start=1):
                    connection.execute(
                        update(task_day_plans)
                        .where(task_day_plans.c.id == row.id)
                        .values(position=max_position + offset)
                    )
                submitted_by_id = {item.id: item for item in input.items}
                for row, slot in zip(
                    (by_id[item.id] for item in input.items), slots, strict=True
                ):
                    if row.position == slot:
                        connection.execute(
                            update(task_day_plans)
                            .where(task_day_plans.c.id == row.id)
                            .values(position=slot)
                        )
                        continue
                    next_revision = row.revision + 1
                    result = connection.execute(
                        update(task_day_plans)
                        .where(
                            task_day_plans.c.id == row.id,
                            task_day_plans.c.revision
                            == submitted_by_id[row.id].expected_revision,
                        )
                        .values(
                            position=slot,
                            updated_at=now_text,
                            revision=next_revision,
                        )
                    )
                    if result.rowcount != 1:
                        raise TodayConflictError(row.id)
                    _audit(
                        connection,
                        entity_id=row.id,
                        action="today_reordered",
                        from_revision=row.revision,
                        to_revision=next_revision,
                        command_id=command_id,
                        occurred_at=now_text,
                    )
            return self._project(connection, input, now, zone)

    def _validate_context(self, context: TodayContext) -> tuple[datetime, ZoneInfo]:
        try:
            zone = ZoneInfo(context.timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise TodayValidationError("invalid IANA timezone") from error
        now = self.clock()
        if now.tzinfo is None:
            raise TodayValidationError("service clock must be timezone-aware")
        now = now.astimezone(UTC)
        if now.astimezone(zone).date() != context.planning_date:
            raise TodayValidationError("stale planning date")
        return now, zone

    @staticmethod
    def _current_plan(connection, plan_id: str, planning_date: date):
        row = connection.execute(
            select(task_day_plans).where(
                task_day_plans.c.id == plan_id,
                task_day_plans.c.planning_date == planning_date.isoformat(),
            )
        ).one_or_none()
        if row is None:
            raise TodayNotFoundError(plan_id)
        return row

    def _project(
        self,
        connection,
        context: TodayContext,
        now: datetime,
        zone: ZoneInfo,
    ) -> TodayOutput:
        task_rows = connection.execute(
            select(
                tasks,
                goals.c.id.label("goal_context_id"),
                goals.c.title.label("goal_context_title"),
                goals.c.state.label("goal_context_state"),
                goals.c.archived_at.label("goal_context_archived_at"),
                projects.c.id.label("project_context_id"),
                projects.c.title.label("project_context_title"),
                projects.c.state.label("project_context_state"),
                projects.c.archived_at.label("project_context_archived_at"),
            )
            .outerjoin(goals, goals.c.id == tasks.c.goal_id)
            .outerjoin(projects, projects.c.id == tasks.c.project_id)
        ).all()
        projected: dict[str, TodayTaskOutput] = {}
        for row in task_rows:
            goal = None
            if row.goal_context_id is not None:
                goal = GoalContextOutput(
                    id=row.goal_context_id,
                    title=row.goal_context_title,
                    state=row.goal_context_state,
                    archived_at=row.goal_context_archived_at,
                )
            project = None
            if row.project_context_id is not None:
                project = ProjectContextOutput(
                    id=row.project_context_id,
                    title=row.project_context_title,
                    state=row.project_context_state,
                    archived_at=row.project_context_archived_at,
                )
            task = _task_output(row)
            projected[task.id] = TodayTaskOutput(task=task, goal=goal, project=project)

        current_date = context.planning_date.isoformat()
        yesterday = (context.planning_date - timedelta(days=1)).isoformat()
        plan_rows = connection.execute(
            select(task_day_plans)
            .where(task_day_plans.c.planning_date.in_([current_date, yesterday]))
            .order_by(
                task_day_plans.c.planning_date,
                task_day_plans.c.role,
                task_day_plans.c.position,
                task_day_plans.c.id,
            )
        ).all()
        current_plans = [row for row in plan_rows if row.planning_date == current_date]
        yesterday_plans = [row for row in plan_rows if row.planning_date == yesterday]
        plan_by_task = {row.task_id: row for row in current_plans}
        selected_ids = set(plan_by_task)

        sections: dict[TodayRole, list[TodayPlanItemOutput]] = {
            "priority": [],
            "planned": [],
            "backup": [],
        }
        for row in sorted(current_plans, key=lambda item: (item.position, item.id)):
            item = projected.get(row.task_id)
            if item is None or not self._visible(item):
                continue
            sections[row.role].append(
                TodayPlanItemOutput(**item.model_dump(), plan=_plan_output(row))
            )

        active = [item for item in projected.values() if self._visible(item)]
        overdue: list[TodayTaskOutput] = []
        due_today: list[TodayTaskOutput] = []
        approaching: list[TodayTaskOutput] = []
        next_midnight = datetime.combine(
            context.planning_date + timedelta(days=1), time.min, zone
        ).astimezone(UTC)
        day_eight = datetime.combine(
            context.planning_date + timedelta(days=8), time.min, zone
        ).astimezone(UTC)
        for item in active:
            deadline = item.task.deadline
            if deadline.kind == "none":
                continue
            if deadline.kind == "date":
                deadline_date = _parse_date(deadline.date or "")
                if deadline_date < context.planning_date:
                    overdue.append(item)
                elif deadline_date == context.planning_date:
                    due_today.append(item)
                elif deadline_date <= context.planning_date + timedelta(days=7):
                    approaching.append(item)
                continue
            instant = _parse_instant(deadline.at or "")
            if instant < now:
                overdue.append(item)
            elif instant < next_midnight:
                due_today.append(item)
            elif instant < day_eight:
                approaching.append(item)

        overdue.sort(key=lambda item: self._deadline_sort_key(item, zone))
        due_today.sort(key=lambda item: self._deadline_sort_key(item, zone))
        approaching.sort(key=lambda item: self._deadline_sort_key(item, zone))
        overdue_ids = {item.task.id for item in overdue}
        due_ids = {item.task.id for item in due_today}
        approaching_ids = {item.task.id for item in approaching}

        attention: list[AttentionItemOutput] = []
        for item in active:
            if item.task.id in selected_ids:
                continue
            reason = None
            if item.task.id in overdue_ids:
                reason = "overdue"
            elif item.task.id in due_ids:
                reason = "due_today"
            elif item.task.id in approaching_ids and item.task.importance == "high":
                reason = "high_importance_approaching"
            elif item.task.state == "in_progress":
                reason = "in_progress_not_planned"
            if reason is not None:
                attention.append(
                    AttentionItemOutput(**item.model_dump(), reason=reason)
                )
        attention.sort(
            key=lambda item: (
                ATTENTION_ORDER[item.reason],
                self._deadline_sort_key(item, zone),
            )
        )

        unfinished: list[TodayPlanItemOutput] = []
        for row in sorted(
            yesterday_plans,
            key=lambda item: (ROLE_ORDER[item.role], item.position, item.id),
        ):
            item = projected.get(row.task_id)
            if (
                item is not None
                and self._visible(item)
                and row.task_id not in selected_ids
            ):
                unfinished.append(
                    TodayPlanItemOutput(**item.model_dump(), plan=_plan_output(row))
                )

        local_start = datetime.combine(
            context.planning_date, time.min, zone
        ).astimezone(UTC)
        completed: list[CompletedTodayItemOutput] = []
        for item in projected.values():
            if (
                item.task.trashed_at is not None
                or item.task.state != "completed"
                or item.task.completed_at is None
            ):
                continue
            completed_at = _parse_instant(item.task.completed_at)
            if local_start <= completed_at < next_midnight:
                row = plan_by_task.get(item.task.id)
                completed.append(
                    CompletedTodayItemOutput(
                        **item.model_dump(),
                        plan=_plan_output(row) if row is not None else None,
                    )
                )
        completed.sort(
            key=lambda item: (
                -_parse_instant(item.task.completed_at or "").timestamp(),
                item.task.id,
            )
        )

        return TodayOutput(
            planning_date=context.planning_date,
            timezone=context.timezone,
            generated_at=_timestamp(now),
            plan=TodayPlanSections(
                priorities=sections["priority"],
                planned=sections["planned"],
                backups=sections["backup"],
            ),
            deadlines=TodayDeadlineSections(
                overdue=overdue,
                due_today=due_today,
                approaching=approaching,
            ),
            needs_attention=attention,
            unfinished_from_yesterday=unfinished,
            completed_today=completed,
        )

    @staticmethod
    def _visible(item: TodayTaskOutput) -> bool:
        return item.task.trashed_at is None and item.task.state in VISIBLE_STATES

    @staticmethod
    def _deadline_sort_key(item: TodayTaskOutput, zone: ZoneInfo):
        deadline = item.task.deadline
        importance = IMPORTANCE_ORDER[item.task.importance]
        tail = (importance, item.task.title.casefold(), item.task.id)
        if deadline.kind == "date":
            return (_parse_date(deadline.date or "").toordinal(), 0, 0.0, *tail)
        if deadline.kind == "instant":
            instant = _parse_instant(deadline.at or "")
            return (
                instant.astimezone(zone).date().toordinal(),
                1,
                instant.timestamp(),
                *tail,
            )
        return (date.max.toordinal(), 2, float("inf"), *tail)
