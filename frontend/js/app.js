/**
 * app.js — Entry point. Loads pre-baked datasets and wires the Canvas 2D
 * renderer, interaction, and panels together. No data crunching here.
 */

import { loadDatasetIndex, loadBaked } from "./data.js";
import { Store } from "./state.js";
import { Renderer } from "./renderer.js";
import { Interaction } from "./interaction.js";
import { Panels } from "./panels.js";

const canvas = document.getElementById("graph-canvas");
const loading = document.getElementById("loading");

const store = new Store();
const renderer = new Renderer(canvas, store);
const interaction = new Interaction(canvas, store, renderer);
const panels = new Panels(store, interaction);

window.addEventListener("resize", () => renderer.resize());
panels.setupSearch();
// Canvas labels use webfonts — redraw once they're ready so the first paint
// doesn't stick with the fallback serif.
document.fonts?.ready.then(() => renderer.scheduleDraw());

// Repaint highlights when selection/filter state changes without a canvas
// event (panel close buttons, sheet drag-dismiss, legend filters on touch).
store.subscribe((reason) => {
  if (reason === "select" || reason === "selectBook" || reason === "regionFilter" || reason === "hover") {
    renderer.scheduleDraw();
  }
});

// Dismiss the intro overlay on the first real interaction (pan/zoom/select).
let introDismissed = false;
store.subscribe((reason) => {
  if (introDismissed) return;
  if (reason === "transform" || reason === "select") {
    document.getElementById("intro")?.classList.add("hidden");
    introDismissed = true;
  }
});

// expose for debugging / scripted screenshots
window.__bg = { store, renderer, interaction, panels };

async function loadLibrary(path, datasets) {
  loading.hidden = false;
  try {
    const graph = await loadBaked(path);
    store.setGraph(graph);
    renderer.setGraph(graph);
    interaction.setGraph(graph);
    panels.setGraph(graph);
    panels.renderLegend(graph.meta.regions);
    interaction.fit(graph.meta, false);
    document.getElementById("intro")?.classList.remove("hidden");
    introDismissed = false;
    // When detail text arrives, refresh any open panel so it fills in.
    graph.detailsReady?.then(() => {
      if (store.selected) store.emit("select");
      if (store.selectedBook) store.emit("selectBook");
    });
  } catch (e) {
    console.error("Failed to load dataset", path, e);
  } finally {
    loading.hidden = true;
  }
}

async function init() {
  const datasets = await loadDatasetIndex();
  if (!datasets.length) {
    console.warn("No baked datasets found. Run: node frontend/build/build.mjs --all");
    return;
  }
  // Always load the merged "All Libraries" graph — no per-library selection.
  const initial = datasets.find((d) => d.path.endsWith("/_all")) || datasets[0];
  await loadLibrary(initial.path, datasets);
}

init();
