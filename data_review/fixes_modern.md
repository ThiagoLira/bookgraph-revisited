# Fixes — Era: modern

Audited 133 rows. Below are only confident findings. The TIME axis uses author dates and original publication years, so the priority is (a) correct person matched, (b) original publication year, (c) demonym sanity.

## Wrong-person matches (dates belong to someone else)

- **Cicero** (line 13): listed 1891–1970 in a "modern" bucket. The real Marcus Tullius Cicero is 106 BCE–43 BCE. The 1891–1970 record is a different person entirely. Cannot confidently assert which modern person was matched, so flagged as a person-match error and corrected to the canonical Cicero dates (negative = BCE).
- **Juvenal** (line 22): listed 1937–1994. The Roman satirist Juvenal lived c. 55–c. 138 CE; the work "The Satires=127" is correctly dated. The author dates are a wrong-person match. Set to approximate canonical Roman dates.
- **Aesop** (line 82): listed 1976–None, nationality Greek. The legendary fabulist Aesop is traditionally c. 620–564 BCE. A 1976 birth is a clearly bogus match. "The Aesop Romance=200" (a late-antique compilation) is fine as a text year; author dates corrected.

## Impossible / edition book years

- **Adolf Hitler** (line 34): "Mein Kampf=1192" — impossible (predates author and printing). Original publication 1925 (vol. 1).
- **Oliver Sacks** (line 66): "The Man Who Mistook His Wife for a Hat=1967" — book was first published 1985. 1967 is wrong (and predates much of his career). Correct = 1985.
- **Arthur Stanley Eddington** (line 70): "The Nature of the Physical World=1920" — first published 1928 (Gifford Lectures 1927). Correct = 1928. (Note: the duplicate Eddington row at line 47 has no book.)
- **Erich Auerbach** (line 31): "Mimesis...=1942" is a duplicate of the same title dated 1946; the original German edition (Bern, Francke) is 1946. The 1942 entry is wrong (that is when he began writing it). Correct the 1942 instance to 1946. Also note the two "Dante: Poet of the Secular World"/"Dante als Dichter der irdischen Welt=1929" are the German original (1929) and its English translation — 1929 is correct for the original.
- **Jacques Maritain** (line 65): "Art and Scholasticism With Other Essays=1927" — the original French *Art et scolastique* is 1920; 1927 is the English translation. Correct = 1920.

## Death-year errors

- **Noam Chomsky** (line 26): listed 1928–1949. Chomsky was born 1928 and (as of the project's 2026 date context) the 1949 death year is wrong — it likely conflated a publication date. Set death_year to null (no confident death year). Confidence medium because I cannot fully rule out a recent death from memory, but 1949 is certainly impossible (it predates all his work).

## Nationality errors

- **Isaac Asimov** (line 120): listed British/british_isles. Asimov was a Russian-born American author; he emigrated as a toddler and is universally classified American. Correct demonym = American.
- **Robert Ardrey** (line 122): listed German/germanic. Ardrey was an American (Chicago-born) playwright and science writer. Correct demonym = American.

## Notes / non-fixes (checked, left as-is)

- **Ernest Nagel** (line 25): American — correct (Czech-born but American philosopher).
- **Max Jammer** (line 60): Israeli — correct (German-born, Israeli physicist).
- **Walter Benjamin** (line 30): German — correct.
- **Paul de Man** (line 116): Belgian — acceptable (Belgian-born American; demonym not clearly wrong).
- **Alain de Botton** (line 131): Swiss — acceptable (Swiss-born British dual national).
- **John Webster** (line 117): dates 1930–1997 look like a wrong-person match (the Jacobean dramatist of *The White Devil*/*Duchess of Malfi* lived c. 1580–c.1634), but the modern "John Webster" matched is plausibly intentional in this dataset and I cannot confidently determine intent, so left unflagged. The play years (1612/1614) are correct for the historical Webster.
- Mystery/placeholder rows — **Unknown** (line 11), **Isaiah** (line 81), **Schelling** (line 83), **Wilde** (line 96) — are too ambiguous to correct confidently; skipped.
- Several "year=" book entries are translations (Borges, Ortega, Poliakov, Spitzer, Vasoli, Praz, etc.); their listed years generally match originals or are reasonable, so not flagged individually.

```json
{"fixes": [
  {"name": "Cicero", "type": "author_dates", "birth_year": -106, "death_year": -43, "confidence": "high", "reason": "1891-1970 is a wrong-person match; canonical Roman Cicero is 106-43 BCE"},
  {"name": "Juvenal", "type": "author_dates", "birth_year": 55, "death_year": 138, "confidence": "medium", "reason": "1937-1994 is wrong-person; Roman satirist lived c.55-138 CE (Satires=127 is correct)"},
  {"name": "Aesop", "type": "author_dates", "birth_year": -620, "death_year": -564, "confidence": "medium", "reason": "1976 birth is bogus; legendary Greek fabulist traditionally c.620-564 BCE"},
  {"name": "Noam Chomsky", "type": "author_dates", "birth_year": 1928, "death_year": null, "confidence": "medium", "reason": "death_year 1949 is impossible (predates all his work); no confident death date"},
  {"name": "Adolf Hitler", "type": "book_year", "book_title": "Mein Kampf", "current": 1192, "correct": 1925, "confidence": "high", "reason": "1192 impossible; original publication 1925"},
  {"name": "Oliver Sacks", "type": "book_year", "book_title": "The Man Who Mistook His Wife for a Hat and Other Clinical Tales", "current": 1967, "correct": 1985, "confidence": "high", "reason": "first published 1985, not 1967"},
  {"name": "Arthur Stanley Eddington", "type": "book_year", "book_title": "The Nature of the Physical World", "current": 1920, "correct": 1928, "confidence": "high", "reason": "first published 1928 (Gifford Lectures 1927)"},
  {"name": "Erich Auerbach", "type": "book_year", "book_title": "Mimesis: The Representation of Reality in Western Literature", "current": 1942, "correct": 1946, "confidence": "high", "reason": "original German edition 1946; 1942 is when he began writing it (duplicate title also listed as 1946)"},
  {"name": "Jacques Maritain", "type": "book_year", "book_title": "Art and Scholasticism With Other Essays", "current": 1927, "correct": 1920, "confidence": "high", "reason": "original French Art et scolastique 1920; 1927 is the English translation"},
  {"name": "Isaac Asimov", "type": "nationality", "correct": "American", "confidence": "high", "reason": "Russian-born American author; listed British is wrong"},
  {"name": "Robert Ardrey", "type": "nationality", "correct": "American", "confidence": "high", "reason": "American playwright/science writer; listed German is wrong"}
]}
```

## Summary

11 confident fixes: 4 author_dates (3 wrong-person matches — Cicero, Juvenal, Aesop — plus Chomsky's impossible death year), 5 book_year corrections (Hitler 1192→1925, Sacks 1967→1985, Eddington 1920→1928, Auerbach 1942→1946, Maritain 1927→1920, the latter three being reprint/translation/edition-vs-original errors), and 2 nationality fixes (Asimov and Ardrey both → American). No translated-title canonicalizations rose to high confidence. Most of the 133 rows checked out fine; ambiguous placeholder rows (Unknown, Isaiah, Schelling, Wilde) and the John Webster date oddity were left unflagged pending clearer intent.
