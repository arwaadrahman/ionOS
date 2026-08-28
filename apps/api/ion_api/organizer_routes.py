from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from ion_api.organizer import (
    AssignmentUnavailableError,
    OrganizerConflictError,
    OrganizerNotFoundError,
    OrganizerService,
    OrganizerValidationError,
    TrashBlockedError,
)
from ion_api.organizer_contracts import (
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
    GoalUpdateInput,
    ListView,
    MilestoneCreateInput,
    MilestoneStateInput,
    MilestoneUpdateInput,
    ProjectCreateInput,
    ProjectDetail,
    ProjectGoalInput,
    ProjectMilestoneOutput,
    ProjectOutput,
    ProjectStateInput,
    ProjectUpdateInput,
    ReorderMilestonesInput,
    RevisionInput,
)


def _command_id() -> str:
    return str(uuid4())


def _call(operation: Callable):
    try:
        return operation()
    except OrganizerNotFoundError as error:
        raise HTTPException(
            404, detail={"code": "not_found", "blockers": []}
        ) from error
    except OrganizerConflictError as error:
        raise HTTPException(
            409, detail={"code": "revision_conflict", "blockers": []}
        ) from error
    except AssignmentUnavailableError as error:
        raise HTTPException(
            409, detail={"code": "assignment_unavailable", "blockers": []}
        ) from error
    except TrashBlockedError as error:
        blockers = [
            {"entity": entity, "count": count}
            for entity, count in sorted(error.blockers.items())
        ]
        raise HTTPException(
            409, detail={"code": "trash_blocked", "blockers": blockers}
        ) from error
    except (OrganizerValidationError, IntegrityError) as error:
        raise HTTPException(
            422, detail={"code": "validation", "blockers": []}
        ) from error


