//! Rust-owned production sidecar lifecycle. No renderer shell capability exists.

use std::{
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};

use getrandom::fill;
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager, Runtime};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};

const READY_PREFIX: &[u8] = b"ION_RUNTIME_READY ";
const READINESS_TIMEOUT: Duration = Duration::from_secs(15);
const SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(5);
const MAX_PROTOCOL_BYTES: usize = 4096;
const SESSION_HEADER: &str = "X-Ion-Session";

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct TaskDeadline {
    pub kind: String,
    pub date: Option<String>,
    pub at: Option<String>,
    pub timezone: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CreateTaskInput {
    pub title: String,
    pub details: Option<String>,
    pub importance: Option<String>,
    pub estimated_minutes: Option<i64>,
    pub progress_percent: Option<i64>,
    pub deadline: TaskDeadline,
    pub project_id: Option<String>,
    pub goal_id: Option<String>,
    pub completion_evidence: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct UpdateTaskInput {
    pub expected_revision: i64,
    pub title: Option<String>,
    pub details: Option<String>,
    pub importance: Option<String>,
    pub estimated_minutes: Option<i64>,
    pub progress_percent: Option<i64>,
    pub deadline: Option<TaskDeadline>,
    pub completion_evidence: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct SetTaskRelationshipsInput {
    pub expected_revision: i64,
    pub goal_id: Option<String>,
    pub project_id: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct RevisionInput {
    pub expected_revision: i64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Task {
    pub id: String,
    pub title: String,
    pub details: Option<String>,
    pub state: String,
    pub source_kind: String,
    pub importance: Option<String>,
    pub estimated_minutes: Option<i64>,
    pub progress_percent: Option<i64>,
    pub deadline: TaskDeadline,
    pub project_id: Option<String>,
    pub goal_id: Option<String>,
    pub completion_evidence: Option<String>,
    pub completed_at: Option<String>,
    pub created_at: String,
    pub updated_at: String,
    pub revision: i64,
    pub trashed_at: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ProductErrorCode {
    NotFound,
    RevisionConflict,
    Validation,
    AssignmentUnavailable,
    TrashBlocked,
    Unavailable,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
pub struct Blocker {
    pub entity: String,
    pub count: i64,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
pub struct ProductError {
    pub code: ProductErrorCode,
    pub blockers: Vec<Blocker>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

impl ProductError {
    pub(crate) fn new(code: ProductErrorCode) -> Self {
        Self {
            code,
            blockers: Vec::new(),
            reason: None,
        }
    }

    fn unavailable() -> Self {
        Self::new(ProductErrorCode::Unavailable)
    }
}

#[derive(Deserialize)]
struct ProductErrorEnvelope {
    detail: ProductError,
}

fn parse_product_error(status: u16, bytes: &[u8]) -> ProductError {
    if matches!(status, 404 | 409 | 422) && bytes.len() <= MAX_PROTOCOL_BYTES {
        if let Ok(envelope) = serde_json::from_slice::<ProductErrorEnvelope>(bytes) {
            return envelope.detail;
        }
        let code = match status {
            404 => ProductErrorCode::NotFound,
            409 => ProductErrorCode::RevisionConflict,
            _ => ProductErrorCode::Validation,
        };
        return ProductError::new(code);
    }
    ProductError::unavailable()
}

fn task_route(task_id: &str, suffix: &str) -> Result<String, ProductError> {
    let valid = task_id.len() == 36
        && task_id
            .bytes()
            .enumerate()
            .all(|(index, byte)| match index {
                8 | 13 | 18 | 23 => byte == b'-',
                _ => byte.is_ascii_hexdigit(),
            });
    if !valid {
        return Err(ProductError::new(ProductErrorCode::Validation));
    }
    Ok(format!("/v1/tasks/{task_id}{suffix}"))
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct ServiceStatus {
    pub state: String,
}

struct ServiceProcess {
    child: CommandChild,
    port: u16,
    token: String,
}

pub struct ServiceState {
    process: Mutex<Option<ServiceProcess>>,
    status: Mutex<String>,
    diagnostic: Mutex<Option<String>>,
}

impl ServiceState {
    fn set_status(&self, status: &str) {
        *self.status.lock().expect("service status lock poisoned") = status.to_owned();
    }

    pub fn status(&self) -> ServiceStatus {
        ServiceStatus {
            state: self
                .status
                .lock()
                .expect("service status lock poisoned")
                .clone(),
        }
    }

    fn mark_unavailable(&self, diagnostic: &str) {
        *self.process.lock().expect("service process lock poisoned") = None;
        *self.status.lock().expect("service status lock poisoned") = "unavailable".into();
        *self
            .diagnostic
            .lock()
            .expect("service diagnostic lock poisoned") = Some(diagnostic.into());
    }

    fn clear_diagnostic(&self) {
        *self
            .diagnostic
            .lock()
            .expect("service diagnostic lock poisoned") = None;
    }

    #[cfg(test)]
    fn safe_diagnostic(&self) -> Option<String> {
        self.diagnostic
            .lock()
            .expect("service diagnostic lock poisoned")
            .clone()
    }
}

impl Default for ServiceState {
    fn default() -> Self {
        Self {
            process: Mutex::new(None),
            status: Mutex::new("unavailable".into()),
            diagnostic: Mutex::new(None),
        }
    }
}

fn encode_session_token(bytes: &[u8; 32]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut token = String::with_capacity(64);
    for byte in bytes {
        token.push(HEX[(byte >> 4) as usize] as char);
        token.push(HEX[(byte & 0x0f) as usize] as char);
    }
    token
}

fn new_session_token() -> Result<String, String> {
    let mut bytes = [0_u8; 32];
    fill(&mut bytes).map_err(|error| format!("secure random generation failed: {error}"))?;
    Ok(encode_session_token(&bytes))
}

fn bootstrap_message(token: &str) -> Result<Vec<u8>, String> {
    let mut message = serde_json::to_vec(&serde_json::json!({
        "type": "bootstrap",
        "session_token": token,
    }))
    .map_err(|error| format!("bootstrap serialization failed: {error}"))?;
    if message.len() >= MAX_PROTOCOL_BYTES {
        return Err("bootstrap message exceeded protocol limit".into());
    }
    message.push(b'\n');
    Ok(message)
}

fn parse_ready(line: &[u8]) -> Result<u16, String> {
    if line.len() > MAX_PROTOCOL_BYTES || !line.starts_with(READY_PREFIX) {
        return Err("invalid sidecar readiness record".into());
    }
    let value: serde_json::Value = serde_json::from_slice(&line[READY_PREFIX.len()..])
        .map_err(|_| "invalid sidecar readiness JSON")?;
    let port = value
        .get("port")
        .and_then(serde_json::Value::as_u64)
        .ok_or("missing sidecar readiness port")?;
    u16::try_from(port)
        .ok()
        .filter(|port| *port > 0)
        .ok_or_else(|| "invalid sidecar readiness port".into())
}

fn await_ready(receiver: &mut tauri::async_runtime::Receiver<CommandEvent>) -> Result<u16, String> {
    let deadline = Instant::now() + READINESS_TIMEOUT;
    loop {
        match receiver.try_recv() {
            Ok(CommandEvent::Stdout(line)) => return parse_ready(&line),
            Ok(CommandEvent::Terminated(_)) => return Err("sidecar exited before readiness".into()),
            Ok(CommandEvent::Error(_)) => return Err("sidecar failed before readiness".into()),
            Ok(CommandEvent::Stderr(_)) => {}
            Ok(_) => return Err("unexpected sidecar readiness output".into()),
            Err(_) => {
                if Instant::now() >= deadline {
                    return Err("sidecar readiness timed out".into());
                }
                thread::sleep(Duration::from_millis(10));
            }
        }
    }
}

fn health_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}/health")
}

async fn authenticate_health(port: u16, token: &str) -> Result<(), String> {
    let response = reqwest::Client::new()
        .get(health_url(port))
        .header(SESSION_HEADER, token)
        .send()
        .await
        .map_err(|_| "sidecar authenticated health request failed")?;
    if response.status().is_success() {
        Ok(())
    } else {
        Err("sidecar authenticated health request was rejected".into())
    }
}

fn monitor_exit<R: Runtime>(
    app: AppHandle<R>,
    mut receiver: tauri::async_runtime::Receiver<CommandEvent>,
) {
    tauri::async_runtime::spawn(async move {
        while let Some(event) = receiver.recv().await {
            if matches!(event, CommandEvent::Terminated(_) | CommandEvent::Error(_)) {
                let state = app.state::<ServiceState>();
                *state.process.lock().expect("service process lock poisoned") = None;
                state.set_status("unavailable");
                return;
            }
        }
        let state = app.state::<ServiceState>();
        *state.process.lock().expect("service process lock poisoned") = None;
        state.set_status("unavailable");
    });
}

pub fn start<R: Runtime>(app: &AppHandle<R>) -> Result<(), String> {
    let state = app.state::<ServiceState>();
    state.set_status("starting");
    let token = new_session_token()?;
    let (mut receiver, mut child) = app
        .shell()
        .sidecar("ion-api")
        .map_err(|_| "packaged Ion sidecar could not be resolved")?
        .arg("--production")
        .spawn()
        .map_err(|_| "packaged Ion sidecar could not be started")?;

    let startup = (|| -> Result<u16, String> {
        child
            .write(&bootstrap_message(&token)?)
            .map_err(|_| "sidecar bootstrap write failed")?;
        let port = await_ready(&mut receiver)?;
        tauri::async_runtime::block_on(authenticate_health(port, &token))?;
        Ok(port)
    })();

    let port = match startup {
        Ok(port) => port,
        Err(error) => {
            let _ = child.kill();
            state.mark_unavailable(&error);
            return Err(error);
        }
    };

    *state.process.lock().expect("service process lock poisoned") =
        Some(ServiceProcess { child, port, token });
    state.clear_diagnostic();
    state.set_status("ready");
    monitor_exit(app.clone(), receiver);
    Ok(())
}

/// Attempts sidecar startup without making ordinary service unavailability fatal
/// to the Tauri application shell. The reason remains Rust-owned state only.
pub fn start_nonfatal<R: Runtime>(app: &AppHandle<R>) {
    if let Err(error) = start(app) {
        app.state::<ServiceState>().mark_unavailable(&error);
    }
}

pub fn request_shutdown<R: Runtime>(app: &AppHandle<R>) {
    let state = app.state::<ServiceState>();
    let mut process = state
        .process
        .lock()
        .expect("service process lock poisoned")
        .take();
    if let Some(mut process) = process.take() {
        let _ = process.child.write(b"{\"type\":\"shutdown\"}\n");
        let deadline = Instant::now() + SHUTDOWN_TIMEOUT;
        while Instant::now() < deadline {
            if state.status().state == "unavailable" {
                return;
            }
            thread::sleep(Duration::from_millis(10));
        }
        let _ = process.child.kill();
    }
    state.set_status("stopped");
}

#[tauri::command]
pub async fn service_health(
    state: tauri::State<'_, ServiceState>,
) -> Result<ServiceStatus, String> {
    let target = {
        let process = state.process.lock().expect("service process lock poisoned");
        process
            .as_ref()
            .map(|process| (process.port, process.token.clone()))
    };
    let Some((port, token)) = target else {
        return Ok(state.status());
    };
    authenticate_health(port, &token).await?;
    Ok(state.status())
}

fn development_port() -> Result<u16, String> {
    std::env::var("ION_API_PORT")
        .unwrap_or_else(|_| "8765".into())
        .parse::<u16>()
        .ok()
        .filter(|port| *port > 0)
        .ok_or_else(|| "unavailable".into())
}

fn product_target(state: &ServiceState) -> Result<(String, Option<String>), ProductError> {
    if cfg!(debug_assertions) {
        let port = development_port().map_err(|_| ProductError::unavailable())?;
        return Ok((format!("http://127.0.0.1:{port}"), None));
    }
    let process = state
        .process
        .lock()
        .map_err(|_| ProductError::unavailable())?;
    process
        .as_ref()
        .map(|process| {
            (
                format!("http://127.0.0.1:{}", process.port),
                Some(process.token.clone()),
            )
        })
        .ok_or_else(ProductError::unavailable)
}

pub(crate) async fn product_request<T: Serialize, R: for<'de> Deserialize<'de>>(
    state: &ServiceState,
    method: reqwest::Method,
    route: &str,
    body: Option<&T>,
) -> Result<R, ProductError> {
    let (origin, token) = product_target(state)?;
    let mut request = reqwest::Client::new().request(method, format!("{origin}{route}"));
    if let Some(token) = token {
        request = request.header(SESSION_HEADER, token);
    }
    if let Some(body) = body {
        request = request.header("content-type", "application/json").body(
            serde_json::to_vec(body)
                .map_err(|_| ProductError::new(ProductErrorCode::Validation))?,
        );
    }
    let response = request
        .send()
        .await
        .map_err(|_| ProductError::unavailable())?;
    let status = response.status().as_u16();
    let bytes = response
        .bytes()
        .await
        .map_err(|_| ProductError::unavailable())?;
    match status {
        200 | 201 => serde_json::from_slice::<R>(&bytes).map_err(|_| ProductError::unavailable()),
        _ => Err(parse_product_error(status, &bytes)),
    }
}

#[tauri::command]
pub async fn list_tasks(state: tauri::State<'_, ServiceState>) -> Result<Vec<Task>, ProductError> {
    product_request::<(), Vec<Task>>(&state, reqwest::Method::GET, "/v1/tasks", None).await
}

#[tauri::command]
pub async fn list_trashed_tasks(
    state: tauri::State<'_, ServiceState>,
) -> Result<Vec<Task>, ProductError> {
    product_request::<(), Vec<Task>>(&state, reqwest::Method::GET, "/v1/tasks/trash", None).await
}

#[tauri::command]
pub async fn create_task(
    state: tauri::State<'_, ServiceState>,
    input: CreateTaskInput,
) -> Result<Task, ProductError> {
    product_request(&state, reqwest::Method::POST, "/v1/tasks", Some(&input)).await
}

#[tauri::command]
pub async fn update_task(
    state: tauri::State<'_, ServiceState>,
    task_id: String,
    input: UpdateTaskInput,
) -> Result<Task, ProductError> {
    let route = task_route(&task_id, "")?;
    product_request(&state, reqwest::Method::PATCH, &route, Some(&input)).await
}

async fn task_revision_action(
    state: tauri::State<'_, ServiceState>,
    task_id: String,
    input: RevisionInput,
    action: &str,
) -> Result<Task, ProductError> {
    let route = task_route(&task_id, &format!("/{action}"))?;
    product_request(&state, reqwest::Method::POST, &route, Some(&input)).await
}

#[tauri::command]
pub async fn complete_task(
    state: tauri::State<'_, ServiceState>,
    task_id: String,
    input: RevisionInput,
) -> Result<Task, ProductError> {
    task_revision_action(state, task_id, input, "complete").await
}

#[tauri::command]
pub async fn reopen_task(
    state: tauri::State<'_, ServiceState>,
    task_id: String,
    input: RevisionInput,
) -> Result<Task, ProductError> {
    task_revision_action(state, task_id, input, "reopen").await
}

#[tauri::command]
pub async fn trash_task(
    state: tauri::State<'_, ServiceState>,
    task_id: String,
    input: RevisionInput,
) -> Result<Task, ProductError> {
    task_revision_action(state, task_id, input, "trash").await
}

#[tauri::command]
pub async fn restore_task(
    state: tauri::State<'_, ServiceState>,
    task_id: String,
    input: RevisionInput,
) -> Result<Task, ProductError> {
    task_revision_action(state, task_id, input, "restore").await
}

#[tauri::command]
pub async fn set_task_relationships(
    state: tauri::State<'_, ServiceState>,
    task_id: String,
    input: SetTaskRelationshipsInput,
) -> Result<Task, ProductError> {
    let route = task_route(&task_id, "/relationships")?;
    product_request(&state, reqwest::Method::PUT, &route, Some(&input)).await
}

#[cfg(test)]
mod tests {
    use super::{
        bootstrap_message, encode_session_token, parse_product_error, parse_ready, task_route,
        ProductErrorCode, ServiceState, MAX_PROTOCOL_BYTES, READY_PREFIX,
    };

    #[test]
    fn token_encodes_exactly_256_bits_without_a_dependency() {
        assert_eq!(encode_session_token(&[0_u8; 32]).len(), 64);
    }

    #[test]
    fn bootstrap_is_bounded_and_newline_delimited() {
        let message = bootstrap_message("a".repeat(64).as_str()).unwrap();
        assert!(message.ends_with(b"\n"));
        assert!(!String::from_utf8_lossy(&message).contains("ION_RUNTIME_READY"));
    }

    #[test]
    fn readiness_rejects_invalid_ports() {
        assert_eq!(
            parse_ready(b"ION_RUNTIME_READY {\"port\":1234}").unwrap(),
            1234
        );
        assert!(parse_ready(b"ION_RUNTIME_READY {\"port\":0}").is_err());
        assert!(parse_ready(READY_PREFIX).is_err());
    }

    #[test]
    fn startup_failure_has_a_safe_unavailable_state_without_process_state() {
        let state = ServiceState::default();
        state.mark_unavailable("sidecar readiness timed out");

        assert_eq!(state.status().state, "unavailable");
        assert_eq!(
            state.safe_diagnostic().as_deref(),
            Some("sidecar readiness timed out")
        );
        assert!(state
            .process
            .lock()
            .expect("service process lock poisoned")
            .is_none());
    }

    #[test]
    fn successful_state_clears_a_previous_safe_diagnostic() {
        let state = ServiceState::default();
        state.mark_unavailable("sidecar exited before readiness");
        state.clear_diagnostic();
        state.set_status("ready");

        assert_eq!(state.status().state, "ready");
        assert_eq!(state.safe_diagnostic(), None);
    }

    #[test]
    fn product_errors_preserve_safe_blockers_and_serialize_narrowly() {
        let error = parse_product_error(
            409,
            br#"{"detail":{"code":"trash_blocked","blockers":[{"entity":"project","count":2}]}}"#,
        );
        assert_eq!(error.code, ProductErrorCode::TrashBlocked);
        assert_eq!(error.blockers[0].entity, "project");
        assert_eq!(error.blockers[0].count, 2);

        let serialized = serde_json::to_string(&error).unwrap();
        assert_eq!(
            serialized,
            r#"{"code":"trash_blocked","blockers":[{"entity":"project","count":2}]}"#
        );
    }

    #[test]
    fn malformed_or_oversized_backend_errors_fall_back_without_body_leakage() {
        assert_eq!(
            parse_product_error(409, b"private traceback").code,
            ProductErrorCode::RevisionConflict
        );
        assert_eq!(
            parse_product_error(500, b"private traceback").code,
            ProductErrorCode::Unavailable
        );
        assert_eq!(
            parse_product_error(422, &vec![b'x'; MAX_PROTOCOL_BYTES + 1]).code,
            ProductErrorCode::Unavailable
        );
    }

    #[test]
    fn task_routes_reject_renderer_control_of_path_segments() {
        let id = "11111111-1111-4111-8111-111111111111";
        assert_eq!(
            task_route(id, "/relationships").unwrap(),
            format!("/v1/tasks/{id}/relationships")
        );
        assert!(task_route("../health", "").is_err());
    }
}
