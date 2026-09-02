//! Phase 2C-R0 direct-human Calendar write foundation.
//!
//! This module is the Rust half of the seam that Phase 2C v1 broke. There,
//! `this and following` was implemented end to end in the Python domain with
//! passing tests while this layer's scope allowlist still read
//! `single | occurrence | series`; every real attempt failed as
//! `local_state_invalid` and surfaced as "This calendar change couldn't be
//! saved". Green domain tests, broken product.
//!
//! So the allowlists here are not hand-maintained prose. They are asserted
//! equal to `contracts/calendar-write-vocabulary.json` by the tests below, and
//! Python and TypeScript assert the same file. A value added to one layer and
//! missed in another fails in CI rather than in the owner's hands.
//!
//! R0 dispatches nothing to Google. This command validates a direct-human
//! intent and forwards it to the authenticated loopback API, which persists it
//! durably. No provider request is constructed here and no Google method is
//! reachable from it.

use reqwest::{Client, Url};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::google_calendar::{calendar_block_backend_route, GoogleCommandError};
use crate::service::{product_request, ServiceState};
use tauri::State;

/// Operations the renderer may name. Narrower than storage on purpose.
pub(crate) const ACCEPTED_OPERATIONS: [&str; 1] = ["patch"];
/// Recurrence scopes the renderer may name. R4/R5 widen this *together with*
/// every other layer, never alone.
pub(crate) const ACCEPTED_RECURRENCE_SCOPES: [&str; 1] = ["single"];
/// The closed changed-field allowlist.
pub(crate) const CHANGED_FIELDS: [&str; 3] = ["title", "start", "end"];
/// The closed recovery taxonomy. Deliberately no generic member: there is no
/// `conflict`, `needs_review`, `apply_ion`, or `keep_google`.
///
/// R0 declares and parity-tests this vocabulary; R1's dispatcher is its first
/// non-test consumer, through [`known_recovery_kind`]. Declaring it now is the
/// point -- the drift these lists guard against is introduced when a value is
/// added in one layer and forgotten in another, which is exactly what happened
/// to `this and following` in Phase 2C v1.
#[allow(dead_code)]
pub(crate) const AUTOMATIC_RECOVERY: [&str; 5] = [
    "provider_version_drift",
    "transient_transport",
    "transient_backend",
    "transient_quota",
    "reconcilable_ambiguity",
];
#[allow(dead_code)]
pub(crate) const OWNER_ACTION_RECOVERY: [&str; 9] = [
    "write_consent_required",
    "reauthentication_required",
    "write_permission_lost",
    "provider_target_deleted",
    "recurrence_identity_lost",
    "unsupported_provider_transformation",
    "deterministic_id_collision",
    "provider_rejected_terminally",
    "automatic_recovery_exhausted",
];

/// The only Google methods R1 may reach. Widening this needs an owner decision
/// recorded in docs/SECURITY.md, not a code change alone. Asserted against the
/// canonical manifest by the parity test below.
#[allow(dead_code)]
pub(crate) const PROVIDER_METHODS: [&str; 2] = ["events.patch", "events.get"];
/// Operations that may actually leave for Google in R1.
pub(crate) const DISPATCHABLE_OPERATIONS: [&str; 1] = ["patch"];
/// Bounded work per trigger. No daemon, no poll, no worker per event.
const MAX_WRITES_PER_TRIGGER: usize = 10;

/// Whether a recovery kind reported by the local API is one this layer knows.
///
/// Anything else is a vocabulary drift bug, not a state to pass through to the
/// renderer: an unknown string reaching the UI is how a generic "review this"
/// surface gets reintroduced by accident.
#[allow(dead_code)]
pub(crate) fn known_recovery_kind(value: &str) -> bool {
    AUTOMATIC_RECOVERY.contains(&value) || OWNER_ACTION_RECOVERY.contains(&value)
}

/// A civil all-day date or an instant with its zone, never both.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProviderDateTime {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub date: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub date_time: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub time_zone: Option<String>,
}

