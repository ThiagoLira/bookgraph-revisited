# Antiquity era — fact-check fixes

Audit of `era_antiquity.md` (113 authors, birth before 500 CE). Below are the
notable corrections, grouped by error type. Rows that looked correct were
skipped.

## 1. Wrong-person match (modern namesake placed in antiquity)

- **George Steiner** — listed at `-570–-490` (Pythagoras/Confucius-era) and
  region "American", but the attached book is *After Babel: Aspects of Language
  and Translation = 1975*. This is the 20th-century literary critic Francis
  George Steiner (1929–2020), wrongly matched into antiquity. He does not belong
  in this era at all; corrected to his real dates 1929/2020.

## 2. BCE sign errors (work stored positive but is BCE)

Tell-tale: a "year" later than the author's death year, for a pre-CE author.

- **Marcus Tullius Cicero** (d. 43 BCE): `Academica=45` → `-45`;
  `Epistulae ad Familiares=44` → `-44`; `De Petitione Consulatus=64` → `-64`
  (the consular-campaign handbook, 64 BCE). Also `De Divinatione=-70` is the
  wrong BCE year — the work is 44 BCE → `-44` (medium confidence).
- **Terence** (d. 159 BCE): the second `Adelphoe=160` is stored positive → `-160`
  (the play premiered 160 BCE; the other `Adelphoe=-160` entry is already right).

## 3. Wrong book year (edition / translation / modern anthology year)

Original composition years substituted for the printing/translation year shown.

- **Homer** — `The Iliad=1598` (a 1598 printing) → `-800`.
- **Augustine of Hippo** — `Erbauliche Schriften=1914` (a 1914 German edition;
  also a foreign title) → `400`.
- **Horace** — `Satires I=1993` (modern translation) → `-35` (Satires Book I,
  c. 35 BCE).
- **Cicero** — `The Academic Questions: Treatise de Finibus, and Tusculan
  Disputations=2006` → `-45`.
- **Plutarch** — `Moralia 15: Fragments=1928` → `100`; `Plutarch's Lives IX=1968`
  → `100`.
- **Pliny the Elder** — `Natural History, Volume IX: Books 33-35=1952` → `77`.
- **Tertullian** — `Latin Christianity: Tertullian (Ante-Nicene Fathers 3)=1867`
  → `200`.
- **Suetonius** — `Divus Augustus=1883` → `121` (part of De vita Caesarum).
- **Jerome** — `Select Letters=1933` → `400` (approx., letters c. 380–419).
- **Plautus** — `Roman Comedy: Five Plays ... =2010` (modern anthology) → `-200`.
- **Gaius Julius Caesar** — `Alexandrian War, African War, Spanish War=1955`
  → `-45` (the Bellum Alexandrinum / Africum / Hispaniense, c. 47–45 BCE).
- **Saint Jerome** — `Adversus Jovinianum=1400` (printing year) → `393`.
- **Dionysius of Halicarnassus** — `Dionysius of Halicarnassus: Roman
  Antiquities, Volume I ... (Loeb ... No. 319)=1937` → `-7` (work c. 7 BCE).
- **Longinus** — `On the Sublime=-100`; the treatise is generally dated to the
  1st century CE → `50` (low confidence given disputed authorship/date).

## 4. Translated / foreign-language titles

- **Homer** — `Odyssée` → `Odyssey`.
- **Hesiod** — `Theogonie` → `Theogony`.
- **Augustine of Hippo** — `Erbauliche Schriften` → `Edifying Writings`
  (also a wrong-year edition, handled above).

## 5. Nationality fixes

- **Jerome** — tagged `British/british_isles`. Jerome was from Stridon in Roman
  Dalmatia and is a Latin Church Father → `Latin`.

## Notes / deliberately skipped

- "Roman/ancient_classical" on Latin-writing Greeks/provincials (Tertullian,
  Apuleius) is acceptable and left alone.
- Lao Tzu's `Tao Te Ching=-349` is consistent with the common 4th-c.-BCE dating
  of the text; left as-is.
- Ovid appears under three name variants (`Ovid`, `Publius Ovidius Naso`,
  `Publius Ovidius Naso (Ovid)`) and Seneca/Livy/Caesar/Lucan likewise have
  Latin-name duplicate rows; flagged here only as a note, not as data fixes,
  since dates are internally consistent.

