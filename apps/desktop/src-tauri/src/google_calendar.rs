//! Rust-owned Google OAuth, Keychain credentials, HTTPS, and fixed sync commands.

use std::{
    collections::{HashMap, HashSet},
    fs,
    io::{Read, Write},
    net::{TcpListener, TcpStream},
    path::{Path, PathBuf},
    process::Command,
    sync::{
        atomic::{AtomicBool, Ordering},
        Mutex,
    },
    time::{Duration, Instant},
};

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use getrandom::fill;
use reqwest::{Client, StatusCode, Url};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Manager, Runtime, State};

use crate::service::{product_request, ProductError, ProductErrorCode, ServiceState};

const CALENDAR_LIST_SCOPE: &str = "https://www.googleapis.com/auth/calendar.calendarlist.readonly";
const EVENTS_READ_SCOPE: &str = "https://www.googleapis.com/auth/calendar.events.readonly";
const EVENTS_WRITE_SCOPE: &str = "https://www.googleapis.com/auth/calendar.events";
const AUTH_ENDPOINT: &str = "https://accounts.google.com/o/oauth2/v2/auth";
const TOKEN_ENDPOINT: &str = "https://oauth2.googleapis.com/token";
const REVOKE_ENDPOINT: &str = "https://oauth2.googleapis.com/revoke";
const CALENDAR_API: &str = "https://www.googleapis.com/calendar/v3/";
const CALLBACK_PATH: &str = "/oauth2/callback";
const CONFIG_FILENAME: &str = "google-oauth.json";
const KEYCHAIN_SERVICE: &str = "com.ionos.desktop.google-calendar";
const MAX_CONFIG_BYTES: u64 = 65_536;
const MAX_CALLBACK_BYTES: usize = 8_192;
const CALLBACK_TIMEOUT: Duration = Duration::from_secs(300);
const PROVIDER_TIMEOUT: Duration = Duration::from_secs(30);
const MAX_PROVIDER_ATTEMPTS: u32 = 3;

#[allow(dead_code)] // Write mode is deliberately unbound from a renderer command in 2C-1.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum OAuthScopeMode {
    ReadOnly,
    CalendarWriteReconsent,
}

impl OAuthScopeMode {
    fn scopes(self) -> [&'static str; 2] {
        match self {
            Self::ReadOnly => [CALENDAR_LIST_SCOPE, EVENTS_READ_SCOPE],
            Self::CalendarWriteReconsent => [CALENDAR_LIST_SCOPE, EVENTS_WRITE_SCOPE],
        }
    }

    fn query(self) -> String {
        self.scopes().join(" ")
    }
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct OAuthConfig {
    client_id: String,
    #[serde(default)]
    client_secret: Option<String>,
}

impl OAuthConfig {
    fn validate(self) -> Result<Self, GoogleCommandError> {
        let valid_id = self.client_id.ends_with(".apps.googleusercontent.com")
            && self.client_id.len() <= 4096
            && !self.client_id.chars().any(char::is_whitespace);
        let valid_secret = match self.client_secret.as_ref() {
            Some(value) => !value.is_empty() && value.len() <= 4096,
            None => true,
        };
        if !valid_id || !valid_secret {
            return Err(GoogleCommandError::new("configuration_invalid"));
        }
        Ok(self)
    }
}

#[derive(Debug, Clone)]
struct CachedAccessToken {
    value: String,
    expires_at: Instant,
}

pub struct GoogleState {
    access_tokens: Mutex<HashMap<String, CachedAccessToken>>,
    sync_active: AtomicBool,
}

impl Default for GoogleState {
    fn default() -> Self {
        Self {
            access_tokens: Mutex::new(HashMap::new()),
            sync_active: AtomicBool::new(false),
        }
    }
}

struct SyncGuard<'a>(&'a AtomicBool);

impl Drop for SyncGuard<'_> {
    fn drop(&mut self) {
        self.0.store(false, Ordering::Release);
    }
}

impl GoogleState {
    fn begin_sync(&self) -> Result<SyncGuard<'_>, GoogleCommandError> {
        self.sync_active
            .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
            .map_err(|_| GoogleCommandError::new("busy"))?;
        Ok(SyncGuard(&self.sync_active))
    }

    fn cached_token(&self, account_id: &str) -> Option<String> {
        self.access_tokens
            .lock()
            .expect("Google access token lock poisoned")
            .get(account_id)
            .filter(|token| token.expires_at > Instant::now() + Duration::from_secs(60))
            .map(|token| token.value.clone())
    }

    fn store_access_token(&self, account_id: &str, value: String, expires_in: u64) {
        self.access_tokens
            .lock()
            .expect("Google access token lock poisoned")
            .insert(
                account_id.to_owned(),
                CachedAccessToken {
                    value,
                    expires_at: Instant::now() + Duration::from_secs(expires_in.saturating_sub(30)),
                },
            );
    }

    fn forget_account(&self, account_id: &str) {
        self.access_tokens
            .lock()
            .expect("Google access token lock poisoned")
            .remove(account_id);
    }
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct GoogleCommandError {
    code: String,
}

impl GoogleCommandError {
    fn new(code: &str) -> Self {
        Self { code: code.into() }
    }
}

