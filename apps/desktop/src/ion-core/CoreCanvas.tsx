import { useEffect, useRef, useState } from "react";
import { CoreGraph, CoreNode } from "../home";
import {
  createIonCoreRenderer,
  IonCoreRendererController,
  IonCoreRendererFactory,
  IonCoreState,
} from "./renderer";

export type CoreCanvasProps = {
  graph: CoreGraph;
  state: IonCoreState;
  selectedId: string | null;
  onSelect: (node: CoreNode | null) => void;
  rendererFactory?: IonCoreRendererFactory;
};

export default function CoreCanvas({
  graph,
  state,
  selectedId,
  onSelect,
  rendererFactory = createIonCoreRenderer,
}: CoreCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const controllerRef = useRef<IonCoreRendererController | null>(null);
  const selectRef = useRef(onSelect);
  const graphRef = useRef(graph);
  const stateRef = useRef(state);
  const selectedRef = useRef(selectedId);
  const [failed, setFailed] = useState(false);
  const [hover, setHover] = useState<{
    node: CoreNode;
    x: number;
    y: number;
  } | null>(null);
  selectRef.current = onSelect;
  graphRef.current = graph;
  stateRef.current = state;
  selectedRef.current = selectedId;

  useEffect(() => {
    if (failed || !containerRef.current) return;
    try {
      const controller = rendererFactory(containerRef.current, {
        graph: graphRef.current,
        state: stateRef.current,
        selectedId: selectedRef.current,
        onHover: (node, x, y) => setHover(node ? { node, x, y } : null),
        onSelect: (node) => selectRef.current(node),
        onFailure: () => setFailed(true),
      });
      controllerRef.current = controller;
      return () => {
        controller.dispose();
        if (controllerRef.current === controller) controllerRef.current = null;
      };
    } catch {
      setFailed(true);
    }
  }, [failed, rendererFactory]);

  useEffect(() => controllerRef.current?.setGraph(graph), [graph]);
  useEffect(() => controllerRef.current?.setState(state), [state]);
  useEffect(() => controllerRef.current?.setSelected(selectedId), [selectedId]);

  if (failed) {
    return (
      <div className="ion-core-fallback" role="status">
        <div className="ion-core-fallback-orbit" aria-hidden="true" />
        <p>The Core is available in a simplified view on this device.</p>
        <button type="button" onClick={() => setFailed(false)}>
          Retry live Core
        </button>
      </div>
    );
  }

  return (
    <div className="ion-core-stage">
      <div ref={containerRef} className="ion-core-renderer" />
      {hover ? (
        <div
          className="ion-core-hover"
          style={{ left: hover.x + 12, top: hover.y + 12 }}
        >
          <strong>{hover.node.label}</strong>
          <span>{hover.node.entity_type.replaceAll("_", " ")}</span>
        </div>
      ) : null}
      <div className="ion-core-controls" aria-label="Ion Core view controls">
        <button
          type="button"
          aria-label="Rotate Core left"
          onClick={() => controllerRef.current?.rotate("left")}
        >
          ←
        </button>
        <button
          type="button"
          aria-label="Rotate Core up"
          onClick={() => controllerRef.current?.rotate("up")}
        >
          ↑
        </button>
        <button
          type="button"
          aria-label="Rotate Core down"
          onClick={() => controllerRef.current?.rotate("down")}
        >
          ↓
        </button>
        <button
          type="button"
          aria-label="Rotate Core right"
          onClick={() => controllerRef.current?.rotate("right")}
        >
          →
        </button>
        <button
          type="button"
          aria-label="Zoom Core in"
          onClick={() => controllerRef.current?.zoom("in")}
        >
          +
        </button>
        <button
          type="button"
          aria-label="Zoom Core out"
          onClick={() => controllerRef.current?.zoom("out")}
        >
          −
        </button>
        <button type="button" onClick={() => controllerRef.current?.reset()}>
          Reset
        </button>
      </div>
    </div>
  );
}
