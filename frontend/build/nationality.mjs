/**
 * nationality.mjs — Resolve an author's nationality and color region.
 *
 * Cascade:
 *   1. Explicit nationality from datasets/authors_metadata.json (canonical).
 *   2. Demonym parsed out of the author's Wikipedia category strings.
 *   3. Unknown (neutral gray).
 *
 * The nationality string is then mapped to one of ~12 regions defined in
 * datasets/nationality_regions.json, each with a distinct legible color.
 */

import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

export function loadRegionMap(repoRoot) {
  const raw = JSON.parse(
    readFileSync(join(repoRoot, "datasets", "nationality_regions.json"), "utf8")
  );
  // Pre-build a lowercase demonym -> region lookup and a compiled regex list.
  const natToRegion = {};
  for (const [k, v] of Object.entries(raw.nationality_to_region)) {
    natToRegion[k.toLowerCase()] = v;
  }
  // Sort demonym patterns longest-first so "South African" beats "African".
  const patterns = raw.demonym_patterns
    .slice()
    .sort((a, b) => b.length - a.length)
    .map((p) => ({ word: p, re: new RegExp(`\\b${p}\\b`, "i") }));
  return { regions: raw.regions, natToRegion, patterns };
}

export function loadAuthorsMeta(repoRoot) {
  const raw = JSON.parse(
    readFileSync(join(repoRoot, "datasets", "authors_metadata.json"), "utf8")
  );
  // Case-insensitive index by author name.
  const index = new Map();
  for (const [name, meta] of Object.entries(raw)) {
    index.set(name.toLowerCase(), meta);
  }
  // Merge manual/agent-sourced nationality overrides (datasets/nationality_overrides.json:
  // { "<lowercased name>": "<demonym>" }). These win over / fill gaps in the metadata.
  const ovPath = join(repoRoot, "datasets", "nationality_overrides.json");
  if (existsSync(ovPath)) {
    const overrides = JSON.parse(readFileSync(ovPath, "utf8"));
    for (const [name, nationality] of Object.entries(overrides)) {
      if (!nationality) continue;
      const key = name.toLowerCase();
      const existing = index.get(key) || {};
      index.set(key, { ...existing, nationality });
    }
  }
  return index;
}

function nationalityFromMeta(name, metaIndex) {
  if (!name) return null;
  const m = metaIndex.get(name.toLowerCase());
  if (m && m.nationality) return String(m.nationality).trim();
  return null;
}

function nationalityFromCategories(categories, patterns) {
  if (!categories || !categories.length) return null;
  const counts = new Map();
  for (const cat of categories) {
    if (typeof cat !== "string") continue;
    // Skip pure birth/death year categories quickly.
    for (const { word, re } of patterns) {
      if (re.test(cat)) {
        counts.set(word, (counts.get(word) || 0) + 1);
        break; // longest-first: take the most specific match per category
      }
    }
  }
  if (counts.size === 0) return null;
  // Most frequent demonym wins; ties broken by longer (more specific) word.
  let best = null;
  let bestCount = 0;
  for (const [word, count] of counts) {
    if (count > bestCount || (count === bestCount && (!best || word.length > best.length))) {
      best = word;
      bestCount = count;
    }
  }
  return best;
}

/**
 * @returns {{ nationality: string|null, region: string, color: string }}
 */
export function resolveRegion(name, birthYear, categories, regionMap, metaIndex) {
  const { regions, natToRegion, patterns } = regionMap;

  let nationality = nationalityFromMeta(name, metaIndex);
  if (!nationality) nationality = nationalityFromCategories(categories, patterns);

  let region = "unknown";
  if (nationality) {
    const key = nationality.toLowerCase().trim();
    region = natToRegion[key] || regionFromTokens(key, natToRegion) || "unknown";
  }

  // Ancient/Classical override: a Greek/Roman/Latin author born before ~500 CE
  // is grouped with antiquity (already the default for those demonyms, but make
  // it explicit and also catch clearly-ancient outliers).
  if (
    region !== "ancient_classical" &&
    typeof birthYear === "number" &&
    birthYear < 0
  ) {
    region = "ancient_classical";
  }

  const color = (regions[region] || regions.unknown).color;
  return { nationality: nationality || null, region, color };
}

// Handle hyphenated/compound demonyms ("German-American", "Anglo-Irish")
// by trying each token.
function regionFromTokens(key, natToRegion) {
  const tokens = key.split(/[\s\-/]+/).filter(Boolean);
  for (const t of tokens) {
    if (natToRegion[t]) return natToRegion[t];
  }
  return null;
}
