/**
 * app.js — Entry point and orchestrator for BookGraph WebGPU frontend.
 */

import { GraphRenderer } from './renderer.js';
import { FallbackRenderer } from './fallback.js';
import { LayoutEngine } from './layout.js';
import { InteractionManager } from './interaction.js';
import { TextLabelManager } from './text-renderer.js';
import { TransitionManager } from './transitions.js';
import d3 from './d3-imports.js';
import { processData, loadDatasetRecords, loadDatasetIndex, slugifyTitle } from './data.js';

// === Donut Chart Classification Helpers ===

const CHART_COLORS = [
  '#d4a574', '#a07850', '#c47a5a', '#8b9a6b',
  '#7a8fa0', '#b07aa0', '#6b8a8a', '#c4956a', '#8a7a6a',
];

function classifyEpoch(birthYear) {
  if (birthYear == null) return null;
  if (birthYear < 500) return 'Ancient';
  if (birthYear < 1000) return 'Early Medieval';
  if (birthYear < 1300) return 'High Medieval';
  if (birthYear < 1500) return 'Late Medieval';
  if (birthYear < 1600) return 'Renaissance';
  if (birthYear < 1800) return 'Enlightenment';
  if (birthYear < 1870) return 'Romantic';
  if (birthYear < 1945) return 'Modern';
  return 'Contemporary';
}

const KNOWN_NATIONALITIES = new Set([
  'German', 'French', 'English', 'British', 'Russian', 'Italian', 'American',
  'Greek', 'Roman', 'Spanish', 'Austrian', 'Polish', 'Dutch', 'Swiss',
  'Japanese', 'Chinese', 'Irish', 'Scottish', 'Czech', 'Swedish', 'Norwegian',
  'Danish', 'Hungarian', 'Portuguese', 'Indian', 'Persian', 'Turkish',
  'Belgian', 'Finnish', 'Romanian', 'Canadian', 'Australian', 'Argentine',
  'Brazilian', 'Mexican', 'Colombian', 'Egyptian', 'Korean', 'Arab',
]);

function extractNationality(meta) {
  if (meta.nationality) return meta.nationality;
  if (meta.categories && Array.isArray(meta.categories)) {
    for (const cat of meta.categories) {
      for (const nat of KNOWN_NATIONALITIES) {
        if (cat.includes(nat)) return nat;
      }
    }
  }
  return null;
}

const INFOBOX_TYPE_MAP = {
  philosopher: 'Philosophy', theologian: 'Philosophy',
  writer: 'Literature', poet: 'Literature', author: 'Literature',
  scientist: 'Science', academic: 'Science', scholar: 'Science',
  'medical person': 'Science', engineer: 'Science', economist: 'Science',
  officeholder: 'Politics', royalty: 'Politics', 'military person': 'Politics',
  saint: 'Religion', 'christian leader': 'Religion', clergy: 'Religion',
  'religious biography': 'Religion',
  artist: 'Arts', 'classical composer': 'Arts', 'musical artist': 'Arts',
  architect: 'Arts',
};

function classifyType(meta) {
  if (!meta.infoboxes || !Array.isArray(meta.infoboxes)) return null;
  for (const raw of meta.infoboxes) {
    const cleaned = raw.replace(/<!--[\s\S]*?-->/g, '').trim().toLowerCase();
    if (INFOBOX_TYPE_MAP[cleaned]) return INFOBOX_TYPE_MAP[cleaned];
  }
  // Second pass: partial match for entries like "writer <!-- ... -->"
  for (const raw of meta.infoboxes) {
    const cleaned = raw.replace(/<!--[\s\S]*?-->/g, '').trim().toLowerCase();
    for (const [key, val] of Object.entries(INFOBOX_TYPE_MAP)) {
      if (cleaned.includes(key)) return val;
    }
  }
  return 'Other';
}

function buildDistribution(values, maxBuckets = 7) {
  const counts = new Map();
  for (const v of values) {
    if (v == null) continue;
    counts.set(v, (counts.get(v) || 0) + 1);
  }
  let entries = Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  if (entries.length > maxBuckets) {
    const top = entries.slice(0, maxBuckets - 1);
    const rest = entries.slice(maxBuckets - 1).reduce((s, e) => s + e[1], 0);
    top.push(['Other', rest]);
    entries = top;
  }
  return entries; // [[label, count], ...]
}

