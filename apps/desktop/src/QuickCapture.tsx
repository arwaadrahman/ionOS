import { FormEvent, useEffect, useRef, useState } from "react";
import { emitTo } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { blankTaskInput, taskClient } from "./tasks";

type CaptureState = "idle" | "saving" | "saved" | "failed";

export function QuickCapture() {
  const [title, setTitle] = useState("");
  const [state, setState] = useState<CaptureState>("idle");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const focus = () => {
      setState("idle");
      inputRef.current?.focus();
    };
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") void getCurrentWindow().hide();
    };
    window.addEventListener("focus", focus);
    window.addEventListener("keydown", keydown);
    return () => {
      window.removeEventListener("focus", focus);
      window.removeEventListener("keydown", keydown);
    };
  }, []);

  async function capture(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = title.trim();
    if (!normalized || state === "saving") return;

    setState("saving");
    try {
      const task = await taskClient.create({
        ...blankTaskInput(),
        title: normalized,
      });
      setTitle("");
      setState("saved");

      // The canonical mutation is already confirmed. Notification or window
      // cleanup failures must not relabel the Task creation as failed.
      try {
        await emitTo("main", "ion:task-created", task);
      } catch {
        // The next canonical refresh still discovers the confirmed Task.
      }
      try {
        await getCurrentWindow().hide();
      } catch {
        // Keep the confirmed success visible if native hiding is unavailable.
      }
    } catch {
      setState("failed");
    }
  }

  return (
    <main className="quick-capture-shell">
      <p className="eyebrow">ION · QUICK CAPTURE</p>
      <h1>Capture a Task</h1>
      <form onSubmit={(event) => void capture(event)}>
        <label htmlFor="quick-task-title">What needs doing?</label>
        <div className="quick-capture-row">
          <input
            ref={inputRef}
            id="quick-task-title"
            autoFocus
            autoComplete="off"
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
              if (state !== "idle") setState("idle");
            }}
          />
          <button type="submit" disabled={!title.trim() || state === "saving"}>
            {state === "saving" ? "Saving…" : "Capture"}
          </button>
        </div>
      </form>
      <p
        className={`capture-feedback capture-feedback--${state}`}
        aria-live="polite"
      >
        {state === "failed"
          ? "Task was not saved. Check Ion and try again."
          : state === "saved"
            ? "Task saved."
            : "Press Escape to hide."}
      </p>
    </main>
  );
}
