/**
 * graph_model.mjs — Build the citation graph (authors + links) from stage-3
 * pipeline JSON. This is a Node port of the browser's old
 * frontend/js/data.js processData(), adapted to:
 *   - capture wikipedia page_id (for author photos)
 *   - emit a lean, position-free model (layout.mjs adds x/y/r)
 *   - preserve the exact dedup / link-aggregation behavior.
 */

// Known duplicate-split / variant author names collapsed into a canonical name
// (datasets/data_overrides.json:name_aliases). Registered by build.mjs before
// buildGraph runs; applied in normalizeAuthor so both author nodes AND link
// endpoints merge consistently. buildGraph extends the static map per dataset
// with auto-detected diacritic twins ("Moliere"/"Molière").
let _staticAliases = null;
let _nameAliases = null;
export function setNameAliases(aliases) {
  _staticAliases = aliases || null;
  _nameAliases = _staticAliases;
}

export function normalizeAuthor(name) {
  if (!name) return "Unknown";
  let n = name.toString().trim();
  if (n.includes(",")) {
    const parts = n.split(",", 2);
    if (parts.length === 2) n = `${parts[1].trim()} ${parts[0].trim()}`;
  }
  n = n.replace(/\s+/g, " ");
  if (_nameAliases && _nameAliases[n]) return _nameAliases[n];
  return n;
}

// Diacritic/punctuation-insensitive key for twin detection.
function foldName(n) {
  return n
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/\./g, "")
    .replace(/\s+/g, " ")
    .trim();
}

// Scan all author-name candidates in the records, group diacritic twins, and
// extend the alias map so every variant resolves to one canonical form (the
// most-accented variant — accents are usually the correct spelling).
function buildDynamicAliases(records) {
  const candidates = new Set();
  const addRaw = (raw) => {
    const n = normalizeAuthor(raw);
    if (n && n !== "Unknown") candidates.add(n);
  };
  for (const rec of records) {
    const src = rec.source || {};
    addRaw(Array.isArray(src.authors) ? src.authors[0] : src.authors);
    for (const cit of rec.citations || []) {
      const match = cit.goodreads_match || {};
      const wiki = cit.wikipedia_match || {};
      if (cit.edge?.target_book_id) {
        addRaw(match.authors && match.authors.length ? match.authors[0] : null);
      } else if (cit.edge?.target_author_ids) {
        addRaw(wiki.title || (match.authors && match.authors.length ? match.authors[0] : match.name));
      }
    }
  }
  const byFold = new Map();
  for (const n of candidates) {
    const k = foldName(n);
    if (!byFold.has(k)) byFold.set(k, []);
    byFold.get(k).push(n);
  }
  const aliases = { ...(_staticAliases || {}) };
  const accents = (s) => [...s].filter((ch) => ch.charCodeAt(0) > 127).length;
  for (const variants of byFold.values()) {
    if (variants.length < 2) continue;
    variants.sort((a, b) => accents(b) - accents(a) || b.length - a.length || a.localeCompare(b));
    const canonical = variants[0];
    for (let i = 1; i < variants.length; i++) aliases[variants[i]] = canonical;
  }
  // Flatten alias chains (static A->B where B is itself a folded variant).
  for (const [k, v] of Object.entries(aliases)) {
    let target = v;
    let hops = 0;
    while (aliases[target] && hops++ < 5) target = aliases[target];
    aliases[k] = target;
  }
  _nameAliases = aliases;
}