function renderDonutChart(container, title, data, total) {
  const size = 120;
  const outerR = size / 2;
  const innerR = outerR * 0.58;

  const wrapper = document.createElement('div');
  wrapper.className = 'donut-chart';

  const titleEl = document.createElement('div');
  titleEl.className = 'donut-chart-title';
  titleEl.textContent = title;
  wrapper.appendChild(titleEl);

  const svgWrap = document.createElement('div');
  svgWrap.className = 'donut-chart-ring';

  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('width', size);
  svg.setAttribute('height', size);
  svg.setAttribute('viewBox', `0 0 ${size} ${size}`);

  // Glow filter
  const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
  const filter = document.createElementNS('http://www.w3.org/2000/svg', 'filter');
  filter.setAttribute('id', `glow-${title}`);
  const blur = document.createElementNS('http://www.w3.org/2000/svg', 'feGaussianBlur');
  blur.setAttribute('stdDeviation', '2.5');
  blur.setAttribute('result', 'glow');
  const merge = document.createElementNS('http://www.w3.org/2000/svg', 'feMerge');
  const m1 = document.createElementNS('http://www.w3.org/2000/svg', 'feMergeNode');
  m1.setAttribute('in', 'glow');
  const m2 = document.createElementNS('http://www.w3.org/2000/svg', 'feMergeNode');
  m2.setAttribute('in', 'SourceGraphic');
  merge.appendChild(m1);
  merge.appendChild(m2);
  filter.appendChild(blur);
  filter.appendChild(merge);
  defs.appendChild(filter);
  svg.appendChild(defs);

  const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  g.setAttribute('transform', `translate(${outerR},${outerR})`);

  const pie = d3.pie().value(d => d[1]).sort(null).padAngle(0.03);
  const arc = d3.arc().innerRadius(innerR).outerRadius(outerR).cornerRadius(2);
  const arcHover = d3.arc().innerRadius(innerR - 2).outerRadius(outerR + 3).cornerRadius(2);
  const arcs = pie(data);

  // Center text group
  const centerTotal = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  centerTotal.setAttribute('text-anchor', 'middle');
  centerTotal.setAttribute('dy', '0.35em');
  centerTotal.setAttribute('fill', '#e8e6e3');
  centerTotal.setAttribute('font-size', '18');
  centerTotal.setAttribute('font-family', 'Cormorant Garamond, Georgia, serif');
  centerTotal.textContent = total;
  centerTotal.style.transition = 'opacity 0.2s ease';

  const centerLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  centerLabel.setAttribute('text-anchor', 'middle');
  centerLabel.setAttribute('dy', '-0.3em');
  centerLabel.setAttribute('fill', '#e8e6e3');
  centerLabel.setAttribute('font-size', '11');
  centerLabel.setAttribute('font-family', 'JetBrains Mono, monospace');
  centerLabel.textContent = '';
  centerLabel.style.opacity = '0';
  centerLabel.style.transition = 'opacity 0.15s ease';

  const centerCount = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  centerCount.setAttribute('text-anchor', 'middle');
  centerCount.setAttribute('dy', '1.1em');
  centerCount.setAttribute('fill', '#d4a574');
  centerCount.setAttribute('font-size', '13');
  centerCount.setAttribute('font-family', 'JetBrains Mono, monospace');
  centerCount.setAttribute('font-weight', '500');
  centerCount.textContent = '';
  centerCount.style.opacity = '0';
  centerCount.style.transition = 'opacity 0.15s ease';

  arcs.forEach((d, i) => {
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', arc(d));
    path.setAttribute('fill', CHART_COLORS[i % CHART_COLORS.length]);
    path.setAttribute('opacity', '0');
    path.style.transition = 'opacity 0.2s ease, d 0.2s ease';
    path.style.cursor = 'default';
    path.setAttribute('filter', `url(#glow-${title})`);

    // Staggered entrance animation
    setTimeout(() => { path.setAttribute('opacity', '0.85'); }, 80 + i * 60);

    path.addEventListener('mouseenter', () => {
      path.setAttribute('d', arcHover(d));
      path.setAttribute('opacity', '1');
      centerTotal.style.opacity = '0';
      centerLabel.textContent = d.data[0];
      centerLabel.style.opacity = '1';
      centerCount.textContent = d.data[1];
      centerCount.style.opacity = '1';
    });
    path.addEventListener('mouseleave', () => {
      path.setAttribute('d', arc(d));
      path.setAttribute('opacity', '0.85');
      centerTotal.style.opacity = '1';
      centerLabel.style.opacity = '0';
      centerCount.style.opacity = '0';
    });

    g.appendChild(path);
  });

  g.appendChild(centerTotal);
  g.appendChild(centerLabel);
  g.appendChild(centerCount);
  svg.appendChild(g);
  svgWrap.appendChild(svg);
  wrapper.appendChild(svgWrap);

  // Legend
  const legend = document.createElement('div');
  legend.className = 'donut-legend';
  data.forEach(([label, count], i) => {
    const item = document.createElement('div');
    item.className = 'donut-legend-item';
    const swatch = document.createElement('span');
    swatch.className = 'donut-legend-swatch';
    swatch.style.background = CHART_COLORS[i % CHART_COLORS.length];
    const text = document.createElement('span');
    text.textContent = label;
    item.appendChild(swatch);
    item.appendChild(text);
    legend.appendChild(item);
  });
  wrapper.appendChild(legend);

  container.appendChild(wrapper);
}

class BookGraphApp {
  constructor() {
    // DOM references
    this.canvas = document.getElementById('graph-canvas');
    this.labelOverlay = document.getElementById('label-overlay');
    this.axisOverlay = document.getElementById('axis-overlay');
    this.tooltipEl = document.getElementById('tooltip');

    // Renderer chosen at init time (WebGPU or WebGL2 fallback)
    this.renderer = null;
    this.layout = new LayoutEngine();
    this.interaction = new InteractionManager(this.canvas, this);
    this.labels = new TextLabelManager(this.labelOverlay);
    this.transitions = new TransitionManager();

    // State
    this.graphData = { authors: [], links: [] };
    this.sourceBookMap = new Map();
    this.focusMode = false;
    this.focusedNode = null;
    this.focusedBook = null;
    this.selectedNode = null;
    this.originalPositions = new Map();
    this.highlightState = {
      dimmedIds: new Set(),
      highlightedIds: new Set(),
      dimmedLinkIndices: new Set(),
      highlightedLinkIndices: new Set(),
    };

    this._renderLoopBound = this._renderLoop.bind(this);
    this._needsUpdate = false;
  }