def organizer_router(service: OrganizerService) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["organizer"])

    @router.get("/areas", response_model=list[AreaOutput])
    def list_areas(view: ListView = "active"):
        return _call(lambda: service.list_areas(view))

    @router.get("/areas/{area_id}", response_model=AreaDetail)
    def get_area(area_id: str):
        return _call(lambda: service.get_area_detail(area_id))

    @router.post(
        "/areas", response_model=AreaOutput, status_code=status.HTTP_201_CREATED
    )
    def create_area(input: AreaCreateInput):
        return _call(lambda: service.create_area(input, _command_id()))

    @router.patch("/areas/{area_id}", response_model=AreaOutput)
    def update_area(area_id: str, input: AreaUpdateInput):
        return _call(lambda: service.update_area(area_id, input, _command_id()))

    @router.post("/areas/{area_id}/archive", response_model=AreaOutput)
    def archive_area(area_id: str, input: RevisionInput):
        return _call(
            lambda: service.archive_area(
                area_id, input.expected_revision, _command_id()
            )
        )

    @router.post("/areas/{area_id}/unarchive", response_model=AreaOutput)
    def unarchive_area(area_id: str, input: RevisionInput):
        return _call(
            lambda: service.unarchive_area(
                area_id, input.expected_revision, _command_id()
            )
        )

    @router.post("/areas/{area_id}/trash", response_model=AreaOutput)
    def trash_area(area_id: str, input: RevisionInput):
        return _call(
            lambda: service.trash_area(area_id, input.expected_revision, _command_id())
        )

    @router.post("/areas/{area_id}/restore", response_model=AreaOutput)
    def restore_area(area_id: str, input: RevisionInput):
        return _call(
            lambda: service.restore_area(
                area_id, input.expected_revision, _command_id()
            )
        )

    @router.get("/goals", response_model=list[GoalOutput])
    def list_goals(view: ListView = "active"):
        return _call(lambda: service.list_goals(view))

    @router.get("/goals/{goal_id}", response_model=GoalDetail)
    def get_goal(goal_id: str):
        return _call(lambda: service.get_goal_detail(goal_id))

    @router.post(
        "/goals", response_model=GoalOutput, status_code=status.HTTP_201_CREATED
    )
    def create_goal(input: GoalCreateInput):
        return _call(lambda: service.create_goal(input, _command_id()))

    @router.patch("/goals/{goal_id}", response_model=GoalOutput)
    def update_goal(goal_id: str, input: GoalUpdateInput):
        return _call(lambda: service.update_goal(goal_id, input, _command_id()))

    @router.put("/goals/{goal_id}/state", response_model=GoalOutput)
    def set_goal_state(goal_id: str, input: GoalStateInput):
        return _call(lambda: service.set_goal_state(goal_id, input, _command_id()))

    @router.put("/goals/{goal_id}/area", response_model=GoalOutput)
    def set_goal_area(goal_id: str, input: GoalAreaInput):
        return _call(lambda: service.set_goal_area(goal_id, input, _command_id()))

    @router.post("/goals/{goal_id}/archive", response_model=GoalOutput)
    def archive_goal(goal_id: str, input: RevisionInput):
        return _call(
            lambda: service.archive_goal(
                goal_id, input.expected_revision, _command_id()
            )
        )

    @router.post("/goals/{goal_id}/unarchive", response_model=GoalOutput)
    def unarchive_goal(goal_id: str, input: RevisionInput):
        return _call(
            lambda: service.unarchive_goal(
                goal_id, input.expected_revision, _command_id()
            )
        )

    @router.post("/goals/{goal_id}/trash", response_model=GoalOutput)
    def trash_goal(goal_id: str, input: RevisionInput):
        return _call(
            lambda: service.trash_goal(goal_id, input.expected_revision, _command_id())
        )

    @router.post("/goals/{goal_id}/restore", response_model=GoalOutput)
    def restore_goal(goal_id: str, input: RevisionInput):
        return _call(
            lambda: service.restore_goal(
                goal_id, input.expected_revision, _command_id()
            )
        )

    @router.get("/goals/{goal_id}/milestones", response_model=list[GoalMilestoneOutput])
    def list_goal_milestones(goal_id: str, trashed: bool = False):
        return _call(lambda: service.list_goal_milestones(goal_id, trashed))

    @router.post(
        "/goals/{goal_id}/milestones",
        response_model=GoalMilestoneOutput,
        status_code=status.HTTP_201_CREATED,
    )
    def create_goal_milestone(goal_id: str, input: MilestoneCreateInput):
        return _call(
            lambda: service.create_goal_milestone(goal_id, input, _command_id())
        )

    @router.put(
        "/goals/{goal_id}/milestones/reorder",
        response_model=list[GoalMilestoneOutput],
    )
    def reorder_goal_milestones(goal_id: str, input: ReorderMilestonesInput):
        return _call(
            lambda: service.reorder_goal_milestones(goal_id, input, _command_id())
        )

    @router.patch("/goal-milestones/{milestone_id}", response_model=GoalMilestoneOutput)
    def update_goal_milestone(milestone_id: str, input: MilestoneUpdateInput):
        return _call(
            lambda: service.update_goal_milestone(milestone_id, input, _command_id())
        )

    @router.put(
        "/goal-milestones/{milestone_id}/state",
        response_model=GoalMilestoneOutput,
    )
    def set_goal_milestone_state(milestone_id: str, input: MilestoneStateInput):
        return _call(
            lambda: service.set_goal_milestone_state(milestone_id, input, _command_id())
        )

    @router.post(
        "/goal-milestones/{milestone_id}/trash",
        response_model=GoalMilestoneOutput,
    )
    def trash_goal_milestone(milestone_id: str, input: RevisionInput):
        return _call(
            lambda: service.trash_goal_milestone(
                milestone_id, input.expected_revision, _command_id()
            )
        )

    @router.post(
        "/goal-milestones/{milestone_id}/restore",
        response_model=GoalMilestoneOutput,
    )
    def restore_goal_milestone(milestone_id: str, input: RevisionInput):
        return _call(
            lambda: service.restore_goal_milestone(
                milestone_id, input.expected_revision, _command_id()
            )
        )

    @router.get("/projects", response_model=list[ProjectOutput])
    def list_projects(view: ListView = "active"):
        return _call(lambda: service.list_projects(view))

    @router.get("/projects/{project_id}", response_model=ProjectDetail)
    def get_project(project_id: str):
        return _call(lambda: service.get_project_detail(project_id))

    @router.post(
        "/projects", response_model=ProjectOutput, status_code=status.HTTP_201_CREATED
    )
    def create_project(input: ProjectCreateInput):
        return _call(lambda: service.create_project(input, _command_id()))

    @router.patch("/projects/{project_id}", response_model=ProjectOutput)
    def update_project(project_id: str, input: ProjectUpdateInput):
        return _call(lambda: service.update_project(project_id, input, _command_id()))

    @router.put("/projects/{project_id}/state", response_model=ProjectOutput)
    def set_project_state(project_id: str, input: ProjectStateInput):
        return _call(
            lambda: service.set_project_state(project_id, input, _command_id())
        )

    @router.put("/projects/{project_id}/goal", response_model=ProjectOutput)
    def set_project_goal(project_id: str, input: ProjectGoalInput):
        return _call(lambda: service.set_project_goal(project_id, input, _command_id()))

    @router.post("/projects/{project_id}/archive", response_model=ProjectOutput)
    def archive_project(project_id: str, input: RevisionInput):
        return _call(
            lambda: service.archive_project(
                project_id, input.expected_revision, _command_id()
            )
        )

    @router.post("/projects/{project_id}/unarchive", response_model=ProjectOutput)
    def unarchive_project(project_id: str, input: RevisionInput):
        return _call(
            lambda: service.unarchive_project(
                project_id, input.expected_revision, _command_id()
            )
        )

    @router.post("/projects/{project_id}/trash", response_model=ProjectOutput)
    def trash_project(project_id: str, input: RevisionInput):
        return _call(
            lambda: service.trash_project(
                project_id, input.expected_revision, _command_id()
            )
        )

    @router.post("/projects/{project_id}/restore", response_model=ProjectOutput)
    def restore_project(project_id: str, input: RevisionInput):
        return _call(
            lambda: service.restore_project(
                project_id, input.expected_revision, _command_id()
            )
        )

    @router.get(
        "/projects/{project_id}/milestones",
        response_model=list[ProjectMilestoneOutput],
    )
    def list_project_milestones(project_id: str, trashed: bool = False):
        return _call(lambda: service.list_project_milestones(project_id, trashed))

    @router.post(
        "/projects/{project_id}/milestones",
        response_model=ProjectMilestoneOutput,
        status_code=status.HTTP_201_CREATED,
    )
    def create_project_milestone(project_id: str, input: MilestoneCreateInput):
        return _call(
            lambda: service.create_project_milestone(project_id, input, _command_id())
        )

    @router.put(
        "/projects/{project_id}/milestones/reorder",
        response_model=list[ProjectMilestoneOutput],
    )
    def reorder_project_milestones(project_id: str, input: ReorderMilestonesInput):
        return _call(
            lambda: service.reorder_project_milestones(project_id, input, _command_id())
        )

    @router.patch(
        "/project-milestones/{milestone_id}",
        response_model=ProjectMilestoneOutput,
    )
    def update_project_milestone(milestone_id: str, input: MilestoneUpdateInput):
        return _call(
            lambda: service.update_project_milestone(milestone_id, input, _command_id())
        )

    @router.put(
        "/project-milestones/{milestone_id}/state",
        response_model=ProjectMilestoneOutput,
    )
    def set_project_milestone_state(milestone_id: str, input: MilestoneStateInput):
        return _call(
            lambda: service.set_project_milestone_state(
                milestone_id, input, _command_id()
            )
        )

    @router.post(
        "/project-milestones/{milestone_id}/trash",
        response_model=ProjectMilestoneOutput,
    )
    def trash_project_milestone(milestone_id: str, input: RevisionInput):
        return _call(
            lambda: service.trash_project_milestone(
                milestone_id, input.expected_revision, _command_id()
            )
        )

    @router.post(
        "/project-milestones/{milestone_id}/restore",
        response_model=ProjectMilestoneOutput,
    )
    def restore_project_milestone(milestone_id: str, input: RevisionInput):
        return _call(
            lambda: service.restore_project_milestone(
                milestone_id, input.expected_revision, _command_id()
            )
        )

    return router
