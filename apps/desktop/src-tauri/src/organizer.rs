//! Fixed Phase 1B organizer commands. The authenticated request primitive stays Rust-only.

use serde::{Deserialize, Serialize};
use tauri::State;

use crate::service::{
    product_request, ProductError, ProductErrorCode, RevisionInput, ServiceState, Task,
};

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ListView {
    Active,
    Archived,
    Trash,
    All,
}

impl ListView {
    fn value(&self) -> &'static str {
        match self {
            Self::Active => "active",
            Self::Archived => "archived",
            Self::Trash => "trash",
            Self::All => "all",
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct AreaCreateInput {
    pub name: String,
    pub description: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct AreaUpdateInput {
    pub expected_revision: i64,
    pub name: Option<String>,
    pub description: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Area {
    pub id: String,
    pub name: String,
    pub description: Option<String>,
    pub archived_at: Option<String>,
    pub created_at: String,
    pub updated_at: String,
    pub revision: i64,
    pub trashed_at: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct AreaDetail {
    pub area: Area,
    pub goals: Vec<Goal>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct GoalCreateInput {
    pub title: String,
    pub description: Option<String>,
    pub kind: String,
    pub area_id: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct GoalUpdateInput {
    pub expected_revision: i64,
    pub title: Option<String>,
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub kind: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct GoalStateInput {
    pub expected_revision: i64,
    pub state: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct GoalAreaInput {
    pub expected_revision: i64,
    pub area_id: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Goal {
    pub id: String,
    pub area_id: Option<String>,
    pub title: String,
    pub description: Option<String>,
    pub kind: String,
    pub state: String,
    pub archived_at: Option<String>,
    pub created_at: String,
    pub updated_at: String,
    pub revision: i64,
    pub trashed_at: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct GoalSummary {
    pub milestone_total: i64,
    pub milestone_achieved: i64,
    pub project_total: i64,
    pub task_total: i64,
    pub task_completed: i64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct GoalDetail {
    pub goal: Goal,
    pub summary: GoalSummary,
    pub milestones: Vec<GoalMilestone>,
    pub projects: Vec<Project>,
    pub direct_tasks: Vec<Task>,
    pub project_tasks: Vec<Task>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ProjectCreateInput {
    pub title: String,
    pub description: Option<String>,
    pub state: String,
    pub goal_id: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ProjectUpdateInput {
    pub expected_revision: i64,
    pub title: Option<String>,
    pub description: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ProjectStateInput {
    pub expected_revision: i64,
    pub state: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ProjectGoalInput {
    pub expected_revision: i64,
    pub goal_id: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Project {
    pub id: String,
    pub goal_id: Option<String>,
    pub title: String,
    pub description: Option<String>,
    pub state: String,
    pub completed_at: Option<String>,
    pub archived_at: Option<String>,
    pub created_at: String,
    pub updated_at: String,
    pub revision: i64,
    pub trashed_at: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ProjectSummary {
    pub milestone_total: i64,
    pub milestone_achieved: i64,
    pub task_total: i64,
    pub task_completed: i64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Activity {
    pub event_id: String,
    pub occurred_at: String,
    pub entity_type: String,
    pub entity_id: String,
    pub action: String,
    pub from_revision: Option<i64>,
    pub to_revision: Option<i64>,
    pub command_id: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct RecoveryItem {
    pub entity_type: String,
    pub entity_id: String,
    pub label: String,
    pub lifecycle: String,
    pub revision: i64,
    pub trashed_at: String,
    pub owner_label: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct RecoveryActivity {
    pub event_id: String,
    pub occurred_at: String,
    pub entity_type: String,
    pub entity_id: String,
    pub label: String,
    pub action: String,
    pub authority: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct RecoveryOutput {
    pub trash: Vec<RecoveryItem>,
    pub recent_activity: Vec<RecoveryActivity>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ProjectDetail {
    pub project: Project,
    pub summary: ProjectSummary,
    pub milestones: Vec<ProjectMilestone>,
    pub current_milestone: Option<ProjectMilestone>,
    pub tasks: Vec<Task>,
    pub next_actions: Vec<Task>,
    pub recent_activity: Vec<Activity>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct MilestoneCreateInput {
    pub title: String,
    pub target_date: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct MilestoneUpdateInput {
    pub expected_revision: i64,
    pub title: Option<String>,
    pub target_date: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct MilestoneStateInput {
    pub expected_revision: i64,
    pub state: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ReorderMilestoneItem {
    pub id: String,
    pub expected_revision: i64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ReorderMilestonesInput {
    pub items: Vec<ReorderMilestoneItem>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct GoalMilestone {
    pub id: String,
    pub goal_id: String,
    pub title: String,
    pub state: String,
    pub target_date: Option<String>,
    pub achieved_at: Option<String>,
    pub position: i64,
    pub created_at: String,
    pub updated_at: String,
    pub revision: i64,
    pub trashed_at: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ProjectMilestone {
    pub id: String,
    pub project_id: String,
    pub title: String,
    pub state: String,
    pub target_date: Option<String>,
    pub achieved_at: Option<String>,
    pub position: i64,
    pub created_at: String,
    pub updated_at: String,
    pub revision: i64,
    pub trashed_at: Option<String>,
}

fn entity_route(prefix: &str, id: &str, suffix: &str) -> Result<String, ProductError> {
    let valid = id.len() == 36
        && id.bytes().enumerate().all(|(index, byte)| match index {
            8 | 13 | 18 | 23 => byte == b'-',
            _ => byte.is_ascii_hexdigit(),
        });
    if !valid {
        return Err(ProductError::new(ProductErrorCode::Validation));
    }
    Ok(format!("{prefix}/{id}{suffix}"))
}

macro_rules! list_command {
    ($name:ident, $route:literal, $output:ty) => {
        #[tauri::command]
        pub async fn $name(
            state: State<'_, ServiceState>,
            view: ListView,
        ) -> Result<Vec<$output>, ProductError> {
            let route = format!(concat!($route, "?view={}"), view.value());
            product_request::<(), Vec<$output>>(&state, reqwest::Method::GET, &route, None).await
        }
    };
}

list_command!(list_areas, "/v1/areas", Area);
list_command!(list_goals, "/v1/goals", Goal);
list_command!(list_projects, "/v1/projects", Project);

#[tauri::command]
pub async fn get_recovery(state: State<'_, ServiceState>) -> Result<RecoveryOutput, ProductError> {
    product_request::<(), RecoveryOutput>(&state, reqwest::Method::GET, "/v1/recovery", None).await
}

macro_rules! create_command {
    ($name:ident, $route:literal, $input:ty, $output:ty) => {
        #[tauri::command]
        pub async fn $name(
            state: State<'_, ServiceState>,
            input: $input,
        ) -> Result<$output, ProductError> {
            product_request(&state, reqwest::Method::POST, $route, Some(&input)).await
        }
    };
}

create_command!(create_area, "/v1/areas", AreaCreateInput, Area);
create_command!(create_goal, "/v1/goals", GoalCreateInput, Goal);
create_command!(create_project, "/v1/projects", ProjectCreateInput, Project);

#[tauri::command]
pub async fn get_area(
    state: State<'_, ServiceState>,
    area_id: String,
) -> Result<AreaDetail, ProductError> {
    let route = entity_route("/v1/areas", &area_id, "")?;
    product_request::<(), AreaDetail>(&state, reqwest::Method::GET, &route, None).await
}

#[tauri::command]
pub async fn get_goal_detail(
    state: State<'_, ServiceState>,
    goal_id: String,
) -> Result<GoalDetail, ProductError> {
    let route = entity_route("/v1/goals", &goal_id, "")?;
    product_request::<(), GoalDetail>(&state, reqwest::Method::GET, &route, None).await
}

#[tauri::command]
pub async fn get_project_detail(
    state: State<'_, ServiceState>,
    project_id: String,
) -> Result<ProjectDetail, ProductError> {
    let route = entity_route("/v1/projects", &project_id, "")?;
    product_request::<(), ProjectDetail>(&state, reqwest::Method::GET, &route, None).await
}

macro_rules! update_command {
    ($name:ident, $prefix:literal, $id_name:ident, $input:ty, $output:ty) => {
        #[tauri::command]
        pub async fn $name(
            state: State<'_, ServiceState>,
            $id_name: String,
            input: $input,
        ) -> Result<$output, ProductError> {
            let route = entity_route($prefix, &$id_name, "")?;
            product_request(&state, reqwest::Method::PATCH, &route, Some(&input)).await
        }
    };
}

update_command!(update_area, "/v1/areas", area_id, AreaUpdateInput, Area);
update_command!(update_goal, "/v1/goals", goal_id, GoalUpdateInput, Goal);
update_command!(
    update_project,
    "/v1/projects",
    project_id,
    ProjectUpdateInput,
    Project
);
update_command!(
    update_goal_milestone,
    "/v1/goal-milestones",
    milestone_id,
    MilestoneUpdateInput,
    GoalMilestone
);
update_command!(
    update_project_milestone,
    "/v1/project-milestones",
    milestone_id,
    MilestoneUpdateInput,
    ProjectMilestone
);

async fn revision_action<R: for<'de> Deserialize<'de>>(
    state: &ServiceState,
    prefix: &str,
    entity_id: &str,
    action: &str,
    input: &RevisionInput,
) -> Result<R, ProductError> {
    let route = entity_route(prefix, entity_id, &format!("/{action}"))?;
    product_request(state, reqwest::Method::POST, &route, Some(input)).await
}

macro_rules! revision_command {
    ($name:ident, $prefix:literal, $id_name:ident, $action:literal, $output:ty) => {
        #[tauri::command]
        pub async fn $name(
            state: State<'_, ServiceState>,
            $id_name: String,
            input: RevisionInput,
        ) -> Result<$output, ProductError> {
            revision_action(&state, $prefix, &$id_name, $action, &input).await
        }
    };
}

revision_command!(archive_area, "/v1/areas", area_id, "archive", Area);
revision_command!(unarchive_area, "/v1/areas", area_id, "unarchive", Area);
revision_command!(trash_area, "/v1/areas", area_id, "trash", Area);
revision_command!(restore_area, "/v1/areas", area_id, "restore", Area);
revision_command!(archive_goal, "/v1/goals", goal_id, "archive", Goal);
revision_command!(unarchive_goal, "/v1/goals", goal_id, "unarchive", Goal);
revision_command!(trash_goal, "/v1/goals", goal_id, "trash", Goal);
revision_command!(restore_goal, "/v1/goals", goal_id, "restore", Goal);
revision_command!(
    archive_project,
    "/v1/projects",
    project_id,
    "archive",
    Project
);
revision_command!(
    unarchive_project,
    "/v1/projects",
    project_id,
    "unarchive",
    Project
);
revision_command!(trash_project, "/v1/projects", project_id, "trash", Project);
revision_command!(
    restore_project,
    "/v1/projects",
    project_id,
    "restore",
    Project
);
revision_command!(
    trash_goal_milestone,
    "/v1/goal-milestones",
    milestone_id,
    "trash",
    GoalMilestone
);
revision_command!(
    restore_goal_milestone,
    "/v1/goal-milestones",
    milestone_id,
    "restore",
    GoalMilestone
);
revision_command!(
    trash_project_milestone,
    "/v1/project-milestones",
    milestone_id,
    "trash",
    ProjectMilestone
);
revision_command!(
    restore_project_milestone,
    "/v1/project-milestones",
    milestone_id,
    "restore",
    ProjectMilestone
);

async fn put_action<T: Serialize, R: for<'de> Deserialize<'de>>(
    state: &ServiceState,
    prefix: &str,
    entity_id: &str,
    action: &str,
    input: &T,
) -> Result<R, ProductError> {
    let route = entity_route(prefix, entity_id, &format!("/{action}"))?;
    product_request(state, reqwest::Method::PUT, &route, Some(input)).await
}

#[tauri::command]
pub async fn set_goal_state(
    state: State<'_, ServiceState>,
    goal_id: String,
    input: GoalStateInput,
) -> Result<Goal, ProductError> {
    put_action(&state, "/v1/goals", &goal_id, "state", &input).await
}

#[tauri::command]
pub async fn set_goal_area(
    state: State<'_, ServiceState>,
    goal_id: String,
    input: GoalAreaInput,
) -> Result<Goal, ProductError> {
    put_action(&state, "/v1/goals", &goal_id, "area", &input).await
}

#[tauri::command]
pub async fn set_project_state(
    state: State<'_, ServiceState>,
    project_id: String,
    input: ProjectStateInput,
) -> Result<Project, ProductError> {
    put_action(&state, "/v1/projects", &project_id, "state", &input).await
}

#[tauri::command]
pub async fn set_project_goal(
    state: State<'_, ServiceState>,
    project_id: String,
    input: ProjectGoalInput,
) -> Result<Project, ProductError> {
    put_action(&state, "/v1/projects", &project_id, "goal", &input).await
}

#[tauri::command]
pub async fn set_goal_milestone_state(
    state: State<'_, ServiceState>,
    milestone_id: String,
    input: MilestoneStateInput,
) -> Result<GoalMilestone, ProductError> {
    put_action(
        &state,
        "/v1/goal-milestones",
        &milestone_id,
        "state",
        &input,
    )
    .await
}

#[tauri::command]
pub async fn set_project_milestone_state(
    state: State<'_, ServiceState>,
    milestone_id: String,
    input: MilestoneStateInput,
) -> Result<ProjectMilestone, ProductError> {
    put_action(
        &state,
        "/v1/project-milestones",
        &milestone_id,
        "state",
        &input,
    )
    .await
}

#[tauri::command]
pub async fn create_goal_milestone(
    state: State<'_, ServiceState>,
    goal_id: String,
    input: MilestoneCreateInput,
) -> Result<GoalMilestone, ProductError> {
    let route = entity_route("/v1/goals", &goal_id, "/milestones")?;
    product_request(&state, reqwest::Method::POST, &route, Some(&input)).await
}

#[tauri::command]
pub async fn create_project_milestone(
    state: State<'_, ServiceState>,
    project_id: String,
    input: MilestoneCreateInput,
) -> Result<ProjectMilestone, ProductError> {
    let route = entity_route("/v1/projects", &project_id, "/milestones")?;
    product_request(&state, reqwest::Method::POST, &route, Some(&input)).await
}

#[tauri::command]
pub async fn reorder_goal_milestones(
    state: State<'_, ServiceState>,
    goal_id: String,
    input: ReorderMilestonesInput,
) -> Result<Vec<GoalMilestone>, ProductError> {
    let route = entity_route("/v1/goals", &goal_id, "/milestones/reorder")?;
    product_request(&state, reqwest::Method::PUT, &route, Some(&input)).await
}

#[tauri::command]
pub async fn reorder_project_milestones(
    state: State<'_, ServiceState>,
    project_id: String,
    input: ReorderMilestonesInput,
) -> Result<Vec<ProjectMilestone>, ProductError> {
    let route = entity_route("/v1/projects", &project_id, "/milestones/reorder")?;
    product_request(&state, reqwest::Method::PUT, &route, Some(&input)).await
}

async fn list_milestones<R: for<'de> Deserialize<'de>>(
    state: &ServiceState,
    prefix: &str,
    owner_id: &str,
    trashed: bool,
) -> Result<Vec<R>, ProductError> {
    let suffix = format!("/milestones?trashed={trashed}");
    let route = entity_route(prefix, owner_id, &suffix)?;
    product_request::<(), Vec<R>>(state, reqwest::Method::GET, &route, None).await
}

#[tauri::command]
pub async fn list_goal_milestones(
    state: State<'_, ServiceState>,
    goal_id: String,
    trashed: bool,
) -> Result<Vec<GoalMilestone>, ProductError> {
    list_milestones(&state, "/v1/goals", &goal_id, trashed).await
}

#[tauri::command]
pub async fn list_project_milestones(
    state: State<'_, ServiceState>,
    project_id: String,
    trashed: bool,
) -> Result<Vec<ProjectMilestone>, ProductError> {
    list_milestones(&state, "/v1/projects", &project_id, trashed).await
}

#[cfg(test)]
mod tests {
    use super::{entity_route, GoalCreateInput, GoalUpdateInput, ListView};

    #[test]
    fn routes_accept_only_canonical_entity_ids() {
        let id = "11111111-1111-4111-8111-111111111111";
        assert_eq!(
            entity_route("/v1/goals", id, "/archive").unwrap(),
            format!("/v1/goals/{id}/archive")
        );
        assert!(entity_route("/v1/goals", "../health", "").is_err());
    }

    #[test]
    fn list_views_and_inputs_serialize_to_backend_contract() {
        assert_eq!(ListView::Archived.value(), "archived");
        let input = GoalCreateInput {
            title: "Synthetic Goal".into(),
            description: None,
            kind: "outcome".into(),
            area_id: None,
        };
        let value = serde_json::to_value(input).unwrap();
        assert_eq!(value["area_id"], serde_json::Value::Null);
        assert_eq!(value["kind"], "outcome");
    }

    #[test]
    fn goal_patch_omits_an_unset_non_nullable_kind() {
        let input = GoalUpdateInput {
            expected_revision: 2,
            title: Some("Edited Goal".into()),
            description: None,
            kind: None,
        };
        let value = serde_json::to_value(input).unwrap();

        assert_eq!(value["description"], serde_json::Value::Null);
        assert!(value.get("kind").is_none());
    }
}
