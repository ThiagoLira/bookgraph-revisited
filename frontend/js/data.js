/**
 * data.js — Load pre-baked datasets. All positions/colors/photos are computed
 * offline by frontend/build/build.mjs; this module just fetches and wires refs.
 */

export async function loadDatasetIndex() {
  const list = await fetch("datasets.json").then((r) => r.json());
  // Only datasets that have been baked are usable by this frontend.
  return list.filter((d) => d.baked);
}

/**
 * @param {string} path - e.g. "./data/philosophy_stress_test"
 * @returns {Promise<Graph>}
 */
export async function loadBaked(path) {
  const baked = await fetch(`${path}/baked.json`).then((r) => r.json());
  const { meta, authors, links } = baked;

  const authorById = new Map(authors.map((a) => [a.id, a]));

  // Adjacency for citation navigation + focus highlighting.
  for (const a of authors) {
    a.out = []; // authors this one cites
    a.in = []; // authors that cite this one
    a._labelLower = a.name.toLowerCase();
  }
  const resolved = [];
  for (const l of links) {
    const s = authorById.get(l.source);
    const t = authorById.get(l.target);
    if (!s || !t) continue;
    const link = { source: s, target: t, count: l.count, source_book_ids: l.source_book_ids };
    s.out.push(link);
    t.in.push(link);
    resolved.push(link);
  }

  // Sort adjacency by year for readable lists.
  for (const a of authors) {
    a.out.sort((x, y) => (x.target.year ?? 0) - (y.target.year ?? 0));
    a.in.sort((x, y) => (x.source.year ?? 0) - (y.source.year ?? 0));
  }

  // Searchable index (authors + books).
  const searchIndex = [];
  const bookById = new Map();
  for (const a of authors) {
    searchIndex.push({ type: "author", node: a, text: a._labelLower });
    for (const b of a.books) {
      bookById.set(b.id, b);
      searchIndex.push({ type: "book", node: a, book: b, text: b.title.toLowerCase() });
    }
  }

  // Lazy-load heavy detail text (descriptions + commentaries) in the background
  // so the initial graph render isn't blocked by it.
  const detailsReady = fetch(`${path}/details.json`)
    .then((r) => (r.ok ? r.json() : { authors: {}, books: {} }))
    .then((det) => {
      for (const [id, d] of Object.entries(det.authors || {})) {
        const a = authorById.get(id);
        if (a) { a.description = d.description; a.commentaries = d.commentaries || []; }
      }
      for (const [id, d] of Object.entries(det.books || {})) {
        const b = bookById.get(id);
        if (b) { b.description = d.description; b.commentaries = d.commentaries || []; }
      }
      return true;
    })
    .catch(() => false);

  return { meta, authors, links: resolved, authorById, searchIndex, detailsReady };
}

/** Cited works for an author = non-source books on the authors it links out to. */
export function citedWorks(author) {
  const seen = new Set();
  const works = [];
  for (const link of author.out) {
    for (const b of link.target.books) {
      if (b.is_source) continue;
      if (seen.has(b.id)) continue;
      seen.add(b.id);
      works.push({ book: b, author: link.target });
    }
  }
  works.sort((a, b) => (a.book.year ?? 0) - (b.book.year ?? 0));
  return works;
}