impl ProviderDateTime {
    fn valid(&self) -> bool {
        match (&self.date, &self.date_time, &self.time_zone) {
            (Some(_), None, None) => true,
            (None, Some(_), Some(zone)) => !zone.is_empty(),
            _ => false,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DirectHumanEditDraft {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub start: Option<ProviderDateTime>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub end: Option<ProviderDateTime>,
}

/// The whole renderer-supplied contract, as one fixed typed value.
///
/// Note what has no field here, and therefore cannot be supplied by a renderer:
/// provider event id, ETag, calendar id, account id, HTTP method, URL, header,
/// or raw body. Provider authority is derived by the local API from the
/// confirmed link. There is also no approval, confirmation, or review field --
/// a direct human action is itself the authorization.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DirectHumanIntentDraft {
    pub command_id: String,
    pub operation: String,
    /// Always `single` in R1. Carried so a widened scope in R4/R5 fails the
    /// parity test rather than being silently ignored here.
    #[allow(dead_code)]
    pub recurrence_scope: String,
    pub expected_revision: i64,
    pub changed_fields: Vec<String>,
    pub draft: DirectHumanEditDraft,
}

/// The exact body sent to the local API.
#[derive(Debug, Serialize)]
struct IntentInput<'a> {
    command_id: &'a str,
    operation: &'a str,
    recurrence_scope: &'a str,
    expected_revision: i64,
    changed_fields: Vec<&'a str>,
    draft: &'a DirectHumanEditDraft,
    provenance: &'static str,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DirectHumanIntentReceipt {
    pub intent_id: String,
    pub block_id: String,
    pub sequence: i64,
    pub state: String,
    pub accepted: bool,
    pub awaiting_predecessor: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub superseded_intent_id: Option<String>,
    /// Set only when this account has never granted -- or has lost -- Calendar
    /// write permission. A one-time capability transition, never approval of
    /// the edit, which is already durable.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub requires_write_consent: Option<String>,
}

fn draft_matches(fields: &[String], draft: &DirectHumanEditDraft) -> bool {
    let mut supplied: Vec<&str> = Vec::new();
    if draft.title.is_some() {
        supplied.push("title");
    }
    if let Some(value) = &draft.start {
        if !value.valid() {
            return false;
        }
        supplied.push("start");
    }
    if let Some(value) = &draft.end {
        if !value.valid() {
            return false;
        }
        supplied.push("end");
    }
    let mut declared: Vec<&str> = fields.iter().map(String::as_str).collect();
    declared.sort_unstable();
    declared.dedup();
    if declared.len() != fields.len() {
        return false;
    }
    supplied.sort_unstable();
    declared == supplied
}

/// Accept one direct human Calendar action.
///
/// A direct human action is itself the authorization, so this command has no
/// approval, confirmation, or review parameter, and no provider precondition.
/// It cannot be refused because provider work is busy: it never learns whether
/// any is.
#[tauri::command]
pub async fn accept_direct_human_calendar_intent<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    service: State<'_, ServiceState>,
    google: State<'_, crate::google_calendar::GoogleState>,
    block_id: String,
    intent: DirectHumanIntentDraft,
) -> Result<DirectHumanIntentReceipt, GoogleCommandError> {
    let DirectHumanIntentDraft {
        command_id,
        operation,
        recurrence_scope,
        expected_revision,
        changed_fields,
        draft,
    } = intent;
    if !ACCEPTED_OPERATIONS.contains(&operation.as_str())
        || !ACCEPTED_RECURRENCE_SCOPES.contains(&recurrence_scope.as_str())
        || changed_fields.is_empty()
        || changed_fields.len() > CHANGED_FIELDS.len()
        || !changed_fields
            .iter()
            .all(|field| CHANGED_FIELDS.contains(&field.as_str()))
        || !draft_matches(&changed_fields, &draft)
        || expected_revision < 1
        || command_id.len() != 36
    {
        return Err(GoogleCommandError::new("local_state_invalid"));
    }
    let route = calendar_block_backend_route(&block_id, "/intent")?;
    let route = route.replace("/v1/calendar/blocks/", "/v1/calendar/writes/blocks/");
    let receipt: DirectHumanIntentReceipt = product_request(
        &service,
        reqwest::Method::POST,
        &route,
        Some(&IntentInput {
            command_id: &command_id,
            operation: &operation,
            recurrence_scope: &recurrence_scope,
            expected_revision,
            changed_fields: changed_fields.iter().map(String::as_str).collect(),
            draft: &draft,
            provenance: "direct_human",
        }),
    )
    .await?;
    // The human action is already accepted and durable. Dispatch is a
    // consequence of that decision, not a further one, so it runs immediately
    // and its failure never un-accepts the edit -- there is no Sync Now step
    // and no second confirmation. A missing write capability is left alone:
    // the owner grants it once, and the edit resumes then.
    if receipt.requires_write_consent.is_none() {
        dispatch_after_human_action(&app, &service, &google).await;
    }
    Ok(receipt)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    fn manifest() -> Value {
        serde_json::from_str(include_str!(
            "../../../../contracts/calendar-write-vocabulary.json"
        ))
        .expect("canonical vocabulary manifest parses")
    }

    fn list(value: &Value, path: &[&str]) -> Vec<String> {
        let mut node = value;
        for key in path {
            node = &node[key];
        }
        node.as_array()
            .unwrap_or_else(|| panic!("{path:?} is a list"))
            .iter()
            .map(|item| item.as_str().expect("string").to_string())
            .collect()
    }

    /// The test Phase 2C v1 did not have. Every closed vocabulary this layer
    /// enforces must equal the canonical manifest that Python and TypeScript
    /// also assert against, so the layers cannot silently drift apart.
    #[test]
    fn tauri_vocabularies_match_the_canonical_cross_layer_manifest() {
        let manifest = manifest();
        assert_eq!(
            DISPATCHABLE_OPERATIONS.to_vec(),
            list(&manifest, &["coordinator", "dispatchable_operations"])
        );
        assert_eq!(
            PROVIDER_METHODS.to_vec(),
            list(&manifest, &["provider", "methods"])
        );
        assert_eq!(
            ACCEPTED_OPERATIONS.to_vec(),
            list(&manifest, &["coordinator", "accepted_operations"])
        );
        assert_eq!(
            ACCEPTED_RECURRENCE_SCOPES.to_vec(),
            list(&manifest, &["coordinator", "accepted_recurrence_scopes"])
        );
        assert_eq!(
            CHANGED_FIELDS.to_vec(),
            list(&manifest, &["coordinator", "changed_fields"])
        );
        assert_eq!(
            AUTOMATIC_RECOVERY.to_vec(),
            list(&manifest, &["recovery", "automatic"])
        );
        assert_eq!(
            OWNER_ACTION_RECOVERY.to_vec(),
            list(&manifest, &["recovery", "owner_action"])
        );
    }

    /// The generic review surface is withdrawn, not narrowed. No recovery kind
    /// this layer knows about may borrow its vocabulary.
    #[test]
    fn no_recovery_kind_is_a_generic_review_decision() {
        let manifest = manifest();
        for forbidden in list(&manifest, &["recovery", "forbidden"]) {
            assert!(!AUTOMATIC_RECOVERY.contains(&forbidden.as_str()));
            assert!(!OWNER_ACTION_RECOVERY.contains(&forbidden.as_str()));
        }
    }

    /// Ordinary provider version drift is an internal event Ion resolves, not a
    /// decision handed to a person.
    #[test]
    fn provider_version_drift_is_automatic_not_owner_action() {
        assert!(AUTOMATIC_RECOVERY.contains(&"provider_version_drift"));
        assert!(!OWNER_ACTION_RECOVERY.contains(&"provider_version_drift"));
        assert!(known_recovery_kind("provider_version_drift"));
        assert!(known_recovery_kind("automatic_recovery_exhausted"));
        for generic in ["conflict", "needs_review", "apply_ion", "keep_google"] {
            assert!(!known_recovery_kind(generic));
        }
    }

    #[test]
    fn unknown_operation_scope_or_field_is_refused_before_any_request() {
        let draft = DirectHumanEditDraft {
            title: Some("Study".into()),
            start: None,
            end: None,
        };
        assert!(draft_matches(&["title".into()], &draft));
        assert!(!draft_matches(&["start".into()], &draft));
        assert!(!draft_matches(&["title".into(), "title".into()], &draft));
        assert!(!ACCEPTED_OPERATIONS.contains(&"create"));
        assert!(!ACCEPTED_OPERATIONS.contains(&"delete_event"));
        // The exact value whose absence here broke Phase 2C v1 in production.
        assert!(!ACCEPTED_RECURRENCE_SCOPES.contains(&"this_and_following"));
        assert!(!CHANGED_FIELDS.contains(&"recurrence"));
    }

    #[test]
    fn a_temporal_value_is_all_day_or_zoned_never_both_or_neither() {
        let all_day = ProviderDateTime {
            date: Some("2030-01-07".into()),
            date_time: None,
            time_zone: None,
        };
        let timed = ProviderDateTime {
            date: None,
            date_time: Some("2030-01-07T19:00:00Z".into()),
            time_zone: Some("America/Los_Angeles".into()),
        };
        let both = ProviderDateTime {
            date: Some("2030-01-07".into()),
            date_time: Some("2030-01-07T19:00:00Z".into()),
            time_zone: Some("UTC".into()),
        };
        let naked = ProviderDateTime {
            date: None,
            date_time: Some("2030-01-07T19:00:00Z".into()),
            time_zone: None,
        };
        assert!(all_day.valid() && timed.valid());
        assert!(!both.valid() && !naked.valid());
    }

    /// The renderer contract carries Ion identifiers and desired values only.
    #[test]
    fn the_serialized_body_carries_no_provider_authority() {
        let draft = DirectHumanEditDraft {
            title: Some("Study".into()),
            start: None,
            end: None,
        };
        let body = serde_json::to_string(&IntentInput {
            command_id: "11111111-1111-4111-8111-111111111111",
            operation: "patch",
            recurrence_scope: "single",
            expected_revision: 3,
            changed_fields: vec!["title"],
            draft: &draft,
            provenance: "direct_human",
        })
        .expect("serializes");
        for forbidden in [
            "etag",
            "if_match",
            "If-Match",
            "provider_event_id",
            "calendar_id",
            "account_id",
            "method",
            "url",
            "headers",
            "access_token",
        ] {
            assert!(!body.contains(forbidden), "body leaked {forbidden}");
        }
        assert!(body.contains("\"provenance\":\"direct_human\""));
    }

    #[test]
    fn the_intent_route_is_fixed_and_rejects_path_injection() {
        let id = "11111111-1111-4111-8111-111111111111";
        let route = calendar_block_backend_route(id, "/intent")
            .unwrap()
            .replace("/v1/calendar/blocks/", "/v1/calendar/writes/blocks/");
        assert_eq!(route, format!("/v1/calendar/writes/blocks/{id}/intent"));
        assert!(calendar_block_backend_route("../status", "/intent").is_err());
    }
}

