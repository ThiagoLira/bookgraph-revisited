#!/usr/bin/env node
/**
 * build.mjs — Offline bake CLI.
 *
 *   node build.mjs --dataset <slug>     # bake one dataset
 *   node build.mjs --all                # bake every dataset + a merged "_all"
 *   flags: --skip-images, --rebuild-images
 *
 * For each frontend/data/<slug>/ it reads the stage-3 JSON (via manifest.json),
 * builds the citation graph, resolves nationality regions, attaches Wikipedia
 * portrait URLs, computes a fixed layout, and writes a baked.json sidecar.
 * Source JSON is never mutated — reruns are idempotent.
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync, readdirSync } from "node:fs";
import { join, dirname, basename } from "node:path";
import { fileURLToPath } from "node:url";

import { buildGraph } from "./graph_model.mjs";
import { bakeLayout } from "./layout.mjs";
import { loadRegionMap, loadAuthorsMeta, resolveRegion } from "./nationality.mjs";
import { ImageCache, ensureImages } from "./images.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, "..", "..");
const FRONTEND = join(REPO_ROOT, "frontend");
const DATA_DIR = join(FRONTEND, "data");
const DATASETS_JSON = join(FRONTEND, "datasets.json");

function parseArgs(argv) {
  const args = { dataset: null, all: false, skipImages: false, rebuildImages: false };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--all") args.all = true;
    else if (a === "--dataset") args.dataset = argv[++i];
    else if (a === "--skip-images") args.skipImages = true;
    else if (a === "--rebuild-images") args.rebuildImages = true;
  }
  return args;
}

function loadDatasetIndex() {
  return JSON.parse(readFileSync(DATASETS_JSON, "utf8"));
}

function slugFromPath(p) {
  return basename(p.replace(/\/+$/, ""));
}

// Read a dataset's stage-3 records (skips baked.json / manifest).
function loadRecords(slug) {
  const dir = join(DATA_DIR, slug);
  if (!existsSync(dir)) return null;
  let files;
  const manifestPath = join(dir, "manifest.json");
  if (existsSync(manifestPath)) {
    files = JSON.parse(readFileSync(manifestPath, "utf8"));
  } else {
    files = readdirSync(dir).filter((f) => f.endsWith(".json"));
  }
  files = files.filter((f) => !["baked.json", "manifest.json", "datasets.json"].includes(f));
  const records = [];
  for (const f of files) {
    try {
      const rec = JSON.parse(readFileSync(join(dir, f), "utf8"));
      if (rec && rec.source) records.push(rec);
    } catch (e) {
      console.warn(`  ! skipping ${f}: ${e.message}`);
    }
  }
  return records;
}

async function bakeRecords(records, slug, ctx) {
  const { regionMap, metaIndex, imageCache, skipImages, rebuildImages } = ctx;
  const { authors, links } = buildGraph(records);

  // Nationality -> region -> color.
  let withRegion = 0;
  for (const a of authors) {
    const { nationality, region, color } = resolveRegion(
      a.name,
      a.birth_year,
      a.categories,
      regionMap,
      metaIndex
    );
    a.nationality = nationality;
    a.region = region;
    a.color = color;
    if (region !== "unknown") withRegion++;
    delete a.categories; // large, not needed at runtime
  }

  // Author portraits.
  if (!skipImages) {
    const pageIds = authors.map((a) => a.page_id).filter(Boolean);
    await ensureImages(pageIds, imageCache, { rebuild: rebuildImages, log: (m) => console.log(m) });
  }
  let withImage = 0;
  for (const a of authors) {
    a.image_url = a.page_id && !skipImages ? imageCache.get(a.page_id) : null;
    if (a.image_url) withImage++;
  }

  // Fixed layout (mutates authors: x,y,r + book x,y,r).
  const { meta } = bakeLayout(authors, links);
  meta.regions = regionMap.regions;
  meta.dataset = slug;

  const pct = authors.length ? Math.round((withRegion / authors.length) * 100) : 0;
  console.log(
    `  ${slug}: ${authors.length} authors (${pct}% region, ${withImage} photos), ${links.length} links, world ${meta.worldWidth}x${meta.worldHeight}`
  );
  return { meta, authors, links };
}

// Split heavy detail text (descriptions + commentaries) out of the render
// payload so the initial graph download stays small; details lazy-load.
function splitDetails(baked) {
  const details = { authors: {}, books: {} };
  for (const a of baked.authors) {
    if ((a.description && a.description.length) || (a.commentaries && a.commentaries.length)) {
      details.authors[a.id] = { description: a.description || null, commentaries: a.commentaries || [] };
    }
    delete a.description;
    delete a.commentaries;
    for (const b of a.books) {
      if ((b.description && b.description.length) || (b.commentaries && b.commentaries.length)) {
        details.books[b.id] = { description: b.description || null, commentaries: b.commentaries || [] };
      }
      delete b.description;
      delete b.commentaries;
    }
  }
  return details;
}

function writeBaked(slug, baked) {
  const dir = join(DATA_DIR, slug);
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  const details = splitDetails(baked); // mutates baked -> lean
  writeFileSync(join(dir, "baked.json"), JSON.stringify(baked));
  writeFileSync(join(dir, "details.json"), JSON.stringify(details));
}

function markBakedInIndex(index, slug, name) {
  const relPath = `./data/${slug}`;
  let entry = index.find((d) => slugFromPath(d.path) === slug);
  if (!entry) {
    entry = { name: name || slug, path: relPath };
    index.push(entry);
  }
  entry.baked = true;
  return index;
}

async function main() {
  const args = parseArgs(process.argv);
  const ctx = {
    regionMap: loadRegionMap(REPO_ROOT),
    metaIndex: loadAuthorsMeta(REPO_ROOT),
    imageCache: new ImageCache(REPO_ROOT),
    skipImages: args.skipImages,
    rebuildImages: args.rebuildImages,
  };

  let index = loadDatasetIndex();
  const allEntries = index.filter((d) => slugFromPath(d.path) !== "_all");

  let targets;
  if (args.dataset) {
    targets = [{ slug: args.dataset, name: args.dataset }];
  } else if (args.all) {
    targets = allEntries.map((d) => ({ slug: slugFromPath(d.path), name: d.name }));
  } else {
    console.error("Usage: node build.mjs (--dataset <slug> | --all) [--skip-images] [--rebuild-images]");
    process.exit(1);
  }

  console.log(`Baking ${targets.length} dataset(s)...`);
  const allRecords = [];
  for (const t of targets) {
    const records = loadRecords(t.slug);
    if (!records || !records.length) {
      console.warn(`  ! ${t.slug}: no records, skipping`);
      continue;
    }
    if (args.all) allRecords.push(...records);
    const baked = await bakeRecords(records, t.slug, ctx);
    writeBaked(t.slug, baked);
    index = markBakedInIndex(index, t.slug, t.name);
  }

  // Merged "All Libraries" view.
  if (args.all && allRecords.length) {
    console.log(`Baking merged _all (${allRecords.length} records)...`);
    const baked = await bakeRecords(allRecords, "_all", ctx);
    writeBaked("_all", baked);
    if (!index.find((d) => slugFromPath(d.path) === "_all")) {
      index.unshift({ name: "All Libraries", path: "./data/_all", baked: true });
    } else {
      index.find((d) => slugFromPath(d.path) === "_all").baked = true;
    }
  }

  ctx.imageCache.save();
  writeFileSync(DATASETS_JSON, JSON.stringify(index, null, 4));
  console.log("Done.");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