  async init() {
    // Try WebGPU first, fall back to WebGL2
    if (navigator.gpu) {
      try {
        this.renderer = new GraphRenderer(this.canvas);
        await this.renderer.init();
        console.log('Using WebGPU renderer');
      } catch (e) {
        console.warn('WebGPU init failed, trying WebGL2:', e);
        this.renderer = null;
      }
    }
    if (!this.renderer) {
      try {
        this.renderer = new FallbackRenderer(this.canvas);
        await this.renderer.init();
        console.log('Using WebGL2 fallback renderer');
      } catch (e) {
        console.error('WebGL2 init also failed:', e);
        document.getElementById('loading').textContent = 'Neither WebGPU nor WebGL2 available.';
        return;
      }
    }

    // Setup zoom handler
    this.interaction.init((transform) => {
      this.renderer.setTransform(transform);
      this.labels.updatePositions(this.graphData.authors, transform);
      this._updateAxisOverlay(transform);
      this._needsUpdate = true;
    });

    // Handle resize
    window.addEventListener('resize', () => {
      this.renderer.handleResize();
      this.renderer.setTransform(this.interaction.transform);
      this._needsUpdate = true;
    });

    // Load dataset index and populate selector
    try {
      const datasets = await loadDatasetIndex();
      const select = document.getElementById('dataset-select');

      // Store datasets for "All Libraries" loading
      this._datasets = datasets;

      // Add "All Libraries" option first
      const allOpt = document.createElement('option');
      allOpt.value = '__all__';
      allOpt.textContent = 'All Libraries';
      // Gather all covers with their full paths
      const allCovers = [];
      datasets.forEach(ds => {
        if (ds.covers) {
          ds.covers.forEach(c => allCovers.push(`${ds.path}/${c}`));
        }
      });
      allOpt.setAttribute('data-covers-abs', JSON.stringify(allCovers));
      select.appendChild(allOpt);

      datasets.forEach(ds => {
        const opt = document.createElement('option');
        opt.value = ds.path;
        opt.textContent = ds.name;
        if (ds.covers) {
          opt.setAttribute('data-covers', JSON.stringify(ds.covers));
        }
        select.appendChild(opt);
      });

      select.addEventListener('change', () => {
        if (select.value) {
          if (select.value === '__all__') {
            this._loadAllDatasets();
          } else {
            this._loadDataset(select.value);
          }
        }
      });

      // Load "All Libraries" by default
      select.value = '__all__';
      this._loadAllDatasets();
    } catch (e) {
      console.error('Failed to load datasets:', e);
      document.getElementById('loading').textContent = 'Error loading datasets.json';
    }

    // Start render loop
    this._renderLoop();
  }

  async _loadDataset(dataDir) {
    // Exit focus mode if active
    if (this.focusMode) {
      this.exitFocusMode();
    }

    document.getElementById('hero').classList.add('hidden');
    document.getElementById('loading').style.display = 'block';
    document.getElementById('loading').textContent = 'Loading...';
    document.getElementById('search').value = '';
    document.getElementById('search-results').textContent = '';

    this.selectedNode = null;
    this.labels.clear();
    this._clearHighlight();
    this.closeCitationPanel();
    this.hideDetailCard();
    this.closePanel();

    try {
      const records = await loadDatasetRecords(dataDir);
      const result = processData(records);

      this.graphData = { authors: result.authors, links: result.links };
      this.sourceBookMap = result.sourceBookMap;

      // Compute timeline layout
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const { totalHeight, gridlines } = this.layout.computeTimeline(result.authors, vw);

      // Create labels
      this.labels.createLabels(result.authors);

      // Render header covers
      const select = document.getElementById('dataset-select');
      const selectedOption = select.options[select.selectedIndex];
      const covers = selectedOption ? JSON.parse(selectedOption.getAttribute('data-covers') || 'null') : null;
      this._renderHeaderCovers(dataDir, covers);

      // Update renderer buffers
      this.renderer.updateCircles(result.authors);
      this.renderer.updateLines(result.links);
      this.renderer.updateGridlines(gridlines, vw);

      // Start force simulation
      this.layout.startForceSimulation(result.authors, vw / 2, () => {
        this.renderer.updateCircles(result.authors, this.highlightState);
        this.renderer.updateLines(result.links, this.highlightState);
        this.labels.updatePositions(result.authors, this.interaction.transform);
        this._needsUpdate = true;
      });

      // Auto-fit: zoom to show the full timeline
      const fitK = vh / totalHeight;
      const scale = Math.max(0.1, Math.min(fitK * 0.9, 1));
      const offsetX = (vw - vw * scale) / 2;
      const offsetY = (vh - totalHeight * scale) / 2;

      // Small delay to let simulation settle
      setTimeout(() => {
        this.interaction.setTransform(offsetX, offsetY, scale, false);
      }, 100);

      document.getElementById('loading').style.display = 'none';
    } catch (e) {
      console.error(e);
      document.getElementById('loading').textContent = 'Error loading data: ' + e.message;
    }
  }

