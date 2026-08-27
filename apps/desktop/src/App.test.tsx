import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { App } from "./App";

test("reports a reachable loopback service", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
  render(<App />);

  expect(await screen.findByText("Local service: ready")).toBeInTheDocument();
});