impl From<ProductError> for GoogleCommandError {
    fn from(error: ProductError) -> Self {
        Self::new(match error.code {
            ProductErrorCode::Unavailable => "local_service_unavailable",
            ProductErrorCode::RevisionConflict => "local_state_conflict",
            ProductErrorCode::NotFound => "local_state_not_found",
            ProductErrorCode::Validation
            | ProductErrorCode::AssignmentUnavailable
            | ProductErrorCode::TrashBlocked => "local_state_invalid",
        })
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct GoogleAccount {
    pub id: String,
    pub provider_account_id: String,
    pub display_name: String,
    pub granted_scopes: Vec<String>,
    pub auth_state: String,
    pub calendar_write_scope_state: String,
    pub last_auth_at: Option<String>,
    pub created_at: String,
    pub updated_at: String,
    pub revision: i64,
}

#[derive(Debug, Clone, Deserialize)]
struct InternalGoogleAccount {
    #[serde(flatten)]
    account: GoogleAccount,
    keychain_locator: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct GoogleCalendar {
    pub id: String,
    pub account_id: String,
    pub provider_calendar_id: String,
    pub summary: String,
    pub description: Option<String>,
    pub location: Option<String>,
    pub timezone: Option<String>,
    pub access_role: String,
    pub is_primary: bool,
    pub provider_selected: bool,
    pub provider_hidden: bool,
    pub enabled_in_ion: bool,
    pub hidden_in_ion: bool,
    pub provider_deleted: bool,
    pub has_sync_token: bool,
    pub sync_state: String,
    pub last_synced_at: Option<String>,
    pub last_error_code: Option<String>,
    pub retry_count: i64,
    pub next_retry_at: Option<String>,
    pub revision: i64,
    pub provider_write_eligible: bool,
    pub provider_write_reason: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ProviderWriteCapability {
    pub eligible: bool,
    pub reason: String,
}

#[derive(Debug, Clone, Deserialize)]
struct InternalGoogleCalendar {
    #[serde(flatten)]
    calendar: GoogleCalendar,
    next_sync_token: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CalendarBlock {
    pub id: String,
    pub calendar_id: String,
    pub provider_event_id: String,
    pub ical_uid: Option<String>,
    pub title: String,
    pub description: Option<String>,
    pub location: Option<String>,
    pub temporal_kind: String,
    pub start_date: Option<String>,
    pub end_date: Option<String>,
    pub start_at: Option<String>,
    pub end_at: Option<String>,
    pub start_timezone: Option<String>,
    pub end_timezone: Option<String>,
    pub status: String,
    pub transparency: String,
    pub recurrence_kind: String,
    pub recurrence_rules: Vec<String>,
    pub recurrence_master_block_id: Option<String>,
    pub recurring_event_id: Option<String>,
    pub original_start_kind: String,
    pub original_start_date: Option<String>,
    pub original_start_at: Option<String>,
    pub original_start_timezone: Option<String>,
    pub flexibility: String,
    pub notes: Option<String>,
    pub category: Option<String>,
    #[serde(default)]
    pub category_subtype: Option<String>,
    pub ion_metadata_revision: i64,
    pub provider_deleted_at: Option<String>,
    pub revision: i64,
    pub provider_write_capability: ProviderWriteCapability,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ProviderWriteIntentSummary {
    pub id: String,
    pub calendar_block_id: String,
    pub operation: String,
    pub recurrence_scope: String,
    pub changed_fields: Vec<String>,
    pub state: String,
    pub attempt_count: i64,
    pub next_attempt_at: Option<String>,
    pub failure_class: Option<String>,
    pub failure_reason: Option<String>,
    pub created_at: String,
    pub updated_at: String,
    pub resolved_at: Option<String>,
    pub provenance: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct AccountWriteCapability {
    pub account_id: String,
    pub state: String,
    pub write_capable: bool,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CalendarWriteCapability {
    pub calendar_id: String,
    pub eligible: bool,
    pub reason: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct BlockWriteCapability {
    pub calendar_block_id: String,
    pub eligible: bool,
    pub reason: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CalendarWriteFoundation {
    pub accounts: Vec<AccountWriteCapability>,
    pub calendars: Vec<CalendarWriteCapability>,
    pub blocks: Vec<BlockWriteCapability>,
    pub pending: Vec<ProviderWriteIntentSummary>,
}

#[allow(dead_code)] // Fixed Rust-internal DTOs are activated by later 2C dispatch work.
#[derive(Debug, Clone, Deserialize, Serialize)]
struct ProviderWriteValues {
    schema_version: i64,
    title: Option<String>,
    description: Option<String>,
    location: Option<String>,
    transparency: Option<String>,
    start: Option<ProviderDateTime>,
    end: Option<ProviderDateTime>,
    recurrence: Option<Vec<String>>,
    status: Option<String>,
}

#[allow(dead_code)]
#[derive(Serialize)]
struct QueueProviderWriteIntentInput {
    command_id: String,
    calendar_block_id: String,
    operation: String,
    recurrence_scope: String,
    changed_fields: Vec<String>,
    base_values: Option<ProviderWriteValues>,
    desired_values: Option<ProviderWriteValues>,
    expected_block_revision: i64,
    provenance: String,
}

#[allow(dead_code)]
#[derive(Serialize)]
struct ReadyProviderWriteIntentsInput {
    now: String,
    limit: u16,
}

#[allow(dead_code)]
#[derive(Serialize)]
struct RecoverProviderWriteIntentsInput {
    now: String,
    limit: u16,
}

#[allow(dead_code)]
#[derive(Serialize)]
struct PruneProviderWriteIntentsInput {
    now: String,
    limit: u16,
}

#[allow(dead_code)]
#[derive(Serialize)]
struct TransitionProviderWriteIntentInput {
    expected_state: String,
    target_state: String,
    occurred_at: String,
    executor_provenance: String,
    result_class: Option<String>,
    safe_reason: Option<String>,
    next_attempt_at: Option<String>,
    resulting_revision: Option<i64>,
}

#[allow(dead_code)]
#[derive(Debug, Clone, Deserialize)]
struct ProviderWritePlan {
    #[serde(flatten)]
    summary: ProviderWriteIntentSummary,
    account_id: String,
    calendar_id: String,
    provider_event_id: String,
    expected_provider_etag: Option<String>,
    base_values: Option<ProviderWriteValues>,
    desired_values: Option<ProviderWriteValues>,
    source_block_revision: i64,
    schema_version: i64,
}

#[allow(dead_code)]
#[derive(Deserialize)]
struct RecoveryResult {
    attempting_to_ambiguous: u16,
    retry_wait_to_ready: u16,
}

#[allow(dead_code)]
#[derive(Deserialize)]
struct PruneResult {
    pruned: u16,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CalendarStatus {
    pub configured: bool,
    #[serde(default)]
    pub configuration_path: String,
    pub accounts: Vec<GoogleAccount>,
    pub calendars: Vec<GoogleCalendar>,
    pub blocks: Vec<CalendarBlock>,
}

#[derive(Debug, Clone, Deserialize)]
struct InternalCalendarState {
    accounts: Vec<InternalGoogleAccount>,
    calendars: Vec<InternalGoogleCalendar>,
}

#[derive(Serialize)]
struct EmptyInput {}

#[derive(Serialize)]
struct SelectionInput {
    enabled: bool,
    expected_revision: i64,
}

#[derive(Serialize)]
struct VisibilityInput {
    hidden: bool,
    expected_revision: i64,
}

#[derive(Serialize)]
struct CategoryInput<'a> {
    category: Option<&'a str>,
    category_subtype: Option<&'a str>,
    expected_revision: i64,
}

#[derive(Serialize)]
struct SyncBeginInput<'a> {
    generation: &'a str,
    mode: &'a str,
}

#[derive(Serialize)]
struct SyncPageInput<'a> {
    generation: &'a str,
    events: &'a [ProviderEvent],
}

#[derive(Serialize)]
struct SyncCompleteInput<'a> {
    generation: &'a str,
    next_sync_token: &'a str,
}

#[derive(Serialize)]
struct SyncFailureInput<'a> {
    error_code: &'a str,
    retry_count: u32,
    next_retry_at: Option<&'a str>,
}

#[derive(Deserialize)]
struct TokenResponse {
    access_token: String,
    #[serde(default)]
    refresh_token: Option<String>,
    expires_in: u64,
    scope: String,
    token_type: String,
}

#[derive(Deserialize)]
struct RefreshResponse {
    access_token: String,
    expires_in: u64,
    token_type: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct CalendarListPage {
    #[serde(default)]
    items: Vec<ProviderCalendarRaw>,
    next_page_token: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ProviderCalendarRaw {
    id: String,
    #[serde(default)]
    summary: String,
    summary_override: Option<String>,
    description: Option<String>,
    location: Option<String>,
    time_zone: Option<String>,
    #[serde(default)]
    access_role: String,
    etag: Option<String>,
    #[serde(default)]
    primary: bool,
    #[serde(default)]
    selected: bool,
    #[serde(default)]
    hidden: bool,
    #[serde(default)]
    deleted: bool,
}

#[derive(Debug, Clone, Serialize)]
struct ProviderCalendar {
    provider_calendar_id: String,
    summary: Option<String>,
    description: Option<String>,
    location: Option<String>,
    timezone: Option<String>,
    access_role: String,
    provider_etag: Option<String>,
    is_primary: bool,
    provider_selected: bool,
    provider_hidden: bool,
    provider_deleted: bool,
}

fn provider_calendar(item: ProviderCalendarRaw) -> ProviderCalendar {
    let summary = item
        .summary_override
        .filter(|value| !value.trim().is_empty())
        .or_else(|| {
            if item.summary.trim().is_empty() {
                None
            } else {
                Some(item.summary)
            }
        });
    ProviderCalendar {
        provider_calendar_id: item.id,
        summary,
        description: item.description,
        location: item.location,
        timezone: item.time_zone,
        access_role: if item.access_role.is_empty() {
            "none".into()
        } else {
            item.access_role
        },
        provider_etag: item.etag,
        is_primary: item.primary,
        provider_selected: item.selected,
        provider_hidden: item.hidden,
        provider_deleted: item.deleted,
    }
}

#[derive(Serialize)]
struct ConnectAccountInput<'a> {
    provider_account_id: &'a str,
    display_name: &'a str,
    granted_scopes: [&'static str; 2],
    keychain_locator: &'a str,
    calendars: &'a [ProviderCalendar],
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct EventsPage {
    #[serde(default)]
    items: Vec<ProviderEventRaw>,
    next_page_token: Option<String>,
    next_sync_token: Option<String>,
}

#[derive(Debug, Deserialize)]
struct GoogleErrorEnvelope {
    error: GoogleErrorBody,
}

#[derive(Debug, Deserialize)]
struct GoogleErrorBody {
    #[serde(default)]
    errors: Vec<GoogleErrorDetail>,
}

#[derive(Debug, Deserialize)]
struct GoogleErrorDetail {
    reason: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ProviderEventRaw {
    id: String,
    i_cal_uid: Option<String>,
    etag: Option<String>,
    updated: Option<String>,
    summary: Option<String>,
    description: Option<String>,
    location: Option<String>,
    status: Option<String>,
    transparency: Option<String>,
    start: Option<ProviderDateTimeRaw>,
    end: Option<ProviderDateTimeRaw>,
    #[serde(default)]
    recurrence: Vec<String>,
    recurring_event_id: Option<String>,
    original_start_time: Option<ProviderDateTimeRaw>,
    event_type: Option<String>,
    #[serde(default)]
    locked: bool,
    attendees: Option<Vec<serde_json::Value>>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ProviderDateTimeRaw {
    date: Option<String>,
    date_time: Option<String>,
    time_zone: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
struct ProviderDateTime {
    date: Option<String>,
    date_time: Option<String>,
    timezone: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
struct ProviderEvent {
    provider_event_id: String,
    ical_uid: Option<String>,
    provider_etag: Option<String>,
    provider_updated_at: Option<String>,
    title: Option<String>,
    description: Option<String>,
    location: Option<String>,
    status: String,
    transparency: String,
    start: Option<ProviderDateTime>,
    end: Option<ProviderDateTime>,
    recurrence: Vec<String>,
    recurring_event_id: Option<String>,
    original_start: Option<ProviderDateTime>,
    provider_event_type: String,
    provider_locked: bool,
    has_attendees: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ProviderFailure {
    Gone,
    Reauth,
    RateLimited,
    Unavailable,
    Rejected(ProviderRejection),
    InvalidResponse,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ProviderRejection {
    BadRequest,
    Forbidden,
    NotFound,
    InsufficientPermissions,
    ApiDisabled,
    Other,
}

#[allow(dead_code)] // Sent only after a later phase authorizes provider dispatch.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ProviderWriteMethod {
    Insert,
    Get,
    Patch,
    Delete,
    Instances,
}

#[allow(dead_code)]
impl ProviderWriteMethod {
    fn from_inventory_name(value: &str) -> Option<Self> {
        match value {
            "events.insert" => Some(Self::Insert),
            "events.get" => Some(Self::Get),
            "events.patch" => Some(Self::Patch),
            "events.delete" => Some(Self::Delete),
            "events.instances" => Some(Self::Instances),
            _ => None,
        }
    }

    fn inventory_name(self) -> &'static str {
        match self {
            Self::Insert => "events.insert",
            Self::Get => "events.get",
            Self::Patch => "events.patch",
            Self::Delete => "events.delete",
            Self::Instances => "events.instances",
        }
    }
}

#[allow(dead_code)]
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct AllowedWriteDateTime {
    #[serde(skip_serializing_if = "Option::is_none")]
    date: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    date_time: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    time_zone: Option<String>,
}

#[allow(dead_code)]
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct AllowedProviderWriteBody {
    #[serde(skip_serializing_if = "Option::is_none")]
    id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    summary: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    location: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    transparency: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    start: Option<AllowedWriteDateTime>,
    #[serde(skip_serializing_if = "Option::is_none")]
    end: Option<AllowedWriteDateTime>,
    #[serde(skip_serializing_if = "Option::is_none")]
    recurrence: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    status: Option<String>,
}

#[allow(dead_code)]
impl AllowedProviderWriteBody {
    fn validate(&self, method: ProviderWriteMethod) -> Result<(), GoogleCommandError> {
        if method == ProviderWriteMethod::Insert {
            let id = self
                .id
                .as_deref()
                .ok_or_else(|| GoogleCommandError::new("provider_write_invalid"))?;
            if id.len() != 32
                || !id
                    .bytes()
                    .all(|byte| byte.is_ascii_digit() || (b'a'..=b'v').contains(&byte))
            {
                return Err(GoogleCommandError::new("provider_write_invalid"));
            }
        } else if self.id.is_some() {
            return Err(GoogleCommandError::new("provider_write_invalid"));
        }
        if self
            .summary
            .as_ref()
            .is_some_and(|value| value.len() > 65_536)
            || self
                .description
                .as_ref()
                .is_some_and(|value| value.len() > 262_144)
            || self
                .location
                .as_ref()
                .is_some_and(|value| value.len() > 65_536)
            || self
                .recurrence
                .as_ref()
                .is_some_and(|values| values.len() > 128 || values.iter().any(|v| v.len() > 4096))
        {
            return Err(GoogleCommandError::new("provider_write_invalid"));
        }
        Ok(())
    }
}

#[allow(dead_code)]
fn provider_write_url(
    method: ProviderWriteMethod,
    provider_calendar_id: &str,
    provider_event_id: Option<&str>,
) -> Result<Url, GoogleCommandError> {
    if provider_calendar_id.is_empty() {
        return Err(GoogleCommandError::new("provider_write_invalid"));
    }
    let needs_event = method != ProviderWriteMethod::Insert;
    if needs_event != provider_event_id.is_some_and(|value| !value.is_empty()) {
        return Err(GoogleCommandError::new("provider_write_invalid"));
    }
    let mut url =
        Url::parse(CALENDAR_API).map_err(|_| GoogleCommandError::new("provider_write_invalid"))?;
    let mut segments = url
        .path_segments_mut()
        .map_err(|_| GoogleCommandError::new("provider_write_invalid"))?;
    segments
        .pop_if_empty()
        .extend(["calendars", provider_calendar_id, "events"]);
    if let Some(event_id) = provider_event_id {
        segments.push(event_id);
    }
    if method == ProviderWriteMethod::Instances {
        segments.push("instances");
    }
    drop(segments);
    Ok(url)
}

#[allow(dead_code)]
fn provider_write_request(
    client: &Client,
    method: ProviderWriteMethod,
    access_token: &str,
    provider_calendar_id: &str,
    provider_event_id: Option<&str>,
    expected_etag: Option<&str>,
    body: Option<&AllowedProviderWriteBody>,
) -> Result<reqwest::Request, GoogleCommandError> {
    let requires_body = matches!(
        method,
        ProviderWriteMethod::Insert | ProviderWriteMethod::Patch
    );
    if requires_body != body.is_some() {
        return Err(GoogleCommandError::new("provider_write_invalid"));
    }
    if let Some(body) = body {
        body.validate(method)?;
    }
    let requires_etag = matches!(
        method,
        ProviderWriteMethod::Patch | ProviderWriteMethod::Delete
    );
    if requires_etag != expected_etag.is_some() {
        return Err(GoogleCommandError::new("provider_write_invalid"));
    }
    if expected_etag.is_some_and(|value| value.is_empty() || value == "*" || value.len() > 4096) {
        return Err(GoogleCommandError::new("provider_write_invalid"));
    }
    let http_method = match method {
        ProviderWriteMethod::Insert => reqwest::Method::POST,
        ProviderWriteMethod::Get | ProviderWriteMethod::Instances => reqwest::Method::GET,
        ProviderWriteMethod::Patch => reqwest::Method::PATCH,
        ProviderWriteMethod::Delete => reqwest::Method::DELETE,
    };
    let mut request = client
        .request(
            http_method,
            provider_write_url(method, provider_calendar_id, provider_event_id)?,
        )
        .bearer_auth(access_token);
    if let Some(etag) = expected_etag {
        request = request.header(reqwest::header::IF_MATCH, etag);
    }
    if let Some(body) = body {
        request = request.json(body);
    }
    request
        .build()
        .map_err(|_| GoogleCommandError::new("provider_write_invalid"))
}

#[allow(dead_code)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
enum ProviderWriteResultClass {
    Success,
    RetryableTransport,
    RetryableBackend,
    RetryableQuota,
    ReauthenticationRequired,
    StalePrecondition,
    DuplicateOrAmbiguousCreate,
    ProviderNotFound,
    InvalidTarget,
    TerminalProviderRejection,
}

#[allow(dead_code)]
fn classify_write_transport_failure(method: ProviderWriteMethod) -> ProviderWriteResultClass {
    if method == ProviderWriteMethod::Insert {
        ProviderWriteResultClass::DuplicateOrAmbiguousCreate
    } else {
        ProviderWriteResultClass::RetryableTransport
    }
}

#[allow(dead_code)]
fn classify_write_provider_result(
    method: ProviderWriteMethod,
    status: StatusCode,
    body: &[u8],
) -> ProviderWriteResultClass {
    if status.is_success() {
        return ProviderWriteResultClass::Success;
    }
    let reason = serde_json::from_slice::<GoogleErrorEnvelope>(body)
        .ok()
        .and_then(|value| value.error.errors.into_iter().next())
        .map(|detail| detail.reason);
    match (status, reason.as_deref()) {
        (StatusCode::UNAUTHORIZED, _) => ProviderWriteResultClass::ReauthenticationRequired,
        (StatusCode::PRECONDITION_FAILED, _) => ProviderWriteResultClass::StalePrecondition,
        (StatusCode::CONFLICT, Some("duplicate")) if method == ProviderWriteMethod::Insert => {
            ProviderWriteResultClass::DuplicateOrAmbiguousCreate
        }
        (StatusCode::NOT_FOUND, _) => ProviderWriteResultClass::ProviderNotFound,
        (StatusCode::TOO_MANY_REQUESTS, _)
        | (
            StatusCode::FORBIDDEN,
            Some(
                "rateLimitExceeded"
                | "userRateLimitExceeded"
                | "quotaExceeded"
                | "dailyLimitExceeded",
            ),
        ) => ProviderWriteResultClass::RetryableQuota,
        (_, _) if status.is_server_error() => ProviderWriteResultClass::RetryableBackend,
        (StatusCode::BAD_REQUEST, _) => ProviderWriteResultClass::InvalidTarget,
        _ => ProviderWriteResultClass::TerminalProviderRejection,
    }
}

fn should_reset_to_full(mode: &str, failure: &ProviderFailure) -> bool {
    mode == "incremental" && matches!(failure, ProviderFailure::Gone)
}

trait RefreshTokenStore {
    fn set(&self, locator: &str, value: &str) -> Result<(), GoogleCommandError>;
    fn get(&self, locator: &str) -> Result<String, GoogleCommandError>;
    fn delete(&self, locator: &str) -> Result<(), GoogleCommandError>;
}

struct SystemKeychain;

#[cfg(target_os = "macos")]
impl RefreshTokenStore for SystemKeychain {
    fn set(&self, locator: &str, value: &str) -> Result<(), GoogleCommandError> {
        security_framework::passwords::set_generic_password(
            KEYCHAIN_SERVICE,
            locator,
            value.as_bytes(),
        )
        .map_err(|_| GoogleCommandError::new("keychain_unavailable"))
    }

    fn get(&self, locator: &str) -> Result<String, GoogleCommandError> {
        let bytes = security_framework::passwords::get_generic_password(KEYCHAIN_SERVICE, locator)
            .map_err(|_| GoogleCommandError::new("reauth_required"))?;
        String::from_utf8(bytes).map_err(|_| GoogleCommandError::new("reauth_required"))
    }

    fn delete(&self, locator: &str) -> Result<(), GoogleCommandError> {
        security_framework::passwords::delete_generic_password(KEYCHAIN_SERVICE, locator)
            .map_err(|_| GoogleCommandError::new("keychain_unavailable"))
    }
}

#[cfg(not(target_os = "macos"))]
impl RefreshTokenStore for SystemKeychain {
    fn set(&self, _: &str, _: &str) -> Result<(), GoogleCommandError> {
        Err(GoogleCommandError::new("keychain_unavailable"))
    }

    fn get(&self, _: &str) -> Result<String, GoogleCommandError> {
        Err(GoogleCommandError::new("keychain_unavailable"))
    }

    fn delete(&self, _: &str) -> Result<(), GoogleCommandError> {
        Err(GoogleCommandError::new("keychain_unavailable"))
    }
}

fn oauth_config_path<R: Runtime>(app: &AppHandle<R>) -> Result<PathBuf, GoogleCommandError> {
    app.path()
        .app_data_dir()
        .map(|directory| directory.join(CONFIG_FILENAME))
        .map_err(|_| GoogleCommandError::new("configuration_unavailable"))
}

fn load_oauth_config(path: &Path) -> Result<OAuthConfig, GoogleCommandError> {
    let metadata = fs::metadata(path).map_err(|_| GoogleCommandError::new("not_configured"))?;
    if metadata.len() > MAX_CONFIG_BYTES || !metadata.is_file() {
        return Err(GoogleCommandError::new("configuration_invalid"));
    }
    let bytes = fs::read(path).map_err(|_| GoogleCommandError::new("configuration_invalid"))?;
    serde_json::from_slice::<OAuthConfig>(&bytes)
        .map_err(|_| GoogleCommandError::new("configuration_invalid"))?
        .validate()
}

fn random_bytes<const N: usize>() -> Result<[u8; N], GoogleCommandError> {
    let mut bytes = [0_u8; N];
    fill(&mut bytes).map_err(|_| GoogleCommandError::new("secure_random_unavailable"))?;
    Ok(bytes)
}

fn new_uuid() -> Result<String, GoogleCommandError> {
    let mut bytes = random_bytes::<16>()?;
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    Ok(format!(
        "{:02x}{:02x}{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}",
        bytes[0],
        bytes[1],
        bytes[2],
        bytes[3],
        bytes[4],
        bytes[5],
        bytes[6],
        bytes[7],
        bytes[8],
        bytes[9],
        bytes[10],
        bytes[11],
        bytes[12],
        bytes[13],
        bytes[14],
        bytes[15]
    ))
}

fn pkce_pair() -> Result<(String, String), GoogleCommandError> {
    let verifier = URL_SAFE_NO_PAD.encode(random_bytes::<64>()?);
    let challenge = URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes()));
    Ok((verifier, challenge))
}

fn authorization_url(
    config: &OAuthConfig,
    redirect_uri: &str,
    state: &str,
    challenge: &str,
    scope_mode: OAuthScopeMode,
) -> Result<Url, GoogleCommandError> {
    let mut url = Url::parse(AUTH_ENDPOINT).map_err(|_| GoogleCommandError::new("oauth_failed"))?;
    url.query_pairs_mut()
        .append_pair("client_id", &config.client_id)
        .append_pair("redirect_uri", redirect_uri)
        .append_pair("response_type", "code")
        .append_pair("scope", &scope_mode.query())
        .append_pair("code_challenge", challenge)
        .append_pair("code_challenge_method", "S256")
        .append_pair("state", state)
        .append_pair("access_type", "offline")
        .append_pair("prompt", "consent");
    Ok(url)
}

#[cfg(target_os = "macos")]
fn open_system_browser(url: &Url) -> Result<(), GoogleCommandError> {
    Command::new("/usr/bin/open")
        .arg(url.as_str())
        .spawn()
        .map(|_| ())
        .map_err(|_| GoogleCommandError::new("browser_unavailable"))
}

#[cfg(not(target_os = "macos"))]
fn open_system_browser(_: &Url) -> Result<(), GoogleCommandError> {
    Err(GoogleCommandError::new("browser_unavailable"))
}

fn callback_code(target: &str, expected_state: &str) -> Result<String, GoogleCommandError> {
    if target.len() > MAX_CALLBACK_BYTES {
        return Err(GoogleCommandError::new("oauth_callback_invalid"));
    }
    let url = Url::parse(&format!("http://127.0.0.1{target}"))
        .map_err(|_| GoogleCommandError::new("oauth_callback_invalid"))?;
    if url.path() != CALLBACK_PATH {
        return Err(GoogleCommandError::new("oauth_callback_invalid"));
    }
    let values: HashMap<_, _> = url.query_pairs().into_owned().collect();
    if values.get("state").map(String::as_str) != Some(expected_state) {
        return Err(GoogleCommandError::new("oauth_state_mismatch"));
    }
    if values.contains_key("error") {
        return Err(GoogleCommandError::new("oauth_cancelled"));
    }
    values
        .get("code")
        .filter(|value| !value.is_empty() && value.len() <= 4096)
        .cloned()
        .ok_or_else(|| GoogleCommandError::new("oauth_callback_invalid"))
}

fn callback_response(stream: &mut TcpStream, success: bool) {
    let message = if success {
        "Ion received Google authorization. You can close this tab."
    } else {
        "Ion could not validate this authorization. Return to Ion and try again."
    };
    let body = format!("<!doctype html><meta charset=\"utf-8\"><title>Ion</title><p>{message}</p>");
    let response = format!(
        "HTTP/1.1 {}\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n{}",
        if success { "200 OK" } else { "400 Bad Request" },
        body.len(),
        body
    );
    let _ = stream.write_all(response.as_bytes());
}

fn await_callback(listener: TcpListener, state: String) -> Result<String, GoogleCommandError> {
    listener
        .set_nonblocking(true)
        .map_err(|_| GoogleCommandError::new("oauth_callback_unavailable"))?;
    let deadline = Instant::now() + CALLBACK_TIMEOUT;
    let (mut stream, peer) = loop {
        match listener.accept() {
            Ok(connection) => break connection,
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                if Instant::now() >= deadline {
                    return Err(GoogleCommandError::new("oauth_callback_timeout"));
                }
                std::thread::sleep(Duration::from_millis(25));
            }
            Err(_) => return Err(GoogleCommandError::new("oauth_callback_unavailable")),
        }
    };
    if !peer.ip().is_loopback() {
        callback_response(&mut stream, false);
        return Err(GoogleCommandError::new("oauth_callback_invalid"));
    }
    stream
        .set_read_timeout(Some(CALLBACK_TIMEOUT))
        .map_err(|_| GoogleCommandError::new("oauth_callback_unavailable"))?;
    let mut bytes = [0_u8; MAX_CALLBACK_BYTES];
    let count = stream
        .read(&mut bytes)
        .map_err(|_| GoogleCommandError::new("oauth_callback_invalid"))?;
    let request = std::str::from_utf8(&bytes[..count])
        .map_err(|_| GoogleCommandError::new("oauth_callback_invalid"))?;
    let line = request
        .lines()
        .next()
        .ok_or_else(|| GoogleCommandError::new("oauth_callback_invalid"))?;
    let mut parts = line.split_whitespace();
    if parts.next() != Some("GET") {
        callback_response(&mut stream, false);
        return Err(GoogleCommandError::new("oauth_callback_invalid"));
    }
    let target = parts
        .next()
        .ok_or_else(|| GoogleCommandError::new("oauth_callback_invalid"))?;
    let result = callback_code(target, &state);
    callback_response(&mut stream, result.is_ok());
    result
}

fn google_client() -> Result<Client, GoogleCommandError> {
    Client::builder()
        .timeout(PROVIDER_TIMEOUT)
        .user_agent("Ion-OS/0.0.0")
        .build()
        .map_err(|_| GoogleCommandError::new("provider_unavailable"))
}

async fn exchange_code(
    client: &Client,
    config: &OAuthConfig,
    code: &str,
    verifier: &str,
    redirect_uri: &str,
    scope_mode: OAuthScopeMode,
) -> Result<TokenResponse, GoogleCommandError> {
    let mut form = vec![
        ("client_id", config.client_id.as_str()),
        ("code", code),
        ("code_verifier", verifier),
        ("grant_type", "authorization_code"),
        ("redirect_uri", redirect_uri),
    ];
    if let Some(secret) = config.client_secret.as_deref() {
        form.push(("client_secret", secret));
    }
    let response = client
        .post(TOKEN_ENDPOINT)
        .form(&form)
        .send()
        .await
        .map_err(|_| GoogleCommandError::new("provider_unavailable"))?;
    if !response.status().is_success() {
        return Err(GoogleCommandError::new("oauth_exchange_failed"));
    }
    let token = response
        .json::<TokenResponse>()
        .await
        .map_err(|_| GoogleCommandError::new("oauth_exchange_failed"))?;
    let granted: HashSet<_> = token.scope.split_whitespace().collect();
    let required = HashSet::from(scope_mode.scopes());
    if token.token_type != "Bearer" || granted != required || token.refresh_token.is_none() {
        return Err(GoogleCommandError::new("oauth_scope_denied"));
    }
    Ok(token)
}

async fn discover_calendars(
    client: &Client,
    access_token: &str,
) -> Result<Vec<ProviderCalendar>, GoogleCommandError> {
    let mut calendars = Vec::new();
    let mut page_token: Option<String> = None;
    loop {
        let mut url = Url::parse(&format!("{CALENDAR_API}users/me/calendarList"))
            .map_err(|_| GoogleCommandError::new("provider_unavailable"))?;
        url.query_pairs_mut()
            .append_pair("maxResults", "250")
            .append_pair("showHidden", "true")
            .append_pair("showDeleted", "true");
        if let Some(value) = page_token.as_deref() {
            url.query_pairs_mut().append_pair("pageToken", value);
        }
        let response = client
            .get(url)
            .bearer_auth(access_token)
            .send()
            .await
            .map_err(|_| GoogleCommandError::new("provider_unavailable"))?;
        if response.status() == StatusCode::UNAUTHORIZED {
            return Err(GoogleCommandError::new("reauth_required"));
        }
        if !response.status().is_success() {
            return Err(GoogleCommandError::new("provider_unavailable"));
        }
        let page = response
            .json::<CalendarListPage>()
            .await
            .map_err(|_| GoogleCommandError::new("provider_response_invalid"))?;
        calendars.extend(page.items.into_iter().map(provider_calendar));
        page_token = page.next_page_token;
        if page_token.is_none() {
            break;
        }
    }
    if calendars.len() > 10_000 {
        return Err(GoogleCommandError::new("provider_response_invalid"));
    }
    Ok(calendars)
}

fn validated_backend_id(id: &str) -> Result<&str, GoogleCommandError> {
    let valid = id.len() == 36
        && id.bytes().enumerate().all(|(index, byte)| match index {
            8 | 13 | 18 | 23 => byte == b'-',
            _ => byte.is_ascii_hexdigit(),
        });
    if !valid {
        return Err(GoogleCommandError::new("local_state_invalid"));
    }
    Ok(id)
}

fn calendar_backend_route(id: &str, suffix: &str) -> Result<String, GoogleCommandError> {
    Ok(format!(
        "/v1/calendar/calendars/{}{suffix}",
        validated_backend_id(id)?
    ))
}

fn account_backend_route(id: &str, suffix: &str) -> Result<String, GoogleCommandError> {
    Ok(format!(
        "/v1/calendar/accounts/{}{suffix}",
        validated_backend_id(id)?
    ))
}

fn calendar_block_backend_route(id: &str, suffix: &str) -> Result<String, GoogleCommandError> {
    Ok(format!(
        "/v1/calendar/blocks/{}{suffix}",
        validated_backend_id(id)?
    ))
}

fn write_intent_backend_route(id: &str, suffix: &str) -> Result<String, GoogleCommandError> {
    Ok(format!(
        "/v1/calendar/internal/write-intents/{}{suffix}",
        validated_backend_id(id)?
    ))
}

#[allow(dead_code)]
async fn queue_provider_write_intent(
    state: &ServiceState,
    input: &QueueProviderWriteIntentInput,
) -> Result<ProviderWriteIntentSummary, GoogleCommandError> {
    product_request(
        state,
        reqwest::Method::POST,
        "/v1/calendar/internal/write-intents",
        Some(input),
    )
    .await
    .map_err(Into::into)
}

#[allow(dead_code)]
async fn ready_provider_write_intents(
    state: &ServiceState,
    input: &ReadyProviderWriteIntentsInput,
) -> Result<Vec<ProviderWritePlan>, GoogleCommandError> {
    product_request(
        state,
        reqwest::Method::POST,
        "/v1/calendar/internal/write-intents/ready",
        Some(input),
    )
    .await
    .map_err(Into::into)
}

#[allow(dead_code)]
async fn recover_provider_write_intents(
    state: &ServiceState,
    input: &RecoverProviderWriteIntentsInput,
) -> Result<RecoveryResult, GoogleCommandError> {
    product_request(
        state,
        reqwest::Method::POST,
        "/v1/calendar/internal/write-intents/recover",
        Some(input),
    )
    .await
    .map_err(Into::into)
}

#[allow(dead_code)]
async fn prune_provider_write_intents(
    state: &ServiceState,
    input: &PruneProviderWriteIntentsInput,
) -> Result<PruneResult, GoogleCommandError> {
    product_request(
        state,
        reqwest::Method::POST,
        "/v1/calendar/internal/write-intents/prune",
        Some(input),
    )
    .await
    .map_err(Into::into)
}

#[allow(dead_code)]
async fn transition_provider_write_intent(
    state: &ServiceState,
    intent_id: &str,
    input: &TransitionProviderWriteIntentInput,
) -> Result<ProviderWriteIntentSummary, GoogleCommandError> {
    let route = write_intent_backend_route(intent_id, "/transition")?;
    product_request(state, reqwest::Method::POST, &route, Some(input))
        .await
        .map_err(Into::into)
}

async fn internal_state(state: &ServiceState) -> Result<InternalCalendarState, GoogleCommandError> {
    product_request(
        state,
        reqwest::Method::POST,
        "/v1/calendar/internal/state",
        Some(&EmptyInput {}),
    )
    .await
    .map_err(Into::into)
}

async fn local_status(state: &ServiceState) -> Result<CalendarStatus, GoogleCommandError> {
    product_request::<EmptyInput, CalendarStatus>(
        state,
        reqwest::Method::GET,
        "/v1/calendar/status",
        None,
    )
    .await
    .map_err(Into::into)
}

fn configured_status<R: Runtime>(app: &AppHandle<R>, mut status: CalendarStatus) -> CalendarStatus {
    let path = oauth_config_path(app);
    status.configuration_path = path
        .as_ref()
        .map(|value| value.display().to_string())
        .unwrap_or_default();
    status.configured = path
        .as_deref()
        .ok()
        .and_then(|value| load_oauth_config(value).ok())
        .is_some();
    status
}

#[tauri::command]
pub async fn get_google_calendar_status<R: Runtime>(
    app: AppHandle<R>,
    service: State<'_, ServiceState>,
) -> Result<CalendarStatus, GoogleCommandError> {
    local_status(&service)
        .await
        .map(|status| configured_status(&app, status))
}

#[tauri::command]
pub async fn get_calendar_write_foundation(
    service: State<'_, ServiceState>,
) -> Result<CalendarWriteFoundation, GoogleCommandError> {
    product_request::<EmptyInput, CalendarWriteFoundation>(
        &service,
        reqwest::Method::GET,
        "/v1/calendar/write-foundation",
        None,
    )
    .await
    .map_err(Into::into)
}

#[tauri::command]
pub async fn connect_google_calendar<R: Runtime>(
    app: AppHandle<R>,
    service: State<'_, ServiceState>,
    google: State<'_, GoogleState>,
) -> Result<CalendarStatus, GoogleCommandError> {
    let config_path = oauth_config_path(&app)?;
    let config = load_oauth_config(&config_path)?;
    let client = google_client()?;
    let listener = TcpListener::bind("127.0.0.1:0")
        .map_err(|_| GoogleCommandError::new("oauth_callback_unavailable"))?;
    let port = listener
        .local_addr()
        .map_err(|_| GoogleCommandError::new("oauth_callback_unavailable"))?
        .port();
    let redirect_uri = format!("http://127.0.0.1:{port}{CALLBACK_PATH}");
    let state_value = URL_SAFE_NO_PAD.encode(random_bytes::<32>()?);
    let (verifier, challenge) = pkce_pair()?;
    let scope_mode = OAuthScopeMode::ReadOnly;
    let url = authorization_url(&config, &redirect_uri, &state_value, &challenge, scope_mode)?;
    open_system_browser(&url)?;
    let callback =
        tauri::async_runtime::spawn_blocking(move || await_callback(listener, state_value))
            .await
            .map_err(|_| GoogleCommandError::new("oauth_callback_unavailable"))??;
    let token = exchange_code(
        &client,
        &config,
        &callback,
        &verifier,
        &redirect_uri,
        scope_mode,
    )
    .await?;
    let calendars = discover_calendars(&client, &token.access_token).await?;
    let primary = calendars
        .iter()
        .find(|calendar| calendar.is_primary && !calendar.provider_deleted)
        .ok_or_else(|| GoogleCommandError::new("provider_response_invalid"))?;
    let primary_summary = primary
        .summary
        .as_deref()
        .unwrap_or("Untitled Google calendar");
    let previous = internal_state(&service).await?;
    let old_locator = previous
        .accounts
        .iter()
        .find(|account| account.account.provider_account_id == primary.provider_calendar_id)
        .map(|account| account.keychain_locator.clone());
    let locator = format!("ion-google-{}", new_uuid()?);
    let refresh_token = token
        .refresh_token
        .as_deref()
        .ok_or_else(|| GoogleCommandError::new("oauth_exchange_failed"))?;
    SystemKeychain.set(&locator, refresh_token)?;
    let input = ConnectAccountInput {
        provider_account_id: &primary.provider_calendar_id,
        display_name: primary_summary,
        granted_scopes: scope_mode.scopes(),
        keychain_locator: &locator,
        calendars: &calendars,
    };
    let connected = product_request::<ConnectAccountInput<'_>, CalendarStatus>(
        &service,
        reqwest::Method::POST,
        "/v1/calendar/accounts/connect",
        Some(&input),
    )
    .await;
    let status = match connected {
        Ok(status) => status,
        Err(error) => {
            let _ = SystemKeychain.delete(&locator);
            return Err(error.into());
        }
    };
    if let Some(old) = old_locator.filter(|value| value != &locator) {
        let _ = SystemKeychain.delete(&old);
    }
    let account = status
        .accounts
        .iter()
        .find(|account| account.provider_account_id == primary.provider_calendar_id)
        .ok_or_else(|| GoogleCommandError::new("local_state_invalid"))?;
    google.store_access_token(&account.id, token.access_token, token.expires_in);
    Ok(configured_status(&app, status))
}

#[tauri::command]
pub async fn set_google_calendar_enabled(
    service: State<'_, ServiceState>,
    calendar_id: String,
    enabled: bool,
    expected_revision: i64,
) -> Result<CalendarStatus, GoogleCommandError> {
    let route = calendar_backend_route(&calendar_id, "/selection")?;
    product_request(
        &service,
        reqwest::Method::PUT,
        &route,
        Some(&SelectionInput {
            enabled,
            expected_revision,
        }),
    )
    .await
    .map_err(Into::into)
}

#[tauri::command]
pub async fn set_google_calendar_hidden(
    service: State<'_, ServiceState>,
    calendar_id: String,
    hidden: bool,
    expected_revision: i64,
) -> Result<CalendarStatus, GoogleCommandError> {
    let route = calendar_backend_route(&calendar_id, "/visibility")?;
    product_request(
        &service,
        reqwest::Method::PUT,
        &route,
        Some(&VisibilityInput {
            hidden,
            expected_revision,
        }),
    )
    .await
    .map_err(Into::into)
}

fn valid_calendar_category(value: &str) -> bool {
    matches!(
        value,
        "academic"
            | "career"
            | "personal_project"
            | "routine_physical"
            | "personal"
            | "fun"
            | "ion_focus"
    )
}

fn calendar_category_requires_subtype(value: &str) -> bool {
    !matches!(value, "ion_focus")
}

fn valid_calendar_category_subtype(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value.bytes().enumerate().all(|(index, byte)| {
            byte.is_ascii_lowercase() || (index > 0 && (byte.is_ascii_digit() || byte == b'_'))
        })
}

#[tauri::command]
pub async fn set_calendar_block_category(
    service: State<'_, ServiceState>,
    block_id: String,
    category: Option<String>,
    category_subtype: Option<String>,
    expected_revision: i64,
) -> Result<CalendarStatus, GoogleCommandError> {
    let valid_category = category
        .as_deref()
        .filter(|value| valid_calendar_category(value));
    let valid_subtype = category_subtype
        .as_deref()
        .filter(|value| valid_calendar_category_subtype(value));
    if (category.is_some() && valid_category.is_none())
        || (category_subtype.is_some() && (valid_category.is_none() || valid_subtype.is_none()))
        || (valid_category.is_some_and(calendar_category_requires_subtype)
            && valid_subtype.is_none())
    {
        return Err(GoogleCommandError::new("local_state_invalid"));
    }
    let route = calendar_block_backend_route(&block_id, "/category")?;
    product_request(
        &service,
        reqwest::Method::PUT,
        &route,
        Some(&CategoryInput {
            category: valid_category,
            category_subtype: valid_subtype,
            expected_revision,
        }),
    )
    .await
    .map_err(Into::into)
}

async fn refresh_access_token(
    client: &Client,
    config: &OAuthConfig,
    refresh_token: &str,
) -> Result<RefreshResponse, ProviderFailure> {
    let mut form = vec![
        ("client_id", config.client_id.as_str()),
        ("refresh_token", refresh_token),
        ("grant_type", "refresh_token"),
    ];
    if let Some(secret) = config.client_secret.as_deref() {
        form.push(("client_secret", secret));
    }
    let response = client
        .post(TOKEN_ENDPOINT)
        .form(&form)
        .send()
        .await
        .map_err(|_| ProviderFailure::Unavailable)?;
    if response.status() == StatusCode::BAD_REQUEST || response.status() == StatusCode::UNAUTHORIZED
    {
        return Err(ProviderFailure::Reauth);
    }
    if !response.status().is_success() {
        return Err(ProviderFailure::Unavailable);
    }
    let token = response
        .json::<RefreshResponse>()
        .await
        .map_err(|_| ProviderFailure::InvalidResponse)?;
    if token.token_type != "Bearer" {
        return Err(ProviderFailure::InvalidResponse);
    }
    Ok(token)
}

fn sanitize_time(
    raw: Option<ProviderDateTimeRaw>,
    fallback_timezone: &str,
) -> Option<ProviderDateTime> {
    raw.and_then(|value| {
        if let Some(date) = value.date {
            return Some(ProviderDateTime {
                date: Some(date),
                date_time: None,
                timezone: None,
            });
        }
        value.date_time.map(|date_time| ProviderDateTime {
            date: None,
            date_time: Some(date_time),
            timezone: Some(
                value
                    .time_zone
                    .filter(|zone| !zone.is_empty())
                    .unwrap_or_else(|| fallback_timezone.to_owned()),
            ),
        })
    })
}

fn sanitize_event(raw: ProviderEventRaw, fallback_timezone: &str) -> ProviderEvent {
    let status = match raw.status.as_deref() {
        Some("tentative") => "tentative",
        Some("cancelled") => "cancelled",
        _ => "confirmed",
    };
    let provider_event_type = match raw.event_type.as_deref() {
        Some("default") | None => "default",
        Some("") => "unknown",
        Some(_) => "special",
    };
    ProviderEvent {
        provider_event_id: raw.id,
        ical_uid: raw.i_cal_uid,
        provider_etag: raw.etag,
        provider_updated_at: raw.updated,
        title: raw.summary,
        description: raw.description,
        location: raw.location,
        status: status.into(),
        transparency: if raw.transparency.as_deref() == Some("transparent") {
            "transparent".into()
        } else {
            "opaque".into()
        },
        start: sanitize_time(raw.start, fallback_timezone),
        end: sanitize_time(raw.end, fallback_timezone),
        recurrence: raw.recurrence,
        recurring_event_id: raw.recurring_event_id,
        original_start: sanitize_time(raw.original_start_time, fallback_timezone),
        provider_event_type: provider_event_type.into(),
        provider_locked: raw.locked,
        has_attendees: raw.attendees.is_some_and(|values| !values.is_empty()),
    }
}

fn events_url(
    provider_calendar_id: &str,
    sync_token: Option<&str>,
    page_token: Option<&str>,
) -> Result<Url, ProviderFailure> {
    if provider_calendar_id.is_empty()
        || sync_token.is_some_and(str::is_empty)
        || page_token.is_some_and(str::is_empty)
    {
        return Err(ProviderFailure::InvalidResponse);
    }
    let mut url = Url::parse(CALENDAR_API).map_err(|_| ProviderFailure::InvalidResponse)?;
    url.path_segments_mut()
        .map_err(|_| ProviderFailure::InvalidResponse)?
        .pop_if_empty()
        .extend(["calendars", provider_calendar_id, "events"]);
    url.query_pairs_mut()
        .append_pair("maxResults", "2500")
        .append_pair("showDeleted", "true")
        .append_pair("singleEvents", "false");
    if let Some(value) = sync_token {
        url.query_pairs_mut().append_pair("syncToken", value);
    }
    if let Some(value) = page_token {
        url.query_pairs_mut().append_pair("pageToken", value);
    }
    Ok(url)
}

fn events_request(
    client: &Client,
    access_token: &str,
    provider_calendar_id: &str,
    sync_token: Option<&str>,
    page_token: Option<&str>,
) -> Result<reqwest::RequestBuilder, ProviderFailure> {
    Ok(client
        .get(events_url(provider_calendar_id, sync_token, page_token)?)
        .bearer_auth(access_token))
}

fn classify_provider_rejection(status: StatusCode, body: &[u8]) -> ProviderFailure {
    let reason = serde_json::from_slice::<GoogleErrorEnvelope>(body)
        .ok()
        .and_then(|value| value.error.errors.into_iter().next())
        .map(|detail| detail.reason);
    match reason.as_deref() {
        Some(
            "rateLimitExceeded" | "userRateLimitExceeded" | "quotaExceeded" | "dailyLimitExceeded",
        ) => ProviderFailure::RateLimited,
        Some("insufficientPermissions") => {
            ProviderFailure::Rejected(ProviderRejection::InsufficientPermissions)
        }
        Some("accessNotConfigured") => ProviderFailure::Rejected(ProviderRejection::ApiDisabled),
        Some("notFound") => ProviderFailure::Rejected(ProviderRejection::NotFound),
        _ if status == StatusCode::BAD_REQUEST => {
            ProviderFailure::Rejected(ProviderRejection::BadRequest)
        }
        _ if status == StatusCode::FORBIDDEN => {
            ProviderFailure::Rejected(ProviderRejection::Forbidden)
        }
        _ if status == StatusCode::NOT_FOUND => {
            ProviderFailure::Rejected(ProviderRejection::NotFound)
        }
        _ => ProviderFailure::Rejected(ProviderRejection::Other),
    }
}

fn provider_failure_code(failure: &ProviderFailure) -> &'static str {
    match failure {
        ProviderFailure::Gone => "invalid_response",
        ProviderFailure::Reauth => "reauth_required",
        ProviderFailure::RateLimited => "rate_limited",
        ProviderFailure::Unavailable => "provider_unavailable",
        ProviderFailure::Rejected(ProviderRejection::BadRequest) => "provider_bad_request",
        ProviderFailure::Rejected(ProviderRejection::Forbidden) => "provider_forbidden",
        ProviderFailure::Rejected(ProviderRejection::NotFound) => "provider_not_found",
        ProviderFailure::Rejected(ProviderRejection::InsufficientPermissions) => {
            "provider_insufficient_permissions"
        }
        ProviderFailure::Rejected(ProviderRejection::ApiDisabled) => "provider_api_disabled",
        ProviderFailure::Rejected(ProviderRejection::Other) => "provider_rejected",
        ProviderFailure::InvalidResponse => "invalid_response",
    }
}

fn retry_delay(attempt: u32) -> Duration {
    Duration::from_millis(250_u64.saturating_mul(1_u64 << attempt.min(4)))
}

async fn fetch_events_page(
    client: &Client,
    access_token: &str,
    provider_calendar_id: &str,
    sync_token: Option<&str>,
    page_token: Option<&str>,
) -> Result<EventsPage, ProviderFailure> {
    for attempt in 0..MAX_PROVIDER_ATTEMPTS {
        let response = events_request(
            client,
            access_token,
            provider_calendar_id,
            sync_token,
            page_token,
        )?
        .send()
        .await;
        let response = match response {
            Ok(value) => value,
            Err(_) if attempt + 1 < MAX_PROVIDER_ATTEMPTS => {
                tokio::time::sleep(retry_delay(attempt)).await;
                continue;
            }
            Err(_) => return Err(ProviderFailure::Unavailable),
        };
        match response.status() {
            StatusCode::GONE => return Err(ProviderFailure::Gone),
            StatusCode::UNAUTHORIZED => return Err(ProviderFailure::Reauth),
            StatusCode::TOO_MANY_REQUESTS if attempt + 1 < MAX_PROVIDER_ATTEMPTS => {
                tokio::time::sleep(retry_delay(attempt)).await;
            }
            StatusCode::TOO_MANY_REQUESTS => return Err(ProviderFailure::RateLimited),
            status if status.is_server_error() && attempt + 1 < MAX_PROVIDER_ATTEMPTS => {
                tokio::time::sleep(retry_delay(attempt)).await;
            }
            status if status.is_server_error() => return Err(ProviderFailure::Unavailable),
            status if !status.is_success() => {
                let body = response.bytes().await.unwrap_or_default();
                return Err(classify_provider_rejection(status, &body));
            }
            _ => {
                return response
                    .json::<EventsPage>()
                    .await
                    .map_err(|_| ProviderFailure::InvalidResponse);
            }
        }
    }
    Err(ProviderFailure::Unavailable)
}

async fn backend_ok<T: Serialize>(
    service: &ServiceState,
    route: &str,
    body: &T,
) -> Result<(), GoogleCommandError> {
    let _: HashMap<String, String> =
        product_request(service, reqwest::Method::POST, route, Some(body)).await?;
    Ok(())
}

async fn report_failure(
    service: &ServiceState,
    calendar_id: &str,
    failure: &ProviderFailure,
) -> Result<(), GoogleCommandError> {
    let code = provider_failure_code(failure);
    let route = calendar_backend_route(calendar_id, "/sync/failure")?;
    backend_ok(
        service,
        &route,
        &SyncFailureInput {
            error_code: code,
            retry_count: if matches!(
                failure,
                ProviderFailure::RateLimited | ProviderFailure::Unavailable
            ) {
                MAX_PROVIDER_ATTEMPTS
            } else {
                0
            },
            next_retry_at: None,
        },
    )
    .await
}

async fn sync_calendar(
    client: &Client,
    service: &ServiceState,
    calendar: &InternalGoogleCalendar,
    access_token: &str,
) -> Result<(), ProviderFailure> {
    let mut mode = if calendar.next_sync_token.is_some() {
        "incremental"
    } else {
        "full"
    };
    loop {
        let generation = new_uuid().map_err(|_| ProviderFailure::InvalidResponse)?;
        let begin_route = calendar_backend_route(&calendar.calendar.id, "/sync/begin")
            .map_err(|_| ProviderFailure::InvalidResponse)?;
        backend_ok(
            service,
            &begin_route,
            &SyncBeginInput {
                generation: &generation,
                mode,
            },
        )
        .await
        .map_err(|_| ProviderFailure::Unavailable)?;
        let sync_token = if mode == "incremental" {
            calendar.next_sync_token.as_deref()
        } else {
            None
        };
        let mut page_token: Option<String> = None;
        let final_sync_token = loop {
            let page = match fetch_events_page(
                client,
                access_token,
                &calendar.calendar.provider_calendar_id,
                sync_token,
                page_token.as_deref(),
            )
            .await
            {
                Err(error) if should_reset_to_full(mode, &error) => break None,
                Err(error) => return Err(error),
                Ok(page) => page,
            };
            let timezone = calendar.calendar.timezone.as_deref().unwrap_or("UTC");
            let events: Vec<_> = page
                .items
                .into_iter()
                .map(|event| sanitize_event(event, timezone))
                .collect();
            let page_route = calendar_backend_route(&calendar.calendar.id, "/sync/page")
                .map_err(|_| ProviderFailure::InvalidResponse)?;
            backend_ok(
                service,
                &page_route,
                &SyncPageInput {
                    generation: &generation,
                    events: &events,
                },
            )
            .await
            .map_err(|_| ProviderFailure::Unavailable)?;
            if let Some(next) = page.next_page_token {
                page_token = Some(next);
                continue;
            }
            break Some(
                page.next_sync_token
                    .ok_or(ProviderFailure::InvalidResponse)?,
            );
        };
        if let Some(next_sync_token) = final_sync_token {
            let complete_route = calendar_backend_route(&calendar.calendar.id, "/sync/complete")
                .map_err(|_| ProviderFailure::InvalidResponse)?;
            backend_ok(
                service,
                &complete_route,
                &SyncCompleteInput {
                    generation: &generation,
                    next_sync_token: &next_sync_token,
                },
            )
            .await
            .map_err(|_| ProviderFailure::Unavailable)?;
            return Ok(());
        }
        mode = "full";
    }
}

fn event_detail_readable(access_role: &str) -> bool {
    matches!(
        access_role,
        "reader" | "writerWithoutPrivateAccess" | "writer" | "owner"
    )
}

async fn synchronize<R: Runtime>(
    app: &AppHandle<R>,
    service: &ServiceState,
    google: &GoogleState,
) -> Result<CalendarStatus, GoogleCommandError> {
    let _guard = google.begin_sync()?;
    let config = load_oauth_config(&oauth_config_path(app)?)?;
    let client = google_client()?;
    let state = internal_state(service).await?;
    for account in state
        .accounts
        .iter()
        .filter(|account| account.account.auth_state == "connected")
    {
        let account_calendars: Vec<_> = state
            .calendars
            .iter()
            .filter(|calendar| {
                calendar.calendar.account_id == account.account.id
                    && calendar.calendar.enabled_in_ion
                    && !calendar.calendar.provider_deleted
                    && event_detail_readable(&calendar.calendar.access_role)
            })
            .collect();
        if account_calendars.is_empty() {
            continue;
        }
        let access_token = if let Some(value) = google.cached_token(&account.account.id) {
            value
        } else {
            let refresh_token = match SystemKeychain.get(&account.keychain_locator) {
                Ok(value) => value,
                Err(_) => {
                    for calendar in &account_calendars {
                        report_failure(service, &calendar.calendar.id, &ProviderFailure::Reauth)
                            .await?;
                    }
                    continue;
                }
            };
            match refresh_access_token(&client, &config, &refresh_token).await {
                Ok(token) => {
                    let value = token.access_token.clone();
                    google.store_access_token(
                        &account.account.id,
                        token.access_token,
                        token.expires_in,
                    );
                    value
                }
                Err(error) => {
                    for calendar in &account_calendars {
                        report_failure(service, &calendar.calendar.id, &error).await?;
                    }
                    continue;
                }
            }
        };
        for calendar in account_calendars {
            if let Err(error) = sync_calendar(&client, service, calendar, &access_token).await {
                report_failure(service, &calendar.calendar.id, &error).await?;
                if matches!(error, ProviderFailure::Reauth) {
                    google.forget_account(&account.account.id);
                    break;
                }
            }
        }
    }
    local_status(service)
        .await
        .map(|status| configured_status(app, status))
}

#[tauri::command]
pub async fn sync_google_calendars<R: Runtime>(
    app: AppHandle<R>,
    service: State<'_, ServiceState>,
    google: State<'_, GoogleState>,
) -> Result<CalendarStatus, GoogleCommandError> {
    synchronize(&app, &service, &google).await
}

#[tauri::command]
pub async fn disconnect_google_calendar<R: Runtime>(
    app: AppHandle<R>,
    service: State<'_, ServiceState>,
    google: State<'_, GoogleState>,
    account_id: String,
) -> Result<CalendarStatus, GoogleCommandError> {
    let state = internal_state(&service).await?;
    let account = state
        .accounts
        .iter()
        .find(|account| account.account.id == account_id)
        .ok_or_else(|| GoogleCommandError::new("not_found"))?;
    let route = account_backend_route(&account_id, "/disconnect")?;
    let status: CalendarStatus = product_request(
        &service,
        reqwest::Method::POST,
        &route,
        Some(&EmptyInput {}),
    )
    .await?;
    if let Ok(token) = SystemKeychain.get(&account.keychain_locator) {
        if let Ok(client) = google_client() {
            let _ = client
                .post(REVOKE_ENDPOINT)
                .form(&[("token", token.as_str())])
                .send()
                .await;
        }
    }
    let _ = SystemKeychain.delete(&account.keychain_locator);
    google.forget_account(&account_id);
    Ok(configured_status(&app, status))
}

#[cfg(test)]
mod tests {
    use std::{collections::HashMap, sync::Mutex};

    use super::*;

    #[derive(Default)]
    struct FakeTokenStore(Mutex<HashMap<String, String>>);

    impl RefreshTokenStore for FakeTokenStore {
        fn set(&self, locator: &str, value: &str) -> Result<(), GoogleCommandError> {
            self.0.lock().unwrap().insert(locator.into(), value.into());
            Ok(())
        }

        fn get(&self, locator: &str) -> Result<String, GoogleCommandError> {
            self.0
                .lock()
                .unwrap()
                .get(locator)
                .cloned()
                .ok_or_else(|| GoogleCommandError::new("reauth_required"))
        }

        fn delete(&self, locator: &str) -> Result<(), GoogleCommandError> {
            self.0.lock().unwrap().remove(locator);
            Ok(())
        }
    }

    fn synthetic_config() -> OAuthConfig {
        OAuthConfig {
            client_id: "synthetic-client.apps.googleusercontent.com".into(),
            client_secret: None,
        }
    }

    fn raw_calendar(
        summary: &str,
        summary_override: Option<&str>,
        deleted: bool,
    ) -> ProviderCalendarRaw {
        ProviderCalendarRaw {
            id: "synthetic-calendar@example.invalid".into(),
            summary: summary.into(),
            summary_override: summary_override.map(str::to_owned),
            description: None,
            location: None,
            time_zone: Some("America/Los_Angeles".into()),
            access_role: if deleted { "".into() } else { "reader".into() },
            etag: Some("synthetic-etag".into()),
            primary: false,
            selected: !deleted,
            hidden: false,
            deleted,
        }
    }

    #[test]
    fn calendar_list_normalization_preserves_titles_and_keeps_tombstones_unnamed() {
        let titled = provider_calendar(raw_calendar(
            "Provider title",
            Some("Owner override"),
            false,
        ));
        assert_eq!(titled.summary.as_deref(), Some("Owner override"));
        assert!(!titled.provider_deleted);

        let tombstone = provider_calendar(raw_calendar("", None, true));
        assert_eq!(tombstone.summary, None);
        assert!(tombstone.provider_deleted);
        assert_eq!(tombstone.access_role, "none");
        assert_eq!(
            serde_json::to_value(&tombstone).unwrap()["summary"],
            serde_json::Value::Null
        );

        let active_unnamed = provider_calendar(raw_calendar("", None, false));
        assert_eq!(active_unnamed.summary, None);
        assert!(!active_unnamed.provider_deleted);
    }

    #[test]
    fn pkce_and_authorization_are_scoped_and_do_not_expose_verifier() {
        let (verifier, challenge) = pkce_pair().unwrap();
        assert!((43..=128).contains(&verifier.len()));
        assert_ne!(verifier, challenge);
        let url = authorization_url(
            &synthetic_config(),
            "http://127.0.0.1:49152/oauth2/callback",
            "synthetic-state",
            &challenge,
            OAuthScopeMode::ReadOnly,
        )
        .unwrap();
        let query: HashMap<_, _> = url.query_pairs().into_owned().collect();
        assert_eq!(query.get("code_challenge_method").unwrap(), "S256");
        assert_eq!(
            query.get("scope").unwrap(),
            &format!("{CALENDAR_LIST_SCOPE} {EVENTS_READ_SCOPE}")
        );
        assert!(!url.as_str().contains(&verifier));
        assert!(!url.as_str().contains("tasks"));
        assert!(!url.as_str().contains("calendar%20"));

        let write_url = authorization_url(
            &synthetic_config(),
            "http://127.0.0.1:49152/oauth2/callback",
            "synthetic-state",
            &challenge,
            OAuthScopeMode::CalendarWriteReconsent,
        )
        .unwrap();
        let write_query: HashMap<_, _> = write_url.query_pairs().into_owned().collect();
        assert_eq!(
            write_query.get("scope").unwrap(),
            &format!("{CALENDAR_LIST_SCOPE} {EVENTS_WRITE_SCOPE}")
        );
        assert!(!write_url.as_str().contains(EVENTS_READ_SCOPE));
        assert!(!write_url.as_str().contains("auth/calendar%20"));
    }

    #[test]
    fn callback_requires_exact_path_state_and_code() {
        assert_eq!(
            callback_code(
                "/oauth2/callback?state=expected&code=synthetic-code",
                "expected"
            )
            .unwrap(),
            "synthetic-code"
        );
        assert_eq!(
            callback_code(
                "/oauth2/callback?state=wrong&code=synthetic-code",
                "expected"
            )
            .unwrap_err()
            .code,
            "oauth_state_mismatch"
        );
        assert_eq!(
            callback_code("/oauth2/callback?state=expected&error=denied", "expected")
                .unwrap_err()
                .code,
            "oauth_cancelled"
        );
        assert!(callback_code("/other?state=expected&code=x", "expected").is_err());
    }

    #[test]
    fn keychain_abstraction_round_trips_without_real_keychain_access() {
        let store = FakeTokenStore::default();
        store
            .set("synthetic-locator", "synthetic-refresh-token")
            .unwrap();
        assert_eq!(
            store.get("synthetic-locator").unwrap(),
            "synthetic-refresh-token"
        );
        store.delete("synthetic-locator").unwrap();
        assert!(store.get("synthetic-locator").is_err());
    }

    #[test]
    fn provider_event_sanitization_preserves_all_day_and_iana_time() {
        let timed = sanitize_time(
            Some(ProviderDateTimeRaw {
                date: None,
                date_time: Some("2030-03-10T03:30:00-07:00".into()),
                time_zone: None,
            }),
            "America/Los_Angeles",
        )
        .unwrap();
        assert_eq!(timed.timezone.as_deref(), Some("America/Los_Angeles"));
        assert_eq!(timed.date, None);

        let date = sanitize_time(
            Some(ProviderDateTimeRaw {
                date: Some("2030-03-10".into()),
                date_time: None,
                time_zone: None,
            }),
            "America/Los_Angeles",
        )
        .unwrap();
        assert_eq!(date.date.as_deref(), Some("2030-03-10"));
        assert_eq!(date.date_time, None);
        assert_eq!(date.timezone, None);
    }

    #[test]
    fn event_urls_encode_provider_ids_and_keep_sync_query_stable() {
        let url = events_url(
            "synthetic/calendar@example.invalid",
            Some("sync+token"),
            Some("page/token"),
        )
        .unwrap();
        assert_eq!(
            url.as_str(),
            "https://www.googleapis.com/calendar/v3/calendars/\
synthetic%2Fcalendar@example.invalid/events?maxResults=2500&showDeleted=true&\
singleEvents=false&syncToken=sync%2Btoken&pageToken=page%2Ftoken"
        );
        assert!(url.path().contains("synthetic%2Fcalendar@example.invalid"));
        let query: HashMap<_, _> = url.query_pairs().into_owned().collect();
        assert_eq!(query.get("singleEvents").unwrap(), "false");
        assert_eq!(query.get("showDeleted").unwrap(), "true");
        assert_eq!(query.get("syncToken").unwrap(), "sync+token");
        assert_eq!(query.get("pageToken").unwrap(), "page/token");
    }

    #[test]
    fn event_urls_match_google_full_and_incremental_request_constraints() {
        let full = events_url("primary", None, None).unwrap();
        assert_eq!(
            full.as_str(),
            "https://www.googleapis.com/calendar/v3/calendars/primary/events?\
maxResults=2500&showDeleted=true&singleEvents=false"
        );
        let full_keys: HashSet<_> = full
            .query_pairs()
            .map(|(key, _)| key.into_owned())
            .collect();
        assert_eq!(
            full_keys,
            HashSet::from([
                "maxResults".to_string(),
                "showDeleted".to_string(),
                "singleEvents".to_string(),
            ])
        );

        let incremental = events_url("primary", Some("synthetic-sync"), None).unwrap();
        let incremental_query: HashMap<_, _> = incremental.query_pairs().into_owned().collect();
        assert_eq!(
            incremental_query.get("syncToken").unwrap(),
            "synthetic-sync"
        );
        assert_eq!(incremental_query.get("showDeleted").unwrap(), "true");
        for incompatible in [
            "iCalUID",
            "orderBy",
            "privateExtendedProperty",
            "q",
            "sharedExtendedProperty",
            "timeMin",
            "timeMax",
            "updatedMin",
        ] {
            assert!(!incremental_query.contains_key(incompatible));
        }
        assert!(events_url("primary", Some(""), None).is_err());
        assert!(events_url("primary", None, Some("")).is_err());
    }

    #[test]
    fn events_request_keeps_bearer_credentials_out_of_the_url() {
        let request = events_request(
            &Client::new(),
            "synthetic-access-token",
            "primary",
            None,
            None,
        )
        .unwrap()
        .build()
        .unwrap();
        assert_eq!(
            request
                .headers()
                .get(reqwest::header::AUTHORIZATION)
                .unwrap(),
            "Bearer synthetic-access-token"
        );
        assert!(!request.url().as_str().contains("synthetic-access-token"));
    }

    #[test]
    fn provider_rejections_are_allowlisted_without_leaking_payload_reasons() {
        let not_found = classify_provider_rejection(
            StatusCode::NOT_FOUND,
            br#"{"error":{"errors":[{"reason":"notFound"}]}}"#,
        );
        assert_eq!(provider_failure_code(&not_found), "provider_not_found");

        let insufficient = classify_provider_rejection(
            StatusCode::FORBIDDEN,
            br#"{"error":{"errors":[{"reason":"insufficientPermissions"}]}}"#,
        );
        assert_eq!(
            provider_failure_code(&insufficient),
            "provider_insufficient_permissions"
        );

        let rate_limited = classify_provider_rejection(
            StatusCode::FORBIDDEN,
            br#"{"error":{"errors":[{"reason":"rateLimitExceeded"}]}}"#,
        );
        assert_eq!(rate_limited, ProviderFailure::RateLimited);

        let private_reason = classify_provider_rejection(
            StatusCode::FORBIDDEN,
            br#"{"error":{"errors":[{"reason":"private-owner-detail"}]}}"#,
        );
        assert_eq!(provider_failure_code(&private_reason), "provider_forbidden");
        assert_ne!(
            provider_failure_code(&private_reason),
            "private-owner-detail"
        );
    }

    fn synthetic_write_body(id: Option<&str>) -> AllowedProviderWriteBody {
        AllowedProviderWriteBody {
            id: id.map(str::to_owned),
            summary: Some("Synthetic event".into()),
            description: None,
            location: None,
            transparency: Some("opaque".into()),
            start: Some(AllowedWriteDateTime {
                date: None,
                date_time: Some("2030-01-01T09:00:00-08:00".into()),
                time_zone: Some("America/Los_Angeles".into()),
            }),
            end: Some(AllowedWriteDateTime {
                date: None,
                date_time: Some("2030-01-01T10:00:00-08:00".into()),
                time_zone: Some("America/Los_Angeles".into()),
            }),
            recurrence: None,
            status: None,
        }
    }

    #[test]
    fn write_method_inventory_is_exact_and_excludes_broad_operations() {
        for (name, expected) in [
            ("events.insert", ProviderWriteMethod::Insert),
            ("events.get", ProviderWriteMethod::Get),
            ("events.patch", ProviderWriteMethod::Patch),
            ("events.delete", ProviderWriteMethod::Delete),
            ("events.instances", ProviderWriteMethod::Instances),
        ] {
            let method = ProviderWriteMethod::from_inventory_name(name).unwrap();
            assert_eq!(method, expected);
            assert_eq!(method.inventory_name(), name);
        }
        for excluded in [
            "events.update",
            "events.move",
            "events.import",
            "events.quickAdd",
            "events.batch",
            "events.watch",
        ] {
            assert_eq!(ProviderWriteMethod::from_inventory_name(excluded), None);
        }
    }

    #[test]
    fn typed_write_requests_are_allowlisted_conditional_and_never_sent() {
        let client = Client::new();
        let insert_body = synthetic_write_body(Some("0123456789abcdefghijklmnopqrstuv"));
        let insert = provider_write_request(
            &client,
            ProviderWriteMethod::Insert,
            "synthetic-access-token",
            "synthetic/calendar@example.invalid",
            None,
            None,
            Some(&insert_body),
        )
        .unwrap();
        assert_eq!(insert.method(), reqwest::Method::POST);
        assert_eq!(
            insert.url().path(),
            "/calendar/v3/calendars/synthetic%2Fcalendar@example.invalid/events"
        );
        let body = String::from_utf8(insert.body().unwrap().as_bytes().unwrap().to_vec()).unwrap();
        assert!(body.contains("\"id\":\"0123456789abcdefghijklmnopqrstuv\""));
        for forbidden in [
            "attendees",
            "reminders",
            "conferenceData",
            "attachments",
            "extendedProperties",
            "colorId",
        ] {
            assert!(!body.contains(forbidden));
        }

        let patch_body = synthetic_write_body(None);
        let patch = provider_write_request(
            &client,
            ProviderWriteMethod::Patch,
            "synthetic-access-token",
            "primary",
            Some("synthetic-event"),
            Some("\"synthetic-etag\""),
            Some(&patch_body),
        )
        .unwrap();
        assert_eq!(patch.method(), reqwest::Method::PATCH);
        assert_eq!(
            patch.headers().get(reqwest::header::IF_MATCH).unwrap(),
            "\"synthetic-etag\""
        );
        assert!(!patch.url().as_str().contains("synthetic-access-token"));
        assert!(provider_write_request(
            &client,
            ProviderWriteMethod::Patch,
            "synthetic-access-token",
            "primary",
            Some("synthetic-event"),
            Some("*"),
            Some(&patch_body),
        )
        .is_err());

        let instances = provider_write_request(
            &client,
            ProviderWriteMethod::Instances,
            "synthetic-access-token",
            "primary",
            Some("synthetic-series"),
            None,
            None,
        )
        .unwrap();
        assert!(instances
            .url()
            .path()
            .ends_with("/synthetic-series/instances"));
    }

    #[test]
    fn synthetic_write_failure_matrix_is_safe_and_deterministic() {
        let cases = [
            (
                ProviderWriteMethod::Insert,
                StatusCode::OK,
                br#"{}"#.as_slice(),
                ProviderWriteResultClass::Success,
            ),
            (
                ProviderWriteMethod::Patch,
                StatusCode::UNAUTHORIZED,
                br#"{}"#.as_slice(),
                ProviderWriteResultClass::ReauthenticationRequired,
            ),
            (
                ProviderWriteMethod::Patch,
                StatusCode::FORBIDDEN,
                br#"{"error":{"errors":[{"reason":"forbidden"}]}}"#.as_slice(),
                ProviderWriteResultClass::TerminalProviderRejection,
            ),
            (
                ProviderWriteMethod::Get,
                StatusCode::NOT_FOUND,
                br#"{}"#.as_slice(),
                ProviderWriteResultClass::ProviderNotFound,
            ),
            (
                ProviderWriteMethod::Insert,
                StatusCode::CONFLICT,
                br#"{"error":{"errors":[{"reason":"duplicate"}]}}"#.as_slice(),
                ProviderWriteResultClass::DuplicateOrAmbiguousCreate,
            ),
            (
                ProviderWriteMethod::Patch,
                StatusCode::PRECONDITION_FAILED,
                br#"{}"#.as_slice(),
                ProviderWriteResultClass::StalePrecondition,
            ),
            (
                ProviderWriteMethod::Patch,
                StatusCode::TOO_MANY_REQUESTS,
                br#"{}"#.as_slice(),
                ProviderWriteResultClass::RetryableQuota,
            ),
            (
                ProviderWriteMethod::Patch,
                StatusCode::SERVICE_UNAVAILABLE,
                br#"{}"#.as_slice(),
                ProviderWriteResultClass::RetryableBackend,
            ),
            (
                ProviderWriteMethod::Patch,
                StatusCode::BAD_REQUEST,
                br#"{}"#.as_slice(),
                ProviderWriteResultClass::InvalidTarget,
            ),
        ];
        for (method, status, body, expected) in cases {
            assert_eq!(
                classify_write_provider_result(method, status, body),
                expected
            );
        }
        assert_eq!(
            classify_write_transport_failure(ProviderWriteMethod::Insert),
            ProviderWriteResultClass::DuplicateOrAmbiguousCreate
        );
        assert_eq!(
            classify_write_transport_failure(ProviderWriteMethod::Patch),
            ProviderWriteResultClass::RetryableTransport
        );
    }

    #[test]
    fn provider_sanitization_reduces_attendees_and_special_types_to_capabilities() {
        let raw: ProviderEventRaw = serde_json::from_str(
            r#"{
                "id":"synthetic-event",
                "eventType":"outOfOffice",
                "locked":true,
                "attendees":[{"email":"private@example.invalid"}]
            }"#,
        )
        .unwrap();
        let sanitized = sanitize_event(raw, "America/Los_Angeles");
        assert_eq!(sanitized.provider_event_type, "special");
        assert!(sanitized.provider_locked);
        assert!(sanitized.has_attendees);
        let serialized = serde_json::to_string(&sanitized).unwrap();
        assert!(!serialized.contains("private@example.invalid"));
        assert!(!serialized.contains("\"attendees\":["));
        assert!(serialized.contains("\"has_attendees\":true"));
    }

    #[test]
    fn event_sync_skips_roles_without_event_detail_access() {
        for role in ["reader", "writerWithoutPrivateAccess", "writer", "owner"] {
            assert!(event_detail_readable(role));
        }
        for role in ["none", "freeBusyReader", "unknown"] {
            assert!(!event_detail_readable(role));
        }
    }

    #[test]
    fn ion_calendar_category_contract_accepts_extensible_safe_subtypes_only() {
        for category in [
            "academic",
            "career",
            "personal_project",
            "routine_physical",
            "personal",
            "fun",
            "ion_focus",
        ] {
            assert!(valid_calendar_category(category));
        }
        assert!(!valid_calendar_category("work"));
        assert!(!valid_calendar_category("provider-write"));
        for subtype in [
            "class_section",
            "homework_study",
            "quiz_exam",
            "future_extension_2",
        ] {
            assert!(valid_calendar_category_subtype(subtype));
        }
        for subtype in ["", "Class", "has-dash", "2starts_with_number"] {
            assert!(!valid_calendar_category_subtype(subtype));
        }
        for category in [
            "academic",
            "career",
            "personal_project",
            "routine_physical",
            "personal",
            "fun",
        ] {
            assert!(calendar_category_requires_subtype(category));
        }
        assert!(!calendar_category_requires_subtype("ion_focus"));
    }

    #[test]
    fn local_product_errors_keep_safe_category_failure_states_distinct() {
        assert_eq!(
            GoogleCommandError::from(ProductError::new(ProductErrorCode::Validation)).code,
            "local_state_invalid"
        );
        assert_eq!(
            GoogleCommandError::from(ProductError::new(ProductErrorCode::RevisionConflict)).code,
            "local_state_conflict"
        );
        assert_eq!(
            GoogleCommandError::from(ProductError::new(ProductErrorCode::Unavailable)).code,
            "local_service_unavailable"
        );
    }

    #[test]
    fn fixed_backend_routes_match_calendar_api_ownership() {
        let id = "11111111-1111-4111-8111-111111111111";
        assert_eq!(
            calendar_backend_route(id, "/selection").unwrap(),
            format!("/v1/calendar/calendars/{id}/selection")
        );
        for stage in ["begin", "page", "complete", "failure"] {
            assert_eq!(
                calendar_backend_route(id, &format!("/sync/{stage}")).unwrap(),
                format!("/v1/calendar/calendars/{id}/sync/{stage}")
            );
        }
        assert_eq!(
            account_backend_route(id, "/disconnect").unwrap(),
            format!("/v1/calendar/accounts/{id}/disconnect")
        );
        assert_eq!(
            calendar_backend_route(id, "/visibility").unwrap(),
            format!("/v1/calendar/calendars/{id}/visibility")
        );
        assert_eq!(
            calendar_block_backend_route(id, "/category").unwrap(),
            format!("/v1/calendar/blocks/{id}/category")
        );
        assert_eq!(
            write_intent_backend_route(id, "/transition").unwrap(),
            format!("/v1/calendar/internal/write-intents/{id}/transition")
        );
        assert!(calendar_backend_route("../status", "/sync/begin").is_err());
        assert!(calendar_block_backend_route("../status", "/category").is_err());
        assert!(account_backend_route("../status", "/disconnect").is_err());
        assert!(write_intent_backend_route("../status", "/transition").is_err());
    }

    #[test]
    fn retries_are_bounded_exponential_backoff() {
        assert_eq!(retry_delay(0), Duration::from_millis(250));
        assert_eq!(retry_delay(1), Duration::from_millis(500));
        assert_eq!(retry_delay(2), Duration::from_millis(1000));
        assert_eq!(retry_delay(99), Duration::from_millis(4000));
    }

    #[test]
    fn renderer_status_has_no_keychain_locator_or_token_field() {
        let status = CalendarStatus {
            configured: true,
            configuration_path: "/synthetic/google-oauth.json".into(),
            accounts: vec![],
            calendars: vec![],
            blocks: vec![],
        };
        let serialized = serde_json::to_string(&status).unwrap();
        assert!(!serialized.contains("keychain"));
        assert!(!serialized.contains("token"));
        assert!(!serialized.contains("verifier"));
        assert!(!serialized.contains("authorization_code"));
    }

    #[test]
    fn provider_pages_parse_pagination_and_final_sync_tokens() {
        let first: EventsPage =
            serde_json::from_str(r#"{"items":[],"nextPageToken":"synthetic-page"}"#).unwrap();
        assert_eq!(first.next_page_token.as_deref(), Some("synthetic-page"));
        assert_eq!(first.next_sync_token, None);

        let last: EventsPage =
            serde_json::from_str(r#"{"items":[],"nextSyncToken":"synthetic-sync"}"#).unwrap();
        assert_eq!(last.next_page_token, None);
        assert_eq!(last.next_sync_token.as_deref(), Some("synthetic-sync"));
    }

    #[test]
    fn http_410_resets_only_incremental_sync_to_a_full_generation() {
        assert!(should_reset_to_full("incremental", &ProviderFailure::Gone));
        assert!(!should_reset_to_full("full", &ProviderFailure::Gone));
        assert!(!should_reset_to_full(
            "incremental",
            &ProviderFailure::Unavailable
        ));
    }
}
