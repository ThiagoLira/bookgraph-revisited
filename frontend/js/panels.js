/**
 * panels.js — DOM UI: detail panel, citation-navigation panel, legend,
 * library selector, search. Subscribes to the store and re-renders.
 */

const $ = (id) => document.getElementById(id);

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
}
function esc(s) {
  return (s ?? "").toString().replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function fmtYear(y) {
  if (y == null || isNaN(y)) return "—";
  y = Math.round(y);
  return y < 0 ? `${-y} BC` : `${y}`;
}
function lifespan(a) {
  if (a.birth_year == null && a.death_year == null) return null;
  return `${fmtYear(a.birth_year)} – ${a.death_year ? fmtYear(a.death_year) : "?"}`;
}

export class Panels {
  constructor(store, interaction) {
    this.store = store;
    this.interaction = interaction;
    this.graph = null;
    this.citeTab = "cites";

    this.elCitation = $("citation-panel");
    this.elDetail = $("detail-panel");
    this.elLegend = $("legend");
    this.elBack = $("nav-back");

    // Hover popover: lets you see & click an author's books without selecting it first.
    this.popover = el("div");
    this.popover.id = "book-popover";
    document.body.appendChild(this.popover);
    this._popTimer = null;
    this.popover.addEventListener("mouseenter", () => clearTimeout(this._popTimer));
    this.popover.addEventListener("mouseleave", () => this._hidePopover());

    // Per-book title tooltip (shown when hovering an inner book ball).
    this.tooltip = el("div");
    this.tooltip.id = "book-tooltip";
    document.body.appendChild(this.tooltip);

    document.querySelectorAll(".panel-close").forEach((b) =>
      b.addEventListener("click", () => {
        if (b.dataset.close === "detail") this.closeDetail();
        else this.store.clearSelection();
      })
    );
    document.querySelectorAll(".cite-tab").forEach((t) =>
      t.addEventListener("click", () => {
        if (t.disabled) return;
        this.citeTab = t.dataset.tab;
        this._renderCitation(this.store.selected);
      })
    );
    this.elBack.addEventListener("click", () => {
      const prev = this.store.back();
      if (prev) this.interaction.flyTo(prev);
    });

    store.subscribe((reason) => {
      if (reason === "graph") this._onGraph();
      else if (reason === "select") this._onSelect();
      else if (reason === "selectBook") {
        this._renderBookDetail();
        if (this.store.selected) this._renderCitation(this.store.selected);
      }
      else if (reason === "hover") this._onHover();
      else if (reason === "hoverBook") this._onHoverBook();
      else if (reason === "transform") { this._hidePopover(0); this._hideTooltip(); }
    });
  }

  // ---- hover book popover -------------------------------------------------
  _onHover() {
    const a = this.store.hover;
    if (a && a.books && a.books.length) {
      clearTimeout(this._popTimer);
      this._popTimer = setTimeout(() => this._showPopover(a), 90);
    } else {
      this._hidePopover();
    }
  }

  _showPopover(a) {
    if (this.store.hover !== a) return;
    const regions = this.graph.meta.regions;
    const color = (regions[a.region] || regions.unknown).color;
    this.popover.innerHTML = "";
    const head = el("div", "bp-head");
    head.innerHTML = `${esc(a.name)} <span>· ${a.books.length} ${a.books.length === 1 ? "book" : "books"}</span>`;
    this.popover.appendChild(head);
    const books = a.books.slice().sort((x, y) => (x.year ?? 0) - (y.year ?? 0));
    for (const b of books) {
      const row = el("div", "bp-row");
      row.appendChild(el("span", "bp-dot")).style.background = color;
      row.appendChild(el("span", "bp-title" + (b.is_source ? " src" : ""), esc(b.title)));
      row.appendChild(el("span", "bp-year", fmtYear(b.year)));
      row.addEventListener("click", () => {
        this._hidePopover(0);
        this.store.selectAuthor(a);
        this.store.selectBook(b, a);
      });
      this.popover.appendChild(row);
    }
    // position next to the node (screen coords from the baked position + transform)
    const t = this.store.transform;
    const sx = a.x * t.k + t.x;
    const sy = a.y * t.k + t.y;
    const r = a.r * t.k;
    this.popover.classList.add("open");
    const pw = this.popover.offsetWidth || 240;
    const ph = this.popover.offsetHeight || 200;
    let left = sx + r + 12;
    if (left + pw > window.innerWidth - 8) left = sx - r - 12 - pw;
    left = Math.max(8, left);
    const top = Math.max(64, Math.min(window.innerHeight - ph - 8, sy - 28));
    this.popover.style.left = left + "px";
    this.popover.style.top = top + "px";
  }

  _onHoverBook() {
    const hb = this.store.hoverBook;
    if (!hb) {
      this._hideTooltip();
      return;
    }
    const t = this.store.transform;
    const sx = (hb.author.x + hb.book.x) * t.k + t.x;
    const sy = (hb.author.y + hb.book.y) * t.k + t.y;
    const r = hb.book.r * t.k;
    this.tooltip.innerHTML = `${esc(hb.book.title)}<span class="tt-year">${fmtYear(hb.book.year)}</span>`;
    this.tooltip.classList.add("open");
    this.tooltip.style.left = sx + "px";
    this.tooltip.style.top = sy - r - this.tooltip.offsetHeight - 7 + "px";
  }

  _hideTooltip() {
    this.tooltip.classList.remove("open");
  }

  _hidePopover(delay = 160) {
    clearTimeout(this._popTimer);
    if (delay === 0) {
      this.popover.classList.remove("open");
      return;
    }
    this._popTimer = setTimeout(() => this.popover.classList.remove("open"), delay);
  }

  setGraph(graph) {
    this.graph = graph;
  }

  _onGraph() {
    this.closeAll();
  }

  // ---- library selector & legend -----------------------------------------
  renderLibrarySelector(datasets, currentPath, onChange) {
    const sel = $("library-select");
    sel.innerHTML = "";
    for (const d of datasets) {
      const o = el("option");
      o.value = d.path;
      o.textContent = d.name;
      if (d.path === currentPath) o.selected = true;
      sel.appendChild(o);
    }
    sel.onchange = () => onChange(sel.value);
  }

  renderLegend(regions) {
    this.elLegend.innerHTML = "";
    this.elLegend.appendChild(el("div", "legend-title", "Region of origin"));
    for (const [key, r] of Object.entries(regions)) {
      const item = el("div", "legend-item");
      item.dataset.region = key;
      item.appendChild(el("span", "legend-swatch")).style.background = r.color;
      item.appendChild(el("span", null, esc(r.label)));
      item.addEventListener("click", () => {
        this.store.setRegionFilter(key);
        this._syncLegend();
      });
      this.elLegend.appendChild(item);
    }
  }

  _syncLegend() {
    const active = this.store.regionFilter;
    this.elLegend.querySelectorAll(".legend-item").forEach((it) => {
      it.classList.toggle("dim", active && it.dataset.region !== active);
    });
  }

  // ---- selection ----------------------------------------------------------
  _onSelect() {
    const node = this.store.selected;
    if (!node) {
      this.closeAll();
      return;
    }
    $("intro")?.classList.add("hidden");
    this._renderCitation(node);
    this._renderAuthorDetail(node);
    this.elCitation.classList.add("open");
    this.elCitation.setAttribute("aria-hidden", "false");
    this.elDetail.classList.add("open");
    this.elDetail.setAttribute("aria-hidden", "false");
    this.elLegend.classList.add("shifted");
    this.elBack.hidden = this.store.backStack.length === 0;
  }

  closeDetail() {
    this.elDetail.classList.remove("open");
    this.elDetail.setAttribute("aria-hidden", "true");
  }
  closeAll() {
    this.elCitation.classList.remove("open");
    this.elDetail.classList.remove("open");
    this.elCitation.setAttribute("aria-hidden", "true");
    this.elDetail.setAttribute("aria-hidden", "true");
    this.elLegend.classList.remove("shifted");
    this.elBack.hidden = true;
  }

  _navTo(node) {
    this.store.selectAuthor(node);
    this.interaction.flyTo(node);
  }

  // Preview a citation on the right panel only — no camera move, no change to
  // the current selection/focus/left panel.
  _previewAuthor(node) {
    this._renderAuthorDetail(node);
    this.elDetail.classList.add("open");
    this.elDetail.setAttribute("aria-hidden", "false");
  }
  _previewBook(book, author) {
    this._renderBookDetail({ book, author });
  }

  // ---- citation panel -----------------------------------------------------
  _renderCitation(node) {
    if (!node) return;
    $("citation-title").textContent = node.name;
    this.elBack.hidden = this.store.backStack.length === 0;

    // Work filter: clicking one of this author's source books narrows the
    // "Cites" lists to the citations that came from THAT book.
    const sb = this.store.selectedBook;
    const workFilter = sb && sb.author === node && sb.book.is_source ? sb.book : null;
    this._renderFilterLine(workFilter);
    if (workFilter) this.citeTab = "cites"; // filtering only applies to outgoing citations

    const outLinks = workFilter
      ? node.out.filter((l) => l.source_book_ids && l.source_book_ids.includes(workFilter.id))
      : node.out;
    const hasOut = outLinks.length > 0;
    const hasIn = node.in.length > 0;

    const tabCites = document.querySelector('.cite-tab[data-tab="cites"]');
    const tabCitedBy = document.querySelector('.cite-tab[data-tab="citedby"]');
    tabCites.disabled = !hasOut;
    tabCitedBy.disabled = !hasIn || !!workFilter;
    if (this.citeTab === "cites" && !hasOut && hasIn && !workFilter) this.citeTab = "citedby";
    if (this.citeTab === "citedby" && !hasIn && hasOut) this.citeTab = "cites";
    tabCites.classList.toggle("is-active", this.citeTab === "cites");
    tabCitedBy.classList.toggle("is-active", this.citeTab === "citedby");

    const authorsUl = $("list-authors");
    const worksUl = $("list-works");
    authorsUl.innerHTML = "";
    worksUl.innerHTML = "";
    const regions = this.graph.meta.regions;

    if (this.citeTab === "cites") {
      $("sec-works").style.display = "";
      if (!hasOut) {
        authorsUl.appendChild(
          el("li", "cite-empty", workFilter
            ? "No resolved citations from this work."
            : "This author's works weren't analyzed, so we don't know who they cite. Try the “Cited by” tab.")
        );
      }
      for (const l of outLinks) authorsUl.appendChild(this._authorRow(l.target, l.count, regions));
      const works = this._worksFromLinks(outLinks);
      if (!works.length) worksUl.appendChild(el("li", "cite-empty", "No specific works resolved."));
      for (const w of works) worksUl.appendChild(this._workRow(w.book, w.author, regions));
    } else {
      $("sec-works").style.display = "none";
      for (const l of node.in) authorsUl.appendChild(this._authorRow(l.source, l.count, regions));
    }
  }

  _worksFromLinks(links) {
    const seen = new Set();
    const works = [];
    for (const l of links) {
      for (const b of l.target.books) {
        if (b.is_source || seen.has(b.id)) continue;
        seen.add(b.id);
        works.push({ book: b, author: l.target });
      }
    }
    works.sort((a, b) => (a.book.year ?? 0) - (b.book.year ?? 0));
    return works;
  }

  _renderFilterLine(workFilter) {
    const elf = $("citation-filter");
    if (!elf) return;
    if (workFilter) {
      elf.hidden = false;
      elf.innerHTML = `Citations filtered on work: <em>${esc(workFilter.title)}</em> <button class="filter-clear" title="Clear filter">×</button>`;
      elf.querySelector(".filter-clear").addEventListener("click", (e) => {
        e.stopPropagation();
        this.store.clearBook();
      });
    } else {
      elf.hidden = true;
      elf.innerHTML = "";
    }
  }

  _authorRow(node, count, regions) {
    const row = el("li", "cite-row");
    row.appendChild(el("span", "cite-dot")).style.background = (regions[node.region] || regions.unknown).color;
    row.appendChild(el("span", "cite-name", esc(node.name)));
    row.appendChild(el("span", "cite-year", fmtYear(node.year)));
    if (count > 1) row.appendChild(el("span", "cite-count", `×${count}`));
    row.addEventListener("click", () => this._previewAuthor(node));
    return row;
  }

  _workRow(book, author, regions) {
    const row = el("li", "cite-row");
    row.appendChild(el("span", "cite-dot")).style.background = (regions[author.region] || regions.unknown).color;
    const name = el("span", "cite-name");
    name.innerHTML = `${esc(book.title)} <span style="color:var(--muted);font-family:var(--mono);font-size:10.5px">— ${esc(author.name)}</span>`;
    row.appendChild(name);
    row.appendChild(el("span", "cite-year", fmtYear(book.year)));
    row.addEventListener("click", () => this._previewBook(book, author));
    return row;
  }

  // ---- detail panel -------------------------------------------------------
  _renderAuthorDetail(a) {
    const regions = this.graph.meta.regions;
    const region = regions[a.region] || regions.unknown;
    const body = $("detail-body");
    body.innerHTML = "";

    const hero = el("div", "detail-hero");
    if (a.image_url) {
      const img = el("img", "detail-portrait");
      img.src = a.image_url;
      img.alt = a.name;
      img.onerror = () => img.replaceWith(this._portraitFallback(a, region));
      hero.appendChild(img);
    } else {
      hero.appendChild(this._portraitFallback(a, region));
    }
    hero.appendChild(el("div", "detail-eyebrow", a.is_source ? "Source Author" : "Author"));
    hero.appendChild(el("div", "detail-title", esc(a.name)));
    const span = lifespan(a);
    if (span) hero.appendChild(el("div", "detail-sub", span));
    const chips = el("div", "chips");
    const chip = el("span", "chip");
    chip.appendChild(el("span", "cite-dot")).style.background = region.color;
    chip.appendChild(document.createTextNode(a.nationality ? a.nationality : region.label));
    chips.appendChild(chip);
    if (a.main_genre) chips.appendChild(el("span", "chip", esc(a.main_genre)));
    hero.appendChild(chips);
    body.appendChild(hero);

    const stats = el("div", "detail-stats");
    stats.appendChild(this._stat(a.books.length, a.books.length === 1 ? "Book" : "Books"));
    if (a.out.length) stats.appendChild(this._stat(a.out.length, "Cites"));
    if (a.in.length) stats.appendChild(this._stat(a.in.length, "Cited by"));
    body.appendChild(stats);

    if (a.description) {
      const s = el("div", "detail-section");
      s.appendChild(el("h4", null, "About"));
      s.appendChild(el("p", "detail-desc", esc(a.description)));
      body.appendChild(s);
    }

    if (a.books.length) {
      const s = el("div", "detail-section");
      s.appendChild(el("h4", null, "Works in graph"));
      for (const b of a.books) {
        const chipEl = el("div", "book-chip" + (b.is_source ? " is-source" : ""));
        chipEl.appendChild(el("span", "book-chip-title", esc(b.title)));
        chipEl.appendChild(el("span", "book-chip-year", fmtYear(b.year)));
        chipEl.addEventListener("click", () => this.store.selectBook(b, a));
        s.appendChild(chipEl);
      }
      body.appendChild(s);
    }

    if (a.commentaries && a.commentaries.length) {
      const s = el("div", "detail-section");
      s.appendChild(el("h4", null, "Cited in context"));
      for (const c of a.commentaries.slice(0, 6)) s.appendChild(el("p", "commentary", esc(c)));
      body.appendChild(s);
    }
    body.scrollTop = 0;
  }

  _renderBookDetail(sb = this.store.selectedBook) {
    if (!sb) return;
    const { book, author } = sb;
    const body = $("detail-body");
    body.innerHTML = "";
    this.elDetail.classList.add("open");
    this.elDetail.setAttribute("aria-hidden", "false");

    const hero = el("div", "detail-hero");
    hero.appendChild(el("div", "detail-eyebrow", book.is_source ? "Source Work" : "Cited Work"));
    hero.appendChild(el("div", "detail-title", esc(book.title)));
    const sub = el("div", "detail-sub");
    const link = el("span", "detail-author-link", esc(author.name));
    link.addEventListener("click", () => this._navTo(author));
    sub.appendChild(document.createTextNode("by "));
    sub.appendChild(link);
    sub.appendChild(document.createTextNode(` · ${fmtYear(book.year)}`));
    hero.appendChild(sub);
    body.appendChild(hero);

    if (book.rating || book.pages) {
      const stats = el("div", "detail-stats");
      if (book.rating) stats.appendChild(this._stat(book.rating.toFixed(2), "Rating"));
      if (book.pages) stats.appendChild(this._stat(book.pages, "Pages"));
      body.appendChild(stats);
    }

    if (book.description) {
      const s = el("div", "detail-section");
      s.appendChild(el("h4", null, "Description"));
      s.appendChild(el("p", "detail-desc", esc(book.description)));
      body.appendChild(s);
    }
    if (book.commentaries && book.commentaries.length) {
      const s = el("div", "detail-section");
      s.appendChild(el("h4", null, "Cited in context"));
      for (const c of book.commentaries.slice(0, 8)) s.appendChild(el("p", "commentary", esc(c)));
      body.appendChild(s);
    }
    if (book.link) {
      const a = el("a", "detail-link", "View on Goodreads →");
      a.href = book.link;
      a.target = "_blank";
      a.rel = "noopener";
      body.appendChild(a);
    }
    body.scrollTop = 0;
  }

  _portraitFallback(a, region) {
    const f = el("div", "detail-portrait-fallback");
    f.style.background = region.color;
    f.textContent = (a.name[0] || "?").toUpperCase();
    return f;
  }
  _stat(num, label) {
    const s = el("div", "stat");
    s.appendChild(el("div", "stat-num", esc(num)));
    s.appendChild(el("div", "stat-label", esc(label)));
    return s;
  }

  // ---- search -------------------------------------------------------------
  setupSearch() {
    const input = $("search-input");
    const results = $("search-results");
    let timer = null;
    const run = () => {
      const q = input.value.trim().toLowerCase();
      results.innerHTML = "";
      if (q.length < 2 || !this.graph) {
        results.classList.remove("open");
        return;
      }
      const regions = this.graph.meta.regions;
      const hits = this.graph.searchIndex
        .filter((it) => it.text.includes(q))
        .slice(0, 40)
        .sort((a, b) => a.text.indexOf(q) - b.text.indexOf(q))
        .slice(0, 12);
      if (!hits.length) {
        results.classList.remove("open");
        return;
      }
      for (const h of hits) {
        const item = el("div", "sr-item");
        const node = h.node;
        const region = regions[node.region] || regions.unknown;
        if (h.type === "author") {
          item.appendChild(el("div", "sr-name", esc(node.name)));
          const meta = el("div", "sr-meta");
          meta.appendChild(el("span", "sr-dot")).style.background = region.color;
          meta.appendChild(el("span", null, `${esc(region.label)} · ${fmtYear(node.year)}`));
          item.appendChild(meta);
        } else {
          item.appendChild(el("div", "sr-name", esc(h.book.title)));
          item.appendChild(el("div", "sr-meta", `${esc(node.name)} · ${fmtYear(h.book.year)}`));
        }
        item.addEventListener("click", () => {
          input.value = "";
          results.classList.remove("open");
          this._navTo(node);
          if (h.type === "book") this.store.selectBook(h.book, node);
        });
        results.appendChild(item);
      }
      results.classList.add("open");
    };
    input.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(run, 160);
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".search-wrap")) results.classList.remove("open");
    });
  }
}
