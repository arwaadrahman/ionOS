import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CoreGraph, CoreNode } from "../home";
import { buildCoreLayout, edgePositionBuffer, stableHash } from "./layout";

export type IonCoreState = "idle" | "processing" | "attention";
export type IonCoreDirection = "left" | "right" | "up" | "down";
export type IonCoreRendererOptions = {
  graph: CoreGraph;
  state: IonCoreState;
  selectedId: string | null;
  onHover: (node: CoreNode | null, x: number, y: number) => void;
  onSelect: (node: CoreNode | null) => void;
  onFailure: () => void;
};
export type IonCoreRendererController = {
  setGraph: (graph: CoreGraph) => void;
  setState: (state: IonCoreState) => void;
  setSelected: (id: string | null) => void;
  rotate: (direction: IonCoreDirection) => void;
  zoom: (direction: "in" | "out") => void;
  reset: () => void;
  dispose: () => void;
};
export type IonCoreRendererFactory = (
  container: HTMLElement,
  options: IonCoreRendererOptions,
) => IonCoreRendererController;

const COLOR_BY_TYPE: Record<
  CoreNode["entity_type"],
  THREE.ColorRepresentation
> = {
  area: 0x6f8dff,
  goal: 0x9d7bff,
  goal_milestone: 0xc3b5ff,
  project: 0x39d5c4,
  project_milestone: 0x8ef0df,
  task: 0xf5f0ff,
};
const DUST_COUNT = 168;

function styleForNode(node: CoreNode) {
  const color = new THREE.Color(COLOR_BY_TYPE[node.entity_type]);
  let size =
    node.entity_type === "task" ? 7 : node.entity_type === "area" ? 14 : 11;
  let alpha = 0.9;
  if (node.lifecycle === "paused") alpha = 0.55;
  if (node.lifecycle === "completed") {
    color.lerp(new THREE.Color(0xbdd6cc), 0.45);
    alpha = 0.58;
  }
  if (node.lifecycle === "archived" || node.lifecycle === "inactive")
    alpha = 0.3;
  if (node.today_role === "priority") {
    color.set(0xffcf72);
    size += 4;
  } else if (node.today_role === "planned") {
    color.lerp(new THREE.Color(0xffe3a4), 0.5);
    size += 2;
  }
  if (node.attention_reason) {
    color.set(0xff7f86);
    size += 3;
  }
  return { color, size, alpha };
}

function nodeMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uTime: { value: 0 },
      uIntensity: { value: 1 },
    },
    vertexShader: `
      attribute float nodeSize;
      attribute float nodeAlpha;
      varying vec3 vColor;
      varying float vAlpha;
      uniform float uTime;
      uniform float uIntensity;
      void main() {
        vColor = color;
        vAlpha = nodeAlpha;
        vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
        float pulse = 1.0 + sin(uTime * 1.4 + position.x * 2.0) * 0.08 * uIntensity;
        gl_PointSize = nodeSize * pulse * (10.0 / max(1.0, -viewPosition.z));
        gl_Position = projectionMatrix * viewPosition;
      }
    `,
    fragmentShader: `
      varying vec3 vColor;
      varying float vAlpha;
      uniform float uIntensity;
      void main() {
        float distanceToCenter = distance(gl_PointCoord, vec2(0.5));
        if (distanceToCenter > 0.5) discard;
        float glow = smoothstep(0.5, 0.06, distanceToCenter);
        gl_FragColor = vec4(vColor * (1.0 + 0.18 * uIntensity), vAlpha * glow);
      }
    `,
    vertexColors: true,
  });
}

function dustGeometry() {
  const positions: number[] = [];
  for (let index = 0; index < DUST_COUNT; index += 1) {
    const z =
      ((stableHash(`ion-dust:${index}:z`) + 0.5) / 0x1_0000_0000) * 2 - 1;
    const angle =
      ((stableHash(`ion-dust:${index}:angle`) + 0.5) / 0x1_0000_0000) *
      Math.PI *
      2;
    const radius = Math.sqrt(Math.max(0, 1 - z * z));
    const shell =
      4.65 + ((stableHash(`ion-dust:${index}:r`) + 0.5) / 0x1_0000_0000) * 1.2;
    positions.push(
      radius * Math.cos(angle) * shell,
      z * shell,
      radius * Math.sin(angle) * shell,
    );
  }
  return new THREE.BufferGeometry().setAttribute(
    "position",
    new THREE.Float32BufferAttribute(positions, 3),
  );
}

