#!/usr/bin/env python3
"""
Post-pipeline cleanup for citation JSON files.

Fixes:
  1. Remove non-person authors (thinkers, poets, Lord, Dionysus, etc.)
  2. Remove "Unknown" / empty authors
  3. Normalize near-duplicate author names (Dostoevski → Dostoevsky, etc.)
  4. Fix known misattributions
  5. Fix typos in author names and titles
  6. Deduplicate citations by merging same-author entries (summing counts, merging contexts)

Usage:
  uv run python scripts/fix_pipeline_output.py <directory_or_file> [--dry-run]
"""

import json
import sys
import unicodedata
from pathlib import Path
from copy import deepcopy
from collections import defaultdict

# ── Authors to remove entirely ──────────────────────────────────────────────
REMOVE_AUTHORS = {
    "unknown", "thinkers", "poets", "lord", "dionysus",
    "elders of zion", "jewish authors", "christian authors",
    "epicureans", "stoics", "pythagorean sect",
}

# ── Author name normalization map ────────────────────────────────────────────
# key: lowercased variant → value: canonical form
AUTHOR_FIXES = {
    # Dostoevsky variants
    "dostoevski": "Fyodor Dostoevsky",
    "dostoyevsky": "Fyodor Dostoevsky",
    "fyodor dostoevsky": "Fyodor Dostoevsky",
    # Chesterton variants
    "g.k. chesterton": "G. K. Chesterton",
    "gilbert k. chesterton": "G. K. Chesterton",
    "chesterton": "G. K. Chesterton",
    # Tolstoy
    "tolstoi": "Leo Tolstoy",
    "tolstoy": "Leo Tolstoy",
    "leo tolstoy": "Leo Tolstoy",
    # Nietzsche
    "nietzsche": "Friedrich Nietzsche",
    # Schopenhauer
    "schopenhauer": "Arthur Schopenhauer",
    "arthur schopenhauer": "Arthur Schopenhauer",
    # Wells
    "wells": "H. G. Wells",
    "h.g. wells": "H. G. Wells",
    "h. g. wells": "H. G. Wells",
    # Gide
    "gide": "André Gide",
    "andre gide": "André Gide",
    "andré gide": "André Gide",
    # Kipling
    "kipling": "Rudyard Kipling",
    "kipling, rudyard": "Rudyard Kipling",
    "rudyard kipling": "Rudyard Kipling",
    # Stalin
    "stalin": "Joseph Stalin",
    "j. v. stalin": "Joseph Stalin",
    "joseph stalin": "Joseph Stalin",
    # Hitler
    "hitler": "Adolf Hitler",
    "adolf hitler": "Adolf Hitler",
    # Himmler
    "himmler": "Heinrich Himmler",
    "heinrich himmler": "Heinrich Himmler",
    # Goebbels
    "goebbels": "Joseph Goebbels",
    "joseph goebbels": "Joseph Goebbels",
    # Trotsky
    "trotsky": "Leon Trotsky",
    "leon trotsky": "Leon Trotsky",
    # Bakunin
    "michael bakunin": "Mikhail Bakunin",
    "mikhail bakunin": "Mikhail Bakunin",
    # Galton
    "sir francis galton": "Francis Galton",
    "fr. galton": "Francis Galton",
    "francis galton": "Francis Galton",
    # Goethe
    "johann wolfgang v. goethe": "Johann Wolfgang von Goethe",
    "johann wolfgang von goethe": "Johann Wolfgang von Goethe",
    # Fritsch
    "theodor fritsch": "Theodor Fritsch",
    "theodor e. fritsch": "Theodor Fritsch",
    # Céline
    "louis ferdinand céline": "Louis-Ferdinand Céline",
    "louis-ferdinand céline": "Louis-Ferdinand Céline",
    # Gobineau
    "arthur de gobineau": "Comte de Gobineau",
    "comte joseph-arthur de gobineau": "Comte de Gobineau",
    # Arndt
    "e. m. arndt": "Ernst Moritz Arndt",
    "ernst moritz arndt": "Ernst Moritz Arndt",
    # Stephen
    "sir james fitzjames stephen": "James Fitzjames Stephen",
    "sir james f. stephen": "James Fitzjames Stephen",
    # Moeller van den Bruck
    "moeller van den bruck": "Arthur Moeller van den Bruck",
    "arthur moeller van den bruck": "Arthur Moeller van den Bruck",
    # Avtorkhanov
    "a. avtorkhanov": "Abdurakhman Avtorkhanov",
    "abdurakhman avtorkhanov": "Abdurakhman Avtorkhanov",
    # Pearson
    "k. pearson": "Karl Pearson",
    "karl pearson": "Karl Pearson",
    # Dühring
    "e. duehring": "Eugen Dühring",
    "e. dühring": "Eugen Dühring",
    "eugen karl duehring": "Eugen Dühring",
    "dühring": "Eugen Dühring",
    # Beck and Godin
    "beck and godin": "F. Beck and W. Godin",
    "f. beck and w. godin": "F. Beck and W. Godin",
    # Monypenny and Buckle
    "monypenny and buckle": "W. F. Monypenny and G. E. Buckle",
    "w. f. monypenny and g. e. buckle": "W. F. Monypenny and G. E. Buckle",
    # Deutscher
    "i. deutscher": "Isaac Deutscher",
    "isaac deutscher": "Isaac Deutscher",
    # Reinach (Théodore)
    "t. reinach": "Théodore Reinach",
    "théodore reinach": "Théodore Reinach",
    # Reinach (Joseph)
    "j. reinach": "Joseph Reinach",
    "joseph reinach": "Joseph Reinach",
    # Kohn-Bramstedt
    "e. kohn-bramstedt": "Kohn-Bramstedt",
    "kohn-bramstedt": "Kohn-Bramstedt",
    # Leclerc de Buffon
    "leclerc de buffon": "Georges-Louis Leclerc, Comte de Buffon",
    "georges-louis leclerc, comte de buffon": "Georges-Louis Leclerc, Comte de Buffon",
    # Janowsky (fix inconsistent middle initial)
    "oscar i. janowsky": "Oscar Janowsky",
    "oscar j. janowsky": "Oscar Janowsky",
    # Borges name variants
    "borges": "Jorge Luis Borges",
    "jorge luis borges": "Jorge Luis Borges",
    # Berkeley
    "berkeley": "George Berkeley",
    "bishop berkeley": "George Berkeley",
    "george berkeley": "George Berkeley",
    # Emerson
    "emerson": "Ralph Waldo Emerson",
    "ralph waldo emerson": "Ralph Waldo Emerson",
    # Carlyle
    "carlyle": "Thomas Carlyle",
    "thomas carlyle": "Thomas Carlyle",
    # Bacon
    "bacon": "Francis Bacon",
    "francis bacon": "Francis Bacon",
    # Flaubert
    "flaubert": "Gustave Flaubert",
    "gustave flaubert": "Gustave Flaubert",
    # Kafka
    "kafka": "Franz Kafka",
    "franz kafka": "Franz Kafka",
    # Joyce
    "joyce": "James Joyce",
    "james joyce": "James Joyce",
    # Proust
    "proust": "Marcel Proust",
    "marcel proust": "Marcel Proust",
    # Wilde
    "wilde": "Oscar Wilde",
    "oscar wilde": "Oscar Wilde",
    # Shaw
    "bernard shaw": "George Bernard Shaw",
    "george bernard shaw": "George Bernard Shaw",
    # Tennyson
    "alfred, lord tennyson": "Alfred Tennyson",
    "alfred tennyson": "Alfred Tennyson",
    # R. L. Stevenson
    "r. l. stevenson": "Robert Louis Stevenson",
    "robert louis stevenson": "Robert Louis Stevenson",
    # Cartier-Bresson
    "cartier-bresson": "Henri Cartier-Bresson",
    "henri cartier-bresson": "Henri Cartier-Bresson",
    # Moholy-Nagy
    "moholy-nagy": "László Moholy-Nagy",
    "laszlo moholy-nagy": "László Moholy-Nagy",
    "lászló moholy-nagy": "László Moholy-Nagy",
    # Fox Talbot
    "william henry fox talbot": "William H. Fox Talbot",
    "william h. fox talbot": "William H. Fox Talbot",
    # Hume
    "hume": "David Hume",
    "david hume": "David Hume",
    # Cicero (keep Q. Cicero separate — different person)
    "cicero": "Cicero",
    "marcus tullius cicero": "Cicero",
    # La Boétie
    "la boetie": "Étienne de La Boétie",
    "estienne de la boetie": "Étienne de La Boétie",
    # Tacitus
    "tacitus": "Cornelius Tacitus",
    "cornelius tacitus": "Cornelius Tacitus",
    # Bodin
    "bodin": "Jean Bodin",
    "jean bodin": "Jean Bodin",
    # Caesar
    "caesar": "Julius Caesar",
    "julius caesar": "Julius Caesar",
    # Le Bon
    "lebon": "Gustave Le Bon",
    # Leibniz
    "leibnitz": "Gottfried Wilhelm Leibniz",
    "leibniz": "Gottfried Wilhelm Leibniz",
    # Lugones typo
    "leopolda lugones": "Leopoldo Lugones",
    "leopoldo lugones": "Leopoldo Lugones",
    # Bloy accent fix
    "león bloy": "Léon Bloy",
    "léon bloy": "Léon Bloy",
    # Erigena
    "johannes scotus erigena": "John Scotus Erigena",
    "john scotus erigena": "John Scotus Erigena",
    # Bradley
    "francis bradley": "F. H. Bradley",
    "f. h. bradley": "F. H. Bradley",
    # Giles
    "h. a. giles": "Herbert Allen Giles",
    "herbert allen giles": "Herbert Allen Giles",
    # Sōseki
    "natsume soseki": "Natsume Sōseki",
    "natsume sōseki": "Natsume Sōseki",
    # Sebastian Bach
    "sebastian bach": "Johann Sebastian Bach",
    "johann sebastian bach": "Johann Sebastian Bach",
    # Thomas Aquinas
    "thomas of aquinas": "Thomas Aquinas",
    "st. thomas aquinas": "Thomas Aquinas",
    "saint thomas aquinas": "Thomas Aquinas",
    "thomas aquinas": "Thomas Aquinas",
    # Augustine
    "augustine": "St. Augustine",
    "st. augustine": "St. Augustine",
    # Frankl
    "frankl": "Viktor E. Frankl",
    "viktor e. frankl": "Viktor E. Frankl",
    # Allport
    "allport": "Gordon W. Allport",
    "gordon w. allport": "Gordon W. Allport",
    # Engels
    "friedrich engels": "Friedrich Engels",
    # Spinoza
    "spinoza": "Baruch Spinoza",
    "baruch spinoza": "Baruch Spinoza",
    # Kant
    "kant": "Immanuel Kant",
    "immanuel kant": "Immanuel Kant",
    # Balzac
    "balzac": "Honoré de Balzac",
    "honoré de balzac": "Honoré de Balzac",
    # Dickens
    "dickens": "Charles Dickens",
    "charles dickens": "Charles Dickens",
    # Kleist
    "kleist": "Heinrich von Kleist",
    "heinrich von kleist": "Heinrich von Kleist",
    # Döblin
    "döblin": "Alfred Döblin",
    "alfred döblin": "Alfred Döblin",
    # Krleža
    "krleža": "Miroslav Krleža",
    "miroslav krleža": "Miroslav Krleža",
    # Zagajewski
    "zagajewski": "Adam Zagajewski",
    "adam zagajewski": "Adam Zagajewski",
    # Milosz
    "milosz": "Czesław Miłosz",
    "czeslaw milosz": "Czesław Miłosz",
    "czesław miłosz": "Czesław Miłosz",
    # Chateaubriand
    "chateaubriand": "François-René de Chateaubriand",
    "françois-rené de chateaubriand": "François-René de Chateaubriand",
    # Norris
    "norris": "Frank Norris",
    "frank norris": "Frank Norris",
    # Eliot (George)
    "eliot": "George Eliot",
    "george eliot": "George Eliot",
    # Disraeli
    "disraeli": "Benjamin Disraeli",
    "benjamin disraeli": "Benjamin Disraeli",
    # Sartre
    "sartre": "Jean-Paul Sartre",
    "jean-paul sartre": "Jean-Paul Sartre",
    # Wagner
    "wagner": "Richard Wagner",
    "richard wagner": "Richard Wagner",
    # Rainer → Rilke (bare first name in Where the Stress Falls)
    "rainer": "Rainer Maria Rilke",
    # Sandel
    "michael j. sandel": "Michael J. Sandel",
    # Milton Friedman
    "milton friedman": "Milton Friedman",
    "milton and rose friedman": "Milton Friedman",
    # Croce
    "croce": "Benedetto Croce",
    "benedetto croce": "Benedetto Croce",
    # Trevor-Roper
    "trevor-roper": "H. R. Trevor-Roper",
    "h. r. trevor-roper": "H. R. Trevor-Roper",
    # Eduardo Gutiérrez typo
    "eduardo gutierrez": "Eduardo Gutiérrez",
    "eduardo gutiérrez": "Eduardo Gutiérrez",
    # Allan/Allen Dulles
    "allan w. dulles": "Allen W. Dulles",
    "allen w. dulles": "Allen W. Dulles",
    # Heraclitus
    "heracleitus": "Heraclitus",
    "heraclitus": "Heraclitus",
    # Pseudo-Gallus
    "pseudo gallus": "Pseudo-Gallus",
    "pseudo-gallus": "Pseudo-Gallus",
    # Vonnegut
    "kurt vonnegut": "Kurt Vonnegut",
    "kurt vonnegut, jr.": "Kurt Vonnegut",
    # Torres Villarroel
    "torres villarroel": "Diego de Torres Villarroel",
    "diego de torres villarroel": "Diego de Torres Villarroel",
    # Hernández
    "hernández": "José Hernández",
    "josé hernández": "José Hernández",
    # Tasso
    "tasso": "Torquato Tasso",
    "torquato tasso": "Torquato Tasso",
    # Feuerbach
    "feuerbach": "Ludwig Feuerbach",
    "ludwig feuerbach": "Ludwig Feuerbach",
    # Zarathustra → Nietzsche (character misattributed as author)
    "zarathustra": "Friedrich Nietzsche",
}