```json
{"fixes": [
  {"name": "George Steiner", "type": "author_dates", "birth_year": 1929, "death_year": 2020, "confidence": "high", "reason": "Dates -570/-490 belong to no real ancient figure; rows attach 'After Babel=1975', the 20th-c. critic Francis George Steiner (1929-2020)."},

  {"name": "Marcus Tullius Cicero", "type": "book_year", "book_title": "Academica", "current": 45, "correct": -45, "confidence": "high", "reason": "Cicero died 43 BCE; work is 45 BCE, stored positive."},
  {"name": "Marcus Tullius Cicero", "type": "book_year", "book_title": "Epistulae ad Familiares", "current": 44, "correct": -44, "confidence": "high", "reason": "BCE letters stored positive."},
  {"name": "Marcus Tullius Cicero", "type": "book_year", "book_title": "De Petitione Consulatus", "current": 64, "correct": -64, "confidence": "high", "reason": "Consular-campaign handbook of 64 BCE, stored positive."},
  {"name": "Marcus Tullius Cicero", "type": "book_year", "book_title": "De Divinatione", "current": -70, "correct": -44, "confidence": "medium", "reason": "De Divinatione was written c. 44 BCE, not 70 BCE."},
  {"name": "Terence", "type": "book_year", "book_title": "Adelphoe", "current": 160, "correct": -160, "confidence": "high", "reason": "Play premiered 160 BCE; duplicate row stores it positive."},

  {"name": "Homer", "type": "book_year", "book_title": "The Iliad", "current": 1598, "correct": -800, "confidence": "high", "reason": "1598 is a printing year, not composition."},
  {"name": "Augustine of Hippo", "type": "book_year", "book_title": "Erbauliche Schriften", "current": 1914, "correct": 400, "confidence": "high", "reason": "1914 German edition year, not original."},
  {"name": "Horace", "type": "book_year", "book_title": "Satires I", "current": 1993, "correct": -35, "confidence": "high", "reason": "1993 is a modern translation; Satires Book I is c. 35 BCE."},
  {"name": "Marcus Tullius Cicero", "type": "book_year", "book_title": "The Academic Questions: Treatise de Finibus, and Tusculan Disputations", "current": 2006, "correct": -45, "confidence": "high", "reason": "2006 edition year; the works date to c. 45 BCE."},
  {"name": "Plutarch", "type": "book_year", "book_title": "Moralia 15: Fragments", "current": 1928, "correct": 100, "confidence": "high", "reason": "1928 Loeb volume year, not original."},
  {"name": "Plutarch", "type": "book_year", "book_title": "Plutarch's Lives IX", "current": 1968, "correct": 100, "confidence": "high", "reason": "1968 edition year, not original."},
  {"name": "Pliny the Elder", "type": "book_year", "book_title": "Natural History, Volume IX: Books 33-35", "current": 1952, "correct": 77, "confidence": "high", "reason": "1952 Loeb volume; Naturalis Historia is c. 77 CE."},
  {"name": "Tertullian", "type": "book_year", "book_title": "Latin Christianity: Tertullian (Ante-Nicene Fathers 3)", "current": 1867, "correct": 200, "confidence": "high", "reason": "1867 is the Ante-Nicene Fathers edition year."},
  {"name": "Suetonius", "type": "book_year", "book_title": "Divus Augustus", "current": 1883, "correct": 121, "confidence": "high", "reason": "1883 printing; De vita Caesarum is c. 121 CE."},
  {"name": "Jerome", "type": "book_year", "book_title": "Select Letters", "current": 1933, "correct": 400, "confidence": "medium", "reason": "1933 Loeb edition; letters span c. 380-419 CE."},
  {"name": "Plautus", "type": "book_year", "book_title": "Roman Comedy: Five Plays by Plautus and Terence: Menaechmi, Rudens and Truculentus by Plautus; Adelphoe and Eunuchus by Terence", "current": 2010, "correct": -200, "confidence": "medium", "reason": "2010 modern anthology; Plautus's plays are c. 205-184 BCE."},
  {"name": "Gaius Julius Caesar", "type": "book_year", "book_title": "Alexandrian War, African War, Spanish War", "current": 1955, "correct": -45, "confidence": "high", "reason": "1955 Loeb; the Bellum Alexandrinum/Africum/Hispaniense are c. 47-45 BCE."},
  {"name": "Saint Jerome", "type": "book_year", "book_title": "Adversus Jovinianum", "current": 1400, "correct": 393, "confidence": "high", "reason": "1400 printing year; Adversus Jovinianum written 393 CE."},
  {"name": "Dionysius of Halicarnassus", "type": "book_year", "book_title": "Dionysius of Halicarnassus: Roman Antiquities, Volume I, Books 1-2 (Loeb Classical Library No. 319)", "current": 1937, "correct": -7, "confidence": "high", "reason": "1937 Loeb; Roman Antiquities published c. 7 BCE."},
  {"name": "Longinus", "type": "book_year", "book_title": "On the Sublime", "current": -100, "correct": 50, "confidence": "low", "reason": "On the Sublime is generally dated to the 1st century CE, not 100 BCE; authorship/date disputed."},

  {"name": "Homer", "type": "title", "book_title": "Odyssée", "correct": "Odyssey", "confidence": "high", "reason": "French title; canonical English is Odyssey."},
  {"name": "Hesiod", "type": "title", "book_title": "Theogonie", "correct": "Theogony", "confidence": "high", "reason": "German/French spelling; canonical English is Theogony."},
  {"name": "Augustine of Hippo", "type": "title", "book_title": "Erbauliche Schriften", "correct": "Edifying Writings", "confidence": "medium", "reason": "German title from a 1914 edition; not a canonical Augustine work title in English."},

  {"name": "Jerome", "type": "nationality", "correct": "Latin", "confidence": "high", "reason": "Tagged British; Jerome was from Stridon in Roman Dalmatia, a Latin Church Father."}
]}
```