function overlay(color: THREE.ColorRepresentation, size: number) {
  const geometry = new THREE.BufferGeometry().setAttribute(
    "position",
    new THREE.Float32BufferAttribute([0, 0, 0], 3),
  );
  const material = new THREE.PointsMaterial({
    color,
    size,
    transparent: true,
    opacity: 0.7,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true,
  });
  const points = new THREE.Points(geometry, material);
  points.visible = false;
  return points;
}

export const createIonCoreRenderer: IonCoreRendererFactory = (
  container,
  initial,
) => {
  let disposed = false;
  let active = document.visibilityState !== "hidden" && document.hasFocus();
  let reducedMotion = false;
  let frame: number | null = null;
  let lastTime = 0;
  let graph = initial.graph;
  let nodeOrder: CoreNode[] = [];
  let nodePoints: THREE.Points | null = null;
  let selectedId = initial.selectedId;
  let hoveredId: string | null = null;
  let state = initial.state;
  const scene = new THREE.Scene();
  const root = new THREE.Group();
  scene.add(root);
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
  camera.position.set(0, 0, 11.5);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setClearColor(0x000000, 0);
  renderer.domElement.className = "ion-core-canvas";
  renderer.domElement.setAttribute("aria-hidden", "true");
  container.append(renderer.domElement);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = false;
  controls.enablePan = false;
  controls.minDistance = 7.3;
  controls.maxDistance = 17;
  controls.saveState();
  const raycaster = new THREE.Raycaster();
  raycaster.params.Points = { threshold: 0.18 };
  const pointer = new THREE.Vector2(2, 2);
  const selectedOverlay = overlay(0xffffff, 0.22);
  const hoverOverlay = overlay(0x9ff9ef, 0.18);
  root.add(selectedOverlay, hoverOverlay);
  const dust = new THREE.Points(
    dustGeometry(),
    new THREE.PointsMaterial({
      color: 0x9cb4dc,
      size: 0.018,
      transparent: true,
      opacity: 0.24,
      depthWrite: false,
    }),
  );
  root.add(dust);

  const render = () => {
    if (!disposed) renderer.render(scene, camera);
  };
  const animate = (time: number) => {
    if (disposed || !active || reducedMotion) {
      frame = null;
      return;
    }
    const delta = Math.min(0.05, lastTime ? (time - lastTime) / 1000 : 0);
    lastTime = time;
    const material = nodePoints?.material;
    if (material instanceof THREE.ShaderMaterial)
      material.uniforms.uTime.value = time / 1000;
    root.rotation.y += delta * (state === "processing" ? 0.11 : 0.035);
    render();
    frame = window.requestAnimationFrame(animate);
  };
  const updateAnimation = () => {
    if (active && !reducedMotion && frame === null) {
      lastTime = 0;
      frame = window.requestAnimationFrame(animate);
    } else if ((!active || reducedMotion) && frame !== null) {
      window.cancelAnimationFrame(frame);
      frame = null;
    }
    render();
  };
  const placeOverlay = (object: THREE.Points, id: string | null) => {
    const index = nodeOrder.findIndex((node) => node.id === id);
    if (index < 0 || !nodePoints) {
      object.visible = false;
      return;
    }
    const position = nodePoints.geometry.getAttribute("position");
    object.position.set(
      position.getX(index),
      position.getY(index),
      position.getZ(index),
    );
    object.visible = true;
  };
  const setGraph = (nextGraph: CoreGraph) => {
    graph = nextGraph;
    if (nodePoints) {
      root.remove(nodePoints);
      nodePoints.geometry.dispose();
      (nodePoints.material as THREE.Material).dispose();
    }
    const layout = buildCoreLayout(graph);
    nodeOrder = layout.nodes;
    const positions: number[] = [];
    const colors: number[] = [];
    const sizes: number[] = [];
    const alphas: number[] = [];
    for (const node of layout.nodes) {
      positions.push(...node.position);
      const style = styleForNode(node);
      colors.push(style.color.r, style.color.g, style.color.b);
      sizes.push(style.size);
      alphas.push(style.alpha);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(positions, 3),
    );
    geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    geometry.setAttribute(
      "nodeSize",
      new THREE.Float32BufferAttribute(sizes, 1),
    );
    geometry.setAttribute(
      "nodeAlpha",
      new THREE.Float32BufferAttribute(alphas, 1),
    );
    nodePoints = new THREE.Points(geometry, nodeMaterial());
    root.add(nodePoints);
    const edgeGeometry = new THREE.BufferGeometry().setAttribute(
      "position",
      new THREE.BufferAttribute(edgePositionBuffer(layout), 3),
    );
    const lines = root.getObjectByName("canonical-edges");
    if (lines instanceof THREE.LineSegments) {
      root.remove(lines);
      lines.geometry.dispose();
      (lines.material as THREE.Material).dispose();
    }
    const nextLines = new THREE.LineSegments(
      edgeGeometry,
      new THREE.LineBasicMaterial({
        color: 0x6682a7,
        transparent: true,
        opacity: 0.24,
        depthWrite: false,
      }),
    );
    nextLines.name = "canonical-edges";
    root.add(nextLines);
    placeOverlay(selectedOverlay, selectedId);
    placeOverlay(hoverOverlay, hoveredId);
    render();
  };
  const resize = () => {
    const width = Math.max(1, container.clientWidth);
    const height = Math.max(1, container.clientHeight);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    renderer.setSize(width, height, false);
    render();
  };
  const pick = (event: PointerEvent) => {
    if (!nodePoints) return null;
    const bounds = renderer.domElement.getBoundingClientRect();
    pointer.set(
      ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
      -((event.clientY - bounds.top) / bounds.height) * 2 + 1,
    );
    raycaster.setFromCamera(pointer, camera);
    const match = raycaster.intersectObject(nodePoints, false)[0];
    return match?.index === undefined ? null : (nodeOrder[match.index] ?? null);
  };
  const pointerMove = (event: PointerEvent) => {
    const node = pick(event);
    hoveredId = node?.id ?? null;
    placeOverlay(hoverOverlay, hoveredId);
    initial.onHover(node, event.clientX, event.clientY);
    renderer.domElement.style.cursor = node ? "pointer" : "grab";
    render();
  };
  const pointerLeave = () => {
    hoveredId = null;
    hoverOverlay.visible = false;
    initial.onHover(null, 0, 0);
    render();
  };
  const click = (event: PointerEvent) => initial.onSelect(pick(event));
  const focus = () => {
    active = document.visibilityState !== "hidden";
    updateAnimation();
  };
  const blur = () => {
    active = false;
    updateAnimation();
  };
  const visibility = () => {
    active = document.visibilityState !== "hidden" && document.hasFocus();
    updateAnimation();
  };
  const contextLost = (event: Event) => {
    event.preventDefault();
    initial.onFailure();
  };
  const media = window.matchMedia("(prefers-reduced-motion: reduce)");
  const motion = () => {
    reducedMotion = media.matches;
    updateAnimation();
  };
  const observer = new ResizeObserver(resize);
  observer.observe(container);
  controls.addEventListener("change", render);
  renderer.domElement.addEventListener("pointermove", pointerMove);
  renderer.domElement.addEventListener("pointerleave", pointerLeave);
  renderer.domElement.addEventListener("click", click);
  renderer.domElement.addEventListener("webglcontextlost", contextLost);
  window.addEventListener("focus", focus);
  window.addEventListener("blur", blur);
  document.addEventListener("visibilitychange", visibility);
  media.addEventListener("change", motion);
  motion();
  resize();
  setGraph(graph);

  return {
    setGraph,
    setState(nextState) {
      state = nextState;
      const material = nodePoints?.material;
      if (material instanceof THREE.ShaderMaterial) {
        material.uniforms.uIntensity.value =
          nextState === "processing"
            ? 1.7
            : nextState === "attention"
              ? 1.35
              : 1;
      }
      render();
    },
    setSelected(id) {
      selectedId = id;
      placeOverlay(selectedOverlay, id);
      render();
    },
    rotate(direction) {
      const amount = 0.16;
      if (direction === "left") controls.rotateLeft(amount);
      if (direction === "right") controls.rotateLeft(-amount);
      if (direction === "up") controls.rotateUp(amount);
      if (direction === "down") controls.rotateUp(-amount);
      controls.update();
      render();
    },
    zoom(direction) {
      if (direction === "in") controls.dollyIn(1.12);
      else controls.dollyOut(1.12);
      controls.update();
      render();
    },
    reset() {
      controls.reset();
      root.rotation.set(0, 0, 0);
      render();
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      if (frame !== null) window.cancelAnimationFrame(frame);
      observer.disconnect();
      controls.removeEventListener("change", render);
      controls.dispose();
      renderer.domElement.removeEventListener("pointermove", pointerMove);
      renderer.domElement.removeEventListener("pointerleave", pointerLeave);
      renderer.domElement.removeEventListener("click", click);
      renderer.domElement.removeEventListener("webglcontextlost", contextLost);
      window.removeEventListener("focus", focus);
      window.removeEventListener("blur", blur);
      document.removeEventListener("visibilitychange", visibility);
      media.removeEventListener("change", motion);
      root.traverse((object) => {
        if (
          object instanceof THREE.Points ||
          object instanceof THREE.LineSegments
        ) {
          object.geometry.dispose();
          if (Array.isArray(object.material))
            object.material.forEach((item) => item.dispose());
          else object.material.dispose();
        }
      });
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    },
  };
};
