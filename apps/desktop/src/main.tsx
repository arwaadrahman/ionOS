import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { App } from "./App";
import { QuickCapture } from "./QuickCapture";
import "./styles.css";

const Root = getCurrentWindow().label === "quick-capture" ? QuickCapture : App;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