  async _loadAllDatasets() {
    if (this.focusMode) {
      this.exitFocusMode();
    }

    document.getElementById('hero').classList.add('hidden');
    document.getElementById('loading').style.display = 'block';
    document.getElementById('loading').textContent = 'Loading all libraries...';
    document.getElementById('search').value = '';
    document.getElementById('search-results').textContent = '';

    this.selectedNode = null;
    this.labels.clear();
    this._clearHighlight();
    this.closeCitationPanel();
    this.hideDetailCard();
    this.closePanel();

    try {
      // Load all datasets in parallel
      const allRecords = [];
      const batches = await Promise.all(
        this._datasets.map(ds => loadDatasetRecords(ds.path))
      );
      for (const records of batches) {
        allRecords.push(...records);
      }

      const result = processData(allRecords);

      this.graphData = { authors: result.authors, links: result.links };
      this.sourceBookMap = result.sourceBookMap;

      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const { totalHeight, gridlines } = this.layout.computeTimeline(result.authors, vw);

      this.labels.createLabels(result.authors);

      // Render covers from all datasets using absolute paths
      const select = document.getElementById('dataset-select');
      const selectedOption = select.options[select.selectedIndex];
      const absCoverPaths = JSON.parse(selectedOption.getAttribute('data-covers-abs') || '[]');
      this._renderHeaderCoversAbsolute(absCoverPaths);

      this.renderer.updateCircles(result.authors);
      this.renderer.updateLines(result.links);
      this.renderer.updateGridlines(gridlines, vw);

      this.layout.startForceSimulation(result.authors, vw / 2, () => {
        this.renderer.updateCircles(result.authors, this.highlightState);
        this.renderer.updateLines(result.links, this.highlightState);
        this.labels.updatePositions(result.authors, this.interaction.transform);
        this._needsUpdate = true;
      });

      const fitK = vh / totalHeight;
      const scale = Math.max(0.1, Math.min(fitK * 0.9, 1));
      const offsetX = (vw - vw * scale) / 2;
      const offsetY = (vh - totalHeight * scale) / 2;

      setTimeout(() => {
        this.interaction.setTransform(offsetX, offsetY, scale, false);
      }, 100);

      document.getElementById('loading').style.display = 'none';
    } catch (e) {
      console.error(e);
      document.getElementById('loading').textContent = 'Error loading data: ' + e.message;
    }
  }

  _renderLoop() {
    if (this._needsUpdate || this.renderer.dirty || this.transitions.isAnimating) {
      this.renderer.render();
      this._needsUpdate = false;
    }
    requestAnimationFrame(this._renderLoopBound);
  }

  // === Highlight System ===

  highlightAuthor(author) {
    if (this.focusMode) return;
    if (this.selectedNode && this.selectedNode.id !== author.id) return;

    const connectedIds = new Set([author.id]);
    const highlightedLinkIndices = new Set();
    const dimmedLinkIndices = new Set();

    this.graphData.links.forEach((l, idx) => {
      if (l.source.id === author.id) {
        connectedIds.add(l.target.id);
        highlightedLinkIndices.add(idx);
      } else {
        dimmedLinkIndices.add(idx);
      }
    });

    const dimmedIds = new Set();
    for (const a of this.graphData.authors) {
      if (!connectedIds.has(a.id)) {
        dimmedIds.add(a.id);
      }
    }

    this.highlightState = { dimmedIds, highlightedIds: connectedIds, dimmedLinkIndices, highlightedLinkIndices };

    this.renderer.updateCircles(this.graphData.authors, this.highlightState);
    this.renderer.updateLines(this.graphData.links, this.highlightState);

    // Show label for hovered author
    this.labels.hideAll();
    this.labels.show(author.id);
    this.labels.updatePositions(this.graphData.authors, this.interaction.transform);

    this._needsUpdate = true;
  }

  highlightSet(nodeIds) {
    const dimmedIds = new Set();
    for (const a of this.graphData.authors) {
      if (!nodeIds.has(a.id)) dimmedIds.add(a.id);
    }

    const dimmedLinkIndices = new Set();
    this.graphData.links.forEach((l, idx) => {
      if (!nodeIds.has(l.source.id) && !nodeIds.has(l.target.id)) {
        dimmedLinkIndices.add(idx);
      }
    });

    this.highlightState = { dimmedIds, highlightedIds: nodeIds, dimmedLinkIndices, highlightedLinkIndices: new Set() };

    this.renderer.updateCircles(this.graphData.authors, this.highlightState);
    this.renderer.updateLines(this.graphData.links, this.highlightState);

    // Show labels for all matches
    this.labels.showOnly(nodeIds);
    this.labels.updatePositions(this.graphData.authors, this.interaction.transform);

    this._needsUpdate = true;
  }

  resetHighlight() {
    if (this.selectedNode || this.focusMode) return;
    this._clearHighlight();
  }

  _clearHighlight() {
    this.highlightState = {
      dimmedIds: new Set(),
      highlightedIds: new Set(),
      dimmedLinkIndices: new Set(),
      highlightedLinkIndices: new Set(),
    };

    this.renderer.updateCircles(this.graphData.authors, this.highlightState);
    this.renderer.updateLines(this.graphData.links, this.highlightState);
    this.labels.hideAll();
    this._needsUpdate = true;
  }