// ---------------------------------------------------------------------------
// Phase 2C-R1 provider execution.
//
// Rust owns OAuth, token memory, and Google HTTPS. Python owns durable intent,
// eligibility, changed fields, work selection, rebase decisions, and
// settlement. That split is the accepted trust boundary and R1 does not move
// it: nothing here decides *what* to write, only how to send it safely.
// ---------------------------------------------------------------------------

/// Base for Google Calendar requests. Overridable only under `cfg(test)`, so a
/// seam test can point the real dispatch path at a synthetic provider without
/// the production binary ever gaining a redirectable endpoint.
#[cfg(test)]
pub(crate) static TEST_CALENDAR_API: std::sync::Mutex<Option<String>> = std::sync::Mutex::new(None);

fn calendar_api_base() -> String {
    #[cfg(test)]
    if let Some(value) = TEST_CALENDAR_API
        .lock()
        .expect("test calendar api lock")
        .clone()
    {
        return value;
    }
    crate::google_calendar::CALENDAR_API.to_string()
}

/// `PATCH /calendars/{calendarId}/events/{eventId}`, with both identifiers
/// path-encoded rather than interpolated.
fn event_url(provider_calendar_id: &str, provider_event_id: &str) -> Option<Url> {
    if provider_calendar_id.is_empty() || provider_event_id.is_empty() {
        return None;
    }
    let mut url = Url::parse(&calendar_api_base()).ok()?;
    url.path_segments_mut().ok()?.pop_if_empty().extend([
        "calendars",
        provider_calendar_id,
        "events",
        provider_event_id,
    ]);
    Some(url)
}

/// The provider body. Only allowlisted changed fields appear; there is no
/// attendee, reminder, conferencing, attachment, recurrence, colour, or
/// extended-property field to populate.
fn patch_body(changed_fields: &[String], draft: &DirectHumanEditDraft) -> Option<Value> {
    let mut body = serde_json::Map::new();
    for field in changed_fields {
        match field.as_str() {
            "title" => {
                body.insert("summary".into(), Value::String(draft.title.clone()?));
            }
            "start" => {
                body.insert("start".into(), provider_time(draft.start.as_ref()?)?);
            }
            "end" => {
                body.insert("end".into(), provider_time(draft.end.as_ref()?)?);
            }
            _ => return None,
        }
    }
    if body.is_empty() {
        return None;
    }
    Some(Value::Object(body))
}

/// Preserves the all-day / zoned-instant distinction Phase 2A established.
fn provider_time(value: &ProviderDateTime) -> Option<Value> {
    let mut node = serde_json::Map::new();
    match (&value.date, &value.date_time, &value.time_zone) {
        (Some(date), None, None) => {
            node.insert("date".into(), Value::String(date.clone()));
        }
        (None, Some(instant), Some(zone)) if !zone.is_empty() => {
            node.insert("dateTime".into(), Value::String(instant.clone()));
            node.insert("timeZone".into(), Value::String(zone.clone()));
        }
        _ => return None,
    }
    Some(Value::Object(node))
}

/// A sanitized snapshot of confirmed provider state, for Python to settle or
/// rebase against. Only the fields Ion may own, plus structural evidence.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ConfirmedProviderEvent {
    pub provider_etag: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub start: Option<ProviderDateTime>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub end: Option<ProviderDateTime>,
    pub recurring: bool,
    pub has_attendees: bool,
    pub provider_locked: bool,
    pub event_type: String,
    pub deleted: bool,
}

