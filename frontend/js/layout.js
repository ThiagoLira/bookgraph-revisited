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

    // Assign Y positions
    authors.forEach(d => {
      d.fy = this.yScale(d.year);
      d.y = d.fy;
      d.x = viewportWidth / 2;
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

    this.simulation = d3.forceSimulation(authors)
      .force("x", d3.forceX(centerX).strength(0.3))
      .force("collide", d3.forceCollide(d => d.r + 5).iterations(2))
      .on("tick", () => {
        // Clamp X positions
        const w = centerX * 2; // approximate viewport width
        authors.forEach(d => {
          d.x = Math.max(d.r + 10, Math.min(w - d.r - 10, d.x));
        });
        if (onTick) onTick();
      });

    return this.simulation;
  }

  /**
   * Compute radial focus layout.
   * @param {Object} centerNode - The focused author node
   * @param {Array} connectedNodes - Connected author nodes (excluding center)
   * @param {number} viewportWidth - Viewport width
   * @param {number} viewportHeight - Viewport height
   * @returns {Map<string, {x, y}>} Target positions by node ID
   */
  computeFocusLayout(centerNode, connectedNodes, viewportWidth, viewportHeight) {
    const targetPositions = new Map();

    const centerX = viewportWidth / 2;
    const centerY = viewportHeight / 2;

    targetPositions.set(centerNode.id, { x: centerX, y: centerY });

    const count = connectedNodes.length;
    const nodesPerRing = 25;
    const baseRadius = Math.min(viewportWidth, viewportHeight) * 0.25;
    const ringSpacing = 100;

    connectedNodes.forEach((n, i) => {
      const ringIndex = Math.floor(i / nodesPerRing);
      const posInRing = i % nodesPerRing;
      const nodesInThisRing = Math.min(nodesPerRing, count - ringIndex * nodesPerRing);

      const radius = baseRadius + ringIndex * ringSpacing;
      const angleStep = (2 * Math.PI) / nodesInThisRing;
      const angleOffset = ringIndex * 0.3;
      const angle = angleStep * posInRing - Math.PI / 2 + angleOffset;

      targetPositions.set(n.id, {
        x: centerX + Math.cos(angle) * radius,
        y: centerY + Math.sin(angle) * radius,
      });
    });

    return targetPositions;
  }

  stopSimulation() {
    if (this.simulation) {
      this.simulation.stop();
      this.simulation = null;
    }
  }
}
