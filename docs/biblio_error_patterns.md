# Bibliographic Error Patterns in Citation Pipeline

## Summary

Audit of ~5,800 citations across 45 JSON files found 159 errors (~2.7% error rate).
These fall into 5 categories, listed by frequency.

---

## 1. Wrong Wikipedia Person Disambiguation (~70% of errors)

**The problem**: When searching Wikipedia for an author name (especially a surname-only
reference like "Heine", "Marr", "Radek"), the pipeline matches the wrong person with
the same or similar name.

**Examples**:
- "Heine" → Jakob Heine (orthopedic surgeon) instead of Heinrich Heine (poet)
- "Radek" → Radek Martinek (ice hockey player) instead of Karl Radek (politician)
- "Darwin" → Susannah Darwin (Charles Darwin's mother) instead of Charles Darwin
- "Virgil" → Virgil Solis (16th-century artist) instead of the Roman poet
- "Juvenal" → modern person born 1937 instead of the Roman satirist (~55-128 AD)
- "Cervantes" → Francisco Cervantes de Salazar instead of Miguel de Cervantes
- "Tolstoy" → Aleksey Nikolayevich Tolstoy instead of Leo Tolstoy

**Root causes**:
1. No contextual disambiguation — pipeline doesn't use the source book's context to
   pick the right person
2. Single-name references are ambiguous (many people share the surname "Heine")
3. Wikipedia search returns the most popular article, which may not be the intended person

**Detection heuristics** (implemented in fix script):
- **Sport/entertainment infobox**: If Wikipedia match has infobox "football biography",
  "ice hockey player", "cricketer", etc. in a scholarly context → wrong match
- **Criminal categories**: "convicted of murder", "spree shooting" categories
- **Anachronistic birth year**: If `wikipedia_match.birth_year > source.publication_year`,
  the cited person couldn't have been referenced (with exceptions for modern editions
  of ancient texts)

**Pipeline fixes to consider**:
1. **Use citation context for disambiguation**: Pass the `raw.contexts` to the Wikipedia
   search to help pick the right person. E.g., "Schopenhauer's concept of negative
   happiness" clearly indicates the philosopher, not a modern namesake.
