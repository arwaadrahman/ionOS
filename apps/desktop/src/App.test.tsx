import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { App } from "./App";

test("reports a reachable loopback service", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
  render(<App />);

  expect(await screen.findByText("Local service: ready")).toBeInTheDocument();
});

test("reports an unavailable development service without exposing diagnostics", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  render(<App />);

  expect(
    await screen.findByText("Local service: unavailable"),
  ).toBeInTheDocument();
  expect(screen.queryByText("offline")).not.toBeInTheDocument();
});
