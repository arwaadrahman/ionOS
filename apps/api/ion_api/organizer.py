"""Phase 1B organizer operations backed by explicit Core transactions."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Engine, Table, and_, func, insert, or_, select, update

from ion_api.organizer_contracts import (
    ActivityOutput,
    AreaCreateInput,
    AreaDetail,
    AreaOutput,
    AreaUpdateInput,
    GoalAreaInput,
    GoalCreateInput,
    GoalDetail,
    GoalMilestoneOutput,
    GoalOutput,
    GoalStateInput,
    GoalSummary,
    GoalUpdateInput,
    MilestoneCreateInput,
    MilestoneStateInput,
    MilestoneUpdateInput,
    ProjectCreateInput,
    ProjectDetail,
    ProjectGoalInput,
    ProjectMilestoneOutput,
    ProjectOutput,
    ProjectStateInput,
    ProjectSummary,
    ProjectUpdateInput,
    ReorderMilestonesInput,
)
from ion_api.schema import (
    areas,
    audit_events,
    goals,
    milestones,
    project_milestones,
    projects,
    tasks,
)
from ion_api.tasks import _task_output


class OrganizerNotFoundError(LookupError):
    pass


class OrganizerConflictError(RuntimeError):
    pass


class AssignmentUnavailableError(RuntimeError):
    pass


class OrganizerValidationError(ValueError):
    pass


class TrashBlockedError(RuntimeError):
    def __init__(self, blockers: dict[str, int]):
        super().__init__("trash blocked")
        self.blockers = blockers


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _model(model_type, row):
    return model_type.model_validate(row._mapping)


def _audit(
    connection,
    *,
    entity_type: str,
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
            entity_type=entity_type,
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


class OrganizerService:
    def __init__(self, engine: Engine):
        self.engine = engine

    def _row(self, connection, table: Table, entity_id: str, *, trash=None):
        query = select(table).where(table.c.id == entity_id)
        if trash is True:
            query = query.where(table.c.trashed_at.is_not(None))
        elif trash is False:
            query = query.where(table.c.trashed_at.is_(None))
        row = connection.execute(query).one_or_none()
        if row is None:
            raise OrganizerNotFoundError(entity_id)
        return row

    def _mutate(
        self,
        connection,
        *,
        table: Table,
        entity_type: str,
        entity_id: str,
        expected_revision: int,
        values: dict,
        action: str,
        command_id: str,
        trash=None,
    ):
        row = self._row(connection, table, entity_id, trash=trash)
        if row.revision != expected_revision:
            raise OrganizerConflictError(entity_id)
        changes = {
            key: value for key, value in values.items() if getattr(row, key) != value
        }
        if not changes:
            return row
        next_revision = row.revision + 1
        result = connection.execute(
            update(table)
            .where(table.c.id == entity_id, table.c.revision == row.revision)
            .values(**changes, updated_at=utc_now(), revision=next_revision)
        )
        if result.rowcount != 1:
            raise OrganizerConflictError(entity_id)
        _audit(
            connection,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            from_revision=row.revision,
            to_revision=next_revision,
            command_id=command_id,
        )
        return self._row(connection, table, entity_id)

    def _available_parent(self, connection, table: Table, parent_id: str):
        row = connection.execute(
            select(table).where(table.c.id == parent_id)
        ).one_or_none()
        archived = row is not None and (
            getattr(row, "archived_at", None) is not None
            or getattr(row, "state", None) == "archived"
        )
        if row is None or row.trashed_at is not None or archived:
            raise AssignmentUnavailableError(parent_id)
        return row

    @staticmethod
    def _list_clause(table: Table, view: str):
        if view == "trash":
            return table.c.trashed_at.is_not(None)
        if view == "all":
            return True
        archived = (
            table.c.state == "archived"
            if table is projects
            else table.c.archived_at.is_not(None)
        )
        if view == "archived":
            return and_(table.c.trashed_at.is_(None), archived)
        return and_(table.c.trashed_at.is_(None), ~archived)

    # Areas
    def create_area(self, input: AreaCreateInput, command_id: str) -> AreaOutput:
        now = utc_now()
        entity_id = str(uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                insert(areas).values(
                    id=entity_id,
                    name=input.name.strip(),
                    description=input.description,
                    archived_at=None,
                    created_at=now,
                    updated_at=now,
                    revision=1,
                    trashed_at=None,
                )
            )
            _audit(
                connection,
                entity_type="area",
                entity_id=entity_id,
                action="created",
                from_revision=None,
                to_revision=1,
                command_id=command_id,
            )
            row = self._row(connection, areas, entity_id)
        return _model(AreaOutput, row)

    def list_areas(self, view: str = "active") -> list[AreaOutput]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(areas)
                .where(self._list_clause(areas, view))
                .order_by(areas.c.name, areas.c.id)
            ).all()
        return [_model(AreaOutput, row) for row in rows]

    def get_area(self, area_id: str) -> AreaOutput:
        with self.engine.connect() as connection:
            row = self._row(connection, areas, area_id)
        return _model(AreaOutput, row)

    def get_area_detail(self, area_id: str) -> AreaDetail:
        with self.engine.connect() as connection:
            area = self._row(connection, areas, area_id)
            goal_rows = connection.execute(
                select(goals)
                .where(
                    goals.c.area_id == area_id,
                    goals.c.trashed_at.is_(None),
                )
                .order_by(goals.c.updated_at.desc(), goals.c.id)
            ).all()
        return AreaDetail(
            area=_model(AreaOutput, area),
            goals=[_model(GoalOutput, row) for row in goal_rows],
        )

    def update_area(
        self, area_id: str, input: AreaUpdateInput, command_id: str
    ) -> AreaOutput:
        values = input.model_dump(exclude_unset=True)
        values.pop("expected_revision")
        if "name" in values:
            values["name"] = values["name"].strip()
        with self.engine.begin() as connection:
            row = self._mutate(
                connection,
                table=areas,
                entity_type="area",
                entity_id=area_id,
                expected_revision=input.expected_revision,
                values=values,
                action="edited",
                command_id=command_id,
                trash=False,
            )
        return _model(AreaOutput, row)

    def archive_area(self, area_id: str, revision: int, command_id: str) -> AreaOutput:
        with self.engine.begin() as connection:
            current = self._row(connection, areas, area_id, trash=False)
            row = self._mutate(
                connection,
                table=areas,
                entity_type="area",
                entity_id=area_id,
                expected_revision=revision,
                values={"archived_at": current.archived_at or utc_now()},
                action="archived",
                command_id=command_id,
                trash=False,
            )
        return _model(AreaOutput, row)

    def unarchive_area(
        self, area_id: str, revision: int, command_id: str
    ) -> AreaOutput:
        return self._area_lifecycle(
            area_id, revision, {"archived_at": None}, "unarchived", command_id, False
        )

    def trash_area(self, area_id: str, revision: int, command_id: str) -> AreaOutput:
        with self.engine.begin() as connection:
            current = self._row(connection, areas, area_id, trash=False)
            if current.revision != revision:
                raise OrganizerConflictError(area_id)
            count = connection.scalar(
                select(func.count())
                .select_from(goals)
                .where(goals.c.area_id == area_id, goals.c.trashed_at.is_(None))
            )
            if count:
                raise TrashBlockedError({"goal": count})
            row = self._mutate(
                connection,
                table=areas,
                entity_type="area",
                entity_id=area_id,
                expected_revision=revision,
                values={"trashed_at": utc_now()},
                action="trashed",
                command_id=command_id,
                trash=False,
            )
        return _model(AreaOutput, row)

    def restore_area(self, area_id: str, revision: int, command_id: str) -> AreaOutput:
        return self._area_lifecycle(
            area_id, revision, {"trashed_at": None}, "restored", command_id, True
        )

    def _area_lifecycle(self, area_id, revision, values, action, command_id, trash):
        with self.engine.begin() as connection:
            row = self._mutate(
                connection,
                table=areas,
                entity_type="area",
                entity_id=area_id,
                expected_revision=revision,
                values=values,
                action=action,
                command_id=command_id,
                trash=trash,
            )
        return _model(AreaOutput, row)

    # Goals
    def create_goal(self, input: GoalCreateInput, command_id: str) -> GoalOutput:
        now = utc_now()
        entity_id = str(uuid4())
        with self.engine.begin() as connection:
            if input.area_id is not None:
                self._available_parent(connection, areas, input.area_id)
            connection.execute(
                insert(goals).values(
                    id=entity_id,
                    area_id=input.area_id,
                    title=input.title.strip(),
                    description=input.description,
                    kind=input.kind,
                    state="active",
                    archived_at=None,
                    created_at=now,
                    updated_at=now,
                    revision=1,
                    trashed_at=None,
                )
            )
            _audit(
                connection,
                entity_type="goal",
                entity_id=entity_id,
                action="created",
                from_revision=None,
                to_revision=1,
                command_id=command_id,
            )
            row = self._row(connection, goals, entity_id)
        return _model(GoalOutput, row)

    def list_goals(self, view: str = "active") -> list[GoalOutput]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(goals)
                .where(self._list_clause(goals, view))
                .order_by(goals.c.updated_at.desc(), goals.c.id)
            ).all()
        return [_model(GoalOutput, row) for row in rows]

    def update_goal(
        self, goal_id: str, input: GoalUpdateInput, command_id: str
    ) -> GoalOutput:
        values = input.model_dump(exclude_unset=True)
        values.pop("expected_revision")
        if "title" in values:
            values["title"] = values["title"].strip()
        return self._goal_mutation(
            goal_id, input.expected_revision, values, "edited", command_id
        )

    def set_goal_state(
        self, goal_id: str, input: GoalStateInput, command_id: str
    ) -> GoalOutput:
        return self._goal_mutation(
            goal_id,
            input.expected_revision,
            {"state": input.state},
            "state_changed",
            command_id,
        )

    def set_goal_area(
        self, goal_id: str, input: GoalAreaInput, command_id: str
    ) -> GoalOutput:
        with self.engine.begin() as connection:
            current = self._row(connection, goals, goal_id, trash=False)
            if current.revision != input.expected_revision:
                raise OrganizerConflictError(goal_id)
            if input.area_id is not None:
                self._available_parent(connection, areas, input.area_id)
            row = self._mutate(
                connection,
                table=goals,
                entity_type="goal",
                entity_id=goal_id,
                expected_revision=input.expected_revision,
                values={"area_id": input.area_id},
                action="area_changed",
                command_id=command_id,
                trash=False,
            )
        return _model(GoalOutput, row)

    def archive_goal(self, goal_id: str, revision: int, command_id: str) -> GoalOutput:
        with self.engine.begin() as connection:
            current = self._row(connection, goals, goal_id, trash=False)
            row = self._mutate(
                connection,
                table=goals,
                entity_type="goal",
                entity_id=goal_id,
                expected_revision=revision,
                values={"archived_at": current.archived_at or utc_now()},
                action="archived",
                command_id=command_id,
                trash=False,
            )
        return _model(GoalOutput, row)

    def unarchive_goal(
        self, goal_id: str, revision: int, command_id: str
    ) -> GoalOutput:
        return self._goal_mutation(
            goal_id, revision, {"archived_at": None}, "unarchived", command_id
        )

    def trash_goal(self, goal_id: str, revision: int, command_id: str) -> GoalOutput:
        with self.engine.begin() as connection:
            current = self._row(connection, goals, goal_id, trash=False)
            if current.revision != revision:
                raise OrganizerConflictError(goal_id)
            blockers = {
                "milestone": connection.scalar(
                    select(func.count())
                    .select_from(milestones)
                    .where(
                        milestones.c.goal_id == goal_id,
                        milestones.c.trashed_at.is_(None),
                    )
                ),
                "project": connection.scalar(
                    select(func.count())
                    .select_from(projects)
                    .where(
                        projects.c.goal_id == goal_id, projects.c.trashed_at.is_(None)
                    )
                ),
                "task": connection.scalar(
                    select(func.count())
                    .select_from(tasks)
                    .where(tasks.c.goal_id == goal_id, tasks.c.trashed_at.is_(None))
                ),
            }
            blockers = {key: value for key, value in blockers.items() if value}
            if blockers:
                raise TrashBlockedError(blockers)
            row = self._mutate(
                connection,
                table=goals,
                entity_type="goal",
                entity_id=goal_id,
                expected_revision=revision,
                values={"trashed_at": utc_now()},
                action="trashed",
                command_id=command_id,
                trash=False,
            )
        return _model(GoalOutput, row)

    def restore_goal(self, goal_id: str, revision: int, command_id: str) -> GoalOutput:
        return self._goal_mutation(
            goal_id, revision, {"trashed_at": None}, "restored", command_id, True
        )

    def _goal_mutation(
        self, goal_id, revision, values, action, command_id, trash=False
    ):
        with self.engine.begin() as connection:
            row = self._mutate(
                connection,
                table=goals,
                entity_type="goal",
                entity_id=goal_id,
                expected_revision=revision,
                values=values,
                action=action,
                command_id=command_id,
                trash=trash,
            )
        return _model(GoalOutput, row)

    def get_goal_detail(self, goal_id: str) -> GoalDetail:
        with self.engine.connect() as connection:
            goal = self._row(connection, goals, goal_id)
            milestone_rows = connection.execute(
                select(milestones)
                .where(
                    milestones.c.goal_id == goal_id,
                    milestones.c.trashed_at.is_(None),
                )
                .order_by(milestones.c.position)
            ).all()
            applicable = [row for row in milestone_rows if row.state != "skipped"]
            project_total = connection.scalar(
                select(func.count())
                .select_from(projects)
                .where(
                    projects.c.goal_id == goal_id,
                    projects.c.trashed_at.is_(None),
                    projects.c.state.not_in(("completed", "archived", "abandoned")),
                )
            )
            task_rows = connection.execute(
                select(tasks).where(
                    tasks.c.goal_id == goal_id, tasks.c.trashed_at.is_(None)
                )
            ).all()
            project_rows = connection.execute(
                select(projects).where(
                    projects.c.goal_id == goal_id,
                    projects.c.trashed_at.is_(None),
                )
            ).all()
            project_ids = [row.id for row in project_rows]
            project_task_rows = (
                connection.execute(
                    select(tasks).where(
                        tasks.c.project_id.in_(project_ids),
                        tasks.c.trashed_at.is_(None),
                    )
                ).all()
                if project_ids
                else []
            )
        return GoalDetail(
            goal=_model(GoalOutput, goal),
            summary=GoalSummary(
                milestone_total=len(applicable),
                milestone_achieved=sum(row.state == "achieved" for row in applicable),
                project_total=project_total,
                task_total=sum(
                    row.state not in ("completed", "canceled") for row in task_rows
                ),
                task_completed=sum(row.state == "completed" for row in task_rows),
            ),
            milestones=[_model(GoalMilestoneOutput, row) for row in milestone_rows],
            projects=[_model(ProjectOutput, row) for row in project_rows],
            direct_tasks=[_task_output(row) for row in task_rows],
            project_tasks=[_task_output(row) for row in project_task_rows],
        )

    # Projects
    def create_project(
        self, input: ProjectCreateInput, command_id: str
    ) -> ProjectOutput:
        if input.state == "archived":
            raise OrganizerValidationError("create project cannot start archived")
        now = utc_now()
        entity_id = str(uuid4())
        completed_at = now if input.state == "completed" else None
        with self.engine.begin() as connection:
            if input.goal_id is not None:
                self._available_parent(connection, goals, input.goal_id)
            connection.execute(
                insert(projects).values(
                    id=entity_id,
                    goal_id=input.goal_id,
                    title=input.title.strip(),
                    description=input.description,
                    state=input.state,
                    completed_at=completed_at,
                    archived_at=None,
                    created_at=now,
                    updated_at=now,
                    revision=1,
                    trashed_at=None,
                )
            )
            _audit(
                connection,
                entity_type="project",
                entity_id=entity_id,
                action="created",
                from_revision=None,
                to_revision=1,
                command_id=command_id,
            )
            row = self._row(connection, projects, entity_id)
        return _model(ProjectOutput, row)

    def list_projects(self, view: str = "active") -> list[ProjectOutput]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(projects)
                .where(self._list_clause(projects, view))
                .order_by(projects.c.updated_at.desc(), projects.c.id)
            ).all()
        return [_model(ProjectOutput, row) for row in rows]

    def update_project(
        self, project_id: str, input: ProjectUpdateInput, command_id: str
    ) -> ProjectOutput:
        values = input.model_dump(exclude_unset=True)
        values.pop("expected_revision")
        if "title" in values:
            values["title"] = values["title"].strip()
        return self._project_mutation(
            project_id, input.expected_revision, values, "edited", command_id
        )

    def set_project_state(
        self, project_id: str, input: ProjectStateInput, command_id: str
    ) -> ProjectOutput:
        if input.state == "archived":
            raise OrganizerValidationError("use archive operation")
        with self.engine.begin() as connection:
            current = self._row(connection, projects, project_id, trash=False)
            if current.state == "archived":
                raise OrganizerValidationError("unarchive project first")
            completed_at = current.completed_at
            if input.state == "completed" and current.state != "completed":
                completed_at = utc_now()
            elif input.state != "completed":
                completed_at = None
            row = self._mutate(
                connection,
                table=projects,
                entity_type="project",
                entity_id=project_id,
                expected_revision=input.expected_revision,
                values={"state": input.state, "completed_at": completed_at},
                action="state_changed",
                command_id=command_id,
                trash=False,
            )
        return _model(ProjectOutput, row)

    def set_project_goal(
        self, project_id: str, input: ProjectGoalInput, command_id: str
    ) -> ProjectOutput:
        with self.engine.begin() as connection:
            current = self._row(connection, projects, project_id, trash=False)
            if current.revision != input.expected_revision:
                raise OrganizerConflictError(project_id)
            if input.goal_id is not None:
                self._available_parent(connection, goals, input.goal_id)
            row = self._mutate(
                connection,
                table=projects,
                entity_type="project",
                entity_id=project_id,
                expected_revision=input.expected_revision,
                values={"goal_id": input.goal_id},
                action="goal_changed",
                command_id=command_id,
                trash=False,
            )
        return _model(ProjectOutput, row)

    def archive_project(
        self, project_id: str, revision: int, command_id: str
    ) -> ProjectOutput:
        with self.engine.begin() as connection:
            current = self._row(connection, projects, project_id, trash=False)
            if current.revision != revision:
                raise OrganizerConflictError(project_id)
            if current.state == "archived":
                return _model(ProjectOutput, current)
            if current.state != "completed":
                raise OrganizerValidationError(
                    "project must be completed before archive"
                )
            row = self._mutate(
                connection,
                table=projects,
                entity_type="project",
                entity_id=project_id,
                expected_revision=revision,
                values={"state": "archived", "archived_at": utc_now()},
                action="archived",
                command_id=command_id,
                trash=False,
            )
        return _model(ProjectOutput, row)

    def unarchive_project(
        self, project_id: str, revision: int, command_id: str
    ) -> ProjectOutput:
        with self.engine.begin() as connection:
            current = self._row(connection, projects, project_id, trash=False)
            if current.revision != revision:
                raise OrganizerConflictError(project_id)
            if current.state != "archived":
                return _model(ProjectOutput, current)
            row = self._mutate(
                connection,
                table=projects,
                entity_type="project",
                entity_id=project_id,
                expected_revision=revision,
                values={"state": "completed", "archived_at": None},
                action="unarchived",
                command_id=command_id,
                trash=False,
            )
        return _model(ProjectOutput, row)

    def trash_project(
        self, project_id: str, revision: int, command_id: str
    ) -> ProjectOutput:
        with self.engine.begin() as connection:
            current = self._row(connection, projects, project_id, trash=False)
            if current.revision != revision:
                raise OrganizerConflictError(project_id)
            blockers = {
                "project_milestone": connection.scalar(
                    select(func.count())
                    .select_from(project_milestones)
                    .where(
                        project_milestones.c.project_id == project_id,
                        project_milestones.c.trashed_at.is_(None),
                    )
                ),
                "task": connection.scalar(
                    select(func.count())
                    .select_from(tasks)
                    .where(
                        tasks.c.project_id == project_id, tasks.c.trashed_at.is_(None)
                    )
                ),
            }
            blockers = {key: value for key, value in blockers.items() if value}
            if blockers:
                raise TrashBlockedError(blockers)
            row = self._mutate(
                connection,
                table=projects,
                entity_type="project",
                entity_id=project_id,
                expected_revision=revision,
                values={"trashed_at": utc_now()},
                action="trashed",
                command_id=command_id,
                trash=False,
            )
        return _model(ProjectOutput, row)

    def restore_project(
        self, project_id: str, revision: int, command_id: str
    ) -> ProjectOutput:
        return self._project_mutation(
            project_id, revision, {"trashed_at": None}, "restored", command_id, True
        )

    def _project_mutation(
        self, project_id, revision, values, action, command_id, trash=False
    ):
        with self.engine.begin() as connection:
            row = self._mutate(
                connection,
                table=projects,
                entity_type="project",
                entity_id=project_id,
                expected_revision=revision,
                values=values,
                action=action,
                command_id=command_id,
                trash=trash,
            )
        return _model(ProjectOutput, row)

    def get_project_detail(self, project_id: str) -> ProjectDetail:
        with self.engine.connect() as connection:
            project = self._row(connection, projects, project_id)
            milestone_rows = connection.execute(
                select(project_milestones)
                .where(
                    project_milestones.c.project_id == project_id,
                    project_milestones.c.trashed_at.is_(None),
                )
                .order_by(project_milestones.c.position)
            ).all()
            applicable = [row for row in milestone_rows if row.state != "skipped"]
            task_rows = connection.execute(
                select(tasks).where(
                    tasks.c.project_id == project_id, tasks.c.trashed_at.is_(None)
                )
            ).all()
            current = next(
                (row for row in milestone_rows if row.state == "in_progress"), None
            )
            if current is None:
                current = next(
                    (row for row in milestone_rows if row.state == "planned"), None
                )
            milestone_ids = select(project_milestones.c.id).where(
                project_milestones.c.project_id == project_id
            )
            activities = connection.execute(
                select(audit_events)
                .where(
                    or_(
                        and_(
                            audit_events.c.entity_type == "project",
                            audit_events.c.entity_id == project_id,
                        ),
                        and_(
                            audit_events.c.entity_type == "project_milestone",
                            audit_events.c.entity_id.in_(milestone_ids),
                        ),
                    )
                )
                .order_by(
                    audit_events.c.occurred_at.desc(), audit_events.c.event_id.desc()
                )
                .limit(25)
            ).all()
        return ProjectDetail(
            project=_model(ProjectOutput, project),
            summary=ProjectSummary(
                milestone_total=len(applicable),
                milestone_achieved=sum(row.state == "achieved" for row in applicable),
                task_total=sum(
                    row.state not in ("completed", "canceled") for row in task_rows
                ),
                task_completed=sum(row.state == "completed" for row in task_rows),
            ),
            milestones=[_model(ProjectMilestoneOutput, row) for row in milestone_rows],
            current_milestone=_model(ProjectMilestoneOutput, current)
            if current
            else None,
            recent_activity=[_model(ActivityOutput, row) for row in activities],
            tasks=[_task_output(row) for row in task_rows],
            next_actions=[
                _task_output(row)
                for row in sorted(
                    (
                        row
                        for row in task_rows
                        if row.state in ("in_progress", "open", "paused")
                    ),
                    key=lambda row: (
                        {"in_progress": 0, "open": 1, "paused": 2}[row.state],
                        row.created_at,
                        row.id,
                    ),
                )
            ],
        )

    # Explicit Goal and Project Milestone operations.
    def create_goal_milestone(
        self, goal_id: str, input: MilestoneCreateInput, command_id: str
    ) -> GoalMilestoneOutput:
        return self._create_milestone(
            milestones,
            "goal_id",
            goals,
            goal_id,
            input,
            command_id,
            "goal_milestone",
            GoalMilestoneOutput,
        )

    def create_project_milestone(
        self, project_id: str, input: MilestoneCreateInput, command_id: str
    ) -> ProjectMilestoneOutput:
        return self._create_milestone(
            project_milestones,
            "project_id",
            projects,
            project_id,
            input,
            command_id,
            "project_milestone",
            ProjectMilestoneOutput,
        )

    def _create_milestone(
        self,
        table,
        owner_column,
        owner_table,
        owner_id,
        input,
        command_id,
        entity_type,
        output_type,
    ):
        now = utc_now()
        entity_id = str(uuid4())
        with self.engine.begin() as connection:
            self._available_parent(connection, owner_table, owner_id)
            maximum = connection.scalar(
                select(func.max(table.c.position)).where(
                    getattr(table.c, owner_column) == owner_id
                )
            )
            position = 0 if maximum is None else maximum + 1
            connection.execute(
                insert(table).values(
                    id=entity_id,
                    **{owner_column: owner_id},
                    title=input.title.strip(),
                    state="planned",
                    target_date=input.target_date,
                    achieved_at=None,
                    position=position,
                    created_at=now,
                    updated_at=now,
                    revision=1,
                    trashed_at=None,
                )
            )
            _audit(
                connection,
                entity_type=entity_type,
                entity_id=entity_id,
                action="created",
                from_revision=None,
                to_revision=1,
                command_id=command_id,
            )
            row = self._row(connection, table, entity_id)
        return _model(output_type, row)

    def list_goal_milestones(
        self, goal_id: str, trashed: bool = False
    ) -> list[GoalMilestoneOutput]:
        return self._list_milestones(
            milestones, "goal_id", goals, goal_id, trashed, GoalMilestoneOutput
        )

    def list_project_milestones(
        self, project_id: str, trashed: bool = False
    ) -> list[ProjectMilestoneOutput]:
        return self._list_milestones(
            project_milestones,
            "project_id",
            projects,
            project_id,
            trashed,
            ProjectMilestoneOutput,
        )

    def _list_milestones(
        self, table, owner_column, owner_table, owner_id, trashed, output_type
    ):
        trash_clause = (
            table.c.trashed_at.is_not(None) if trashed else table.c.trashed_at.is_(None)
        )
        with self.engine.connect() as connection:
            self._row(connection, owner_table, owner_id)
            rows = connection.execute(
                select(table)
                .where(getattr(table.c, owner_column) == owner_id, trash_clause)
                .order_by(table.c.position)
            ).all()
        return [_model(output_type, row) for row in rows]

    def update_goal_milestone(
        self, milestone_id: str, input: MilestoneUpdateInput, command_id: str
    ) -> GoalMilestoneOutput:
        return self._update_milestone(
            milestones,
            milestone_id,
            input,
            command_id,
            "goal_milestone",
            GoalMilestoneOutput,
        )

    def update_project_milestone(
        self, milestone_id: str, input: MilestoneUpdateInput, command_id: str
    ) -> ProjectMilestoneOutput:
        return self._update_milestone(
            project_milestones,
            milestone_id,
            input,
            command_id,
            "project_milestone",
            ProjectMilestoneOutput,
        )

    def _update_milestone(
        self, table, entity_id, input, command_id, entity_type, output_type
    ):
        values = input.model_dump(exclude_unset=True)
        values.pop("expected_revision")
        if "title" in values:
            values["title"] = values["title"].strip()
        return self._milestone_mutation(
            table,
            entity_id,
            input.expected_revision,
            values,
            "edited",
            command_id,
            entity_type,
            output_type,
        )

    def set_goal_milestone_state(
        self, milestone_id: str, input: MilestoneStateInput, command_id: str
    ) -> GoalMilestoneOutput:
        return self._set_milestone_state(
            milestones,
            milestone_id,
            input,
            command_id,
            "goal_milestone",
            GoalMilestoneOutput,
        )

    def set_project_milestone_state(
        self, milestone_id: str, input: MilestoneStateInput, command_id: str
    ) -> ProjectMilestoneOutput:
        return self._set_milestone_state(
            project_milestones,
            milestone_id,
            input,
            command_id,
            "project_milestone",
            ProjectMilestoneOutput,
        )

    def _set_milestone_state(
        self, table, entity_id, input, command_id, entity_type, output_type
    ):
        with self.engine.begin() as connection:
            current = self._row(connection, table, entity_id, trash=False)
            achieved_at = current.achieved_at
            if input.state == "achieved" and current.state != "achieved":
                achieved_at = utc_now()
            elif input.state != "achieved":
                achieved_at = None
            row = self._mutate(
                connection,
                table=table,
                entity_type=entity_type,
                entity_id=entity_id,
                expected_revision=input.expected_revision,
                values={"state": input.state, "achieved_at": achieved_at},
                action="state_changed",
                command_id=command_id,
                trash=False,
            )
        return _model(output_type, row)

    def trash_goal_milestone(
        self, milestone_id: str, revision: int, command_id: str
    ) -> GoalMilestoneOutput:
        return self._milestone_mutation(
            milestones,
            milestone_id,
            revision,
            {"trashed_at": utc_now()},
            "trashed",
            command_id,
            "goal_milestone",
            GoalMilestoneOutput,
            False,
        )

    def restore_goal_milestone(
        self, milestone_id: str, revision: int, command_id: str
    ) -> GoalMilestoneOutput:
        return self._milestone_mutation(
            milestones,
            milestone_id,
            revision,
            {"trashed_at": None},
            "restored",
            command_id,
            "goal_milestone",
            GoalMilestoneOutput,
            True,
        )

    def trash_project_milestone(
        self, milestone_id: str, revision: int, command_id: str
    ) -> ProjectMilestoneOutput:
        return self._milestone_mutation(
            project_milestones,
            milestone_id,
            revision,
            {"trashed_at": utc_now()},
            "trashed",
            command_id,
            "project_milestone",
            ProjectMilestoneOutput,
            False,
        )

    def restore_project_milestone(
        self, milestone_id: str, revision: int, command_id: str
    ) -> ProjectMilestoneOutput:
        return self._milestone_mutation(
            project_milestones,
            milestone_id,
            revision,
            {"trashed_at": None},
            "restored",
            command_id,
            "project_milestone",
            ProjectMilestoneOutput,
            True,
        )

    def _milestone_mutation(
        self,
        table,
        entity_id,
        revision,
        values,
        action,
        command_id,
        entity_type,
        output_type,
        trash=False,
    ):
        with self.engine.begin() as connection:
            row = self._mutate(
                connection,
                table=table,
                entity_type=entity_type,
                entity_id=entity_id,
                expected_revision=revision,
                values=values,
                action=action,
                command_id=command_id,
                trash=trash,
            )
        return _model(output_type, row)

    def reorder_goal_milestones(
        self, goal_id: str, input: ReorderMilestonesInput, command_id: str
    ) -> list[GoalMilestoneOutput]:
        return self._reorder(
            milestones,
            "goal_id",
            goals,
            goal_id,
            input,
            command_id,
            "goal_milestone",
            GoalMilestoneOutput,
        )

    def reorder_project_milestones(
        self, project_id: str, input: ReorderMilestonesInput, command_id: str
    ) -> list[ProjectMilestoneOutput]:
        return self._reorder(
            project_milestones,
            "project_id",
            projects,
            project_id,
            input,
            command_id,
            "project_milestone",
            ProjectMilestoneOutput,
        )

    def _reorder(
        self,
        table,
        owner_column,
        owner_table,
        owner_id,
        input,
        command_id,
        entity_type,
        output_type,
    ):
        submitted = input.items
        submitted_ids = [item.id for item in submitted]
        if len(set(submitted_ids)) != len(submitted_ids):
            raise OrganizerValidationError("duplicate milestone")
        with self.engine.begin() as connection:
            self._row(connection, owner_table, owner_id)
            siblings = connection.execute(
                select(table)
                .where(getattr(table.c, owner_column) == owner_id)
                .order_by(table.c.position)
            ).all()
            active = [row for row in siblings if row.trashed_at is None]
            if set(submitted_ids) != {row.id for row in active}:
                raise OrganizerConflictError(owner_id)
            by_id = {row.id: row for row in active}
            for item in submitted:
                if by_id[item.id].revision != item.expected_revision:
                    raise OrganizerConflictError(item.id)
            slots = sorted(row.position for row in active)
            changed = [
                (by_id[item.id], slot)
                for item, slot in zip(submitted, slots, strict=True)
                if by_id[item.id].position != slot
            ]
            if changed:
                temporary = (
                    (max(row.position for row in siblings) + 1) if siblings else 0
                )
                for offset, (row, _) in enumerate(changed):
                    result = connection.execute(
                        update(table)
                        .where(table.c.id == row.id, table.c.revision == row.revision)
                        .values(position=temporary + offset)
                    )
                    if result.rowcount != 1:
                        raise OrganizerConflictError(row.id)
                now = utc_now()
                for row, final_position in changed:
                    result = connection.execute(
                        update(table)
                        .where(table.c.id == row.id, table.c.revision == row.revision)
                        .values(
                            position=final_position,
                            updated_at=now,
                            revision=row.revision + 1,
                        )
                    )
                    if result.rowcount != 1:
                        raise OrganizerConflictError(row.id)
                    _audit(
                        connection,
                        entity_type=entity_type,
                        entity_id=row.id,
                        action="reordered",
                        from_revision=row.revision,
                        to_revision=row.revision + 1,
                        command_id=command_id,
                    )
            rows = connection.execute(
                select(table)
                .where(
                    getattr(table.c, owner_column) == owner_id,
                    table.c.trashed_at.is_(None),
                )
                .order_by(table.c.position)
            ).all()
        return [_model(output_type, row) for row in rows]
