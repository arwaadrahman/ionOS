import { useState } from "react";
import {
  CalendarStatus,
  asGoogleError,
  googleCalendarClient,
} from "./calendar";

const errorCopy: Record<string, string> = {
  not_configured:
    "Add the local Google Desktop OAuth configuration, then try again.",
  configuration_invalid: "The local OAuth configuration is invalid.",
  oauth_cancelled:
    "Google authorization was cancelled. No account was connected.",
  oauth_scope_denied: "Both read-only Calendar permissions are required.",
  oauth_state_mismatch:
    "Ion rejected an OAuth callback that did not match this request.",
  reauth_required:
    "Google authorization expired or was revoked. Reconnect this account.",
  busy: "A calendar synchronization is already running.",
  unavailable:
    "Calendar synchronization is unavailable. Cached events remain local.",
  local_service_unavailable:
    "The local calendar service is unavailable. Cached events remain unchanged.",
};

function formatTimestamp(value: string | null) {
  if (!value) return "Never synced";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}

export function CalendarWorkspace({
  status,
  onStatus,
}: {
  status: CalendarStatus;
  onStatus: (status: CalendarStatus) => void;
}) {
  const [pending, setPending] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  async function run(label: string, operation: () => Promise<CalendarStatus>) {
    if (pending) return;
    setPending(label);
    setFeedback(null);
    try {
      onStatus(await operation());
    } catch (reason) {
      const error = asGoogleError(reason);
      setFeedback(errorCopy[error.code] ?? errorCopy.unavailable);
    } finally {
      setPending(null);
    }
  }

  async function connect() {
    if (pending) return;
    setPending("connect");
    setFeedback(null);
    try {
      onStatus(await googleCalendarClient.connect());
      setPending("sync");
      onStatus(await googleCalendarClient.sync());
    } catch (reason) {
      const error = asGoogleError(reason);
      setFeedback(errorCopy[error.code] ?? errorCopy.unavailable);
    } finally {
      setPending(null);
    }
  }

  const connected = status.accounts.filter(
    (account) => account.auth_state !== "disconnected",
  );

  return (
    <section className="workspace calendar-workspace">
      <header className="calendar-header">
        <div>
          <p className="eyebrow">CALENDAR · READ SYNC FOUNDATION</p>
          <h1>Google Calendar</h1>
          <p className="summary">
            Google owns synchronized event fields. Ion keeps a local canonical
            cache and its own calendar selection and metadata.
          </p>
        </div>
        <div className="calendar-header-actions">
          <button
            type="button"
            disabled={Boolean(pending) || !status.configured}
            onClick={() => void connect()}
          >
            {pending === "connect"
              ? "Waiting for Google…"
              : connected.length
                ? "Connect another account"
                : "Connect Google account"}
          </button>
          <button
            type="button"
            disabled={Boolean(pending) || connected.length === 0}
            onClick={() => void run("sync", googleCalendarClient.sync)}
          >
            {pending === "sync" ? "Syncing…" : "Sync now"}
          </button>
        </div>
      </header>

      {!status.configured ? (
        <div className="notice notice--warning" role="status">
          <strong>Local OAuth configuration required.</strong>
          <span>
            Create{" "}
            <code>{status.configuration_path || "google-oauth.json"}</code> with
            a Google Desktop OAuth <code>client_id</code> and optional{" "}
            <code>client_secret</code>. Credentials remain outside Git.
          </span>
        </div>
      ) : null}
      {feedback ? (
        <p className="notice notice--warning" role="alert">
          {feedback}
        </p>
      ) : null}

      {connected.length === 0 ? (
        <div className="calendar-empty">
          <h2>No Google account connected</h2>
          <p>
            Ion requests only read access to your Calendar list and events.
            Login opens in your system browser; refresh tokens stay in macOS
            Keychain.
          </p>
          <p>
            Scopes: <code>calendar.calendarlist.readonly</code> and{" "}
            <code>calendar.events.readonly</code>.
          </p>
        </div>
      ) : (
        connected.map((account) => {
          const calendars = status.calendars.filter(
            (calendar) => calendar.account_id === account.id,
          );
          const blockCount = status.blocks.filter((block) =>
            calendars.some((calendar) => calendar.id === block.calendar_id),
          ).length;
          return (
            <section className="calendar-account" key={account.id}>
              <div className="calendar-account-heading">
                <div>
                  <span className="badge">
                    {account.auth_state.replace("_", " ")}
                  </span>
                  <h2>{account.display_name}</h2>
                  <p>
                    {blockCount} cached canonical block
                    {blockCount === 1 ? "" : "s"}
                  </p>
                </div>
                <button
                  className="danger-button"
                  type="button"
                  disabled={Boolean(pending)}
                  onClick={() =>
                    void run(`disconnect:${account.id}`, () =>
                      googleCalendarClient.disconnect(account),
                    )
                  }
                >
                  {pending === `disconnect:${account.id}`
                    ? "Disconnecting…"
                    : "Disconnect & revoke"}
                </button>
              </div>
              {account.auth_state === "reauth_required" ? (
                <p className="notice notice--warning">
                  Reauthentication is required. Use Connect to authorize this
                  account again; cached blocks remain available.
                </p>
              ) : null}
              <ul className="calendar-list">
                {calendars.map((calendar) => (
                  <li key={calendar.id}>
                    <div className="calendar-copy">
                      <strong>
                        {calendar.summary}
                        {calendar.is_primary ? (
                          <span className="badge">Primary</span>
                        ) : null}
                      </strong>
                      <span>
                        {calendar.access_role} ·{" "}
                        {calendar.timezone ?? "Google default"}
                      </span>
                      <span>
                        {calendar.sync_state.replace("_", " ")} ·{" "}
                        {formatTimestamp(calendar.last_synced_at)}
                      </span>
                      {calendar.last_error_code ? (
                        <span className="calendar-error">
                          {calendar.last_error_code.replaceAll("_", " ")}
                          {calendar.next_retry_at
                            ? ` · retry after ${formatTimestamp(calendar.next_retry_at)}`
                            : ""}
                        </span>
                      ) : null}
                    </div>
                    <label className="calendar-toggle">
                      <input
                        type="checkbox"
                        checked={calendar.enabled_in_ion}
                        disabled={
                          Boolean(pending) ||
                          calendar.provider_deleted ||
                          ["none", "freeBusyReader"].includes(
                            calendar.access_role,
                          )
                        }
                        onChange={(event) =>
                          void run(`selection:${calendar.id}`, () =>
                            googleCalendarClient.setEnabled(
                              calendar,
                              event.currentTarget.checked,
                            ),
                          )
                        }
                      />
                      Enabled in Ion
                    </label>
                  </li>
                ))}
              </ul>
            </section>
          );
        })
      )}
      <p className="context-note">
        Phase 2A is read-only. Ion does not create, edit, delete, share, or
        change Google Calendar visibility settings.
      </p>
    </section>
  );
}
