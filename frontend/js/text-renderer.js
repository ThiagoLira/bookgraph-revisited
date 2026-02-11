/**
 * text-renderer.js — DOM overlay for author labels.
 * Labels are positioned absolutely over the canvas, transformed with zoom.
 */

export class TextLabelManager {
  constructor(container) {
    this.container = container; // #label-overlay div
    this.labels = new Map();   // authorId -> DOM element
    this.visibleSet = new Set();
  }

  /**
   * Create label elements for all authors.
   * @param {Array} authors - Author nodes with id, name
   */
  createLabels(authors) {
    // Clear existing
    this.container.innerHTML = '';
    this.labels.clear();
    this.visibleSet.clear();

    for (const a of authors) {
      const el = document.createElement('div');
      el.className = 'node-label';
      el.textContent = a.name;
      el.dataset.id = a.id;
      this.container.appendChild(el);
      this.labels.set(a.id, el);
    }
  }

  /**
   * Update label positions based on current zoom transform.
   * Only positions visible labels (viewport culling).
   * @param {Array} authors - Author nodes with x, y, r
   * @param {{ x: number, y: number, k: number }} transform - d3-zoom transform
   */
  updatePositions(authors, transform) {
    const { x: tx, y: ty, k } = transform;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const margin = 100; // px margin outside viewport to hide

    for (const a of authors) {
      const el = this.labels.get(a.id);
      if (!el) continue;

      if (!this.visibleSet.has(a.id)) {
        // Not visible — skip transform computation
        continue;
      }

      // World to screen
      const sx = a.x * k + tx;
      const sy = (a.y - a.r - 10) * k + ty; // offset above circle

      // Viewport culling
      if (sx < -margin || sx > vw + margin || sy < -margin || sy > vh + margin) {
        el.style.opacity = '0';
        continue;
      }

      // Reset inline opacity so CSS .visible class takes effect
      el.style.opacity = '';

      el.style.left = sx + 'px';
      el.style.top = sy + 'px';

      // Scale labels slightly with zoom (but clamp)
      const fontSize = Math.max(9, Math.min(14, 12 * Math.sqrt(k)));
      el.style.fontSize = fontSize + 'px';
    }
  }

  /**
   * Show label for a specific node.
   */
  show(nodeId) {
    this.visibleSet.add(nodeId);
    const el = this.labels.get(nodeId);
    if (el) el.classList.add('visible');
  }

  /**
   * Hide label for a specific node.
   */
  hide(nodeId) {
    this.visibleSet.delete(nodeId);
    const el = this.labels.get(nodeId);
    if (el) el.classList.remove('visible');
  }

  /**
   * Show only the given set of node IDs.
   */
  showOnly(nodeIds) {
    for (const [id, el] of this.labels) {
      if (nodeIds.has(id)) {
        el.classList.add('visible');
        this.visibleSet.add(id);
      } else {
        el.classList.remove('visible');
        this.visibleSet.delete(id);
      }
    }
  }

  /**
   * Hide all labels.
   */
  hideAll() {
    for (const [id, el] of this.labels) {
      el.classList.remove('visible');
    }
    this.visibleSet.clear();
  }

  /**
   * Remove all labels.
   */
  clear() {
    this.container.innerHTML = '';
    this.labels.clear();
    this.visibleSet.clear();
  }
}
