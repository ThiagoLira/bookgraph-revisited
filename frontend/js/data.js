/**
 * data.js — Data loading and processing for BookGraph.
 * Extracts citation graph structure from pipeline JSON output.
 */

import d3 from './d3-imports.js';

export function slugifyTitle(title) {
  return title.toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

export function parseYear(dateStr) {
  if (!dateStr) return null;
  if (typeof dateStr === 'number') return dateStr;
  if (dateStr.toString().includes("BC")) return -parseInt(dateStr.replace(/\D/g, ''));
  const d = new Date(dateStr);
  return !isNaN(d.getFullYear()) ? d.getFullYear() : null;
}

export function getBookYear(meta) {
  if (meta.original_year !== undefined && meta.original_year !== null) return meta.original_year;
  if (meta.publication_year) return meta.publication_year;
  return null;
}

export function normalizeAuthor(name) {
  if (!name) return "Unknown";
  let n = name.toString().trim();
  if (n.includes(",")) {
    const parts = n.split(",", 2);
    if (parts.length === 2) n = `${parts[1].trim()} ${parts[0].trim()}`;
  }
  return n.replace(/\s+/g, " ");
}

function normalizeTitle(title) {
  if (!title) return '';
  return title.toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')  // strip diacritics
    .replace(/^(the|a|an|la|le|les|el|los|las|der|die|das)\s+/i, '')
    .replace(/[''`ʼ]/g, "'")
    .replace(/[""«»]/g, '"')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Process raw pipeline JSON records into graph data.
 * @param {Array} records - Array of pipeline output JSON objects
 * @returns {{ authors: Array, links: Array, sourceBookMap: Map }}
 */
export function processData(records) {
  const authorMap = new Map();
  const bookMap = new Map();

  records.forEach(rec => {
    const src = rec.source;
    const srcAuth = normalizeAuthor(Array.isArray(src.authors) ? src.authors[0] : src.authors);
    const srcYear = getBookYear(src);

    if (!authorMap.has(srcAuth)) authorMap.set(srcAuth, {
      name: srcAuth, books: [], isSource: true, meta: {},
      commentaries: []
    });
    const srcAuthorNode = authorMap.get(srcAuth);
    srcAuthorNode.isSource = true;

    if (src.author_meta) srcAuthorNode.meta = src.author_meta;

    const srcBook = {
      id: `book:${src.goodreads_id}`,
      title: src.title,
      year: srcYear,
      isSource: true,
      meta: src,
      commentaries: []
    };
    srcAuthorNode.books.push(srcBook);
    bookMap.set(srcBook.id, srcBook);

    const authorRefRe = /\b(The|the) author\b/g;

    (rec.citations || []).forEach(cit => {
      const match = cit.goodreads_match || {};
      const wiki = cit.wikipedia_match || {};

      const authorMeta = match.author_meta || {};
      const wikiAuthorMeta = (wiki && (wiki.birth_year || wiki.death_year)) ? {
        birth_year: wiki.birth_year,
        death_year: wiki.death_year,
        canonical_name: wiki.title
      } : {};

      if (cit.edge && cit.edge.target_book_id) {
        const citedAuth = normalizeAuthor(match.authors && match.authors.length > 0 ? match.authors[0] : "Unknown");
        const citedYear = getBookYear(match);

        if (!authorMap.has(citedAuth)) authorMap.set(citedAuth, { name: citedAuth, books: [], meta: {}, commentaries: [] });
        const citedAuthorNode = authorMap.get(citedAuth);

        if (Object.keys(authorMeta).length > 0 && (authorMeta.birth_year || authorMeta.death_year)) citedAuthorNode.meta = authorMeta;
        else if (Object.keys(wikiAuthorMeta).length > 0) citedAuthorNode.meta = wikiAuthorMeta;

        // Preserve wiki enrichment fields (infoboxes, categories, nationality, genre)
        const person1 = (cit.edge && cit.edge.target_person) || wiki;
        if (person1.infoboxes) citedAuthorNode.meta.infoboxes = person1.infoboxes;
        if (person1.categories) citedAuthorNode.meta.categories = person1.categories;
        if (authorMeta.nationality) citedAuthorNode.meta.nationality = authorMeta.nationality;
        if (authorMeta.main_genre) citedAuthorNode.meta.main_genre = authorMeta.main_genre;

        const citedBook = {
          id: `book:${cit.edge.target_book_id}`,
          title: match.title || "Unknown",
          year: citedYear,
          isSource: false,
          meta: match,
          commentaries: (cit.raw.commentaries || []).map(c => c.replace(authorRefRe, srcAuth))
        };

        const existingBook = citedAuthorNode.books.find(b => b.id === citedBook.id);
        if (existingBook) {
          // Merge commentaries into existing book (handles source books cited by other sources)
          if (citedBook.commentaries && citedBook.commentaries.length) {
            if (!existingBook.commentaries) existingBook.commentaries = [];
            existingBook.commentaries.push(...citedBook.commentaries);
          }
        } else {
          citedAuthorNode.books.push(citedBook);
          bookMap.set(citedBook.id, citedBook);
        }
      }
      else if (cit.edge && cit.edge.target_author_ids) {
        const name = wiki.title || (match.authors && match.authors.length > 0 ? match.authors[0] : match.name) || "Unknown";
        const normName = normalizeAuthor(name);
        if (!authorMap.has(normName)) authorMap.set(normName, { name: normName, books: [], meta: {}, commentaries: [] });

        const authNode = authorMap.get(normName);
        if (Object.keys(authorMeta).length > 0) authNode.meta = authorMeta;
        else if (Object.keys(wikiAuthorMeta).length > 0) authNode.meta = wikiAuthorMeta;

        // Preserve wiki enrichment fields (infoboxes, categories, nationality, genre)
        const person2 = (cit.edge && cit.edge.target_person) || wiki;
        if (person2.infoboxes) authNode.meta.infoboxes = person2.infoboxes;
        if (person2.categories) authNode.meta.categories = person2.categories;
        if (authorMeta.nationality) authNode.meta.nationality = authorMeta.nationality;
        if (authorMeta.main_genre) authNode.meta.main_genre = authorMeta.main_genre;

        if (cit.raw.commentaries) {
          if (!authNode.commentaries) authNode.commentaries = [];
          authNode.commentaries.push(...cit.raw.commentaries.map(c => c.replace(authorRefRe, srcAuth)));
        }
      }
    });
  });

  // Dedup books within each author by normalized title (merges different editions)
  for (const [, authNode] of authorMap) {
    if (authNode.books.length <= 1) continue;
    const titleGroups = new Map();
    for (const book of authNode.books) {
      const key = normalizeTitle(book.title);
      if (!titleGroups.has(key)) titleGroups.set(key, []);
      titleGroups.get(key).push(book);
    }
    const deduped = [];
    for (const [, group] of titleGroups) {
      if (group.length === 1) { deduped.push(group[0]); continue; }
      // Keep the book with richest metadata
      group.sort((a, b) => Object.keys(b.meta || {}).length - Object.keys(a.meta || {}).length);
      const best = group[0];
      for (let i = 1; i < group.length; i++) {
        // Merge commentaries
        if (group[i].commentaries && group[i].commentaries.length) {
          if (!best.commentaries) best.commentaries = [];
          best.commentaries.push(...group[i].commentaries);
        }
        // Redirect old ID in bookMap
        bookMap.set(group[i].id, best);
      }
      deduped.push(best);
    }
    authNode.books = deduped;
  }

  const authors = Array.from(authorMap.values()).map(auth => {
    let year = null;
    const meta = auth.meta || {};

    if (meta.birth_year) {
      const endYear = meta.death_year || (meta.birth_year + 60);
      year = (meta.birth_year + endYear) / 2;
    }

    if (year === null) {
      const validBookYears = auth.books.map(b => b.year).filter(y => y !== null);
      if (validBookYears.length > 0) {
        year = validBookYears.reduce((a, b) => a + b, 0) / validBookYears.length;
      }
    }

    // Pack book circles within author enclosure
    const circles = (auth.books || []).map(b => ({
      r: b.isSource ? 12 : 6,
      x: 0, y: 0,
      data: b
    }));
    d3.packSiblings(circles);

    const enclosure = d3.packEnclose(circles);
    const r = enclosure ? enclosure.r + 5 : (auth.isSource ? 10 : 5);

    return {
      commentaries: [...new Set(auth.commentaries || [])],
      id: `author:${auth.name}`,
      name: auth.name,
      year,
      r,
      books: circles,
      x: 0,
      y: 0,
      isSource: auth.isSource || false,
      meta: auth.meta || {}
    };
  });

  // Default year for source authors with no year data
  authors.forEach(a => {
    if (a.year === null && a.isSource) {
      a.year = 2000;
    }
  });

  // Build sourceBookMap
  const sourceBookMap = new Map();
  authors.forEach(a => {
    (a.books || []).forEach(b => {
      if (b.data && b.data.isSource && b.data.title) {
        const slug = slugifyTitle(b.data.title);
        sourceBookMap.set(slug, { authorNode: a, bookData: b.data, bookCircle: b });
      }
    });
  });

  // Build links (author → author edges, tracking which source books produced each)
  const authorNodeMap = new Map(authors.map(a => [a.name, a]));
  const linkMap = new Map();

  records.forEach(rec => {
    const src = rec.source;
    const srcName = normalizeAuthor(Array.isArray(src.authors) ? src.authors[0] : src.authors);
    const srcNode = authorNodeMap.get(srcName);
    if (!srcNode) return;
    const srcBookId = `book:${src.goodreads_id}`;

    (rec.citations || []).forEach(cit => {
      let targetName = null;
      const match = cit.goodreads_match || {};
      const wiki = cit.wikipedia_match || {};

      if (cit.edge && cit.edge.target_book_id) {
        targetName = normalizeAuthor(match.authors && match.authors.length > 0 ? match.authors[0] : "Unknown");
      } else if (cit.edge && cit.edge.target_author_ids) {
        targetName = normalizeAuthor(wiki.title || (match.authors && match.authors.length > 0 ? match.authors[0] : match.name) || "Unknown");
      }

      if (targetName) {
        const targetNode = authorNodeMap.get(targetName);
        if (targetNode && targetNode !== srcNode) {
          const key = `${srcName}|${targetName}`;
          if (!linkMap.has(key)) {
            linkMap.set(key, { source: srcNode, target: targetNode, sourceBookIds: new Set() });
          }
          linkMap.get(key).sourceBookIds.add(srcBookId);
        }
      }
    });
  });

  const links = Array.from(linkMap.values());

  // Estimate years for cited authors with missing metadata
  authors.forEach(a => {
    if (a.year === null) {
      const connectedSources = links
        .filter(l => l.source === a || l.target === a)
        .map(l => l.source === a ? l.target : l.source)
        .filter(n => n.year);
      if (connectedSources.length > 0) {
        const avgYear = connectedSources.reduce((s, n) => s + n.year, 0) / connectedSources.length;
        a.year = Math.round(avgYear - 40);
      }
    }
  });

  return { authors, links, sourceBookMap };
}

/**
 * Load a dataset from a directory path.
 * @param {string} dataDir - Path to dataset directory (e.g. "data/philosophy_stress_test")
 * @returns {Promise<{records: Array, covers: Array|null}>}
 */
export async function loadDatasetRecords(dataDir) {
  const manifest = await fetch(`${dataDir}/manifest.json`).then(r => r.json());

  const files = [];
  const batchSize = 3;

  for (let i = 0; i < manifest.length; i += batchSize) {
    const batch = manifest.slice(i, i + batchSize);
    const results = await Promise.all(batch.map(f => fetch(`${dataDir}/${f}`).then(r => r.json())));
    files.push(...results);
  }

  return files;
}

/**
 * Load datasets.json index.
 * @returns {Promise<Array<{path: string, name: string, covers?: string[]}>>}
 */
export async function loadDatasetIndex() {
  return fetch("datasets.json").then(r => r.json());
}
