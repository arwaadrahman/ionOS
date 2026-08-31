import { memo } from "react";
import { CalendarStatus, GoogleAccount, GoogleCalendar } from "./calendar";
import { sourceCalendarColor } from "./calendarProjection";

function formatTimestamp(value: string | null) {
  if (!value) return "Never synced";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}

export const CalendarSidebar = memo(function CalendarSidebar({
  status,
  pending,
  onConnect,
  onToggle,
  onHidden,
  onDisconnect,
}: {
  status: CalendarStatus;
  pending: string | null;
  onConnect(): void;
  onToggle(calendar: GoogleCalendar, enabled: boolean): void;
  onHidden(calendar: GoogleCalendar, hidden: boolean): void;
  onDisconnect(account: GoogleAccount): void;
}) {
  const activeAccounts = status.accounts.filter(
    (account) =>
      account.auth_state !== "disconnected" ||
      status.calendars.some(
        (calendar) =>
          calendar.account_id === account.id && !calendar.provider_deleted,
      ),
  );
  const connected = status.accounts.filter(
    (account) => account.auth_state === "connected",
  );
  const needsReauthentication = status.accounts.some(
    (account) => account.auth_state === "reauth_required",
  );
  const hiddenCalendars = status.calendars.filter(
    (calendar) => calendar.hidden_in_ion && !calendar.provider_deleted,
  );

  return (
    <>
      <div className="calendar-sidebar-management">
        {activeAccounts.length === 0 ? (
          <div className="calendar-sidebar-empty">
            <strong>No calendar sources</strong>
            <span>
              Connect Google to populate the local read-only calendar.
            </span>
          </div>
        ) : (
          activeAccounts.map((account) => {
            const calendars = status.calendars.filter(
              (calendar) =>
                calendar.account_id === account.id &&
                !calendar.hidden_in_ion &&
                !calendar.provider_deleted,
            );
            const blockCount = status.blocks.filter((block) =>
              calendars.some((calendar) => calendar.id === block.calendar_id),
            ).length;
            return (
              <details className="calendar-source-group" key={account.id} open>
                <summary>
                  <span>
                    <strong>{account.display_name}</strong>
                    <small>
                      {account.auth_state.replaceAll("_", " ")} · {blockCount}{" "}
                      cached canonical {blockCount === 1 ? "block" : "blocks"}
                    </small>
                  </span>
                </summary>
                <ul>
                  {calendars.map((calendar) => {
                    const color = sourceCalendarColor(calendar.id);
                    const unreadable = ["none", "freeBusyReader"].includes(
                      calendar.access_role,
                    );
                    return (
                      <li className="calendar-source-row" key={calendar.id}>
                        <label>
                          <input
                            type="checkbox"
                            aria-label={`${calendar.summary} enabled in Ion`}
                            checked={calendar.enabled_in_ion}
                            disabled={
                              Boolean(pending) ||
                              calendar.provider_deleted ||
                              unreadable
                            }
                            onChange={(event) =>
                              onToggle(calendar, event.currentTarget.checked)
                            }
                          />
                          <span
                            className="calendar-color-dot"
                            style={{ background: color.accent }}
                            aria-hidden="true"
                          />
                          <span className="calendar-source-copy">
                            <strong>{calendar.summary}</strong>
                            <small>
                              {calendar.is_primary ? "Primary · " : ""}
                              {calendar.sync_state.replaceAll("_", " ")} ·{" "}
                              {formatTimestamp(calendar.last_synced_at)}
                            </small>
                            <small>
                              {calendar.access_role} · {calendar.timezone}
                            </small>
                            {calendar.last_error_code ? (
                              <small className="calendar-error">
                                {calendar.last_error_code.replaceAll("_", " ")}
                              </small>
                            ) : null}
                          </span>
                        </label>
                        <button
                          className="quiet-button calendar-hide-source"
                          type="button"
                          disabled={Boolean(pending)}
                          aria-label={`Hide ${calendar.summary} from Ion`}
                          onClick={() => onHidden(calendar, true)}
                        >
                          {pending === `visibility:${calendar.id}`
                            ? "Hiding…"
                            : "Hide from Ion"}
                        </button>
                      </li>
                    );
                  })}
                </ul>
                {account.auth_state === "reauth_required" ? (
                  <div className="calendar-reauth-action">
                    <span>
                      Google access expired or was revoked. Saved events remain
                      available.
                    </span>
                    <button
                      type="button"
                      disabled={Boolean(pending) || !status.configured}
                      onClick={onConnect}
                    >
                      Reconnect Google account
                    </button>
                  </div>
                ) : null}
                <button
                  className="quiet-button calendar-disconnect"
                  type="button"
                  disabled={
                    Boolean(pending) || account.auth_state === "disconnected"
                  }
                  onClick={() => onDisconnect(account)}
                >
                  {pending === `disconnect:${account.id}`
                    ? "Disconnecting…"
                    : "Disconnect & revoke"}
                </button>
              </details>
            );
          })
        )}
        {hiddenCalendars.length > 0 ? (
          <details className="calendar-hidden-sources">
            <summary>Hidden calendars · {hiddenCalendars.length}</summary>
            <ul>
              {hiddenCalendars.map((calendar) => {
                const account = status.accounts.find(
                  (item) => item.id === calendar.account_id,
                );
                return (
                  <li key={calendar.id}>
                    <span>
                      <strong>{calendar.summary}</strong>
                      <small>
                        {account?.display_name ?? "Calendar account"}
                      </small>
                    </span>
                    <button
                      className="quiet-button"
                      type="button"
                      disabled={Boolean(pending)}
                      onClick={() => onHidden(calendar, false)}
                    >
                      {pending === `visibility:${calendar.id}`
                        ? "Restoring…"
                        : "Restore to Ion"}
                    </button>
                  </li>
                );
              })}
            </ul>
          </details>
        ) : null}
      </div>
      <footer className="calendar-sidebar-footer">
        <p className="context-note">
          Calendar visibility is local to Ion. Google is read-only; provider
          subscriptions and event fields are never changed.
        </p>
        <div className="calendar-sidebar-actions">
          <button
            type="button"
            disabled={Boolean(pending) || !status.configured}
            onClick={onConnect}
          >
            {pending === "connect"
              ? "Waiting for Google…"
              : needsReauthentication
                ? "Reconnect Google account"
                : connected.length
                  ? "Connect another account"
                  : "Connect Google account"}
          </button>
        </div>
      </footer>
    </>
  );
});
