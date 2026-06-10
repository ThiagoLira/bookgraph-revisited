/**
 * renderer.js — Canvas 2D renderer. Reads fixed baked positions; no physics.
 * Draws era strata + timeline gridlines, curved citation edges, nested
 * author/book circles, author photos (fade-in on zoom), labels (LOD), and
 * focus/hover/region dimming.
 */

const PHOTO_ZOOM = 0.85; // start loading/showing portraits past this scale (earlier)
const LABEL_MIN_PX = 13; // show author label when on-screen radius exceeds this
const DIM = 0.07;
const HOVER_DIM = 0.22;

const BG = "rgba(14,11,8,0.88)"; // label halo — match --bg-0
const GOLD = "#c89c5a"; // outgoing citations (this author cites …)
const VERDIGRIS = "#87a791"; // incoming citations (… cites this author)
const IVORY = "#eae1cf";

// Historical strata painted behind the graph. `until` is the band's upper
// (more recent) year bound.
const ERAS = [
  { until: -800, name: "BRONZE AGE" },
  { until: 500, name: "ANTIQUITY" },
  { until: 1400, name: "MEDIEVAL" },
  { until: 1600, name: "RENAISSANCE" },
  { until: 1800, name: "ENLIGHTENMENT" },
  { until: 1900, name: "19TH CENTURY" },
  { until: 2000, name: "MODERN" },
  { until: Infinity, name: "CONTEMPORARY" },
];