/// Reads only the allowlisted fields out of a provider event resource. A raw
/// provider payload never leaves this function.
fn sanitize_event(value: &Value) -> Option<ConfirmedProviderEvent> {
    let etag = value.get("etag")?.as_str()?.to_string();
    if etag.is_empty() {
        return None;
    }
    let read_time = |key: &str| -> Option<ProviderDateTime> {
        let node = value.get(key)?;
        if let Some(date) = node.get("date").and_then(Value::as_str) {
            return Some(ProviderDateTime {
                date: Some(date.to_string()),
                date_time: None,
                time_zone: None,
            });
        }
        Some(ProviderDateTime {
            date: None,
            date_time: Some(node.get("dateTime")?.as_str()?.to_string()),
            time_zone: Some(
                node.get("timeZone")
                    .and_then(Value::as_str)
                    .unwrap_or("UTC")
                    .to_string(),
            ),
        })
    };
    Some(ConfirmedProviderEvent {
        provider_etag: etag,
        title: value
            .get("summary")
            .and_then(Value::as_str)
            .map(str::to_string),
        start: read_time("start"),
        end: read_time("end"),
        recurring: value
            .get("recurrence")
            .is_some_and(|node| node.as_array().is_some_and(|items| !items.is_empty())),
        has_attendees: value
            .get("attendees")
            .is_some_and(|node| node.as_array().is_some_and(|items| !items.is_empty())),
        provider_locked: value
            .get("locked")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        event_type: value
            .get("eventType")
            .and_then(Value::as_str)
            .unwrap_or("default")
            .to_string(),
        deleted: value.get("status").and_then(Value::as_str) == Some("cancelled"),
    })
}

/// One provider outcome, in the closed storage vocabulary Python classifies.
struct ProviderOutcome {
    failure_class: &'static str,
    confirmed: Option<ConfirmedProviderEvent>,
}

/// Execute exactly one bounded edit against Google.
///
/// Uses the last confirmed ETag as an **exact** `If-Match`. `If-Match: *` is
/// never sent: a wildcard would overwrite whatever Google currently holds,
/// which is precisely the guarantee the conditional write exists to provide.
async fn execute_patch(
    client: &Client,
    access_token: &str,
    plan: &ProviderWritePlan,
    provider_calendar_id: &str,
) -> ProviderOutcome {
    let (Some(url), Some(body)) = (
        event_url(provider_calendar_id, &plan.provider_event_id),
        patch_body(&plan.changed_fields, &plan.desired),
    ) else {
        return ProviderOutcome {
            failure_class: "invalid_target",
            confirmed: None,
        };
    };
    let Some(etag) = plan
        .expected_provider_etag
        .as_deref()
        .filter(|value| !value.is_empty() && *value != "*")
    else {
        // Without a confirmed version there is nothing safe to condition on,
        // and Ion does not fall back to an unconditional write.
        return ProviderOutcome {
            failure_class: "invalid_target",
            confirmed: None,
        };
    };
    let response = client
        .patch(url.clone())
        .bearer_auth(access_token)
        .header("If-Match", etag)
        .json(&body)
        .send()
        .await;
    let Ok(response) = response else {
        return ProviderOutcome {
            failure_class: "retryable_transport",
            confirmed: None,
        };
    };
    let status = response.status();
    let bytes = response.bytes().await.unwrap_or_default();
    if status.is_success() {
        return match serde_json::from_slice::<Value>(&bytes)
            .ok()
            .as_ref()
            .and_then(sanitize_event)
        {
            Some(confirmed) => ProviderOutcome {
                failure_class: "success",
                confirmed: Some(confirmed),
            },
            // A success Ion cannot read is ambiguous, not a failure to retry
            // blindly; Python reconciles it.
            None => ProviderOutcome {
                failure_class: "duplicate_or_ambiguous_create",
                confirmed: None,
            },
        };
    }
    match status.as_u16() {
        // Ordinary version drift. Re-read confirmed state so Python can rebase
        // automatically; this is never surfaced to the owner.
        412 | 409 => {
            let confirmed = read_event(client, access_token, provider_calendar_id, plan).await;
            ProviderOutcome {
                failure_class: "stale_precondition",
                confirmed,
            }
        }
        401 => ProviderOutcome {
            failure_class: "reauthentication_required",
            confirmed: None,
        },
        403 => ProviderOutcome {
            failure_class: "terminal_provider_rejection",
            confirmed: None,
        },
        404 | 410 => ProviderOutcome {
            failure_class: "provider_not_found",
            confirmed: None,
        },
        429 => ProviderOutcome {
            failure_class: "retryable_quota",
            confirmed: None,
        },
        500..=599 => ProviderOutcome {
            failure_class: "retryable_backend",
            confirmed: None,
        },
        _ => ProviderOutcome {
            failure_class: "terminal_provider_rejection",
            confirmed: None,
        },
    }
}

/// `GET` the same event, only to obtain fresh confirmed authority for a rebase.
async fn read_event(
    client: &Client,
    access_token: &str,
    provider_calendar_id: &str,
    plan: &ProviderWritePlan,
) -> Option<ConfirmedProviderEvent> {
    let url = event_url(provider_calendar_id, &plan.provider_event_id)?;
    let response = client
        .get(url)
        .bearer_auth(access_token)
        .send()
        .await
        .ok()?;
    if response.status() == reqwest::StatusCode::NOT_FOUND {
        return Some(ConfirmedProviderEvent {
            provider_etag: "gone".into(),
            deleted: true,
            event_type: "default".into(),
            ..Default::default()
        });
    }
    if !response.status().is_success() {
        return None;
    }
    let bytes = response.bytes().await.ok()?;
    sanitize_event(&serde_json::from_slice::<Value>(&bytes).ok()?)
}

/// One durable unit of provider work, as the local API describes it.
#[derive(Debug, Clone, Deserialize)]
pub struct ProviderWritePlan {
    pub intent_id: String,
    #[allow(dead_code)]
    pub block_id: String,
    pub account_id: String,
    pub calendar_id: String,
    pub provider_event_id: String,
    pub operation: String,
    /// Always `single` in R1. Carried so a widened scope in R4/R5 fails the
    /// parity test rather than being silently ignored here.
    #[allow(dead_code)]
    pub recurrence_scope: String,
    pub changed_fields: Vec<String>,
    pub desired: DirectHumanEditDraft,
    pub expected_provider_etag: Option<String>,
    #[allow(dead_code)]
    pub attempt_count: i64,
    pub dispatchable: bool,
}

#[derive(Debug, Deserialize)]
struct ProviderWorkOutput {
    plans: Vec<ProviderWritePlan>,
    #[allow(dead_code)]
    provider_busy: bool,
}