# ── Known misattributions: (author_lower, title_fragment) → fix ──────────────
MISATTRIBUTIONS = [
    {
        "match_author": "dostoevsky",
        "match_title": "great expectations",
        "fix_author": "Charles Dickens",
    },
    {
        "match_author": "robert louis stevenson",
        "match_title": "ethical studies",
        "fix_author": "F. H. Bradley",
    },
    {
        "match_author": "plato",
        "match_title": "death in teheran",
        "remove": True,
    },
]

# ── Title typo fixes ────────────────────────────────────────────────────────
TITLE_FIXES = {
    "Eth.": "Ethics",
    "El delincuente espahol: su lenguaje": "El delincuente español: su lenguaje",
    "Die Welt ist schon": "Die Welt ist schön",
    "Kopfe des Alltags": "Köpfe des Alltags",
}


def normalize_key(name: str) -> str:
    """Normalize author name for dedup key."""
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().replace(".", "").replace(",", "").strip()
    s = " ".join(s.split())
    return s


def fix_author(author: str) -> str | None:
    """Return canonical author name, or None to remove."""
    low = author.strip().lower()
    if low in REMOVE_AUTHORS or not low:
        return None
    if low in AUTHOR_FIXES:
        return AUTHOR_FIXES[low]
    return author.strip()


