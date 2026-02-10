#!/usr/bin/env python3
"""Fix birth/death year metadata errors in authors_metadata.json and frontend data files.

Error patterns fixed:
1. Sign error on death_year: birth>0, death<0, abs(death)-birth is plausible lifespan → flip sign
2. Sign error on birth_year: birth<0, death>0, death-abs(birth) is plausible lifespan → flip sign
3. Wrong-person disambiguation: birth>death (both positive) → null both
4. Era mismatch: birth>0, death<0, but implausible lifespan → null death_year
5. Both signs wrong: both<0, death<birth (numerically), plausible lifespan when flipped → flip both
6. Both signs wrong but implausible → null both

Usage:
    uv run python scripts/fix_metadata_errors.py [--dry-run] [--verbose]
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTHORS_META = ROOT / "datasets" / "authors_metadata.json"
FRONTEND_DATA = ROOT / "frontend" / "data"

MAX_LIFESPAN = 120


def fix_dates(birth, death, name=""):
    """Check a birth/death pair and return a fix if needed.

    Returns (fixed_birth, fixed_death, fix_category) or None if no fix needed.
    """
    if birth is None or death is None:
        return None

    # Rule 1: sign error on death (positive birth, negative death, plausible lifespan)
    if birth > 0 and death < 0 and 0 < (abs(death) - birth) < MAX_LIFESPAN:
        return (birth, abs(death), "sign_error_death")

    # Rule 2: sign error on birth (negative birth, positive death, plausible lifespan)
    if birth < 0 and death > 0 and 0 < (death - abs(birth)) < MAX_LIFESPAN:
        return (abs(birth), death, "sign_error_birth")

    # Rule 4: sign error on death but implausible (wrong person's death year)
    if birth > 0 and death < 0:
        return (birth, None, "wrong_person_death")

    # Rule 4b: birth<0, death>0 but Rule 2 didn't fire.
    # Check if this is a legitimate BC-to-AD boundary person (e.g., Ovid: -43, 17)
    if birth < 0 and death > 0:
        bc_ad_lifespan = abs(birth) + death  # e.g., 43 + 17 = 60 for Ovid
        if 0 < bc_ad_lifespan < MAX_LIFESPAN:
            return None  # legitimate BC-to-AD person, no fix needed
        return (None, death, "wrong_person_birth")

    # Rule 5: both negative, death < birth numerically (e.g., Shakespeare: -1564, -1616)
    # When both flipped to positive, check if lifespan is plausible
    if birth < 0 and death < 0 and death < birth:
        lifespan = abs(death) - abs(birth)
        if 0 < lifespan < MAX_LIFESPAN:
            return (abs(birth), abs(death), "sign_error_both")
        else:
            return (None, None, "wrong_person_both_neg")

    # Rule 3: birth > death, both positive (wrong person entirely)
    if birth > 0 and death > 0 and birth > death:
        return (None, None, "wrong_person_both")

    # Rule 3b: lifespan > 200 years (both positive, but absurd)
    if birth > 0 and death > 0 and (death - birth) > 200:
        return (None, None, "implausible_lifespan")

    return None


def fix_meta_dict(meta, name="", prefix=""):
    """Apply fix_dates to a dict with birth_year/death_year keys.

    Returns list of (description_string, fix_category) for each fix applied.
    """
    fixes = []
    birth = meta.get("birth_year")
    death = meta.get("death_year")
    result = fix_dates(birth, death, name)
    if result:
        new_birth, new_death, category = result
        desc = f"{prefix}{name}: birth={birth} death={death} → birth={new_birth} death={new_death} [{category}]"
        meta["birth_year"] = new_birth
        meta["death_year"] = new_death
        fixes.append((desc, category))
    return fixes


def fix_authors_metadata(dry_run=False, verbose=False):
    """Fix datasets/authors_metadata.json. Returns (fixes_list, post_fix_data)."""
    with open(AUTHORS_META) as f:
        data = json.load(f)

    fixes = []
    for name, meta in data.items():
        fixes.extend(fix_meta_dict(meta, name=name, prefix="[cache] "))

    if verbose or dry_run:
        for desc, _ in fixes:
            print(f"  {desc}")

    if not dry_run and fixes:
        with open(AUTHORS_META, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return fixes, data


def fix_frontend_file(filepath, dry_run=False, verbose=False):
    """Fix a single frontend data JSON file."""
    with open(filepath) as f:
        data = json.load(f)

    fixes = []
    rel = filepath.relative_to(ROOT)
    prefix = f"[{rel}] "

    # Fix source.author_metadata
    source_meta = data.get("source", {}).get("author_metadata")
    if source_meta:
        source_name = ", ".join(data.get("source", {}).get("authors", ["?"]))
        fixes.extend(fix_meta_dict(source_meta, name=source_name, prefix=prefix + "source: "))

    # Fix each citation
    for cit in data.get("citations", []):
        cit_author = cit.get("raw", {}).get("canonical_author", "?")

        # goodreads_match.author_meta
        gr = cit.get("goodreads_match")
        if gr and gr.get("author_meta"):
            fixes.extend(fix_meta_dict(
                gr["author_meta"],
                name=gr.get("name", cit_author),
                prefix=prefix + "goodreads: ",
            ))

        # wikipedia_match (has birth_year/death_year at top level)
        wiki = cit.get("wikipedia_match")
        if wiki and ("birth_year" in wiki or "death_year" in wiki):
            fixes.extend(fix_meta_dict(
                wiki,
                name=wiki.get("title", cit_author),
                prefix=prefix + "wikipedia: ",
            ))

        # edge.target_person
        person = cit.get("edge", {}).get("target_person")
        if person and ("birth_year" in person or "death_year" in person):
            fixes.extend(fix_meta_dict(
                person,
                name=person.get("title", cit_author),
                prefix=prefix + "edge: ",
            ))

    if verbose or dry_run:
        for desc, _ in fixes:
            print(f"  {desc}")

    if not dry_run and fixes:
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return fixes


def find_remaining_suspicious(cache_data):
    """Scan post-fix cache data for entries that still look wrong."""
    suspicious = []
    for name, meta in cache_data.items():
        b = meta.get("birth_year")
        d = meta.get("death_year")
        if b is not None and d is not None:
            # BC author where death is before birth (both negative, death more negative)
            if b < 0 and d < 0 and d < b:
                suspicious.append(f"[cache] {name}: birth={b} death={d} (BC death before birth?)")
            # Lifespan over 200 years (either era)
            if b < d and (d - b) > 200:
                suspicious.append(f"[cache] {name}: birth={b} death={d} (lifespan {d - b} years?)")
    return suspicious


def main():
    parser = argparse.ArgumentParser(description="Fix metadata birth/death year errors")
    parser.add_argument("--dry-run", action="store_true", help="Report fixes without writing")
    parser.add_argument("--verbose", action="store_true", help="Print each fix")
    args = parser.parse_args()

    all_fixes = []
    categories = Counter()

    # 1. Fix authors_metadata.json
    print("=== Fixing datasets/authors_metadata.json ===")
    fixes, cache_data = fix_authors_metadata(dry_run=args.dry_run, verbose=args.verbose)
    all_fixes.extend(fixes)
    for _, cat in fixes:
        categories[cat] += 1
    print(f"  → {len(fixes)} fixes")

    # 2. Fix frontend data files
    print("\n=== Fixing frontend data files ===")
    frontend_files = sorted(FRONTEND_DATA.glob("**/*.json"))
    frontend_total = 0
    for fp in frontend_files:
        # Skip manifest files — they don't have citation data
        if fp.name == "manifest.json":
            continue
        # Skip non-citation files
        if fp.name in ("original_publication_dates.json", "authors_metadata.json"):
            continue
        # Skip raw/preprocessed intermediate files
        if "raw_extracted_citations" in str(fp) or "preprocessed_extracted_citations" in str(fp):
            continue

        fixes = fix_frontend_file(fp, dry_run=args.dry_run, verbose=args.verbose)
        all_fixes.extend(fixes)
        for _, cat in fixes:
            categories[cat] += 1
        frontend_total += len(fixes)
    print(f"  → {frontend_total} fixes across frontend files")

    # 3. Summary
    print(f"\n=== Summary ===")
    print(f"Total fixes: {len(all_fixes)}")
    for cat, count in categories.most_common():
        print(f"  {cat}: {count}")

    if args.dry_run:
        print("\n(dry-run mode — no files were modified)")

    # 4. Check for remaining suspicious entries (uses post-fix in-memory data)
    suspicious = find_remaining_suspicious(cache_data)
    if suspicious:
        print(f"\n=== Remaining suspicious entries ({len(suspicious)}) ===")
        for s in suspicious:
            print(f"  {s}")
    else:
        print("\nNo remaining suspicious entries.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