  clearSelection() {
    this.selectedNode = null;
    this.resetHighlight();
  }

  // === Focus Mode ===

  enterFocusMode(node, book = null) {
    this.focusMode = true;
    this.focusedNode = node;
    this.focusedBook = book;
    this.selectedNode = node;

    const bookId = book ? book.data.id : null;

    // Store original positions
    this.originalPositions.clear();
    for (const a of this.graphData.authors) {
      this.originalPositions.set(a.id, { x: a.x, y: a.y, fx: a.fx, fy: a.fy });
    }

    // Find connected nodes (filtered by source book if specified)
    const connectedIds = new Set([node.id]);
    const connectedNodes = [];
    this.graphData.links.forEach(l => {
      if (l.source.id === node.id) {
        if (bookId && l.sourceBookIds && !l.sourceBookIds.has(bookId)) return;
        connectedIds.add(l.target.id);
        connectedNodes.push(l.target);
      }
    });

    // Update UI
    const focusLabel = book ? book.data.title : node.name;
    document.getElementById('focus-author-name').textContent = focusLabel;
    document.getElementById('focus-count').textContent = connectedNodes.length;
    document.getElementById('focus-exit').classList.add('visible');
    document.getElementById('focus-info').classList.add('visible');

    // Stop simulation
    this.layout.stopSimulation();

    // Store original zoom transform for exit restoration
    const t = this.interaction.transform;
    this.originalTransform = { x: t.x, y: t.y, k: t.k };

    // Compute timeline-based focus layout (world coordinates)
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const targetPositions = this.layout.computeFocusLayout(node, connectedNodes);

    // Auto-zoom to fit the sub-graph bounding box
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const [id, pos] of targetPositions) {
      const n = this.graphData.authors.find(a => a.id === id);
      const r = n ? n.r : 20;
      minX = Math.min(minX, pos.x - r);
      maxX = Math.max(maxX, pos.x + r);
      minY = Math.min(minY, pos.y - r);
      maxY = Math.max(maxY, pos.y + r);
    }
    const pad = 100;
    const scale = Math.min(vw / (maxX - minX + pad * 2), vh / (maxY - minY + pad * 2));
    const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
    setTimeout(() => {
      this.interaction.setTransform(vw / 2 - cx * scale, vh / 2 - cy * scale, scale, true);
    }, 50);

    // Highlight state for focus mode
    const dimmedIds = new Set();
    const dimmedLinkIndices = new Set();
    const highlightedLinkIndices = new Set();
    for (const a of this.graphData.authors) {
      if (!connectedIds.has(a.id)) dimmedIds.add(a.id);
    }
    this.graphData.links.forEach((l, idx) => {
      if (l.source.id === node.id && (!bookId || !l.sourceBookIds || l.sourceBookIds.has(bookId))) {
        highlightedLinkIndices.add(idx);
      } else {
        dimmedLinkIndices.add(idx);
      }
    });
    this.highlightState = {
      dimmedIds, highlightedIds: connectedIds,
      dimmedLinkIndices, highlightedLinkIndices,
      dimAlpha: 0.03, dimLinkAlpha: 0.015,
    };

    // Show labels for connected nodes
    this.labels.showOnly(connectedIds);

    // Set fixed positions for connected nodes
    for (const a of this.graphData.authors) {
      const target = targetPositions.get(a.id);
      if (target) {
        a.fx = target.x;
        a.fy = target.y;
      }
    }

    // Animate to target positions
    this.transitions.animatePositions(
      this.graphData.authors,
      targetPositions,
      () => {
        this.renderer.updateCircles(this.graphData.authors, this.highlightState);
        this.renderer.updateLines(this.graphData.links, this.highlightState);
        this.labels.updatePositions(this.graphData.authors, this.interaction.transform);
        this._needsUpdate = true;
      },
      600
    );

    // Show citation panel for focused author/book
    this.showCitationPanel(node, book);

