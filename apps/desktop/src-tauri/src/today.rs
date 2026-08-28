//! Fixed Phase 1C Today commands over the Rust-owned authenticated service.

use serde::{Deserialize, Serialize};
use tauri::State;

use crate::service::{product_request, ProductError, ProductErrorCode, ServiceState, Task};

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct TodayContext {
    pub planning_date: String,
    pub timezone: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TodayRole {
    Priority,
    Planned,
    Backup,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct AddTaskToTodayInput {
    pub planning_date: String,
    pub timezone: String,
    pub task_id: String,
    pub role: TodayRole,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct RemoveTaskFromTodayInput {
    pub planning_date: String,
    pub timezone: String,
    pub expected_revision: i64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct SetTodayRoleInput {
    pub planning_date: String,
    pub timezone: String,
    pub expected_revision: i64,
    pub role: TodayRole,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ReorderTodayItem {
    pub id: String,
    pub expected_revision: i64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ReorderTodayTasksInput {
    pub planning_date: String,
    pub timezone: String,
    pub role: TodayRole,
    pub items: Vec<ReorderTodayItem>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct DayPlan {
    pub id: String,
    pub task_id: String,
    pub planning_date: String,
    pub role: TodayRole,
    pub position: i64,
    pub created_at: String,
    pub updated_at: String,
    pub revision: i64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct GoalContext {
    pub id: String,
    pub title: String,
    pub state: String,
    pub archived_at: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ProjectContext {
    pub id: String,
    pub title: String,
    pub state: String,
    pub archived_at: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct TodayTask {
    pub task: Task,
    pub goal: Option<GoalContext>,
    pub project: Option<ProjectContext>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct TodayPlanItem {
    pub task: Task,
    pub goal: Option<GoalContext>,
    pub project: Option<ProjectContext>,
    pub plan: DayPlan,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum AttentionReason {
    Overdue,
    DueToday,
    HighImportanceApproaching,
    InProgressNotPlanned,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct AttentionItem {
    pub task: Task,
    pub goal: Option<GoalContext>,
    pub project: Option<ProjectContext>,
    pub reason: AttentionReason,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CompletedTodayItem {
    pub task: Task,
    pub goal: Option<GoalContext>,
    pub project: Option<ProjectContext>,
    pub plan: Option<DayPlan>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct TodayPlanSections {
    pub priorities: Vec<TodayPlanItem>,
    pub planned: Vec<TodayPlanItem>,
    pub backups: Vec<TodayPlanItem>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct TodayDeadlineSections {
    pub overdue: Vec<TodayTask>,
    pub due_today: Vec<TodayTask>,
    pub approaching: Vec<TodayTask>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct TodayOutput {
    pub planning_date: String,
    pub timezone: String,
    pub generated_at: String,
    pub plan: TodayPlanSections,
    pub deadlines: TodayDeadlineSections,
    pub needs_attention: Vec<AttentionItem>,
    pub unfinished_from_yesterday: Vec<TodayPlanItem>,
    pub completed_today: Vec<CompletedTodayItem>,
}

fn valid_id(id: &str) -> bool {
    id.len() == 36
        && id.bytes().enumerate().all(|(index, byte)| match index {
            8 | 13 | 18 | 23 => byte == b'-',
            _ => byte.is_ascii_hexdigit(),
        })
}

fn validate_context(planning_date: &str, timezone: &str) -> Result<(), ProductError> {
    let date_valid = planning_date.len() == 10
        && planning_date
            .bytes()
            .enumerate()
            .all(|(index, byte)| match index {
                4 | 7 => byte == b'-',
                _ => byte.is_ascii_digit(),
            });
    if !date_valid || timezone.is_empty() || timezone.len() > 255 {
        return Err(ProductError::new(ProductErrorCode::Validation));
    }
    Ok(())
}

fn get_route(context: &TodayContext) -> Result<String, ProductError> {
    validate_context(&context.planning_date, &context.timezone)?;
    let mut url = reqwest::Url::parse("http://ion.invalid/v1/today")
        .map_err(|_| ProductError::new(ProductErrorCode::Validation))?;
    url.query_pairs_mut()
        .append_pair("planning_date", &context.planning_date)
        .append_pair("timezone", &context.timezone);
    Ok(format!(
        "{}?{}",
        url.path(),
        url.query()
            .ok_or_else(|| ProductError::new(ProductErrorCode::Validation))?
    ))
}

fn plan_route(plan_id: &str, suffix: &str) -> Result<String, ProductError> {
    if !valid_id(plan_id) {
        return Err(ProductError::new(ProductErrorCode::Validation));
    }
    Ok(format!("/v1/today/plans/{plan_id}{suffix}"))
}

#[tauri::command]
pub async fn get_today(
    state: State<'_, ServiceState>,
    context: TodayContext,
) -> Result<TodayOutput, ProductError> {
    let route = get_route(&context)?;
    product_request::<(), TodayOutput>(&state, reqwest::Method::GET, &route, None).await
}

#[tauri::command]
pub async fn add_task_to_today(
    state: State<'_, ServiceState>,
    input: AddTaskToTodayInput,
) -> Result<TodayOutput, ProductError> {
    validate_context(&input.planning_date, &input.timezone)?;
    if !valid_id(&input.task_id) {
        return Err(ProductError::new(ProductErrorCode::Validation));
    }
    product_request(
        &state,
        reqwest::Method::POST,
        "/v1/today/plans",
        Some(&input),
    )
    .await
}

#[tauri::command]
pub async fn remove_task_from_today(
    state: State<'_, ServiceState>,
    plan_id: String,
    input: RemoveTaskFromTodayInput,
) -> Result<TodayOutput, ProductError> {
    validate_context(&input.planning_date, &input.timezone)?;
    let route = plan_route(&plan_id, "/remove")?;
    product_request(&state, reqwest::Method::POST, &route, Some(&input)).await
}

#[tauri::command]
pub async fn set_today_role(
    state: State<'_, ServiceState>,
    plan_id: String,
    input: SetTodayRoleInput,
) -> Result<TodayOutput, ProductError> {
    validate_context(&input.planning_date, &input.timezone)?;
    let route = plan_route(&plan_id, "/role")?;
    product_request(&state, reqwest::Method::PUT, &route, Some(&input)).await
}

#[tauri::command]
pub async fn reorder_today_tasks(
    state: State<'_, ServiceState>,
    input: ReorderTodayTasksInput,
) -> Result<TodayOutput, ProductError> {
    validate_context(&input.planning_date, &input.timezone)?;
    if input.items.len() > 10_000 || input.items.iter().any(|item| !valid_id(&item.id)) {
        return Err(ProductError::new(ProductErrorCode::Validation));
    }
    product_request(
        &state,
        reqwest::Method::PUT,
        "/v1/today/plans/order",
        Some(&input),
    )
    .await
}

#[cfg(test)]
mod tests {
    use super::{get_route, plan_route, TodayContext};

    #[test]
    fn today_query_is_encoded_and_bounded() {
        let route = get_route(&TodayContext {
            planning_date: "2030-01-02".into(),
            timezone: "America/Los_Angeles".into(),
        })
        .unwrap();
        assert_eq!(
            route,
            "/v1/today?planning_date=2030-01-02&timezone=America%2FLos_Angeles"
        );
        assert!(get_route(&TodayContext {
            planning_date: "bad".into(),
            timezone: "UTC".into()
        })
        .is_err());
        assert!(get_route(&TodayContext {
            planning_date: "2030-01-02".into(),
            timezone: "x".repeat(256)
        })
        .is_err());
    }

    #[test]
    fn today_plan_routes_reject_non_uuid_identifiers() {
        assert!(plan_route("not-an-id", "/remove").is_err());
        assert_eq!(
            plan_route("11111111-1111-4111-8111-111111111111", "/role").unwrap(),
            "/v1/today/plans/11111111-1111-4111-8111-111111111111/role"
        );
    }
}
