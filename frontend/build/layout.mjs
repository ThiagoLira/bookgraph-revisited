/**
 * layout.mjs — Pre-bake fixed node positions.
 *   Y = time (piecewise-linear date scale, generous spacing).
 *   X = pure spacing: an offline force relaxation (Y pinned) run to
 *       convergence, then frozen. No runtime physics.
 *   Inner books packed via d3 circle packing.
 */

import * as d3 from "d3";

const SOURCE_BOOK_R = 12;
const CITED_BOOK_R = 6;
const ENCLOSE_PAD = 5;
const LONE_AUTHOR_R = 8;

// ---- inner-book packing -----------------------------------------------------
export function packBooks(author) {
  const books = author.books || [];
  if (!books.length) {
    author.r = LONE_AUTHOR_R;
    return;
  }
  const circles = books.map((b) => ({ r: b.is_source ? SOURCE_BOOK_R : CITED_BOOK_R, b }));
  d3.packSiblings(circles);
  const enc = d3.packEnclose(circles);
  author.r = enc ? enc.r + ENCLOSE_PAD : (author.is_source ? 10 : LONE_AUTHOR_R);
  for (const c of circles) {
    c.b.x = +c.x.toFixed(2);
    c.b.y = +c.y.toFixed(2);
    c.b.r = c.r;
  }
}

// ---- deterministic RNG ------------------------------------------------------
function hashStr(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}
function mulberry32(a) {
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---- fill missing years -----------------------------------------------------
function fillYears(authors, links) {
  const byId = new Map(authors.map((a) => [a.id, a]));
  const known = authors.map((a) => a.year).filter((y) => y !== null && !isNaN(y));
  known.sort((a, b) => a - b);
  const median = known.length ? known[Math.floor(known.length / 2)] : 1900;

  // adjacency for neighbor estimation
  const neighbors = new Map();
  for (const l of links) {
    (neighbors.get(l.source) || neighbors.set(l.source, []).get(l.source)).push(l.target);
    (neighbors.get(l.target) || neighbors.set(l.target, []).get(l.target)).push(l.source);
  }
  for (const a of authors) {
    if (a.year !== null && !isNaN(a.year)) continue;
    const ns = (neighbors.get(a.id) || [])
      .map((id) => byId.get(id))
      .filter((n) => n && n.year !== null && !isNaN(n.year));
    if (ns.length) {
      const avg = ns.reduce((s, n) => s + n.year, 0) / ns.length;
      a.year = Math.round(avg - 40); // cited authors usually predate their citers
    } else {
      a.year = median;
    }
  }
  return median;
}

// ---- Y time scale -----------------------------------------------------------
function buildYScale(authors) {
  const years = authors.map((a) => a.year);
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  const split = 1800;
  const lowRes = 0.6; // px/yr before 1800
  const highRes = 10; // px/yr after 1800

  let yScale, totalHeight, tickValues;
  const topPad = 120;
  const botPad = 120;

  if (minYear < split && maxYear > split) {
    const ancientH = (split - minYear) * lowRes;
    const modernH = (maxYear - split) * highRes;
    totalHeight = ancientH + modernH + topPad + botPad;
    const yBottom = totalHeight - botPad;
    const ySplit = yBottom - ancientH;
    const yTop = ySplit - modernH;
    yScale = d3.scaleLinear().domain([minYear, split, maxYear]).range([yBottom, ySplit, yTop]);
    tickValues = [
      ...d3.range(Math.ceil(minYear / 100) * 100, split, 100),
      ...d3.range(split, maxYear + 1, 10),
    ];
  } else {
    const res = maxYear > split ? highRes : lowRes;
    totalHeight = (maxYear - minYear) * res + topPad + botPad;
    const yBottom = totalHeight - botPad;
    const yTop = topPad;
    yScale = d3.scaleLinear().domain([minYear, maxYear]).range([yBottom, yTop]);
    const step = maxYear > split ? 10 : 100;
    tickValues = d3.range(Math.ceil(minYear / step) * step, maxYear + 1, step);
  }
  return { yScale, totalHeight, tickValues, minYear, maxYear };
}

// ---- main bake --------------------------------------------------------------
export function bakeLayout(authors, links) {
  authors.forEach(packBooks);
  fillYears(authors, links);

  const { yScale, totalHeight, tickValues, minYear, maxYear } = buildYScale(authors);
  const n = authors.length;
  const worldWidth = Math.max(2400, Math.round(Math.sqrt(n) * 240));

  // Fixed Y from time; deterministic spread initial X.
  const rng = mulberry32(0xb00c);
  for (const a of authors) {
    a.fy = yScale(a.year);
    a.y = a.fy;
    const jitter = (mulberry32(hashStr(a.id))() - 0.5);
    a.x = worldWidth / 2 + jitter * worldWidth * 0.92;
  }

  // Offline relaxation. Y is hard-pinned per node via `fy` (d3 fixes any node
  // with fy set and zeroes its vy), so every force below only moves nodes in X:
  //   - link:    pull connected authors together horizontally; heavier
  //              co-citation (count) pulls tighter, hub-normalized by degree so
  //              high-degree nodes don't collapse the whole field.
  //   - collide: keep circles from overlapping (sets the floor on closeness).
  //   - x:       very weak centering so disconnected components don't drift off.
  const pad = n > 1500 ? 16 : n > 600 ? 20 : 26; // generous gaps (old desktop was 5)

  // Disposable link copy: d3.forceLink rewrites source/target from id strings to
  // node refs; the original `links` array must keep string ids for baked.json.
  const simLinks = links.map((l) => ({ source: l.source, target: l.target, count: l.count }));
  const degree = new Map();
  for (const l of simLinks) {
    degree.set(l.source, (degree.get(l.source) || 0) + 1);
    degree.set(l.target, (degree.get(l.target) || 0) + 1);
  }

  const sim = d3
    .forceSimulation(authors)
    .force("y", d3.forceY((d) => d.fy).strength(1))
    .force(
      "link",
      d3
        .forceLink(simLinks)
        .id((d) => d.id)
        .distance((l) => (l.source.r || 8) + (l.target.r || 8) + 22)
        .strength((l) => {
          const w = Math.min(l.count || 1, 8) / 8; // 0.125–1 by co-citation weight
          const k = 1 / Math.min(degree.get(l.source.id) || 1, degree.get(l.target.id) || 1);
          return 0.5 * w * k; // hub-normalized attraction
        })
    )
    .force("x", d3.forceX(worldWidth / 2).strength(0.004))
    .force("collide", d3.forceCollide((d) => d.r + pad).iterations(4))
    .stop();

  const TICKS = 800;
  for (let i = 0; i < TICKS; i++) sim.tick();

  // Normalize bounding box -> margins, derive final world size.
  const margin = 160;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const a of authors) {
    minX = Math.min(minX, a.x - a.r);
    maxX = Math.max(maxX, a.x + a.r);
    minY = Math.min(minY, a.y - a.r);
    maxY = Math.max(maxY, a.y + a.r);
  }
  const dx = margin - minX;
  for (const a of authors) {
    a.x = +(a.x + dx).toFixed(2);
    a.y = +a.y.toFixed(2);
    delete a.fy;
  }
  const finalWidth = Math.round(maxX - minX + margin * 2);
  const finalHeight = Math.round(Math.max(totalHeight, maxY - minY + margin * 2));

  const gridlines = tickValues.map((year) => ({ year, y: +yScale(year).toFixed(2) }));

  return {
    meta: {
      worldWidth: finalWidth,
      worldHeight: finalHeight,
      yearRange: [minYear, maxYear],
      gridlines,
    },
  };
}