function normalizeTitle(title) {
  if (!title) return "";
  return title
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/^(the|a|an|la|le|les|el|los|las|der|die|das)\s+/i, "")
    .replace(/[''`ʼ]/g, "'")
    .replace(/[""«»]/g, '"')
    .replace(/\s+/g, " ")
    .trim();
}

function getBookYear(meta) {
  if (meta.original_year !== undefined && meta.original_year !== null) return meta.original_year;
  if (meta.publication_year !== undefined && meta.publication_year !== null) return meta.publication_year;
  return null;
}

function leanBook(id, title, year, isSource, meta, commentaries) {
  return {
    id,
    title: title || "Unknown",
    year: year ?? null,
    is_source: !!isSource,
    rating: meta.average_rating ?? null,
    pages: meta.num_pages ?? null,
    link: meta.link ?? null,
    work_id: meta.work_id ?? null,
    description: meta.description ?? null,
    commentaries: commentaries || [],
  };
}

/**
 * @param {Array} records - stage-3 JSON objects ({source, citations})
 * @returns {{authors: Array, links: Array}}
 */
export function buildGraph(records) {
  buildDynamicAliases(records); // merge diacritic-twin author names
  const authorMap = new Map();
  const authorRefRe = /\b(The|the) author\b/g;

  function ensureAuthor(name) {
    if (!authorMap.has(name)) {
      authorMap.set(name, {
        name,
        books: [],
        isSource: false,
        meta: {},
        pageId: null,
        commentaries: [],
      });
    }
    return authorMap.get(name);
  }

  records.forEach((rec) => {
    const src = rec.source || {};
    const srcAuth = normalizeAuthor(Array.isArray(src.authors) ? src.authors[0] : src.authors);
    const srcYear = getBookYear(src);

    const srcAuthorNode = ensureAuthor(srcAuth);
    srcAuthorNode.isSource = true;
    if (src.author_metadata && Object.keys(src.author_metadata).length) {
      srcAuthorNode.meta = { ...srcAuthorNode.meta, ...src.author_metadata };
    }

    const srcBook = leanBook(
      `book:${src.goodreads_id ?? src.book_id}`,
      src.title,
      srcYear,
      true,
      src,
      []
    );
    srcAuthorNode.books.push(srcBook);

    (rec.citations || []).forEach((cit) => {
      const match = cit.goodreads_match || {};
      const wiki = cit.wikipedia_match || {};
      const person = (cit.edge && cit.edge.target_person) || wiki;
      const authorMeta = match.author_meta || {};
      const wikiAuthorMeta =
        wiki && (wiki.birth_year || wiki.death_year)
          ? { birth_year: wiki.birth_year, death_year: wiki.death_year, canonical_name: wiki.title }
          : {};

      const applyAuthorMeta = (node) => {
        if (authorMeta.birth_year || authorMeta.death_year) {
          node.meta = { ...node.meta, ...authorMeta };
        } else if (Object.keys(wikiAuthorMeta).length) {
          node.meta = { ...node.meta, ...wikiAuthorMeta };
        }
        if (person && person.categories) node.meta.categories = person.categories;
        if (person && person.infoboxes) node.meta.infoboxes = person.infoboxes;
        if (authorMeta.nationality) node.meta.nationality = authorMeta.nationality;
        if (authorMeta.main_genre) node.meta.main_genre = authorMeta.main_genre;
        const pid = (person && person.page_id) || wiki.page_id;
        if (pid && !node.pageId) node.pageId = pid;
      };

      if (cit.edge && cit.edge.target_book_id) {
        const citedAuth = normalizeAuthor(
          match.authors && match.authors.length ? match.authors[0] : "Unknown"
        );
        const node = ensureAuthor(citedAuth);
        applyAuthorMeta(node);

        const citedBook = leanBook(
          `book:${cit.edge.target_book_id}`,
          match.title,
          getBookYear(match),
          false,
          match,
          (cit.raw?.commentaries || []).map((c) => c.replace(authorRefRe, srcAuth))
        );
        const existing = node.books.find((b) => b.id === citedBook.id);
        if (existing) {
          if (citedBook.commentaries.length) {
            existing.commentaries.push(...citedBook.commentaries);
          }
        } else {
          node.books.push(citedBook);
        }
      } else if (cit.edge && cit.edge.target_author_ids) {
        const name = normalizeAuthor(
          wiki.title || (match.authors && match.authors.length ? match.authors[0] : match.name) || "Unknown"
        );
        // Unresolved citations (not_found: no wiki/goodreads identity) would
        // all aggregate into a meaningless "Unknown" node — skip them.
        if (name === "Unknown") return;
        const node = ensureAuthor(name);
        applyAuthorMeta(node);
        if (cit.raw?.commentaries) {
          node.commentaries.push(...cit.raw.commentaries.map((c) => c.replace(authorRefRe, srcAuth)));
        }
      }
    });
  });

  // Dedup books within each author by work_id (definitive) with title fallback.
  // bookIdRemap records dropped-duplicate id -> kept id so per-citation
  // target_book references (built below) still resolve after dedup.
  const bookIdRemap = new Map();
  for (const node of authorMap.values()) {
    if (node.books.length <= 1) continue;
    const groups = new Map();
    for (const book of node.books) {
      const key = book.work_id ? `work:${book.work_id}` : `title:${normalizeTitle(book.title)}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(book);
    }
    const deduped = [];
    for (const group of groups.values()) {
      if (group.length === 1) {
        deduped.push(group[0]);
        continue;
      }
      // Keep the richest (most fields), merge commentaries.
      group.sort((a, b) => scoreBook(b) - scoreBook(a));
      const best = group[0];
      for (let i = 1; i < group.length; i++) {
        if (group[i].commentaries.length) best.commentaries.push(...group[i].commentaries);
        best.is_source = best.is_source || group[i].is_source;
        bookIdRemap.set(group[i].id, best.id);
      }
      deduped.push(best);
    }
    node.books = deduped;
  }

  // Finalize author nodes (year from birth_year or book years; dedup commentaries).
  const authors = [];
  for (const node of authorMap.values()) {
    const m = node.meta || {};
    let year = null;
    if (m.birth_year) {
      year = m.birth_year;
    } else {
      const ys = node.books.map((b) => b.year).filter((y) => y !== null && !isNaN(y));
      if (ys.length) {
        ys.sort((a, b) => a - b);
        year = ys[Math.floor(ys.length / 2)]; // median book year
      }
    }
    authors.push({
      id: `author:${node.name}`,
      name: node.name,
      is_source: node.isSource,
      birth_year: m.birth_year ?? null,
      death_year: m.death_year ?? null,
      year, // may be null -> filled by layout (neighbor / dataset median)
      nationality: m.nationality ?? null,
      main_genre: m.main_genre ?? null,
      page_id: node.pageId ?? null,
      categories: m.categories ?? null,
      description: m.description ?? null,
      books: node.books.map((b) => ({ ...b, commentaries: [...new Set(b.commentaries)] })),
      commentaries: [...new Set(node.commentaries)],
    });
  }

  // Build author -> author links, tracking source books + citation counts.
  const nodeByName = new Map(authors.map((a) => [a.name, a]));
  const linkMap = new Map();
  records.forEach((rec) => {
    const src = rec.source || {};
    const srcName = normalizeAuthor(Array.isArray(src.authors) ? src.authors[0] : src.authors);
    const srcNode = nodeByName.get(srcName);
    if (!srcNode) return;
    // Remap through book dedup: if this source book merged into an existing
    // node (e.g. it was already in the graph as a cited work), reference the
    // surviving id — otherwise source_book_ids / citation sb dangle.
    let srcBookId = `book:${src.goodreads_id ?? src.book_id}`;
    if (bookIdRemap.has(srcBookId)) srcBookId = bookIdRemap.get(srcBookId);

    (rec.citations || []).forEach((cit) => {
      const match = cit.goodreads_match || {};
      const wiki = cit.wikipedia_match || {};
      let targetName = null;
      if (cit.edge && cit.edge.target_book_id) {
        targetName = normalizeAuthor(match.authors && match.authors.length ? match.authors[0] : "Unknown");
      } else if (cit.edge && cit.edge.target_author_ids) {
        targetName = normalizeAuthor(
          wiki.title || (match.authors && match.authors.length ? match.authors[0] : match.name) || "Unknown"
        );
      }
      if (!targetName) return;
      const targetNode = nodeByName.get(targetName);
      if (!targetNode || targetNode === srcNode) return;
      const key = `${srcName}|${targetName}`;
      if (!linkMap.has(key)) {
        linkMap.set(key, { source: srcNode.id, target: targetNode.id, source_book_ids: new Set(), count: 0, citations: [] });
      }
      const l = linkMap.get(key);
      l.source_book_ids.add(srcBookId);
      l.count += cit.raw?.count || 1;

      // Per-citation provenance: which source book cited which target work,
      // with the verbatim passages (contexts) and LLM commentary. Shipped via
      // details.json and rendered as grouped "cited by X in Y" sections.
      let targetBookId = cit.edge?.target_book_id ? `book:${cit.edge.target_book_id}` : null;
      if (targetBookId && bookIdRemap.has(targetBookId)) targetBookId = bookIdRemap.get(targetBookId);
      const contexts = [...new Set(cit.raw?.contexts || [])];
      const commentaries = [...new Set((cit.raw?.commentaries || []).map((c) => c.replace(authorRefRe, srcName)))];
      if (contexts.length || commentaries.length || targetBookId) {
        l.citations.push({
          sb: srcBookId,
          tb: targetBookId,
          t: cit.raw?.title || null,
          n: cit.raw?.count || 1,
          q: contexts,
          c: commentaries,
        });
      }
    });
  });

  const links = Array.from(linkMap.values()).map((l) => ({
    source: l.source,
    target: l.target,
    count: l.count,
    source_book_ids: [...l.source_book_ids],
    citations: l.citations,
  }));

  return { authors, links };
}