def fix_title(title: str) -> str:
    return TITLE_FIXES.get(title, title)


def check_misattribution(author: str, title: str):
    """Check if this citation is a known misattribution. Returns (new_author, should_remove)."""
    a_low = author.strip().lower()
    t_low = title.strip().lower()
    for mis in MISATTRIBUTIONS:
        if mis["match_author"] in a_low and mis["match_title"] in t_low:
            return mis.get("fix_author", author), mis.get("remove", False)
    return author, False


def merge_citations(group: list[dict]) -> dict:
    """Merge a group of citations for the same author into one, keeping the richest entry."""
    priority = {"book": 0, "author": 1, "person": 2, "not_found": 3, "unknown": 4, "error": 5}

    group.sort(key=lambda c: priority.get(c.get("edge", {}).get("target_type", "error"), 5))
    best = deepcopy(group[0])

    all_contexts = []
    all_commentaries = []
    all_titles = set()
    total_count = 0
    for c in group:
        raw = c.get("raw", {})
        all_contexts.extend(raw.get("contexts", []))
        all_commentaries.extend(raw.get("commentaries", []))
        t = raw.get("title", "")
        if t:
            all_titles.add(t)
        total_count += raw.get("count", 1)

    best["raw"]["contexts"] = list(dict.fromkeys(all_contexts))
    best["raw"]["commentaries"] = list(dict.fromkeys(all_commentaries))
    best["raw"]["count"] = total_count

    if len(all_titles) > 1:
        best_title = best["raw"].get("title", "")
        others = sorted(all_titles - {best_title})
        if others:
            best["raw"]["other_titles"] = others

    return best