export class Renderer {
  constructor(canvas, store) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.store = store;
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.graph = null;
    this.images = new Map(); // id -> {img, alpha, status}
    this._raf = null;
    this._loadsThisFrame = 0;
    this.resize();
  }

  setGraph(graph) {
    this.graph = graph;
    this.images.clear();
    this._buildEras();
    // Positions are baked and static — compute each edge's bezier control
    // point once, not per frame.
    for (const l of graph.links) {
      const dx = l.target.x - l.source.x, dy = l.target.y - l.source.y;
      const dist = Math.hypot(dx, dy) || 1;
      const bow = Math.min(150, dist * 0.16) * (dx >= 0 ? 1 : -1);
      l.cx = (l.source.x + l.target.x) / 2 - (dy / dist) * bow;
      l.cy = (l.source.y + l.target.y) / 2 + (dx / dist) * bow;
    }
    this._bakeMesh();
    this.scheduleDraw();
  }

  /**
   * Pre-render the full neutral edge mesh to an offscreen bitmap, once.
   * Re-tessellating 8k bezier strokes per frame saturates the canvas
   * thread; blitting a cached bitmap is a single GPU-scaled drawImage.
   * Per-frame alpha (normal vs dimmed-for-focus) is applied at blit time.
   */
  _bakeMesh() {
    const meta = this.graph.meta;
    const maxDim = 4096;
    const scale = Math.min(maxDim / meta.worldWidth, maxDim / meta.worldHeight);
    const c = document.createElement("canvas");
    c.width = Math.ceil(meta.worldWidth * scale);
    c.height = Math.ceil(meta.worldHeight * scale);
    const mctx = c.getContext("2d");
    mctx.scale(scale, scale);
    mctx.strokeStyle = "rgb(196,182,158)";
    mctx.lineWidth = 1 / scale; // 1 bitmap px — hairline at every zoom
    mctx.beginPath();
    for (const l of this.graph.links) {
      mctx.moveTo(l.source.x, l.source.y);
      mctx.quadraticCurveTo(l.cx, l.cy, l.target.x, l.target.y);
    }
    mctx.stroke();
    this._mesh = { canvas: c, scale };
  }

  /** Piecewise-linear year→worldY from the baked gridlines, then era bands. */
  _buildEras() {
    const lines = (this.graph.meta.gridlines || []).slice().sort((a, b) => a.year - b.year);
    this.eras = [];
    if (lines.length < 2) return;
    const yOf = (year) => {
      if (year <= lines[0].year) return lines[0].y;
      if (year >= lines[lines.length - 1].year) return lines[lines.length - 1].y;
      for (let i = 1; i < lines.length; i++) {
        if (year <= lines[i].year) {
          const a = lines[i - 1], b = lines[i];
          const f = (year - a.year) / (b.year - a.year);
          return a.y + f * (b.y - a.y);
        }
      }
      return lines[lines.length - 1].y;
    };
    const minYear = lines[0].year, maxYear = lines[lines.length - 1].year;
    let from = minYear;
    for (const e of ERAS) {
      const to = Math.min(e.until, maxYear);
      if (to <= from) { from = Math.max(from, e.until); continue; }
      // y decreases as years increase: band spans [yTop, yBottom]
      this.eras.push({ name: e.name, yTop: yOf(to), yBottom: yOf(from), from, to });
      from = e.until;
      if (from >= maxYear) break;
    }
  }

  resize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = w * this.dpr;
    this.canvas.height = h * this.dpr;
    this.canvas.style.width = w + "px";
    this.canvas.style.height = h + "px";
    this.W = w;
    this.H = h;
    this.scheduleDraw();
  }

  scheduleDraw() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => {
      this._raf = null;
      this.draw();
    });
  }

  // ---- alpha logic --------------------------------------------------------
  _nodeAlpha(node) {
    const s = this.store;
    if (s.regionFilter) return node.region === s.regionFilter ? 1 : DIM;
    if (s.focus) return s.focus.relatedIds.has(node.id) ? 1 : DIM;
    if (s.hover) {
      return this._hoverRelated && this._hoverRelated.has(node.id) ? 1 : HOVER_DIM;
    }
    return 1;
  }


  // ---- main draw ----------------------------------------------------------
  draw() {
    const ctx = this.ctx;
    const t = this.store.transform;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, this.W, this.H);
    if (!this.graph || !t) return;

    this._loadsThisFrame = 0;
    let animating = false;

    // Rebuild the hover-related set only when the hovered node changes —
    // probing 500-link adjacency lists per node per frame melts the CPU.
    if (this.store.hover !== this._hoverNode) {
      this._hoverNode = this.store.hover;
      const h = this._hoverNode;
      this._hoverRelated = h
        ? new Set([h.id, ...h.out.map((l) => l.target.id), ...h.in.map((l) => l.source.id)])
        : null;
    }

    const m = 80;
    const vx0 = (-t.x - m) / t.k;
    const vy0 = (-t.y - m) / t.k;
    const vx1 = (this.W - t.x + m) / t.k;
    const vy1 = (this.H - t.y + m) / t.k;

    ctx.save();
    ctx.translate(t.x, t.y);
    ctx.scale(t.k, t.k);

    this._drawStrata(ctx, vx0, vx1, vy0, vy1, t.k);
    this._drawEdges(ctx, vx0, vy0, vx1, vy1);

    for (const a of this.graph.authors) {
      if (a.x + a.r < vx0 || a.x - a.r > vx1 || a.y + a.r < vy0 || a.y - a.r > vy1) continue;
      const alpha = this._nodeAlpha(a);
      if (this._drawAuthor(ctx, a, alpha, t.k)) animating = true;
    }
    ctx.restore();

    this._drawLabels(ctx, t, vx0, vy0, vx1, vy1);
    this._drawYearAxis(ctx, t);
    this._drawEraLabels(ctx, t);

    if (animating) this.scheduleDraw();
  }

  /** Alternating sediment bands per era + faint century gridlines. */
  _drawStrata(ctx, vx0, vx1, vy0, vy1, k) {
    const eras = this.eras || [];
    for (let i = 0; i < eras.length; i++) {
      const e = eras[i];
      if (e.yBottom < vy0 || e.yTop > vy1) continue;
      if (i % 2 === 0) {
        ctx.fillStyle = "rgba(234,225,207,0.016)";
        ctx.fillRect(vx0, e.yTop, vx1 - vx0, e.yBottom - e.yTop);
      }
      // era boundary rule, slightly stronger than century lines
      ctx.strokeStyle = "rgba(200,156,90,0.07)";
      ctx.lineWidth = 1 / k;
      ctx.beginPath();
      ctx.moveTo(vx0, e.yTop);
      ctx.lineTo(vx1, e.yTop);
      ctx.stroke();
    }

    const lines = this.graph.meta.gridlines || [];
    ctx.lineWidth = 1 / k;
    ctx.strokeStyle = "rgba(234,225,207,0.035)";
    ctx.beginPath();
    for (const g of lines) {
      if (g.y < vy0 || g.y > vy1) continue;
      ctx.moveTo(vx0, g.y);
      ctx.lineTo(vx1, g.y);
    }
    ctx.stroke();
  }

  _drawEdges(ctx, vx0, vy0, vx1, vy1) {
    const k = this.store.transform.k;
    const s = this.store;
    const meta = this.graph.meta;

    // 1. Ambient mesh: one cached-bitmap blit, alpha picked by state.
    //    (Highlighted edges are redrawn bright on top, so the mesh just
    //    provides the dimmed background texture.)
    if (this._mesh) {
      const m = this._mesh;
      // Bitmap strokes are ~(1/scale) world units wide, so their on-screen
      // weight grows with k — counter-scale alpha to keep perceived density
      // constant (sub-pixel lines brighten, fat lines fade).
      const base = Math.min(0.45, (0.042 * m.scale) / k);
      ctx.globalAlpha = s.regionFilter ? base * 0.25 : s.focus ? base * 0.2 : s.hover ? base * 0.3 : base;
      ctx.drawImage(m.canvas, 0, 0, m.canvas.width, m.canvas.height, 0, 0, meta.worldWidth, meta.worldHeight);
      ctx.globalAlpha = 1;
    }

    // 2. Live edges: only the highlighted few, batched into ≤3 strokes.
    let live = null, alpha = 0, directional = false, centerId = null;
    if (s.regionFilter) {
      live = this.graph.links.filter(
        (l) => l.source.region === s.regionFilter || l.target.region === s.regionFilter
      );
      alpha = 0.16;
    } else if (s.focus || s.hover) {
      const node = s.focus ? this.graph.authorById.get(s.focus.centerId) : s.hover;
      if (node) {
        live = [...node.out, ...node.in];
        centerId = node.id;
        directional = true;
        // dense hubs: fade each strand so 500 edges read as filigree, not flare
        alpha = Math.max(0.1, Math.min(0.42, 3.5 / Math.sqrt(live.length + 1)));
      }
    }
    if (!live || !live.length) return;

    const buckets = new Map(); // color -> links[]
    for (const l of live) {
      const src = l.source, tgt = l.target;
      if (
        (src.x < vx0 && tgt.x < vx0) || (src.x > vx1 && tgt.x > vx1) ||
        (src.y < vy0 && tgt.y < vy0) || (src.y > vy1 && tgt.y > vy1)
      ) continue;
      // gold = the highlighted node cites, verdigris = it is cited by
      const color = !directional ? "rgb(196,182,158)" : l.source.id === centerId ? GOLD : VERDIGRIS;
      let arr = buckets.get(color);
      if (!arr) buckets.set(color, (arr = []));
      arr.push(l);
    }
    ctx.globalAlpha = alpha;
    ctx.lineWidth = (alpha > 0.3 ? 1.2 : 0.8) / k;
    for (const [color, links] of buckets) {
      ctx.strokeStyle = color;
      ctx.beginPath();
      for (const l of links) {
        ctx.moveTo(l.source.x, l.source.y);
        ctx.quadraticCurveTo(l.cx, l.cy, l.target.x, l.target.y);
      }
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  _drawAuthor(ctx, a, alpha, k) {
    let animating = false;
    ctx.globalAlpha = alpha;

    // Default node = a plain ball. Zoom in -> portrait. Hover -> reveal books.
    const isHovered = this.store.hover === a;
    const wantPhoto = k > PHOTO_ZOOM && a.image_url && alpha > 0.5 && !isHovered;
    let entry = this.images.get(a.id);
    if (wantPhoto && !entry && this._loadsThisFrame < 8) entry = this._loadImage(a);
    const photoReady = entry && entry.status === "ok";

    if (photoReady && wantPhoto) {
      if (entry.alpha < 1) { entry.alpha = Math.min(1, entry.alpha + 0.08); animating = true; }
      const pa = entry.alpha;
      if (pa < 1) this._drawPlainBall(ctx, a, alpha * (1 - pa), k);
      ctx.save();
      ctx.beginPath();
      ctx.arc(a.x, a.y, a.r, 0, Math.PI * 2);
      ctx.clip();
      const img = entry.img;
      const d = a.r * 2;
      const scale = Math.max(d / img.width, d / img.height);
      const iw = img.width * scale, ih = img.height * scale;
      ctx.globalAlpha = alpha * pa;
      ctx.drawImage(img, a.x - iw / 2, a.y - ih / 2, iw, ih);
      ctx.restore();
      ctx.globalAlpha = alpha;
      ctx.lineWidth = Math.max(1.5 / k, a.r * 0.04);
      ctx.strokeStyle = a.color;
      ctx.beginPath();
      ctx.arc(a.x, a.y, a.r, 0, Math.PI * 2);
      ctx.stroke();
    } else if (isHovered && a.books && a.books.length) {
      this._drawBooks(ctx, a, alpha, k); // reveal books on hover
    } else {
      this._drawPlainBall(ctx, a, alpha, k);
      if (wantPhoto && entry && entry.status === "loading") animating = true;
    }

    if (this.store.selected === a) {
      // double gilt ring marks the selection
      ctx.globalAlpha = 1;
      ctx.strokeStyle = IVORY;
      ctx.lineWidth = 2 / k;
      ctx.beginPath();
      ctx.arc(a.x, a.y, a.r + 4 / k, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 0.55;
      ctx.strokeStyle = GOLD;
      ctx.lineWidth = 1 / k;
      ctx.beginPath();
      ctx.arc(a.x, a.y, a.r + 9 / k, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
    return animating;
  }

  _drawPlainBall(ctx, a, alpha, k) {
    ctx.globalAlpha = alpha;
    ctx.fillStyle = a.color;
    ctx.beginPath();
    ctx.arc(a.x, a.y, a.r, 0, Math.PI * 2);
    ctx.fill();
    // subtle edge for depth
    ctx.globalAlpha = alpha * 0.35;
    ctx.lineWidth = 1 / k;
    ctx.strokeStyle = "rgba(0,0,0,0.45)";
    ctx.stroke();
    // source authors get a gilt ring to stand out
    if (a.is_source) {
      ctx.globalAlpha = alpha * 0.9;
      ctx.lineWidth = 1.6 / k;
      ctx.strokeStyle = GOLD;
      ctx.beginPath();
      ctx.arc(a.x, a.y, a.r, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.globalAlpha = alpha;
  }

  _drawBooks(ctx, a, alpha, k) {
    ctx.globalAlpha = alpha * 0.13;
    ctx.fillStyle = a.color;
    ctx.beginPath();
    ctx.arc(a.x, a.y, a.r, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = alpha * 0.4;
    ctx.lineWidth = 1 / k;
    ctx.strokeStyle = a.color;
    ctx.stroke();

    const books = a.books || [];
    if (!books.length) {
      ctx.globalAlpha = alpha;
      ctx.fillStyle = a.color;
      ctx.beginPath();
      ctx.arc(a.x, a.y, Math.min(a.r, 4), 0, Math.PI * 2);
      ctx.fill();
    } else {
      const hb = this.store.hoverBook;
      for (const b of books) {
        const isHB = hb && hb.book === b;
        ctx.globalAlpha = alpha;
        ctx.fillStyle = a.color;
        ctx.beginPath();
        ctx.arc(a.x + b.x, a.y + b.y, b.r, 0, Math.PI * 2);
        ctx.fill();
        if (isHB) {
          ctx.globalAlpha = 1;
          ctx.lineWidth = 2.5 / k;
          ctx.strokeStyle = GOLD;
          ctx.stroke();
        } else if (b.is_source) {
          ctx.globalAlpha = alpha * 0.9;
          ctx.lineWidth = 1.5 / k;
          ctx.strokeStyle = IVORY;
          ctx.stroke();
        }
      }
    }
    ctx.globalAlpha = alpha;
  }

  _loadImage(a) {
    const entry = { img: new Image(), alpha: 0, status: "loading" };
    entry.img.crossOrigin = "anonymous";
    entry.img.onload = () => { entry.status = "ok"; this.scheduleDraw(); };
    entry.img.onerror = () => { entry.status = "err"; };
    entry.img.src = a.image_url;
    this.images.set(a.id, entry);
    this._loadsThisFrame++;
    return entry;
  }

  _drawLabels(ctx, t, vx0, vy0, vx1, vy1) {
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (const a of this.graph.authors) {
      if (a.x < vx0 || a.x > vx1 || a.y < vy0 || a.y > vy1) continue;
      const onScreenR = a.r * t.k;
      const isPrimary = a === this.store.selected || a === this.store.hover;
      const isKey = isPrimary ||
        (this.store.focus && this.store.focus.relatedIds.has(a.id));
      if (onScreenR < LABEL_MIN_PX && !isKey) continue;
      // related-but-tiny nodes stay unlabeled, or a dense hub becomes label soup
      if (isKey && !isPrimary && onScreenR < 5) continue;
      const alpha = this._nodeAlpha(a);
      if (alpha < 0.3 && !isKey) continue;
      const sx = a.x * t.k + t.x;
      const sy = (a.y + a.r) * t.k + t.y + 6;
      const fs = isKey ? 13.5 : 12;
      ctx.font = `${fs}px "Libre Caslon Text", Georgia, serif`;
      ctx.globalAlpha = Math.min(1, alpha + 0.15);
      ctx.lineWidth = 3.5;
      ctx.strokeStyle = BG;
      ctx.strokeText(a.name, sx, sy);
      ctx.fillStyle = isKey ? IVORY : "#c9bda6";
      ctx.fillText(a.name, sx, sy);
    }
    ctx.globalAlpha = 1;
  }

  _drawYearAxis(ctx, t) {
    const lines = this.graph.meta.gridlines || [];
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    ctx.font = '10px "IBM Plex Mono", monospace';
    const x = this.W - 14;
    let lastY = -1e9;
    for (const g of lines) {
      const sy = g.y * t.k + t.y;
      if (sy < 70 || sy > this.H - 14) continue;
      if (Math.abs(sy - lastY) < 30) continue;
      lastY = sy;
      const label = g.year < 0 ? `${-g.year} BC` : `${g.year}`;
      ctx.globalAlpha = 0.5;
      ctx.fillStyle = "#93876e";
      ctx.fillText(label, x, sy);
      ctx.globalAlpha = 0.3;
      ctx.strokeStyle = "#93876e";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x + 4, sy);
      ctx.lineTo(x + 10, sy);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  /** Era names set vertically along the left edge, screen-space. */
  _drawEraLabels(ctx, t) {
    const eras = this.eras || [];
    ctx.save();
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = '500 9px "IBM Plex Mono", monospace';
    for (const e of eras) {
      const syTop = Math.max(64, e.yTop * t.k + t.y);
      const syBottom = Math.min(this.H - 8, e.yBottom * t.k + t.y);
      const visible = syBottom - syTop;
      if (visible < 70) continue; // band too thin on screen for a label
      const mid = (syTop + syBottom) / 2;
      const label = e.name.split("").join(" "); // hair-spaced letterspacing
      ctx.save();
      ctx.translate(16, mid);
      ctx.rotate(-Math.PI / 2);
      ctx.globalAlpha = 0.45;
      ctx.fillStyle = "#a08a5e";
      ctx.fillText(label, 0, 0);
      ctx.restore();
    }
    ctx.restore();
    ctx.globalAlpha = 1;
  }
}