function scoreBook(b) {
  let s = 0;
  if (b.year !== null) s += 2;
  if (b.rating !== null) s += 1;
  if (b.pages !== null) s += 1;
  if (b.link) s += 1;
  if (b.description) s += 1;
  return s;
}

/**
 * Apply durable manual corrections (datasets/data_overrides.json) to the built
 * author list, in-place. Fixes author birth/death years (which drive Y-axis
 * placement) and per-book titles/years. Name merges are handled upstream by
 * setNameAliases(); this only patches dates/titles on already-merged nodes.
 *
 * Shape:
 *   { author_dates: { "<name>": {birth_year, death_year} },
 *     books:        { "<name>": [ {match, year?, title?} ] } }
 *
 * @returns {{datesApplied:number, booksApplied:number, missed:string[]}}
 */
export function applyDataOverrides(authors, overrides) {
  const stats = { datesApplied: 0, booksApplied: 0, missed: [] };
  if (!overrides) return stats;
  const byName = new Map(authors.map((a) => [a.name, a]));
  const ad = overrides.author_dates || {};
  for (const [name, dates] of Object.entries(ad)) {
    const a = byName.get(name);
    if (!a) {
      stats.missed.push(`dates:${name}`);
      continue;
    }
    if ("birth_year" in dates) a.birth_year = dates.birth_year;
    if ("death_year" in dates) a.death_year = dates.death_year;
    // year drives Y placement; prefer corrected birth_year when present.
    if (a.birth_year != null) a.year = a.birth_year;
    stats.datesApplied++;
  }
  const bk = overrides.books || {};
  for (const [name, edits] of Object.entries(bk)) {
    const a = byName.get(name);
    if (!a) {
      stats.missed.push(`books:${name}`);
      continue;
    }
    for (const edit of edits) {
      // Apply to every book with this title (handles duplicate-edition rows
      // that escaped work_id dedup, e.g. two "Adelphoe" entries).
      const targets = a.books.filter((b) => b.title === edit.match);
      if (!targets.length) {
        stats.missed.push(`book:${name}:${edit.match}`);
        continue;
      }
      for (const target of targets) {
        if ("year" in edit) target.year = edit.year;
        if ("title" in edit) target.title = edit.title;
      }
      stats.booksApplied++;
    }
  }
  return stats;
}