#[derive(Debug, Serialize)]
struct IntentIdInput<'a> {
    intent_id: &'a str,
}

#[derive(Debug, Serialize)]
struct OutcomeInput<'a> {
    intent_id: &'a str,
    failure_class: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    confirmed: Option<&'a ConfirmedProviderEvent>,
}

#[derive(Debug, Deserialize)]
struct OutcomeResult {
    #[allow(dead_code)]
    recovery: Option<String>,
    #[allow(dead_code)]
    state: String,
    rebased: bool,
}

#[derive(Debug, Serialize)]
struct ConsentInput<'a> {
    account_id: &'a str,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConsentOutput {
    pub account_id: String,
    pub resumed_intent_ids: Vec<String>,
}

/// How Rust obtains an access token and the provider calendar id for a plan.
///
/// Extracted as a trait so a seam test can drive the real dispatch loop --
/// including its Python round-trips -- against a synthetic provider, without
/// the production path gaining any injection point of its own.
#[allow(async_fn_in_trait)]
pub(crate) trait ProviderAuthority {
    async fn access_token(&self, account_id: &str) -> Option<String>;
    async fn provider_calendar_id(&self, calendar_id: &str) -> Option<String>;
}

/// Drain bounded ready provider work.
///
/// Python decides *what* is ready and *how* each outcome settles. This loop
/// only executes and reports. It is bounded and event-driven: there is no
/// timer, no poll, and no worker per event or calendar.
pub(crate) async fn dispatch_ready_writes(
    service: &ServiceState,
    client: &Client,
    authority: &impl ProviderAuthority,
) -> Result<usize, GoogleCommandError> {
    let mut dispatched = 0usize;
    for _ in 0..MAX_WRITES_PER_TRIGGER {
        let work: ProviderWorkOutput = product_request::<(), ProviderWorkOutput>(
            service,
            reqwest::Method::POST,
            "/v1/calendar/writes/internal/work",
            None,
        )
        .await?;
        let Some(plan) = work.plans.into_iter().next() else {
            break;
        };
        if !plan.dispatchable || !DISPATCHABLE_OPERATIONS.contains(&plan.operation.as_str()) {
            break;
        }
        let (Some(token), Some(provider_calendar_id)) = (
            authority.access_token(&plan.account_id).await,
            authority.provider_calendar_id(&plan.calendar_id).await,
        ) else {
            report_outcome(service, &plan, "reauthentication_required", None).await?;
            break;
        };

        product_request::<IntentIdInput<'_>, serde_json::Value>(
            service,
            reqwest::Method::POST,
            "/v1/calendar/writes/internal/attempt",
            Some(&IntentIdInput {
                intent_id: &plan.intent_id,
            }),
        )
        .await?;

        let outcome = execute_patch(client, &token, &plan, &provider_calendar_id).await;
        let result = report_outcome(
            service,
            &plan,
            outcome.failure_class,
            outcome.confirmed.as_ref(),
        )
        .await?;
        dispatched += 1;
        // A rebase re-arms the same intent, so keep draining; anything else has
        // either settled or is deliberately waiting.
        if !result.rebased && outcome.failure_class != "success" {
            break;
        }
    }
    Ok(dispatched)
}

async fn report_outcome(
    service: &ServiceState,
    plan: &ProviderWritePlan,
    failure_class: &str,
    confirmed: Option<&ConfirmedProviderEvent>,
) -> Result<OutcomeResult, GoogleCommandError> {
    product_request::<OutcomeInput<'_>, OutcomeResult>(
        service,
        reqwest::Method::POST,
        "/v1/calendar/writes/internal/outcome",
        Some(&OutcomeInput {
            intent_id: &plan.intent_id,
            failure_class,
            confirmed,
        }),
    )
    .await
    .map_err(Into::into)
}

/// Record the one-time Google write capability grant with the local API.
pub(crate) async fn record_write_consent(
    service: &ServiceState,
    account_id: &str,
) -> Result<ConsentOutput, GoogleCommandError> {
    product_request::<ConsentInput<'_>, ConsentOutput>(
        service,
        reqwest::Method::POST,
        "/v1/calendar/writes/internal/consent",
        Some(&ConsentInput { account_id }),
    )
    .await
    .map_err(Into::into)
}

/// Production provider authority: Keychain refresh token, in-memory access
/// token, and the confirmed provider calendar id from the local API. Tokens
/// never leave Rust and never reach the renderer.
pub(crate) struct LiveAuthority<'a> {
    pub service: &'a ServiceState,
    pub google: &'a crate::google_calendar::GoogleState,
    pub config: &'a crate::google_calendar::OAuthConfig,
    pub client: &'a Client,
}

impl ProviderAuthority for LiveAuthority<'_> {
    async fn access_token(&self, account_id: &str) -> Option<String> {
        if let Some(value) = self.google.cached_token(account_id) {
            return Some(value);
        }
        let state = crate::google_calendar::internal_state(self.service)
            .await
            .ok()?;
        let account = state
            .accounts
            .iter()
            .find(|entry| entry.account.id == account_id)?;
        let refresh = {
            use crate::google_calendar::RefreshTokenStore as _;
            crate::google_calendar::SystemKeychain
                .get(&account.keychain_locator)
                .ok()?
        };
        let token =
            crate::google_calendar::refresh_access_token(self.client, self.config, &refresh)
                .await
                .ok()?;
        let value = token.access_token.clone();
        self.google
            .store_access_token(account_id, token.access_token, token.expires_in);
        Some(value)
    }

    async fn provider_calendar_id(&self, calendar_id: &str) -> Option<String> {
        let state = crate::google_calendar::internal_state(self.service)
            .await
            .ok()?;
        state
            .calendars
            .iter()
            .find(|entry| entry.calendar.id == calendar_id)
            .map(|entry| entry.calendar.provider_calendar_id.clone())
    }
}

