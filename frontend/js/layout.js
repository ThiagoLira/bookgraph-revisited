/**
 * layout.js — Timeline layout, force simulation, and focus mode layout.
 */

import d3 from './d3-imports.js';

export class LayoutEngine {
  constructor() {
    this.simulation = null;
    this.yScale = null;
    this.totalHeight = 0;
    this.tickValues = [];
    this.gridlines = [];
  }

  /**
   * Compute timeline Y positions using a two-scale approach:
   * - Pre-1800: 0.3 px/year (compressed ancient history)
   * - Post-1800: 8 px/year (expanded modern era)
   * @param {Array} authors - Author nodes with .year
   * @param {number} viewportWidth - Viewport width for initial X centering
   * @returns {{ yScale, totalHeight, tickValues, gridlines }}
   */
  computeTimeline(authors, viewportWidth) {
    const years = authors.map(a => a.year).filter(y => y !== null && !isNaN(y));
    if (years.length === 0) return { yScale: d3.scaleLinear(), totalHeight: 1000, tickValues: [], gridlines: [] };

    const minYear = Math.min(...years);
    const maxYear = Math.max(...years);

    // Assign median year to authors with unknown years
    const sorted = years.slice().sort((a, b) => a - b);
    const medianYear = sorted[Math.floor(sorted.length / 2)];
    authors.forEach(a => { if (a.year === null) a.year = medianYear; });

    const splitYear = 1800;
    const lowRes = 0.3;
    const highRes = 8;

    const ancientSpan = Math.max(0, splitYear - minYear);
    const modernSpan = Math.max(0, maxYear - splitYear);

    const ancientHeight = ancientSpan * lowRes;
    const modernHeight = modernSpan * highRes;

    this.totalHeight = ancientHeight + modernHeight + 400;

    const yBottom = this.totalHeight - 100;
    const ySplit = yBottom - ancientHeight;
    const yTop = ySplit - modernHeight;

    this.yScale = d3.scaleLinear()
      .domain([minYear, splitYear, maxYear])
      .range([yBottom, ySplit, yTop]);

    // Compute tick values
    this.tickValues = [
      ...d3.range(Math.ceil(minYear / 100) * 100, splitYear, 100),
      ...d3.range(splitYear, maxYear + 1, 10)
    ];

    // Build gridlines for rendering
    this.gridlines = this.tickValues.map(year => ({
      y: this.yScale(year),
      year,
    }));

    // Assign Y positions + initial X
    const isMobile = viewportWidth <= 600;
    this._worldWidth = isMobile ? viewportWidth * 2 : viewportWidth;
    const initialX = isMobile ? viewportWidth : viewportWidth / 2;
    authors.forEach(d => {
      d.fy = this.yScale(d.year);
      d.y = d.fy;
      d.x = initialX;
    });

    return {
      yScale: this.yScale,
      totalHeight: this.totalHeight,
      tickValues: this.tickValues,
      gridlines: this.gridlines,
    };
  }

  /**
   * Start force simulation for X-axis collision avoidance.
   * @param {Array} authors - Author nodes
   * @param {number} centerX - X center for forceX
   * @param {Function} onTick - Called each tick with updated positions
   */
  startForceSimulation(authors, centerX, onTick) {
    if (this.simulation) this.simulation.stop();

    const isMobile = window.innerWidth <= 600;
    // Mobile: moderate centering + large collision padding → clean funnel
    const xStrength = isMobile ? 0.03 : 0.3;
    const collidePad = isMobile ? 25 : 5;
    const collideIter = isMobile ? 5 : 2;

    this.simulation = d3.forceSimulation(authors)
      .force("x", d3.forceX(centerX).strength(xStrength))
      .force("collide", d3.forceCollide(d => d.r + collidePad).iterations(collideIter));

    // Mobile: run synchronous ticks so nodes are spread before zoom computes
    if (isMobile) {
      this.simulation.stop();
      for (let i = 0; i < 200; i++) this.simulation.tick();
      if (onTick) onTick();
      this.simulation.alpha(0.3).restart();
    }

    this.simulation.on("tick", () => {
      if (onTick) onTick();
    });

    return this.simulation;
  }

  /**
   * Compute timeline-based focus layout (sub-graph view).
   * Y positions come from the timeline scale, X positions use a brief
   * force simulation for collision avoidance around the center node's X.
   * @param {Object} centerNode - The focused author node
   * @param {Array} connectedNodes - Connected author nodes (excluding center)
   * @returns {Map<string, {x, y}>} Target positions by node ID (world coords)
   */
  computeFocusLayout(centerNode, connectedNodes) {
    const allNodes = [centerNode, ...connectedNodes];
    const centerX = centerNode.x;
    const n = connectedNodes.length;

    // Scale padding and spread based on citation count —
    // more citations need more spacing so labels remain readable
    const basePad = 40;
    const extraPad = n > 50 ? 30 : n > 20 ? 15 : 0;
    const collidePad = basePad + extraPad;

    // Weaker X centering for large graphs to allow wider spread
    const xStrength = n > 50 ? 0.015 : n > 20 ? 0.02 : 0.03;

    // Create temp proxy objects (don't mutate real nodes)
    const tempNodes = allNodes.map(n => ({
      id: n.id,
      r: n.r,
      x: centerX,
      y: this.yScale ? this.yScale(n.year || 1900) : n.y,
    }));

    const targetY = new Map(tempNodes.map(tn => [tn.id, tn.y]));

    // Brief force simulation: pin Y to timeline, spread X via collision
    const sim = d3.forceSimulation(tempNodes)
      .force('y', d3.forceY(d => targetY.get(d.id)).strength(1))
      .force('x', d3.forceX(centerX).strength(xStrength))
      .force('collide', d3.forceCollide(d => d.r + collidePad))
      .stop();

    for (let i = 0; i < 300; i++) sim.tick();

    const result = new Map();
    tempNodes.forEach(tn => result.set(tn.id, { x: tn.x, y: tn.y }));
    return result;
  }

  stopSimulation() {
    if (this.simulation) {
      this.simulation.stop();
      this.simulation = null;
    }
  }
}
