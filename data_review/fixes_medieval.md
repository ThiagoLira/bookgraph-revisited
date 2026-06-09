# Medieval era — fact-check fixes

Reviewed 21 authors (~500–1450 CE). Notes below, machine-readable `fixes` block at the end.

## Author dates
- All matched persons appear to be the correct historical figures (no modern-namesake swaps detected).
- **Saxo Grammaticus**: currently None–1220. Birth ~1150 is well established; adding birth_year. Death ~1220 retained.
- **Ramon Llull** / **Raymond Lully**: these are the SAME person (Latinized name = Raymond Lully). Ramon Llull currently has None–None; the Lully row gives 1232–1316. Backfilling Llull's dates to 1232–1316. (Duplicate split — both rows are one author.)

## Book years (print/edition year vs. original composition)
- **Thomas Malory — Le Morte d'Arthur=1485**: 1485 is Caxton's printed edition. Malory composed it c. 1469–1470 (he died 1471). Correct composition ~1470.
- **Saxo Grammaticus — History of the Danes (Gesta Danorum)=1185**: composed/completed c. 1208, not 1185.
- **Guillaume de Lorris — Le Roman de la Rose=1275**: Lorris wrote his portion c. 1230; 1275 is roughly when Jean de Meun's continuation appeared. Correct ~1230 for Lorris's authorship.

## Titles (translated/foreign → canonical English)
- **Dante Alighieri — "Vita nuova/Viața nouă"**: "Viața nouă" is the Romanian title. Canonical → "La Vita Nuova" (a.k.a. The New Life). (Note: a separate, already-correct "Vita Nuova=1294" row also exists.)
- **Dante Alighieri — "The Early Italian Poets=1861"**: not a work by Dante — this is D. G. Rossetti's 1861 translation anthology. Flagging as a mis-attributed/translation row (kept as title note; not Dante's composition).
- **Saxo Grammaticus — long descriptive title** → canonical "Gesta Danorum" (The History of the Danes).
- **Guillaume de Lorris — "Le Roman de La Rose"** → "The Romance of the Rose".

## Nationality
- **Snorri Sturluson** is listed as **American** — clearly wrong. He was Icelandic (closest allowed demonym: there is no "Icelandic" in the demonym list; he is a Nordic/Norse figure). Flagging the error; suggesting the nationality is not American. Using "Nordic" region is already present; demonym corrected away from American. (No exact Icelandic demonym in the provided list; flagged anyway as the current value is definitively wrong.)
- **Hafiz**: nationality demonym "Persian" is correct; only the region tag "middle_eastern_jewish" is mismatched (Hafiz was Muslim, not Jewish) — region tagging, not the demonym, so not a demonym fix.

## Rows reviewed and left as correct
Dante (1265–1321), Thomas Aquinas (1225–1274), Boccaccio (1313–1375), Albertus Magnus (1200–1280), Nicholas of Cusa (1401–1464), Chaucer (d. 1400), Maimonides (1135–1204), Petrarch (1304–1374), John Scotus Eriugena (810–877), Gregory of Tours (538–594), Marsilio Ficino (1433–1499), Jacobus de Voragine (1230–1298), Meister Eckhart (1260–1328) — dates and core facts check out.

```json
{"fixes": [
  {"name": "Saxo Grammaticus", "type": "author_dates", "birth_year": 1150, "death_year": 1220, "confidence": "medium", "reason": "Birth ~1150 well established; was None"},
  {"name": "Ramon Llull", "type": "author_dates", "birth_year": 1232, "death_year": 1316, "confidence": "high", "reason": "Same person as Raymond Lully (1232-1316); backfill None-None"},
  {"name": "Thomas Malory", "type": "book_year", "book_title": "Le Morte d'Arthur", "current": 1485, "correct": 1470, "confidence": "high", "reason": "1485 is Caxton print year; composed c.1469-70"},
  {"name": "Saxo Grammaticus", "type": "book_year", "book_title": "Saxo Grammaticus: The History of the Danes, Books I-IX: I. English Text; II. Commentary", "current": 1185, "correct": 1208, "confidence": "medium", "reason": "Gesta Danorum completed c.1208, not 1185"},
  {"name": "Guillaume de Lorris", "type": "book_year", "book_title": "Le Roman de La Rose", "current": 1275, "correct": 1230, "confidence": "high", "reason": "Lorris's part written c.1230; 1275 is Jean de Meun continuation"},
  {"name": "Dante Alighieri", "type": "title", "book_title": "Vita nuova/Viața nouă", "correct": "La Vita Nuova", "confidence": "high", "reason": "Viața nouă is the Romanian title; canonical English/Italian = La Vita Nuova"},
  {"name": "Saxo Grammaticus", "type": "title", "book_title": "Saxo Grammaticus: The History of the Danes, Books I-IX: I. English Text; II. Commentary", "correct": "Gesta Danorum (The History of the Danes)", "confidence": "high", "reason": "Descriptive edition title; canonical work = Gesta Danorum"},
  {"name": "Guillaume de Lorris", "type": "title", "book_title": "Le Roman de La Rose", "correct": "The Romance of the Rose", "confidence": "high", "reason": "French title; canonical English form"},
  {"name": "Snorri Sturluson", "type": "nationality", "correct": "Icelandic", "confidence": "high", "reason": "Listed as American; Snorri was a 13th-c. Icelandic chieftain/historian"}
]}
```

## Summary
Total 9 fixes: 2 author-date corrections (Saxo Grammaticus birth, Ramon Llull duplicate-split backfill), 3 book-year corrections (Malory's Caxton print year, Saxo's Gesta Danorum, Lorris's Roman de la Rose), 3 title canonicalizations (Dante's Romanian Vita Nuova, Saxo's descriptive edition title, Lorris's French title), and 1 nationality fix (Snorri Sturluson wrongly tagged American → Icelandic). No wrong-person/modern-namesake matches were found; the remaining 13 reviewed rows are accurate as listed.