    // Also show the info panel (right side) for the source book itself
    // On portrait mobile, skip to avoid overlapping bottom sheets — user taps nodes instead
    if (book && !this._isPortraitMobile()) {
      this.showPanel(book.data);
    }
  }

  exitFocusMode() {
    if (!this.focusMode) return;

    this.focusMode = false;
    this.focusedNode = null;
    this.focusedBook = null;
    this.selectedNode = null;

    document.getElementById('focus-exit').classList.remove('visible');
    document.getElementById('focus-info').classList.remove('visible');

    // Build target positions from originals
    const targetPositions = new Map();
    for (const a of this.graphData.authors) {
      const orig = this.originalPositions.get(a.id);
      if (orig) {
        targetPositions.set(a.id, { x: orig.x, y: orig.y });
      }
    }

    this._clearHighlight();

    // Restore the original zoom transform
    if (this.originalTransform) {
      const ot = this.originalTransform;
      setTimeout(() => {
        this.interaction.setTransform(ot.x, ot.y, ot.k, true);
      }, 50);
    }

    // Animate back
    this.transitions.animatePositions(
      this.graphData.authors,
      targetPositions,
      () => {
        this.renderer.updateCircles(this.graphData.authors, this.highlightState);
        this.renderer.updateLines(this.graphData.links, this.highlightState);
        this.labels.updatePositions(this.graphData.authors, this.interaction.transform);
        this._needsUpdate = true;
      },
      600
    ).then(() => {
      // Restore original positions and fixed coords without restarting simulation
      for (const a of this.graphData.authors) {
        const orig = this.originalPositions.get(a.id);
        if (orig) {
          a.fx = orig.fx;
          a.fy = orig.fy;
          a.x = orig.x;
          a.y = orig.y;
        }
      }
      // Final buffer update at rest positions
      this.renderer.updateCircles(this.graphData.authors, this.highlightState);
      this.renderer.updateLines(this.graphData.links, this.highlightState);
      this._needsUpdate = true;
    });

    this.closeCitationPanel();
    this.hideDetailCard();
    this.closePanel();
  }

  _isPortraitMobile() {
    return window.innerWidth <= 600 && window.innerHeight > window.innerWidth;
  }

  // === Panel ===

  showPanel(node) {
    this.hideDetailCard();
    const panel = document.getElementById('info-panel');
    const isBook = node.id && node.id.startsWith('book:');
    const title = isBook ? node.title : node.name;
    const meta = node.meta || {};

    document.getElementById('panel-type').textContent = isBook ? 'Book' : 'Author';
    document.getElementById('panel-title').textContent = title;

    let metaText = '';
    if (isBook) {
      const authors = meta.authors ? (Array.isArray(meta.authors) ? meta.authors.join(', ') : meta.authors) : 'Unknown Author';
      metaText = `${node.year || 'Unknown Year'} \u00B7 ${authors}`;
    } else {
      if (meta.birth_year) {
        metaText = `${meta.birth_year} \u2013 ${meta.death_year || 'Present'}`;
      }
    }
    document.getElementById('panel-meta').textContent = metaText;

    const content = document.getElementById('panel-content');
    let html = '';

    if (isBook && (meta.average_rating || meta.num_pages || meta.publisher)) {
      html += `<div class="panel-stats">`;
      if (meta.average_rating) {
        html += `<div class="panel-stat">
          <span class="panel-stat-value">\u2605 ${this._esc(String(meta.average_rating))}</span>
          <span class="panel-stat-label">Rating</span>
        </div>`;
      }
      if (meta.num_pages) {
        html += `<div class="panel-stat">
          <span class="panel-stat-value">${this._esc(String(meta.num_pages))}</span>
          <span class="panel-stat-label">Pages</span>
        </div>`;
      }
      if (meta.publisher) {
        html += `<div class="panel-stat">
          <span class="panel-stat-value">${this._esc(meta.publisher)}</span>
          <span class="panel-stat-label">Publisher</span>
        </div>`;
      }
      html += `</div>`;
    }

    if (meta.description) {
      html += `<div class="panel-description">${this._esc(meta.description)}</div>`;
    }

    const commentaries = node.commentaries || [];
    if (commentaries.length > 0) {
      html += `<div class="citations-section">`;
      html += `<div class="citations-header">
        <h3 class="citations-title">${isBook ? 'Author Commentary' : 'Referenced As'}</h3>
        <span class="citations-count">${commentaries.length} citation${commentaries.length > 1 ? 's' : ''}</span>
      </div>`;

      commentaries.forEach((c, i) => {
        const isLong = c.length > 200;
        const cardClass = isLong ? 'citation-card expandable' : 'citation-card';

        html += `<div class="${cardClass}" data-index="${i}">
          <div class="citation-card-inner">
            <span class="citation-number">${String(i + 1).padStart(2, '0')}</span>
            <p class="citation-quote">${this._esc(c)}</p>
            ${isLong ? `<div class="citation-expand">
              <button class="citation-expand-btn" onclick="this.closest('.citation-card').classList.add('expanded')">Read more</button>
            </div>` : ''}
          </div>
        </div>`;
      });

      html += `</div>`;
    } else if (!isBook) {
      html += `<div class="empty-citations">
        <div class="empty-citations-icon">\u{1F4DA}</div>
        <p>No direct citations found</p>
      </div>`;
    }

    const link = meta.link || meta.url;
    if (link) {
      html += `<a href="${this._esc(link)}" target="_blank" class="panel-link">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
          <polyline points="15 3 21 3 21 9"></polyline>
          <line x1="10" y1="14" x2="21" y2="3"></line>
        </svg>
        View on Goodreads
      </a>`;
    }

    content.innerHTML = html;
    panel.classList.add('visible');
  }

  closePanel() {
    document.getElementById('info-panel').classList.remove('visible');
  }

  // === Citation Panel ===

  showCitationPanel(node, book = null) {
    const panel = document.getElementById('citation-panel');
    const bookId = book ? book.data.id : null;

    // Panel title: book title or author name
    const titleEl = document.getElementById('citation-panel-title');
    if (book) {
      titleEl.innerHTML = `${this._esc(book.data.title)}<span class="citation-panel-subtitle">${this._esc(node.name)}</span>`;
    } else {
      titleEl.textContent = node.name;
    }

    // Find cited authors (filtered by source book if specified)
    const citedAuthors = [];
    const citedAuthorIds = new Set();
    this.graphData.links.forEach(l => {
      if (l.source.id === node.id && !citedAuthorIds.has(l.target.id)) {
        if (bookId && l.sourceBookIds && !l.sourceBookIds.has(bookId)) return;
        citedAuthorIds.add(l.target.id);
        citedAuthors.push(l.target);
      }
    });

    // Sort by birth year (oldest first), unknown at end
    citedAuthors.sort((a, b) => {
      const ya = a.meta && a.meta.birth_year ? a.meta.birth_year : Infinity;
      const yb = b.meta && b.meta.birth_year ? b.meta.birth_year : Infinity;
      return ya - yb;
    });

    // Collect cited works from those authors
    const citedWorks = [];
    citedAuthors.forEach(a => {
      (a.books || []).forEach(b => {
        citedWorks.push({
          bookData: b.data,
          authorName: a.name,
          authorNode: a,
          year: b.data.year
        });
      });
    });

    // Sort by year (oldest first), unknown at end
    citedWorks.sort((a, b) => {
      const ya = a.year != null ? a.year : Infinity;
      const yb = b.year != null ? b.year : Infinity;
      return ya - yb;
    });

    // Update counts
    const counts = panel.querySelectorAll('.citation-col-count');
    if (counts[0]) counts[0].textContent = citedAuthors.length;
    if (counts[1]) counts[1].textContent = citedWorks.length;

    // Render author list
    const authorsList = document.getElementById('cited-authors-list');
    authorsList.innerHTML = '';

    if (citedAuthors.length === 0) {
      authorsList.innerHTML = '<li class="citation-col-empty">No cited authors</li>';
    } else {
      citedAuthors.forEach(a => {
        const li = document.createElement('li');
        li.className = 'citation-list-item';
        const years = a.meta && a.meta.birth_year
          ? `${a.meta.birth_year}\u2013${a.meta.death_year || 'present'}`
          : '';
        const bookCount = (a.books || []).length;
        const nameSpan = document.createElement('span');
        nameSpan.className = 'citation-item-name';
        nameSpan.textContent = a.name;
        const metaSpan = document.createElement('span');
        metaSpan.className = 'citation-item-meta';
        metaSpan.textContent = `${years}${years && bookCount ? ' \u00B7 ' : ''}${bookCount} book${bookCount !== 1 ? 's' : ''}`;
        li.appendChild(nameSpan);
        li.appendChild(metaSpan);

        li.addEventListener('click', () => {
          authorsList.querySelectorAll('.citation-list-item').forEach(el => el.classList.remove('active'));
          li.classList.add('active');
          this.showPanel(a);
        });
        authorsList.appendChild(li);
      });
    }

    // Render works list
    const worksList = document.getElementById('cited-works-list');
    worksList.innerHTML = '';

    if (citedWorks.length === 0) {
      worksList.innerHTML = '<li class="citation-col-empty">No cited works</li>';
    } else {
      citedWorks.forEach(w => {
        const li = document.createElement('li');
        li.className = 'citation-list-item';
        const year = w.year || '';
        const nameSpan = document.createElement('span');
        nameSpan.className = 'citation-item-name';
        nameSpan.textContent = w.bookData.title;
        const metaSpan = document.createElement('span');
        metaSpan.className = 'citation-item-meta';
        metaSpan.textContent = `${year}${year && w.authorName ? ' \u00B7 ' : ''}${w.authorName}`;
        li.appendChild(nameSpan);
        li.appendChild(metaSpan);

        li.addEventListener('click', () => {
          worksList.querySelectorAll('.citation-list-item').forEach(el => el.classList.remove('active'));
          li.classList.add('active');
          this.showPanel(w.bookData);
        });
        worksList.appendChild(li);
      });
    }

    // === Donut Charts ===
    const chartsContainer = document.getElementById('citation-charts');
    chartsContainer.innerHTML = '';

    const epochs = citedAuthors.map(a => classifyEpoch(a.meta && a.meta.birth_year));
    const nationalities = citedAuthors.map(a => extractNationality(a.meta || {}));
    const types = citedAuthors.map(a => classifyType(a.meta || {}));

    const epochDist = buildDistribution(epochs);
    const natDist = buildDistribution(nationalities);
    const typeDist = buildDistribution(types);

    const hasCharts = epochDist.length >= 3 || natDist.length >= 3 || typeDist.length >= 3;

    if (hasCharts) {
      const desc = document.createElement('div');
      desc.className = 'citation-charts-desc';
      desc.textContent = `Distribution of ${citedAuthors.length} cited authors by historical period, origin, and field`;
      chartsContainer.appendChild(desc);

      const row = document.createElement('div');
      row.className = 'citation-charts-row';

      if (epochDist.length >= 3) renderDonutChart(row, 'Epoch', epochDist, epochDist.reduce((s, e) => s + e[1], 0));
      if (natDist.length >= 3) renderDonutChart(row, 'Nationality', natDist, natDist.reduce((s, e) => s + e[1], 0));
      if (typeDist.length >= 3) renderDonutChart(row, 'Type', typeDist, typeDist.reduce((s, e) => s + e[1], 0));

      chartsContainer.appendChild(row);
    }

    chartsContainer.style.display = hasCharts ? '' : 'none';

    panel.classList.add('visible');
  }

  closeCitationPanel() {
    document.getElementById('citation-panel').classList.remove('visible');
    document.getElementById('citation-charts').innerHTML = '';
  }

  // === Detail Card (compact right-side preview) ===

  showDetailCard(node) {
    this.closePanel();
    const card = document.getElementById('detail-card');
    const isBook = node.id && node.id.startsWith('book:');

    document.getElementById('detail-card-type').textContent = isBook ? 'Book' : 'Author';
    document.getElementById('detail-card-title').textContent = isBook ? node.title : node.name;

    const meta = node.meta || {};
    let metaText = '';
    if (isBook) {
      const authors = meta.authors ? (Array.isArray(meta.authors) ? meta.authors.join(', ') : meta.authors) : '';
      metaText = [node.year, authors].filter(Boolean).join(' \u00B7 ');
    } else {
      if (meta.birth_year) {
        metaText = `${meta.birth_year}\u2013${meta.death_year || 'present'}`;
      }
    }
    document.getElementById('detail-card-meta').textContent = metaText;

    // Clicking the card opens the full detail panel
    card.onclick = () => {
      this.hideDetailCard();
      this.showPanel(node);
    };

    card.classList.add('visible');
  }

  hideDetailCard() {
    const card = document.getElementById('detail-card');
    card.classList.remove('visible');
    card.onclick = null;
  }

  _esc(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // === Tooltip ===

  showTooltip(x, y, text) {
    this.tooltipEl.textContent = text;
    this.tooltipEl.style.display = 'block';
    this.tooltipEl.style.left = (x + 12) + 'px';
    this.tooltipEl.style.top = (y - 12) + 'px';
  }

  hideTooltip() {
    this.tooltipEl.style.display = 'none';
  }

  // === Axis Overlay ===

  _updateAxisOverlay(transform) {
    if (!this.layout.tickValues || !this.layout.yScale) return;

    const { x: tx, y: ty, k } = transform;
    const vh = window.innerHeight;

    this.axisOverlay.innerHTML = '';

    for (const year of this.layout.tickValues) {
      const worldY = this.layout.yScale(year);
      const screenY = worldY * k + ty;

      // Viewport culling
      if (screenY < -20 || screenY > vh + 20) continue;

      const tick = document.createElement('div');
      tick.className = 'axis-tick';
      tick.style.top = screenY + 'px';
      tick.textContent = year < 0 ? `${-year} BC` : year;
      this.axisOverlay.appendChild(tick);
    }
  }

  // === Header Covers ===

  _renderHeaderCovers(dataDir, covers) {
    const headerCov = document.getElementById('header-cover');
    headerCov.style.display = 'none';
    headerCov.src = '';

    let shelfContainer = document.getElementById('header-shelf');
    if (!shelfContainer) {
      shelfContainer = document.createElement('div');
      shelfContainer.id = 'header-shelf';
      headerCov.parentNode.insertBefore(shelfContainer, headerCov);
    }
    shelfContainer.innerHTML = '';

    const attachCoverClick = (img, coverPath) => {
      const filename = coverPath.split('/').pop() || '';
      const slug = filename.replace(/\.[^/.]+$/, '');
      img.style.cursor = 'pointer';
      img.addEventListener('click', (e) => {
        e.stopPropagation();
        const target = this.sourceBookMap.get(slug);
        if (target) {
          this.enterFocusMode(target.authorNode, target.bookCircle || null);
        }
      });
    };

    if (covers && covers.length > 0) {
      headerCov.style.display = 'none';
      covers.forEach(c => {
        const img = document.createElement('img');
        img.className = 'cover-image';
        img.onload = function () {
          if (this.naturalWidth > 50 && this.naturalHeight > 50) {
            this.style.display = 'block';
          } else {
            this.remove();
          }
        };
        img.onerror = function () { this.remove(); };
        img.style.display = 'none';
        img.src = `${dataDir}/${c}`;
        attachCoverClick(img, c);
        shelfContainer.appendChild(img);
      });
    } else {
      const coverPath = `${dataDir}/cover.jpg`;
      const img = new Image();
      img.onload = () => {
        headerCov.src = coverPath;
        headerCov.style.display = 'block';
        attachCoverClick(headerCov, 'cover.jpg');
      };
      img.src = coverPath;
    }
  }

  _renderHeaderCoversAbsolute(coverPaths) {
    const headerCov = document.getElementById('header-cover');
    headerCov.style.display = 'none';
    headerCov.src = '';

    let shelfContainer = document.getElementById('header-shelf');
    if (!shelfContainer) {
      shelfContainer = document.createElement('div');
      shelfContainer.id = 'header-shelf';
      headerCov.parentNode.insertBefore(shelfContainer, headerCov);
    }
    shelfContainer.innerHTML = '';

    coverPaths.forEach(fullPath => {
      const img = document.createElement('img');
      img.className = 'cover-image';
      img.onload = function () {
        if (this.naturalWidth > 50 && this.naturalHeight > 50) {
          this.style.display = 'block';
        } else {
          this.remove();
        }
      };
      img.onerror = function () { this.remove(); };
      img.style.display = 'none';
      img.src = fullPath;

      const filename = fullPath.split('/').pop() || '';
      const slug = filename.replace(/\.[^/.]+$/, '');
      img.style.cursor = 'pointer';
      img.addEventListener('click', (e) => {
        e.stopPropagation();
        const target = this.sourceBookMap.get(slug);
        if (target) {
          this.enterFocusMode(target.authorNode, target.bookCircle || null);
        }
      });

      shelfContainer.appendChild(img);
    });
  }
}

// Boot
const app = new BookGraphApp();
app.init();