def process_file(path: Path) -> tuple[dict, dict]:
    data = json.loads(path.read_text())
    citations = data.get("citations", [])

    stats = {"total": len(citations), "removed": 0, "fixed_author": 0,
             "fixed_title": 0, "misattributed": 0, "merged": 0}

    cleaned = []
    for cit in citations:
        raw = cit.get("raw", {})
        author = raw.get("author", "")
        title = raw.get("title", "")

        # Check misattribution
        new_author, should_remove = check_misattribution(author, title)
        if should_remove:
            stats["removed"] += 1
            stats["misattributed"] += 1
            continue
        if new_author != author:
            stats["misattributed"] += 1
            raw["author"] = new_author
            raw["canonical_author"] = new_author
            author = new_author

        # Fix author
        fixed = fix_author(author)
        if fixed is None:
            stats["removed"] += 1
            continue
        if fixed != author:
            stats["fixed_author"] += 1
            raw["author"] = fixed
            raw["canonical_author"] = fixed

        # Fix title
        new_title = fix_title(title)
        if new_title != title:
            stats["fixed_title"] += 1
            raw["title"] = new_title

        cleaned.append(cit)

    # Deduplicate: group by normalized author + normalized title
    groups = defaultdict(list)
    for cit in cleaned:
        raw = cit.get("raw", {})
        author = raw.get("author", "")
        title = raw.get("title", "")
        akey = normalize_key(author)
        tkey = normalize_key(title) if title.strip() else ""
        groups[(akey, tkey)].append(cit)

    final = []
    for (akey, tkey), group in groups.items():
        if len(group) > 1:
            stats["merged"] += len(group) - 1
        final.append(merge_citations(group))

    data["citations"] = final
    stats["final"] = len(final)
    return data, stats


def main():
    if len(sys.argv) < 2:
        print("Usage: fix_pipeline_output.py <directory_or_file> [--dry-run]")
        sys.exit(1)

    target = Path(sys.argv[1])
    dry_run = "--dry-run" in sys.argv

    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = sorted(target.glob("*.json"))
    else:
        print(f"Error: {target} not found")
        sys.exit(1)

    print(f"Processing {len(files)} file(s){'  [DRY RUN]' if dry_run else ''}...\n")

    for fpath in files:
        data, stats = process_file(fpath)
        source = data.get("source", {})
        book_title = source.get("title", fpath.stem)
        print(f"  {fpath.name} ({book_title}):")
        print(f"    {stats['total']} citations -> {stats['final']} after cleanup")
        print(f"    Removed: {stats['removed']}  Author fixes: {stats['fixed_author']}  "
              f"Title fixes: {stats['fixed_title']}  Misattributions: {stats['misattributed']}  "
              f"Merged: {stats['merged']}")

        if not dry_run:
            fpath.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            print(f"    Written.")
        print()

    print("Done.")


if __name__ == "__main__":
    main()
