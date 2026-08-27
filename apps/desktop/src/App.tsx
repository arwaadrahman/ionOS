import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { ionTokens } from "@ion/design";

type HealthState = "checking" | "ready" | "unavailable";

const apiOrigin = __ION_API_ORIGIN__;

type ServiceStatus = { state: HealthState };

export function App() {
  const [health, setHealth] = useState<HealthState>("checking");

  useEffect(() => {
    const controller = new AbortController();

    async function checkService(): Promise<void> {
      try {
        if (!import.meta.env.DEV) {
          const status = await invoke<ServiceStatus>("service_health");
          setHealth(status.state);
          return;
        }
        const response = await fetch(`${apiOrigin}/health`, {
          signal: controller.signal,
        });
        setHealth(response.ok ? "ready" : "unavailable");
      } catch {
        if (!controller.signal.aborted) {
          setHealth("unavailable");
        }
      }
    }

    void checkService();
    return () => controller.abort();
  }, []);

  return (
    <main className="engineering-shell">
      <p className="eyebrow">ION OS · PHASE 0C</p>
      <h1>Engineering foundation</h1>
      <p className="summary">
        Local desktop shell. Product behavior is intentionally deferred.
      </p>
      <div className={`service-status service-status--${health}`}>
        <span aria-hidden="true" className="status-dot" />
        <span>Local service: {health}</span>
      </div>
      <style>{`:root { --ion-accent: ${ionTokens.color.accent}; }`}</style>
    </main>
  );
}