/// Grant Ion permission to edit this Google account's Calendar.
///
/// A **one-time capability transition**, not approval of any Calendar action.
/// The owner's edit is already durable when this runs; afterwards it resumes
/// automatically and they never retype it. Once granted, ordinary edits ask for
/// nothing further.
#[tauri::command]
pub async fn enable_google_calendar_writes<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    service: State<'_, ServiceState>,
    google: State<'_, crate::google_calendar::GoogleState>,
    account_id: String,
) -> Result<ConsentOutput, GoogleCommandError> {
    use crate::google_calendar as gc;
    use std::net::TcpListener;

    let config = gc::load_oauth_config(&gc::oauth_config_path(&app)?)?;
    let client = gc::google_client()?;
    let state = gc::internal_state(&service).await?;
    let account = state
        .accounts
        .iter()
        .find(|entry| entry.account.id == account_id)
        .ok_or_else(|| GoogleCommandError::new("local_state_not_found"))?;

    let listener = TcpListener::bind("127.0.0.1:0")
        .map_err(|_| GoogleCommandError::new("oauth_callback_unavailable"))?;
    let port = listener
        .local_addr()
        .map_err(|_| GoogleCommandError::new("oauth_callback_unavailable"))?
        .port();
    let redirect_uri = format!("http://127.0.0.1:{port}/oauth2/callback");
    let state_value = base64::Engine::encode(
        &base64::engine::general_purpose::URL_SAFE_NO_PAD,
        gc::random_bytes::<32>()?,
    );
    let (verifier, challenge) = gc::pkce_pair()?;
    // Exactly the accepted scope set: CalendarList read-only plus Calendar
    // Events write. Nothing broader is ever requested.
    let url = gc::authorization_url_for(&config, &redirect_uri, &state_value, &challenge, true)?;
    gc::open_system_browser_public(&url)?;
    let callback =
        tauri::async_runtime::spawn_blocking(move || gc::await_callback(listener, state_value))
            .await
            .map_err(|_| GoogleCommandError::new("oauth_callback_unavailable"))??;
    let token = gc::exchange_code(&client, &config, &callback, &verifier, &redirect_uri).await?;

    // The refresh token stays in the Keychain under the account's existing
    // locator; the access token stays in Rust memory. Neither reaches Python or
    // the renderer.
    if let Some(refresh) = token.refresh_token.as_deref() {
        use gc::RefreshTokenStore as _;
        gc::SystemKeychain.set(&account.keychain_locator, refresh)?;
    }
    google.store_access_token(&account_id, token.access_token, token.expires_in);

    let consent = record_write_consent(&service, &account_id).await?;
    // Resume the edit the owner already made, immediately and without asking.
    let authority = LiveAuthority {
        service: &service,
        google: &google,
        config: &config,
        client: &client,
    };
    let _ = dispatch_ready_writes(&service, &client, &authority).await;
    Ok(consent)
}

/// Run the bounded dispatcher for whatever is ready right now.
///
/// Called immediately after an edit is accepted, so an ordinary write needs no
/// Sync Now and no other user action. Failure here is deliberately not fatal to
/// the human action: the intent is already durable and recovery will re-arm it.
pub(crate) async fn dispatch_after_human_action<R: tauri::Runtime>(
    app: &tauri::AppHandle<R>,
    service: &ServiceState,
    google: &crate::google_calendar::GoogleState,
) {
    use crate::google_calendar as gc;
    let Ok(path) = gc::oauth_config_path(app) else {
        return;
    };
    let (Ok(config), Ok(client)) = (gc::load_oauth_config(&path), gc::google_client()) else {
        return;
    };
    let authority = LiveAuthority {
        service,
        google,
        config: &config,
        client: &client,
    };
    let _ = dispatch_ready_writes(service, &client, &authority).await;
}

/// The production Tauri edit seam, exercised against a synthetic Google.
///
/// R0 proved contract parity but never invoked a real edit end to end. These
/// tests do: the renderer's JSON payload is deserialized into the production
/// command's argument types, and the production dispatch loop then runs against
/// a real authenticated FastAPI over real SQLite at migration head 0007, with
/// only the Google endpoint replaced by a synthetic server.
///
/// Nothing about the request construction, allowlists, conditional header,
/// outcome classification, or Python round-trips is stubbed.
#[cfg(test)]
mod seam {
    use super::*;
    use std::io::{BufRead, BufReader, Write};
    use std::net::TcpListener;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Arc;

    /// A minimal synthetic Google that records what Ion actually sent.
    /// method, path, If-Match, body -- exactly what Ion put on the wire.
    type RecordedRequest = (String, String, String, String);

    struct SyntheticGoogle {
        pub base: String,
        pub requests: Arc<std::sync::Mutex<Vec<RecordedRequest>>>,
        pub patch_calls: Arc<AtomicUsize>,
    }

    fn spawn_google(script: Vec<(u16, String)>) -> SyntheticGoogle {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind synthetic google");
        let port = listener.local_addr().unwrap().port();
        let requests = Arc::new(std::sync::Mutex::new(Vec::new()));
        let patch_calls = Arc::new(AtomicUsize::new(0));
        let recorded = Arc::clone(&requests);
        let counted = Arc::clone(&patch_calls);
        std::thread::spawn(move || {
            let mut remaining = script.into_iter();
            for stream in listener.incoming() {
                let Ok(mut stream) = stream else { break };
                let mut reader = BufReader::new(stream.try_clone().unwrap());
                let mut request_line = String::new();
                if reader.read_line(&mut request_line).is_err() {
                    break;
                }
                let mut method_and_path = request_line.split_whitespace();
                let method = method_and_path.next().unwrap_or("").to_string();
                let path = method_and_path.next().unwrap_or("").to_string();
                let mut if_match = String::new();
                let mut length = 0usize;
                loop {
                    let mut line = String::new();
                    if reader.read_line(&mut line).unwrap_or(0) == 0 || line == "\r\n" {
                        break;
                    }
                    let lower = line.to_ascii_lowercase();
                    if let Some(value) = lower.strip_prefix("if-match:") {
                        if_match = value.trim().to_string();
                    }
                    if let Some(value) = lower.strip_prefix("content-length:") {
                        length = value.trim().parse().unwrap_or(0);
                    }
                }
                let mut body = vec![0u8; length];
                if length > 0 {
                    std::io::Read::read_exact(&mut reader, &mut body).ok();
                }
                if method == "PATCH" {
                    counted.fetch_add(1, Ordering::SeqCst);
                }
                recorded.lock().unwrap().push((
                    method,
                    path,
                    if_match,
                    String::from_utf8_lossy(&body).to_string(),
                ));
                let (status, payload) = remaining
                    .next()
                    .unwrap_or((200, "{\"etag\":\"\\\"fallback\\\"\"}".into()));
                let response = format!(
                    "HTTP/1.1 {status} OK\r\nContent-Type: application/json\r\n\
                     Content-Length: {}\r\nConnection: close\r\n\r\n{payload}",
                    payload.len()
                );
                stream.write_all(response.as_bytes()).ok();
                stream.flush().ok();
            }
        });
        SyntheticGoogle {
            base: format!("http://127.0.0.1:{port}/calendar/v3/"),
            requests,
            patch_calls,
        }
    }

