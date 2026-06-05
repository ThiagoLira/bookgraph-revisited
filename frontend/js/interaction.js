/**
 * interaction.js — d3-zoom pan/zoom, quadtree hit-testing against baked
 * positions, hover, click selection, and animated flyTo for navigation.
 */

import d3 from "./d3-imports.js";

export class Interaction {
  constructor(canvas, store, renderer) {
    this.canvas = canvas;
    this.store = store;
    this.renderer = renderer;
    this.quadtree = null;
    this.onSelect = () => {};

    this.zoom = d3
      .zoom()
      .scaleExtent([0.04, 14])
      .on("zoom", (e) => {
        this.store.setTransform(e.transform);
        this.renderer.scheduleDraw();
      })
      .on("start", () => canvas.classList.add("grabbing"))
      .on("end", () => canvas.classList.remove("grabbing"));

    this.sel = d3.select(canvas);
    this.sel.call(this.zoom).on("dblclick.zoom", null);

    canvas.addEventListener("mousemove", (e) => this._onMove(e));
    canvas.addEventListener("mouseleave", () => this.store.setHover(null));
    canvas.addEventListener("click", (e) => this._onClick(e));
  }

  setGraph(graph) {
    this.graph = graph;
    this.quadtree = d3
      .quadtree()
      .x((a) => a.x)
      .y((a) => a.y)
      .addAll(graph.authors);
  }

  _screen(e) {
    const r = this.canvas.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }
  _toWorld([sx, sy]) {
    const t = this.store.transform;
    return [(sx - t.x) / t.k, (sy - t.y) / t.k];
  }

  hitTest(sx, sy) {
    if (!this.quadtree) return null;
    const t = this.store.transform;
    const [wx, wy] = this._toWorld([sx, sy]);
    // search radius in world units: max author radius + a touch tolerance
    const tol = 30 / t.k;
    const found = this.quadtree.find(wx, wy, 200 + tol);
    if (!found) return null;
    const d = Math.hypot(found.x - wx, found.y - wy);
    if (d > found.r + tol) return null;

    // inner book hit?
    let book = null;
    let bestD = Infinity;
    for (const b of found.books || []) {
      const bd = Math.hypot(found.x + b.x - wx, found.y + b.y - wy);
      if (bd <= b.r + 2 / t.k && bd < bestD) { bestD = bd; book = b; }
    }
    return { author: found, book };
  }

  _onMove(e) {
    const [sx, sy] = this._screen(e);
    const hit = this.hitTest(sx, sy);
    this.store.setHover(hit ? hit.author : null);
    this.canvas.classList.toggle("pointer", !!hit);
    this.renderer.scheduleDraw();
  }

  _onClick(e) {
    const [sx, sy] = this._screen(e);
    const hit = this.hitTest(sx, sy);
    if (!hit) {
      this.store.clearSelection();
      this.onSelect(null);
      return;
    }
    this.store.selectAuthor(hit.author);
    if (hit.book) this.store.selectBook(hit.book, hit.author);
    this.onSelect(hit.author, hit.book);
    this.flyTo(hit.author);
  }

  /** Animate pan/zoom to center a node, zooming in past the photo threshold. */
  flyTo(node, targetK) {
    const k = targetK || Math.max(2.0, Math.min(4, this.store.transform.k));
    const tx = this.renderer.W / 2 - node.x * k;
    const ty = this.renderer.H / 2 - node.y * k;
    const transform = d3.zoomIdentity.translate(tx, ty).scale(k);
    this.sel.transition().duration(750).ease(d3.easeCubicInOut).call(this.zoom.transform, transform);
  }

  /** Fit the whole world into view. */
  fit(meta, animate = false) {
    const pad = 80;
    const k = Math.min(
      (this.renderer.W - pad * 2) / meta.worldWidth,
      (this.renderer.H - pad * 2) / meta.worldHeight
    );
    const kk = Math.max(0.04, k);
    const tx = (this.renderer.W - meta.worldWidth * kk) / 2;
    const ty = (this.renderer.H - meta.worldHeight * kk) / 2;
    const transform = d3.zoomIdentity.translate(tx, ty).scale(kk);
    if (animate) {
      this.sel.transition().duration(700).call(this.zoom.transform, transform);
    } else {
      this.sel.call(this.zoom.transform, transform);
    }
  }
}
