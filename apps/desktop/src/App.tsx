import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { ionTokens } from "@ion/design";
import { OrganizerShell } from "./OrganizerShell";
import { StartupData, loadStartupData } from "./startup";

type HealthState = "checking" | "ready" | "unavailable";
type ServiceStatus = { state: HealthState };
type AppProps = { development?: boolean };
const apiOrigin = __ION_API_ORIGIN__;

export function App({ development = import.meta.env.DEV }: AppProps = {}) {
  const [health, setHealth] = useState<HealthState>("checking");
  const [data, setData] = useState<StartupData | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    async function hydrate() {
      try {
        if (!development) {
          const status = await invoke<ServiceStatus>("service_health");
          if (status.state !== "ready") {
            setHealth(status.state);
            return;
          }
        } else {
          const response = await fetch(`${apiOrigin}/health`, {
            signal: controller.signal,
          });
          if (!response.ok) {
            setHealth("unavailable");
            return;
          }
        }
        const startup = await loadStartupData();
        if (!controller.signal.aborted) {
          setData(startup);
          setHealth("ready");
        }
      } catch {
        if (!controller.signal.aborted) setHealth("unavailable");
      }
    }
    void hydrate();
    return () => controller.abort();
  }, [development]);

  if (health === "ready" && data) return <OrganizerShell initialData={data} />;
  return (
    <main className="engineering-shell">
      <p className="eyebrow">ION OS · PHASE 1B</p>
      <h1>
        {health === "checking"
          ? "Preparing your workspace"
          : "Local service unavailable"}
      </h1>
      <p className="summary">
        Organizer data appears only after Ion confirms its local service and
        canonical startup state.
      </p>
      <div className={`service-status service-status--${health}`}>
        <span aria-hidden="true" className="status-dot" />
        <span>Local service: {health}</span>
      </div>
      <style>{`:root { --ion-accent: ${ionTokens.color.accent}; }`}</style>
    </main>
  );
}
