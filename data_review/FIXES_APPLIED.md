# Frontend Data Audit — Fixes Applied (2026-06-09)

A 5-agent audit of the 546 most-cited authors (by era) surfaced 124 proposed fixes.
After validation/dedup these were applied as a **durable build-time override layer** so
they survive every re-bake. Result: cited hard-anomalies went from **~14 → 2 non-issues**.

## New durable mechanism
- **`datasets/data_overrides.json`** (new) — `name_aliases`, `author_dates`, `books`.
  - `name_aliases` applied in `frontend/build/graph_model.mjs` → `normalizeAuthor()` (via `setNameAliases`), so duplicate-split nodes **and their link endpoints** merge.
  - `author_dates` / `books` applied by new `applyDataOverrides()` after `buildGraph`, wired in `frontend/build/build.mjs` (`loadDataOverrides()` + ctx). Patches **all** books matching a title (handles duplicate-edition rows).
- **`datasets/nationality_overrides.json`** (existing) — 6 nationality fixes appended (645 → 651).
- Source stage-3 JSON is still never mutated; everything regenerates with `node build.mjs --all`.

## What was applied
- **13 author merges** (duplicate-split collapse): Goethe→Johann Wolfgang von Goethe, Wagner→Richard Wagner (also fixed bogus "Greek/1813–None"), Rene→René Descartes, Pascal→Blaise Pascal, Honore→Honoré de Balzac, Emile→Émile Zola, Soren→Søren Kierkegaard, Hawthorne→Nathaniel Hawthorne, Tennyson→Alfred Tennyson, Moses→Moses Mendelssohn, + Cervantes/Rabelais/Machiavelli accent variants. Author count 2924 → 2912.
- **20 author date fixes** — wrong-person Wikipedia matches reassigned to the correct historical figure: Juvenal (1937→55–138), Aesop (1976→−620–−564), John Webster the dramatist (1930→1580–1634), Cicero/Theocritus/Menander misplacements, Thomas More death (1505→1535), Benjamin Franklin death (1730→1790), Pseudo-Dionysius (→470–530), Moses Mendelssohn, Richard Wagner, Chomsky impossible death nulled, etc.
- **101 book field fixes** — BCE sign errors (Cicero's *Academica* 45→−45, etc.), edition/translation years swapped for originals (*Mein Kampf* 1192→1925, *Ecce Homo* 2011→1908, *The Devils* 2025→1872, dozens more), and foreign-language titles normalized to canonical English (Odyssée→Odyssey, Le Rouge et le Noir→The Red and the Black, Die Fröhliche…, etc.).

## Known remaining (not data errors — left intentionally)
- **`Anonymous`** is a single mega-node aggregating the Bible books, Quran, and assorted medieval texts under a meaningless birth of −796. This is a **structural** issue (anonymous works collapse to one node), not a field to patch — recommend splitting anonymous/sacred works into per-work nodes in a future pipeline pass.
- ***The Aesop Romance*** (yr 200) genuinely post-dates Aesop — it's a later anonymous *Life of Aesop*, correctly later than its subject.

## Provenance
- Per-era review inputs: `data_review/era_*.md`
- Per-era agent findings (human-readable + JSON): `data_review/fixes_*.md` (+ `frontend/data_review/fixes_enlighten_19c.md`)
- Consolidated machine fix set: `data_review/_all_fixes.json`
