import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { ionTokens } from "@ion/design";
import { TaskWorkspace } from "./TaskWorkspace";
import { Task, taskClient } from "./tasks";

type HealthState = "checking" | "ready" | "unavailable";

const apiOrigin = __ION_API_ORIGIN__;

type ServiceStatus = { state: HealthState };

type AppProps = { development?: boolean };

export function App({ development = import.meta.env.DEV }: AppProps = {}) {
  const [health, setHealth] = useState<HealthState>("checking");
  const [tasks, setTasks] = useState<Task[]>([]);

  useEffect(() => {
    const controller = new AbortController();

    async function checkService(): Promise<void> {
      try {
        if (!development) {
          const status = await invoke<ServiceStatus>("service_health");
          if (status.state === "ready") {
            setTasks(await taskClient.list());
            setHealth("ready");
          } else setHealth(status.state);
          return;
        }
        const response = await fetch(`${apiOrigin}/health`, {
          signal: controller.signal,
        });
        if (response.ok) {
          setTasks(await taskClient.list());
          setHealth("ready");
        } else setHealth("unavailable");
      } catch {
        if (!controller.signal.aborted) {
          setHealth("unavailable");
        }
      }
    }

    void checkService();
    return () => controller.abort();
  }, [development]);

  if (health === "ready") return <TaskWorkspace initialTasks={tasks} />;
  return (
    <main className="engineering-shell">
      <p className="eyebrow">ION OS · PHASE 0C</p>
      <h1>Local service unavailable</h1>
      <p className="summary">
        Tasks will be available when Ion's local service is ready.
      </p>
      <div className={`service-status service-status--${health}`}>
        <span aria-hidden="true" className="status-dot" />
        <span>Local service: {health}</span>
      </div>
      <style>{`:root { --ion-accent: ${ionTokens.color.accent}; }`}</style>
    </main>
  );
}
