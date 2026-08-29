//! Fixed Phase 1D Home command over the Rust-owned authenticated service.

use serde::{Deserialize, Serialize};
use tauri::State;

use crate::service::{product_request, ProductError, ServiceState, TaskDeadline};
use crate::today::{
    context_route, AttentionReason, GoalContext, ProjectContext, TodayContext, TodayRole,
};

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CoreEntityType {
    Area,
    Goal,
    GoalMilestone,
    Project,
    ProjectMilestone,
    Task,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CoreLifecycle {
    Active,
    Paused,
    Completed,
    Archived,
    Inactive,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CoreRelationshipType {
    GoalArea,
    ProjectGoal,
    GoalMilestoneGoal,
    ProjectMilestoneProject,
    TaskGoal,
    TaskProject,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CoreNode {
    pub id: String,
    pub entity_type: CoreEntityType,
    pub label: String,
    pub lifecycle: CoreLifecycle,
    pub today_role: Option<TodayRole>,
    pub attention_reason: Option<AttentionReason>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CoreEdge {
    pub source_id: String,
    pub target_id: String,
    pub relationship_type: CoreRelationshipType,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CoreGraph {
    pub nodes: Vec<CoreNode>,
    pub edges: Vec<CoreEdge>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct HomeTaskSummary {
    pub id: String,
    pub title: String,
    pub state: String,
    pub deadline: TaskDeadline,
    pub goal: Option<GoalContext>,
    pub project: Option<ProjectContext>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct HomeAttentionSummary {
    pub id: String,
    pub title: String,
    pub state: String,
    pub deadline: TaskDeadline,
    pub goal: Option<GoalContext>,
    pub project: Option<ProjectContext>,
    pub reason: AttentionReason,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct HomeOutput {
    pub planning_date: String,
    pub timezone: String,
    pub generated_at: String,
    pub core: CoreGraph,
    pub focus: Option<HomeTaskSummary>,
    pub needs_attention: Vec<HomeAttentionSummary>,
    pub upcoming: Vec<HomeTaskSummary>,
}

#[tauri::command]
pub async fn get_home(
    state: State<'_, ServiceState>,
    context: TodayContext,
) -> Result<HomeOutput, ProductError> {
    let route = context_route("/v1/home", &context)?;
    product_request::<(), HomeOutput>(&state, reqwest::Method::GET, &route, None).await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn home_route_encodes_context() {
        let route = context_route(
            "/v1/home",
            &TodayContext {
                planning_date: "2030-03-10".into(),
                timezone: "America/Los_Angeles".into(),
            },
        )
        .expect("valid route");
        assert_eq!(
            route,
            "/v1/home?planning_date=2030-03-10&timezone=America%2FLos_Angeles"
        );
    }
}
