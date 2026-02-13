/**
 * interaction.js — Events, hit testing, zoom/pan, hover, click, search.
 */

import d3 from './d3-imports.js';

export class InteractionManager {
  constructor(canvas, app) {
    this.canvas = canvas;
    this.app = app;  // reference to app for accessing state
    this.zoom = null;
    this.transform = d3.zoomIdentity;
    this.hoveredAuthor = null;
    this.hoveredBook = null;
    this.searchTimeout = null;
  }

  /**
   * Initialize d3-zoom on the canvas and set up all event listeners.
   * @param {Function} onTransform - Called with {x, y, k} on zoom/pan
   */
  init(onTransform) {
    this.onTransform = onTransform;

    // d3-zoom
    this.zoom = d3.zoom()
      .scaleExtent([0.1, 10])
      .filter(event => {
        // Disable double-click zoom (we use it for focus mode exit)
        if (event.type === 'dblclick') return false;
        return true;
      })
      .on('zoom', (event) => {
        this.transform = event.transform;
        onTransform({ x: event.transform.x, y: event.transform.y, k: event.transform.k });
      });

    d3.select(this.canvas).call(this.zoom);

    // Prevent default context menu on canvas
    this.canvas.addEventListener('contextmenu', e => e.preventDefault());

    // Mouse events for hit testing
    this.canvas.addEventListener('mousemove', (e) => this._onMouseMove(e));
    this.canvas.addEventListener('click', (e) => this._onClick(e));
    this.canvas.addEventListener('dblclick', (e) => this._onDblClick(e));

    // Touch events
    this.canvas.addEventListener('touchend', (e) => this._onTouchEnd(e), { passive: true });

    // Keyboard
    document.addEventListener('keydown', (e) => this._onKeyDown(e));

    // Search
    const searchInput = document.getElementById('search');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => this._onSearch(e));
      searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          e.target.value = '';
          e.target.dispatchEvent(new Event('input'));
        }
      });
    }

    // Panel close
    const panelClose = document.getElementById('panel-close');
    if (panelClose) {
      panelClose.onclick = () => {
        this.app.closePanel();
        this.app.clearSelection();
      };
    }

    // Citation panel close
    const citationPanelClose = document.getElementById('citation-panel-close');
    if (citationPanelClose) {
      citationPanelClose.addEventListener('click', () => {
        this.app.exitFocusMode();
      });
    }

    // Focus exit button
    const focusExit = document.getElementById('focus-exit');
    if (focusExit) {
      focusExit.addEventListener('click', (e) => {
        e.stopPropagation();
        this.app.exitFocusMode();
      });
    }

    // Mobile hint close
    const mobileHintClose = document.getElementById('mobile-hint-close');
    if (mobileHintClose) {
      mobileHintClose.addEventListener('click', () => {
        document.getElementById('mobile-hint').style.display = 'none';
      });
    }

    // Mobile bottom sheet drag-to-dismiss
    this._setupPanelDrag(
      document.getElementById('citation-panel'),
      80,
      () => this.app.exitFocusMode()
    );
    this._setupPanelDrag(
      document.getElementById('info-panel'),
      80,
      () => { this.app.closePanel(); this.app.clearSelection(); }
    );
  }

  /**
   * Programmatically set the zoom transform (for auto-fit, animated zoom).
   */
  setTransform(x, y, k, animate = false) {
    const t = d3.zoomIdentity.translate(x, y).scale(k);
    const sel = d3.select(this.canvas);
    if (animate) {
      sel.transition().duration(600).call(this.zoom.transform, t);
    } else {
      sel.call(this.zoom.transform, t);
    }
  }

  /**
   * Convert screen coordinates to world coordinates.
   */
  screenToWorld(sx, sy) {
    const t = this.transform;
    return {
      x: (sx - t.x) / t.k,
      y: (sy - t.y) / t.k,
    };
  }

  /**
   * CPU-side brute-force hit test against all author nodes and book circles.
   * Returns { author, book } or null.
   */
  hitTest(screenX, screenY) {
    const world = this.screenToWorld(screenX, screenY);
    const authors = this.app.graphData.authors;

    // Check authors (and nested books) from front to back
    for (let i = authors.length - 1; i >= 0; i--) {
      const a = authors[i];
      const dx = world.x - a.x;
      const dy = world.y - a.y;
      const distToAuthor = Math.sqrt(dx * dx + dy * dy);

      if (distToAuthor <= a.r) {
        // Check individual books within this author
        if (a.books) {
          for (let j = a.books.length - 1; j >= 0; j--) {
            const b = a.books[j];
            const bx = world.x - (a.x + b.x);
            const by = world.y - (a.y + b.y);
            const distToBook = Math.sqrt(bx * bx + by * by);

            // Add touch margin for coarse pointers
            const touchMargin = this._isTouch() ? 8 : 0;
            if (distToBook <= b.r + touchMargin) {
              return { author: a, book: b };
            }
          }
        }
        return { author: a, book: null };
      }
    }

    return null;
  }

  _isTouch() {
    return matchMedia('(pointer: coarse)').matches;
  }

  _isPortraitMobile() {
    return window.innerWidth <= 600 && window.innerHeight > window.innerWidth;
  }

  /**
   * Set up touch drag on a bottom sheet panel.
   * Drag up to expand to ~90vh, drag down to dismiss.
   * Only activates in portrait mobile mode.
   * @param {HTMLElement} panel - The panel element
   * @param {number} headerHeight - Max touch-start Y offset from panel top to initiate drag
   * @param {Function} onClose - Called when the panel is dismissed
   */
  _setupPanelDrag(panel, headerHeight, onClose) {
    if (!panel) return;

    let startY, deltaY, isDragging, startTime, expanded;

    const onTouchMove = (e) => {
      e.preventDefault();
      deltaY = e.touches[0].clientY - startY;

      if (expanded) {
        // When expanded, only allow dragging down (positive deltaY)
        const clamped = Math.max(0, deltaY);
        panel.style.transform = `translateY(${clamped}px)`;
      } else {
        // Default state: allow both directions
        panel.style.transform = `translateY(${deltaY}px)`;
      }
    };

    const endDrag = (action) => {
      isDragging = false;
      panel.removeEventListener('touchmove', onTouchMove);
      const ease = 'transform 0.3s cubic-bezier(0.16, 1, 0.3, 1)';

      if (action === 'dismiss') {
        panel.style.transition = ease;
        panel.style.transform = 'translateY(100%)';
        setTimeout(() => {
          panel.style.transition = '';
          panel.style.transform = '';
          panel.classList.remove('expanded');
          expanded = false;
          onClose();
        }, 300);
      } else if (action === 'expand') {
        expanded = true;
        panel.classList.add('expanded');
        panel.style.transition = ease;
        panel.style.transform = '';
        setTimeout(() => { panel.style.transition = ''; }, 300);
      } else if (action === 'collapse') {
        expanded = false;
        panel.classList.remove('expanded');
        panel.style.transition = ease;
        panel.style.transform = '';
        setTimeout(() => { panel.style.transition = ''; }, 300);
      } else {
        // snap back
        panel.style.transition = ease;
        panel.style.transform = '';
        setTimeout(() => { panel.style.transition = ''; }, 300);
      }
      deltaY = 0;
    };

    panel.addEventListener('touchstart', (e) => {
      if (!this._isPortraitMobile()) return;
      if (!panel.classList.contains('visible')) return;
      const rect = panel.getBoundingClientRect();
      if (e.touches[0].clientY - rect.top > headerHeight) return;

      startY = e.touches[0].clientY;
      startTime = Date.now();
      deltaY = 0;
      isDragging = true;
      expanded = panel.classList.contains('expanded');
      panel.style.transition = 'none';
      panel.addEventListener('touchmove', onTouchMove, { passive: false });
    }, { passive: true });

    panel.addEventListener('touchend', () => {
      if (!isDragging) return;
      const elapsed = Math.max(Date.now() - startTime, 1);
      const velocity = deltaY / elapsed; // px/ms, negative = upward

      if (expanded) {
        // Expanded: drag down to collapse or dismiss
        if (deltaY > 150 || velocity > 0.5) {
          endDrag('dismiss');
        } else if (deltaY > 60 || velocity > 0.3) {
          endDrag('collapse');
        } else {
          endDrag('snapback');
        }
      } else {
        // Default: drag up to expand, drag down to dismiss
        if (deltaY < -60 || velocity < -0.3) {
          endDrag('expand');
        } else if (deltaY > 80 || velocity > 0.5) {
          endDrag('dismiss');
        } else {
          endDrag('snapback');
        }
      }
    });

    panel.addEventListener('touchcancel', () => {
      if (!isDragging) return;
      endDrag('snapback');
    });
  }

  _onMouseMove(e) {
    const rect = this.canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    const hit = this.hitTest(sx, sy);

    if (hit) {
      this.canvas.style.cursor = 'pointer';
      if (hit.book) {
        this.app.showTooltip(e.clientX, e.clientY, hit.book.data.title);
      } else {
        this.app.hideTooltip();
      }

      if (!this.app.focusMode) {
        if (hit.author !== this.hoveredAuthor) {
          this.hoveredAuthor = hit.author;
          this.app.highlightAuthor(hit.author);
        }
      }
    } else {
      this.canvas.style.cursor = 'default';
      this.app.hideTooltip();
      if (!this.app.focusMode && this.hoveredAuthor) {
        this.hoveredAuthor = null;
        this.app.resetHighlight();
      }
    }
  }

  _onClick(e) {
    // Debounce duplicate clicks (d3-zoom can cause double-fire)
    const now = performance.now();
    if (now - (this._lastClickTime || 0) < 50) return;
    this._lastClickTime = now;

    const rect = this.canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    const hit = this.hitTest(sx, sy);

    if (hit) {
      if (this.app.focusMode) {
        // In focus mode
        if (hit.author && this.app.focusedNode && this.app.focusedNode.id === hit.author.id) {
          // Clicking center node exits focus mode
          this.app.exitFocusMode();
        } else if (hit.book) {
          this.app.showPanel(hit.book.data);
        } else if (hit.author) {
          this.app.showPanel(hit.author);
        }
      } else {
        // Normal mode
        if (hit.author.isSource) {
          // Source nodes — enter focus mode
          // If a specific source book was clicked, scope to that book
          const sourceBook = (hit.book && hit.book.data && hit.book.data.isSource) ? hit.book : null;
          this.app.enterFocusMode(hit.author, sourceBook);
        } else if (hit.book) {
          // Cited book — show detail directly
          this.app.selectedNode = hit.author;
          this.app.highlightAuthor(hit.author);
          this.app.showPanel(hit.book.data);
        } else {
          // Cited author — show detail directly
          this.app.selectedNode = hit.author;
          this.app.highlightAuthor(hit.author);
          this.app.showPanel(hit.author);
        }
      }
    } else {
      // Clicked empty space
      if (this.app.focusMode) {
        this.app.exitFocusMode();
      } else {
        this.app.closePanel();
        this.app.clearSelection();
      }
    }
  }

  _onDblClick(e) {
    // Prevent d3-zoom's default double-click zoom
    e.preventDefault();
    e.stopPropagation();
  }

  _onTouchEnd(e) {
    // Touch hit testing handled by click events via d3-zoom
  }

  _onKeyDown(e) {
    if (e.key === 'Escape') {
      if (this.app.focusMode) {
        this.app.exitFocusMode();
      }
    }
  }

  _onSearch(e) {
    const query = e.target.value.toLowerCase().trim();
    const resultsEl = document.getElementById('search-results');

    if (this.searchTimeout) clearTimeout(this.searchTimeout);

    if (!query) {
      this.app.resetHighlight();
      if (resultsEl) resultsEl.textContent = '';
      return;
    }

    this.searchTimeout = setTimeout(() => {
      const authors = this.app.graphData.authors;
      const matches = [];

      for (const a of authors) {
        const authorMatch = a.name.toLowerCase().includes(query);
        const bookMatch = a.books && a.books.some(b => b.data.title.toLowerCase().includes(query));
        const isMatch = authorMatch || bookMatch;

        if (isMatch) {
          let score = 0;
          if (a.name.toLowerCase() === query) score = 100;
          else if (a.name.toLowerCase().startsWith(query)) score = 80;
          else if (authorMatch) score = 60;
          else score = 40;

          matches.push({ node: a, score, authorMatch });
        }
      }

      matches.sort((a, b) => b.score - a.score);

      if (matches.length > 0) {
        if (resultsEl) resultsEl.textContent = `${matches.length} match${matches.length > 1 ? 'es' : ''} found`;

        // Highlight matches, dim everything else
        const matchIds = new Set(matches.map(m => m.node.id));
        this.app.highlightSet(matchIds);

        // Zoom to best match
        const best = matches[0].node;
        const t = this.transform;
        const screenX = best.x * t.k + t.x;
        const screenY = best.y * t.k + t.y;
        const cx = window.innerWidth / 2;
        const cy = window.innerHeight / 3;

        this.setTransform(
          t.x + (cx - screenX),
          t.y + (cy - screenY),
          t.k,
          true
        );
      } else {
        if (resultsEl) resultsEl.textContent = 'No matches';
      }
    }, 200);
  }
}