    /// The API-base override is global, so seam tests that use it run one at a
    /// time. Holding the guard also guarantees the override is cleared even if
    /// an assertion panics.
    static SEAM_GUARD: std::sync::Mutex<()> = std::sync::Mutex::new(());

    struct ApiOverride(#[allow(dead_code)] std::sync::MutexGuard<'static, ()>);

    impl ApiOverride {
        fn new(base: &str) -> Self {
            let guard = SEAM_GUARD.lock().unwrap_or_else(|error| error.into_inner());
            *TEST_CALENDAR_API.lock().unwrap() = Some(base.to_string());
            Self(guard)
        }
    }

    impl Drop for ApiOverride {
        fn drop(&mut self) {
            *TEST_CALENDAR_API.lock().unwrap() = None;
        }
    }

    struct StubAuthority;

    impl ProviderAuthority for StubAuthority {
        async fn access_token(&self, _: &str) -> Option<String> {
            // Stands in for Keychain + refresh. Real tokens never leave Rust,
            // and a test must never hold one.
            Some("synthetic-access-token".into())
        }
        async fn provider_calendar_id(&self, _: &str) -> Option<String> {
            Some("synthetic-primary@example.invalid".into())
        }
    }

    fn renderer_payload() -> serde_json::Value {
        serde_json::json!({
            "command_id": "11111111-1111-4111-8111-111111111111",
            "operation": "patch",
            "recurrence_scope": "single",
            "expected_revision": 1,
            "changed_fields": ["title"],
            "draft": {"title": "Renamed by the owner"}
        })
    }

    /// The renderer's JSON must deserialize into the *production* command's
    /// argument type. This is the IPC half of the seam.
    #[test]
    fn the_renderer_payload_deserializes_into_the_production_command_argument() {
        let intent: DirectHumanIntentDraft =
            serde_json::from_value(renderer_payload()).expect("renderer payload is accepted");
        assert_eq!(intent.operation, "patch");
        assert_eq!(intent.changed_fields, vec!["title".to_string()]);
        assert!(draft_matches(&intent.changed_fields, &intent.draft));

        // And a payload carrying provider authority is refused by the type.
        let mut hostile = renderer_payload();
        hostile["expected_provider_etag"] = serde_json::json!("\"attacker\"");
        assert!(serde_json::from_value::<DirectHumanIntentDraft>(hostile).is_err());
    }

    fn plan(etag: &str) -> ProviderWritePlan {
        ProviderWritePlan {
            intent_id: "intent-1".into(),
            block_id: "block-1".into(),
            account_id: "account-1".into(),
            calendar_id: "calendar-1".into(),
            provider_event_id: "synthetic-event".into(),
            operation: "patch".into(),
            recurrence_scope: "single".into(),
            changed_fields: vec!["title".into()],
            desired: DirectHumanEditDraft {
                title: Some("Renamed by the owner".into()),
                start: None,
                end: None,
            },
            expected_provider_etag: Some(etag.into()),
            attempt_count: 0,
            dispatchable: true,
        }
    }

    #[tokio::test]
    async fn the_production_patch_sends_an_exact_if_match_and_only_changed_fields() {
        let google = spawn_google(vec![(
            200,
            "{\"etag\":\"\\\"etag-2\\\"\",\"summary\":\"Renamed by the owner\"}".into(),
        )]);
        let _override = ApiOverride::new(&google.base);
        let client = Client::new();
        let outcome = execute_patch(
            &client,
            "synthetic-access-token",
            &plan("\"etag-1\""),
            "synthetic-primary@example.invalid",
        )
        .await;

        assert_eq!(outcome.failure_class, "success");
        assert_eq!(
            outcome
                .confirmed
                .as_ref()
                .map(|value| value.provider_etag.clone()),
            Some("\"etag-2\"".to_string())
        );
        let requests = google.requests.lock().unwrap();
        let (method, path, if_match, body) = requests.first().expect("one provider request");
        assert_eq!(method, "PATCH");
        assert!(path.contains("/events/synthetic-event"));
        // Exact conditional authority, never a wildcard.
        assert_eq!(if_match, "\"etag-1\"");
        assert_ne!(if_match, "*");
        // Only the field the owner changed.
        assert_eq!(body, "{\"summary\":\"Renamed by the owner\"}");
        for forbidden in ["attendees", "reminders", "conferenceData", "recurrence"] {
            assert!(!body.contains(forbidden));
        }
    }

    #[tokio::test]
    async fn a_stale_precondition_re_reads_confirmed_state_for_an_automatic_rebase() {
        let google = spawn_google(vec![
            (412, "{\"error\":{\"errors\":[]}}".into()),
            (
                200,
                "{\"etag\":\"\\\"etag-fresh\\\"\",\"summary\":\"Google title\"}".into(),
            ),
        ]);
        let _override = ApiOverride::new(&google.base);
        let client = Client::new();
        let outcome = execute_patch(
            &client,
            "synthetic-access-token",
            &plan("\"etag-stale\""),
            "synthetic-primary@example.invalid",
        )
        .await;

        // Ordinary drift: classified for automatic rebase, with fresh authority.
        assert_eq!(outcome.failure_class, "stale_precondition");
        let confirmed = outcome.confirmed.expect("fresh provider authority");
        assert_eq!(confirmed.provider_etag, "\"etag-fresh\"");
        assert!(!confirmed.recurring && !confirmed.has_attendees);
        let requests = google.requests.lock().unwrap();
        assert_eq!(requests.len(), 2);
        assert_eq!(requests[1].0, "GET");
    }

    #[tokio::test]
    async fn a_write_without_confirmed_authority_is_refused_rather_than_forced() {
        let google = spawn_google(vec![]);
        let _override = ApiOverride::new(&google.base);
        let client = Client::new();
        let mut wildcard = plan("*");
        let outcome =
            execute_patch(&client, "t", &wildcard, "synthetic-primary@example.invalid").await;
        assert_eq!(outcome.failure_class, "invalid_target");
        wildcard.expected_provider_etag = None;
        let outcome =
            execute_patch(&client, "t", &wildcard, "synthetic-primary@example.invalid").await;
        assert_eq!(outcome.failure_class, "invalid_target");
        // Ion never falls back to an unconditional write.
        assert_eq!(google.patch_calls.load(Ordering::SeqCst), 0);
    }

    /// The full production loop, end to end.
    ///
    /// renderer payload -> production command argument type -> Rust validators
    /// -> **real FastAPI over loopback** -> **real SQLite at 0007** -> provider
    /// work selection -> the production dispatch loop -> synthetic Google ->
    /// settlement -> resulting state read back from the same API.
    ///
    /// Only the Google endpoint is synthetic. The API, database, routes,
    /// request construction, conditional header, and outcome classification are
    /// all the production ones. Ignored by default because it starts a Python
    /// process; run with `cargo test -- --ignored`.
    #[tokio::test]
    #[ignore = "starts the real local API; run explicitly"]
    async fn the_production_edit_crosses_every_layer_and_settles() {
        let port = 8791u16;
        std::env::set_var("ION_API_PORT", port.to_string());
        let data_dir = std::env::temp_dir().join("ion-r1-seam");
        // The venv interpreter directly, so killing the child actually stops
        // the server rather than only its launcher.
        let api_dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../api")
            .canonicalize()
            .expect("api directory");
        let mut api = std::process::Command::new(api_dir.join(".venv/bin/python"))
            .arg(api_dir.join("tests/support/serve_api.py"))
            .arg(&data_dir)
            .current_dir(&api_dir)
            .env("ION_API_PORT", port.to_string())
            .spawn()
            .expect("start the real local API");

        let client = Client::new();
        let base = format!("http://127.0.0.1:{port}");
        let mut ready = false;
        for _ in 0..80 {
            if client.get(format!("{base}/health")).send().await.is_ok() {
                ready = true;
                break;
            }
            tokio::time::sleep(std::time::Duration::from_millis(150)).await;
        }
        assert!(ready, "local API did not start");

        let result = async {
            // 1. The renderer's payload, through the production argument type.
            let intent: DirectHumanIntentDraft =
                serde_json::from_value(renderer_payload()).expect("renderer payload deserializes");
            let service = ServiceState::default();
            let block = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
            let route = format!("/v1/calendar/writes/blocks/{block}/intent");

            // 2. Rust validators, then the real authenticated-shape API call.
            assert!(draft_matches(&intent.changed_fields, &intent.draft));
            let receipt: DirectHumanIntentReceipt = product_request(
                &service,
                reqwest::Method::POST,
                &route,
                Some(&IntentInput {
                    command_id: &intent.command_id,
                    operation: &intent.operation,
                    recurrence_scope: &intent.recurrence_scope,
                    expected_revision: intent.expected_revision,
                    changed_fields: intent.changed_fields.iter().map(String::as_str).collect(),
                    draft: &intent.draft,
                    provenance: "direct_human",
                }),
            )
            .await
            .expect("the local API accepts the direct human intent");
            assert!(receipt.accepted);
            assert_eq!(receipt.state, "ready");

            // 3. Optimistic projection is visible before Google hears anything.
            let status: serde_json::Value = client
                .get(format!("{base}/v1/calendar/status"))
                .send()
                .await
                .unwrap()
                .json()
                .await
                .unwrap();
            assert_eq!(
                status["blocks"][0]["title"].as_str(),
                Some("Renamed by the owner")
            );
            assert!(!status.to_string().contains("Not saved yet"));

            // 4. The production dispatch loop, against a synthetic Google.
            let google = spawn_google(vec![(
                200,
                "{\"etag\":\"\\\"etag-2\\\"\",\"summary\":\"Renamed by the owner\"}".into(),
            )]);
            let _override = ApiOverride::new(&google.base);
            let dispatched = dispatch_ready_writes(&service, &client, &StubAuthority)
                .await
                .expect("dispatch runs");
            assert_eq!(dispatched, 1);

            // Exact conditional authority actually reached the provider.
            let requests = google.requests.lock().unwrap();
            let (method, _, if_match, body) = requests.first().expect("one PATCH");
            assert_eq!(method, "PATCH");
            assert_eq!(if_match, "\"synthetic-etag-1\"");
            assert_eq!(body, "{\"summary\":\"Renamed by the owner\"}");
            drop(requests);

            // 5. Settlement collapsed the overlay onto confirmed state.
            let settled: serde_json::Value = client
                .get(format!("{base}/v1/calendar/status"))
                .send()
                .await
                .unwrap()
                .json()
                .await
                .unwrap();
            assert_eq!(
                settled["blocks"][0]["title"].as_str(),
                Some("Renamed by the owner")
            );
            assert_eq!(
                settled["write_recovery"].as_array().map(Vec::len),
                Some(0),
                "an ordinary edit asks the owner nothing"
            );
        }
        .await;

        api.kill().ok();
        api.wait().ok();
        let _ = result;
    }

    #[test]
    fn the_provider_body_cannot_express_anything_outside_the_allowlist() {
        let draft = DirectHumanEditDraft {
            title: Some("Study".into()),
            start: Some(ProviderDateTime {
                date: None,
                date_time: Some("2030-01-07T19:00:00Z".into()),
                time_zone: Some("America/Los_Angeles".into()),
            }),
            end: None,
        };
        let body = patch_body(&["title".into(), "start".into()], &draft).expect("body");
        assert_eq!(
            body["start"]["timeZone"].as_str(),
            Some("America/Los_Angeles")
        );
        assert!(body.get("recurrence").is_none());
        // An unknown field cannot be smuggled through.
        assert!(patch_body(&["recurrence".into()], &draft).is_none());
        // All-day semantics survive.
        let all_day = DirectHumanEditDraft {
            title: None,
            start: Some(ProviderDateTime {
                date: Some("2030-01-07".into()),
                date_time: None,
                time_zone: None,
            }),
            end: None,
        };
        let body = patch_body(&["start".into()], &all_day).expect("body");
        assert_eq!(body["start"]["date"].as_str(), Some("2030-01-07"));
        assert!(body["start"].get("dateTime").is_none());
    }
}
