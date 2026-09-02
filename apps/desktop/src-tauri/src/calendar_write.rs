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

use serde::{Deserialize, Serialize};

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
pub(crate) const OWNER_ACTION_RECOVERY: [&str; 8] = [
    "reauthentication_required",
    "write_permission_lost",
    "provider_target_deleted",
    "recurrence_identity_lost",
    "unsupported_provider_transformation",
    "deterministic_id_collision",
    "provider_rejected_terminally",
    "automatic_recovery_exhausted",
];

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
pub struct DirectHumanIntentDraft {
    pub command_id: String,
    pub operation: String,
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
pub async fn accept_direct_human_calendar_intent(
    service: State<'_, ServiceState>,
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
    product_request(
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
    .await
    .map_err(Into::into)
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
