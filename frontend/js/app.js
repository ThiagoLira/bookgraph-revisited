/**
 * app.js — Entry point and orchestrator for BookGraph WebGPU frontend.
 */

import { GraphRenderer } from './renderer.js';
import { FallbackRenderer } from './fallback.js';
import { LayoutEngine } from './layout.js';
import { InteractionManager } from './interaction.js';
import { TextLabelManager } from './text-renderer.js';
import { TransitionManager } from './transitions.js';
import { processData, loadDatasetRecords, loadDatasetIndex, slugifyTitle } from './data.js';

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
          this._loadDataset(select.value);
        }
      });

      // Load first dataset
      if (datasets.length > 0) {
        select.value = datasets[0].path;
        this._loadDataset(datasets[0].path);
      }
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

  enterFocusMode(node) {
    this.focusMode = true;
    this.focusedNode = node;
    this.selectedNode = node;

    // Store original positions
    this.originalPositions.clear();
    for (const a of this.graphData.authors) {
      this.originalPositions.set(a.id, { x: a.x, y: a.y, fx: a.fx, fy: a.fy });
    }

    // Find connected nodes
    const connectedIds = new Set([node.id]);
    const connectedNodes = [];
    this.graphData.links.forEach(l => {
      if (l.source.id === node.id) {
        connectedIds.add(l.target.id);
        connectedNodes.push(l.target);
      }
    });

    // Update UI
    document.getElementById('focus-author-name').textContent = node.name;
    document.getElementById('focus-count').textContent = connectedNodes.length;
    document.getElementById('focus-exit').classList.add('visible');
    document.getElementById('focus-info').classList.add('visible');

    // Stop simulation
    this.layout.stopSimulation();

    // Compute radial layout in world coordinates
    // Use the current viewport center in world space
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const t = this.interaction.transform;
    const worldCenterX = (vw / 2 - t.x) / t.k;
    const worldCenterY = (vh / 2 - t.y) / t.k;

    const targetPositions = this.layout.computeFocusLayout(
      node, connectedNodes, vw / t.k, vh / t.k
    );

    // Adjust: center at world viewport center
    const layoutCenter = targetPositions.get(node.id);
    const offsetX = worldCenterX - layoutCenter.x;
    const offsetY = worldCenterY - layoutCenter.y;
    for (const [id, pos] of targetPositions) {
      pos.x += offsetX;
      pos.y += offsetY;
    }

    // Highlight state for focus mode
    const dimmedIds = new Set();
    const dimmedLinkIndices = new Set();
    const highlightedLinkIndices = new Set();
    for (const a of this.graphData.authors) {
      if (!connectedIds.has(a.id)) dimmedIds.add(a.id);
    }
    this.graphData.links.forEach((l, idx) => {
      if (l.source.id === node.id) {
        highlightedLinkIndices.add(idx);
      } else {
        dimmedLinkIndices.add(idx);
      }
    });
    this.highlightState = { dimmedIds, highlightedIds: connectedIds, dimmedLinkIndices, highlightedLinkIndices };

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

    // Show panel for focused author (not on portrait mobile)
    if (!this._isPortraitMobile()) {
      this.showPanel(node);
    }
  }

  exitFocusMode() {
    if (!this.focusMode) return;

    this.focusMode = false;
    this.focusedNode = null;
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

    this.closePanel();
  }

  _isPortraitMobile() {
    return window.innerWidth <= 600 && window.innerHeight > window.innerWidth;
  }

  // === Panel ===

  showPanel(node) {
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
      shelfContainer.style.display = 'flex';
      shelfContainer.style.gap = '8px';
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
          this.selectedNode = target.authorNode;
          this.highlightAuthor(target.authorNode);
          this.showPanel(target.bookData);
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
}

// Boot
const app = new BookGraphApp();
app.init();