2. **Category/infobox validation**: After matching, check if the Wikipedia person's
   categories are consistent with the citation context (a philosopher cited in a
   philosophy book shouldn't match a footballer).
3. **Era consistency check**: If the source book cites "Juvenal" in the context of
   "Roman satire", a person born in 1937 is clearly wrong.
4. **Prefer people with literary/scholarly categories** when the source is a scholarly work.
5. **Known author alias mapping**: For common names (Virgil, Terence, Juvenal, Homer,
   etc.), maintain a mapping to the correct Wikipedia article. The existing
   `author_aliases.json` could be extended with Wikipedia page IDs.

---

## 2. Wrong Goodreads Book Match (~15% of errors)

**The problem**: A citation's title matches a different book by a different author on
Goodreads. Same title, completely different work.

**Examples**:
- "Diplomacy" by Harold Nicolson → matched to "Diplomacy" by Henry Kissinger
- "African Genesis" by Frobenius/Fox (1937 mythology) → Robert Ardrey (1961 evolution)
- "Ivan the Terrible" by Ian Grey → Isabel de Madariaga's "Ivan the Terrible"
- "Historia Naturalis" by Pliny the Elder → Dan Chiasson poetry collection (2005)
- "Quantum Theory" by Fritz Reiche → David Bohm's "Quantum Theory"

**Root causes**:
1. Title-only search matches the most popular Goodreads book with that title
2. No author verification after the match
3. Common titles shared across different works/eras

**Detection heuristic**: Compare `raw.author` with `goodreads_match.authors`. If the
author names don't match at all (after normalizing diacritics and checking last names),
the match is likely wrong. CAVEAT: This has high false positive rates due to:
- Different transliterations (Dostoevsky/Dostoyevsky)
- Different romanizations (Ko Hung/Ge Hong, Laozi/Lao Tzu)
- German ue/oe ↔ ü/ö (Schroedinger/Schrödinger, Buelow/Bülow)
- Latin vs vernacular names (Cluverius/Clüver)
- Titles vs real names (Lord Raglan/FitzRoy Somerset)

**Pipeline fixes to consider**:
1. **Author name verification**: After finding a Goodreads book match, verify that at
   least one of the Goodreads authors fuzzy-matches the `raw.author`. Use diacritics-
   normalized comparison with transliteration awareness.
2. **Publication year check**: If `raw.contexts` mention a publication year and the
   Goodreads book's `original_publication_year` is very different, it's wrong.
3. **Edition preference**: When multiple Goodreads editions exist for the same title,
   prefer the one whose author matches `raw.author`.

---

## 3. Anachronistic Matches (~8% of errors)

**The problem**: The matched Wikipedia person was born after the source book was
published, making it impossible for the source author to reference them.

**Examples**:
- "Genchi Kato" → manga artist born 1967 (source book: 1935 Shinto text)
- "Margaret Sinclair Stevenson" → person born 1938 (wrote book in 1915)
- "Francois Secret" → person born 1959 (book published 1964)
- "John Bakeless" → person born 1734, died 1756 (book published 1942)

**Caveat**: Modern annotated editions of ancient texts (e.g., Montaigne's Essays
published 1580 but with modern scholarly apparatus) legitimately cite modern scholars
like Hazlitt (1778) or La Bruyère (1645). The heuristic needs exceptions for these.

**Pipeline fix**: Add a post-match validation step that checks
`wikipedia_match.birth_year < source.publication_year`. Flag violations for review.

---

## 4. Wrong Data Extraction (~5% of errors)

**The problem**: The correct Wikipedia page was matched, but the extracted birth/death
years are wrong — likely pulled from a disambiguation or a different section.

**Examples**:
- Benjamin Franklin: correct page, but death_year=1730 (should be 1790)
- W.V.O. Quine: correct page, but death_year=1932 (should be 2000)
- Aulus Gellius: correct page, but birth_year=-125 (should be +125 AD)
- Moses: Wikipedia birth_year=1730 (Moses Mendelssohn's dates on Moses page?)

**Pipeline fix**: Validate extracted dates against Wikipedia categories. E.g., if
categories say "1706 births" but extracted birth_year is different, use the category
date. Cross-check birth/death from categories vs infobox.

---

## 5. Category/Article Mismatch (~2% of errors)

**The problem**: The Wikipedia article is the right topic area but the wrong specific
entity within that topic.

**Examples**:
- "Trebellius Pollio" → "Vedius Pollio" (both Roman, but different people)
- "Valerius Maximus" → "Terentius Maximus" (both Roman, similar name pattern)
- "Jacques de Vitry" → "Philippe de Vitry" (both medieval, "de Vitry" surname)
- "Photius" → "Photius Fisk" (both named Photius, centuries apart)

**Pipeline fix**: After matching, verify that the Wikipedia article title contains or
closely matches the citation's `raw.author` name, not just a partial match.

---

## Most Error-Prone Source Books

| Book | Errors | Cited | Rate | Why |
|------|--------|-------|------|-----|
| Gibbon's Decline and Fall | 23 | 346 | 6.6% | Obscure ancient figures |
| Montaigne's Essays | 22 | 276 | 8.0% | Ancient classical refs |
| Stalin's Library | 20 | 336 | 6.0% | Soviet surname-only refs |
| Hero With a Thousand Faces | 13 | 259 | 5.0% | Cross-cultural mythology |
| Borges's Other Inquisitions | 9 | 566 | 1.6% | Diverse global refs |
| Arendt's Origins of Totalitarianism | 9 | 189 | 4.8% | Obscure political refs |
| Frye's Anatomy of Criticism | 9 | 367 | 2.5% | Classical literary refs |
| Kuhn's Structure of Sci. Revolutions | 10 | 176 | 5.7% | Historical scientists |

---

## Recurring Systematic Patterns

1. **"Juvenal"** consistently matches a modern person (born 1937) across 5 files
2. **"Terence"** consistently matches a modern person (born 1957) across 2 files
3. **"Cervantes"** matches Francisco Cervantes de Salazar across 2 files
4. **"Hafiz"** matches a modern person (born 1931) across 2 files
5. **"Dostoevsky"/"Dostoyevsky"** — transliteration variants cause GR mismatches

These should be added to `author_aliases.json` with correct Wikipedia page IDs.

---

## Recommended Priority Actions for Pipeline

1. **High impact, low effort**: Add author name verification to Goodreads matching
   (compare raw.author to GR authors with diacritics normalization)
2. **High impact, medium effort**: Add anachronistic birth year check as post-validation
3. **High impact, medium effort**: Extend `author_aliases.json` with Wikipedia page IDs
   for common classical/historical figures (Juvenal, Terence, Virgil, Hafiz, etc.)
4. **Medium impact, higher effort**: Use citation context for Wikipedia disambiguation
5. **Low effort**: Add sport/criminal category check as post-validation filter
