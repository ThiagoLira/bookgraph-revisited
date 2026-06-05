/**
 * images.mjs — Pre-fetch author portrait thumbnails from the MediaWiki API.
 *
 * Keyed by Wikipedia page_id so the cache dedups across datasets and reruns
 * are cheap. Result is a thumbnail URL on upload.wikimedia.org (CORS-open for
 * <img> at runtime). Missing pageimage -> null (frontend shows a flat circle).
 */

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const API = "https://en.wikipedia.org/w/api.php";
const THUMB_SIZE = 240;
const BATCH = 50; // MediaWiki pageids limit per request
const UA =
  "BookGraph/1.0 (https://github.com/ThiagoLira/bookgraph-revisited; thlira15@gmail.com)";

export class ImageCache {
  constructor(repoRoot) {
    this.path = join(repoRoot, "datasets", "author_images.json");
    this.data = existsSync(this.path)
      ? JSON.parse(readFileSync(this.path, "utf8"))
      : {};
    this.dirty = false;
  }

  has(pageId) {
    return Object.prototype.hasOwnProperty.call(this.data, String(pageId));
  }

  get(pageId) {
    const e = this.data[String(pageId)];
    return e ? e.image_url : null;
  }

  set(pageId, imageUrl) {
    this.data[String(pageId)] = {
      image_url: imageUrl,
      fetched_at: new Date().toISOString(),
    };
    this.dirty = true;
  }

  save() {
    if (!this.dirty) return;
    writeFileSync(this.path, JSON.stringify(this.data, null, 0));
    this.dirty = false;
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function fetchBatch(pageIds, attempt = 0) {
  const url =
    `${API}?action=query&prop=pageimages&piprop=thumbnail` +
    `&pithumbsize=${THUMB_SIZE}&format=json&formatversion=2` +
    `&pageids=${pageIds.join("|")}`;
  try {
    const res = await fetch(url, { headers: { "User-Agent": UA, "Api-User-Agent": UA } });
    if (res.status === 429) {
      if (attempt >= 4) return {};
      await sleep(2000 * (attempt + 1));
      return fetchBatch(pageIds, attempt + 1);
    }
    if (!res.ok) return {};
    const json = await res.json();
    const out = {};
    for (const page of json?.query?.pages || []) {
      out[String(page.pageid)] = page.thumbnail ? page.thumbnail.source : null;
    }
    return out;
  } catch {
    if (attempt >= 4) return {};
    await sleep(1500 * (attempt + 1));
    return fetchBatch(pageIds, attempt + 1);
  }
}

/**
 * Ensure thumbnails for the given page ids are present in the cache.
 * @param {Array<number|string>} pageIds
 * @param {ImageCache} cache
 * @param {{rebuild?: boolean, log?: Function}} opts
 */
export async function ensureImages(pageIds, cache, opts = {}) {
  const log = opts.log || (() => {});
  const wanted = [
    ...new Set(
      pageIds
        .filter((id) => id !== null && id !== undefined && id !== "")
        .map((id) => String(id))
    ),
  ];
  const todo = opts.rebuild ? wanted : wanted.filter((id) => !cache.has(id));
  if (!todo.length) {
    log(`  images: ${wanted.length} authors, all cached`);
    return;
  }
  log(`  images: fetching ${todo.length} new of ${wanted.length} (cached: ${wanted.length - todo.length})`);
  let fetched = 0;
  for (let i = 0; i < todo.length; i += BATCH) {
    const slice = todo.slice(i, i + BATCH);
    const res = await fetchBatch(slice);
    for (const id of slice) cache.set(id, res[id] ?? null);
    fetched += slice.length;
    cache.save();
    if (i + BATCH < todo.length) await sleep(1000); // be polite
  }
  log(`  images: done (${fetched} fetched)`);
}
