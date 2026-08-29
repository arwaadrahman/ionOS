import "@testing-library/jest-dom/vitest";
import { StrictMode } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { CoreGraph } from "../home";
import CoreCanvas from "./CoreCanvas";
import { IonCoreRendererFactory } from "./renderer";

const graph: CoreGraph = { nodes: [], edges: [] };

afterEach(cleanup);

test("owns and releases renderer lifetimes under StrictMode remounting", () => {
  const dispose = vi.fn();
  const factory = vi.fn(() => ({
    setGraph: vi.fn(),
    setState: vi.fn(),
    setSelected: vi.fn(),
    rotate: vi.fn(),
    zoom: vi.fn(),
    reset: vi.fn(),
    dispose,
  })) as IonCoreRendererFactory;
  const view = render(
    <StrictMode>
      <CoreCanvas
        graph={graph}
        state="idle"
        selectedId={null}
        onSelect={vi.fn()}
        rendererFactory={factory}
      />
    </StrictMode>,
  );
  expect(factory).toHaveBeenCalledTimes(2);
  expect(dispose).toHaveBeenCalledTimes(1);
  view.unmount();
  expect(dispose).toHaveBeenCalledTimes(2);
});

test("shows the static fallback when WebGL initialization fails", () => {
  const factory = vi.fn(() => {
    throw new Error("synthetic WebGL failure");
  }) as IonCoreRendererFactory;
  render(
    <CoreCanvas
      graph={graph}
      state="idle"
      selectedId={null}
      onSelect={vi.fn()}
      rendererFactory={factory}
    />,
  );
  expect(
    screen.getByText(
      "The Core is available in a simplified view on this device.",
    ),
  ).toBeInTheDocument();
});

test("balances controller creation and cleanup across 20 Home-style remounts", () => {
  const dispose = vi.fn();
  const factory = vi.fn(() => ({
    setGraph: vi.fn(),
    setState: vi.fn(),
    setSelected: vi.fn(),
    rotate: vi.fn(),
    zoom: vi.fn(),
    reset: vi.fn(),
    dispose,
  })) as IonCoreRendererFactory;
  for (let index = 0; index < 20; index += 1) {
    const view = render(
      <CoreCanvas
        graph={graph}
        state="idle"
        selectedId={null}
        onSelect={vi.fn()}
        rendererFactory={factory}
      />,
    );
    view.unmount();
  }
  expect(factory).toHaveBeenCalledTimes(20);
  expect(dispose).toHaveBeenCalledTimes(20);
});
