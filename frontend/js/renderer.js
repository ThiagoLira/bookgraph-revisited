/**
 * renderer.js — Canvas 2D renderer. Reads fixed baked positions; no physics.
 * Draws timeline gridlines, edges, nested author/book circles, author photos
 * (fade-in on zoom), labels (LOD), and focus/hover/region dimming.
 */

const PHOTO_ZOOM = 0.85; // start loading/showing portraits past this scale (earlier)
const LABEL_MIN_PX = 13; // show author label when on-screen radius exceeds this
const DIM = 0.07;
const HOVER_DIM = 0.22;

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
    this.scheduleDraw();
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
      if (node === s.hover) return 1;
      return s.hover.out.some((l) => l.target === node) || s.hover.in.some((l) => l.source === node)
        ? 1
        : HOVER_DIM;
    }
    return 1;
  }

  _edgeAlpha(link) {
    const s = this.store;
    if (s.regionFilter) {
      return link.source.region === s.regionFilter || link.target.region === s.regionFilter ? 0.18 : 0.02;
    }
    if (s.focus) {
      const c = s.focus.centerId;
      return link.source.id === c || link.target.id === c ? 0.45 : 0.015;
    }
    if (s.hover) {
      return link.source === s.hover || link.target === s.hover ? 0.4 : 0.02;
    }
    return 0.07;
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

    const m = 80;
    const vx0 = (-t.x - m) / t.k;
    const vy0 = (-t.y - m) / t.k;
    const vx1 = (this.W - t.x + m) / t.k;
    const vy1 = (this.H - t.y + m) / t.k;

    ctx.save();
    ctx.translate(t.x, t.y);
    ctx.scale(t.k, t.k);

    this._drawGridlines(ctx, vx0, vx1, vy0, vy1, t.k);
    this._drawEdges(ctx, vx0, vy0, vx1, vy1);

    for (const a of this.graph.authors) {
      if (a.x + a.r < vx0 || a.x - a.r > vx1 || a.y + a.r < vy0 || a.y - a.r > vy1) continue;
      const alpha = this._nodeAlpha(a);
      if (this._drawAuthor(ctx, a, alpha, t.k)) animating = true;
    }
    ctx.restore();

    this._drawLabels(ctx, t, vx0, vy0, vx1, vy1);
    this._drawYearAxis(ctx, t);

    if (animating) this.scheduleDraw();
  }

  _drawGridlines(ctx, vx0, vx1, vy0, vy1, k) {
    const lines = this.graph.meta.gridlines || [];
    ctx.lineWidth = 1 / k;
    ctx.strokeStyle = "rgba(236,228,214,0.05)";
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
    const focused = !!this.store.focus;
    for (const l of this.graph.links) {
      const a = this._edgeAlpha(l);
      if (a < 0.02) continue;
      const s = l.source, t2 = l.target;
      if (
        (s.x < vx0 && t2.x < vx0) || (s.x > vx1 && t2.x > vx1) ||
        (s.y < vy0 && t2.y < vy0) || (s.y > vy1 && t2.y > vy1)
      ) continue;
      ctx.globalAlpha = a;
      ctx.strokeStyle = focused ? "#d4a574" : "rgba(180,170,150,1)";
      ctx.lineWidth = (a > 0.3 ? 1.3 : 0.7) / k;
      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(t2.x, t2.y);
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
      ctx.globalAlpha = 1;
      ctx.lineWidth = 2.5 / k;
      ctx.strokeStyle = "#ece4d6";
      ctx.beginPath();
      ctx.arc(a.x, a.y, a.r + 4 / k, 0, Math.PI * 2);
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
    // source authors get a light ring to stand out
    if (a.is_source) {
      ctx.globalAlpha = alpha * 0.85;
      ctx.lineWidth = 1.6 / k;
      ctx.strokeStyle = "#ece4d6";
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
          ctx.strokeStyle = "#d4a574";
          ctx.stroke();
        } else if (b.is_source) {
          ctx.globalAlpha = alpha * 0.9;
          ctx.lineWidth = 1.5 / k;
          ctx.strokeStyle = "#ece4d6";
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
      const isKey = a === this.store.selected || a === this.store.hover ||
        (this.store.focus && this.store.focus.relatedIds.has(a.id));
      if (onScreenR < LABEL_MIN_PX && !isKey) continue;
      const alpha = this._nodeAlpha(a);
      if (alpha < 0.3 && !isKey) continue;
      const sx = a.x * t.k + t.x;
      const sy = (a.y + a.r) * t.k + t.y + 5;
      const fs = isKey ? 14 : 12.5;
      ctx.font = `500 ${fs}px "Cormorant Garamond", serif`;
      ctx.globalAlpha = Math.min(1, alpha + 0.15);
      ctx.lineWidth = 3;
      ctx.strokeStyle = "rgba(20,17,13,0.85)";
      ctx.strokeText(a.name, sx, sy);
      ctx.fillStyle = isKey ? "#ece4d6" : "#cfc4b0";
      ctx.fillText(a.name, sx, sy);
    }
    ctx.globalAlpha = 1;
  }

  _drawYearAxis(ctx, t) {
    const lines = this.graph.meta.gridlines || [];
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    ctx.font = '11px "JetBrains Mono", monospace';
    const x = this.W - 12;
    let lastY = -1e9;
    for (const g of lines) {
      const sy = g.y * t.k + t.y;
      if (sy < 60 || sy > this.H - 8) continue;
      if (Math.abs(sy - lastY) < 26) continue;
      lastY = sy;
      const label = g.year < 0 ? `${-g.year} BC` : `${g.year}`;
      ctx.globalAlpha = 0.55;
      ctx.fillStyle = "#8a7f6e";
      ctx.fillText(label, x, sy);
    }
    ctx.globalAlpha = 1;
  }
}
