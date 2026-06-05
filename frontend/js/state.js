/**
 * state.js — Central app state with a tiny pub/sub. Replaces the old app.js
 * god-object. UI + renderer subscribe and react to `change` events.
 */

export class Store {
  constructor() {
    this.listeners = new Set();
    this.graph = null;
    this.transform = null; // d3 zoomTransform
    this.hover = null; // author node
    this.selected = null; // author node
    this.selectedBook = null; // {book, author}
    this.focus = null; // { centerId, relatedIds: Set<string> }
    this.regionFilter = null; // region key or null
    this.backStack = [];
  }

  subscribe(fn) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }
  emit(reason) {
    for (const fn of this.listeners) fn(reason, this);
  }

  setGraph(graph) {
    this.graph = graph;
    this.hover = null;
    this.selected = null;
    this.selectedBook = null;
    this.focus = null;
    this.regionFilter = null;
    this.backStack = [];
    this.emit("graph");
  }

  setTransform(t) {
    this.transform = t;
    this.emit("transform");
  }

  setHover(node) {
    if (this.hover === node) return;
    this.hover = node;
    this.emit("hover");
  }

  _computeFocus(node) {
    const related = new Set([node.id]);
    for (const l of node.out) related.add(l.target.id);
    for (const l of node.in) related.add(l.source.id);
    return { centerId: node.id, relatedIds: related };
  }

  selectAuthor(node, { pushHistory = true } = {}) {
    if (pushHistory && this.selected && this.selected !== node) {
      this.backStack.push(this.selected);
    }
    this.selected = node;
    this.selectedBook = null;
    this.regionFilter = null;
    this.focus = node ? this._computeFocus(node) : null;
    this.emit("select");
  }

  selectBook(book, author) {
    this.selectedBook = { book, author };
    this.emit("selectBook");
  }

  back() {
    const prev = this.backStack.pop();
    if (prev) {
      this.selected = prev;
      this.selectedBook = null;
      this.focus = this._computeFocus(prev);
      this.emit("select");
    }
    return prev;
  }

  clearSelection() {
    this.selected = null;
    this.selectedBook = null;
    this.focus = null;
    this.backStack = [];
    this.emit("select");
  }

  setRegionFilter(region) {
    this.regionFilter = this.regionFilter === region ? null : region;
    // Region filter overrides focus dimming.
    this.emit("regionFilter");
  }
}
