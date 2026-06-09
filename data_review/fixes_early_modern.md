# Fixes: early_modern era

Audit of authors born ~1450–1700. Skipped rows that are correct. Notes below, machine-readable JSON at the end.

## Author date / wrong-person matches

- **Thomas More** — shown `1478–1505`. Death year 1505 is wrong; More was executed **6 July 1535**. Birth 1478 is correct. (Utopia=1516 is fine.) HIGH.
- **Francisco Cervantes de Salazar** — shown `1547–1616`, i.e. the dates of *Miguel de Cervantes*. This is a different person: the Toledo-born humanist who taught in Mexico, **c.1514–1575**. Wrong-person match. HIGH.
- **Edmund Spenser** — birth shown `None`. Spenser was born **c.1552** (died 1599, which is present). Filling in the missing birth year. HIGH.

No modern-birth-year wrong-person matches (e.g. the John Webster=1930 type) were found in this batch; all early-modern figures carry plausible early-modern dates except the three above.

## Misplaced ancient figures (year field only — dates already null)

Several classical authors landed in this 1450–1700 batch because of a stray `yr=` value (1595/1676/1692 etc.), but their birth/death are already `None–None`, so no date fix is emitted. Noted for awareness, not actionable as author_dates: **Anacreon** (yr=1676), **Ausonius** (yr=1595), **Stilpo** (yr=1595), **Sappho** (yr=1692), **Quintus Curtius Rufus** (yr=1595), **Leucippus** (yr=1676). These are ancient Greek/Roman, not early-modern; the `yr` is almost certainly a publication/edition artifact and misplaces them on the time axis, but the underlying birth/death are correctly null.

## Book years: modern edition/translation instead of original publication

- **Francis Bacon** — "Essays=2018" → original **1597** (or 1625 final ed.). The row already lists "Essays of Francis Bacon=1597"; 2018 is a reprint. HIGH.
- **Blaise Pascal** — "The Physical Treatises of Pascal=1937" → these treatises (on vacuum/equilibrium of liquids) date to **1663** (posthumous). 1937 is the English translation. HIGH.
- **Emanuel Swedenborg** — "True Christian Religion, Vol 1=1936" → original *Vera Christiana Religio* **1771**. And "The Mystical Works of Emanuel Swedenborg=1907" is a 20th-c. compilation; underlying works are 18th c. I fix the True Christian Religion year (1771); the "Mystical Works" anthology has no single canonical year, flagged low.
- **Giovanni Pico della Mirandola** — "De hominis dignitate. Heptaplus. De ente et uno=1942" → 1942 is a modern critical edition. *Oratio de hominis dignitate* was written 1486, *Heptaplus* 1489. Using **1486**. Also "Opera omnia=1496" is the posthumous first edition (fine, near death 1494).
- **William Congreve** — "The Mourning Bride=2008" → first performed/published **1697**. 2008 is a reprint. HIGH.

## Book years: First Folio / posthumous year instead of composition

- **William Shakespeare** — "Macbeth=1623" → composed **c.1606**; 1623 is the First Folio (first print, posthumous-of-publication but Shakespeare d.1616). "The Winter's Tale=1623" → composed **c.1611**, also First Folio. These post-date... well within life, but the year shown is the Folio print, not the play. Medium confidence on exact composition years.
- **Christopher Marlowe** — "Doctor Faustus=1588" and "The Tragical History of Doctor Faustus=1604" both appear; 1604 is the (A-text) first print, after Marlowe's death (1593). Faustus was written **c.1592**. The 1588 entry is closer. Leaving as-is (duplicate listing); no single clean fix. Noted only.

## Foreign / non-canonical titles → canonical English

- **Voltaire** — "Dictionnaire Philosophique" → *Philosophical Dictionary*; "La Princesse de Babylone" → *The Princess of Babylon*; "Histoire de Charles XII" → *History of Charles XII*; "Siècle de Louis XIV" → *The Age of Louis XIV*.
- **Leibniz** — "La Monadologie" → *The Monadology*.
- **Erasmus** — "MORIAE ENCOMIUM OR, THE PRAISE OF FOLLY" → *The Praise of Folly*; "Adagia. Lateinisch / Deutsch" → *Adages* (Adagia).
- **Tasso** — "Gerusalemme liberata" → *Jerusalem Delivered*; "Gerusalemme Conquistata" → *Jerusalem Conquered*.
- **Galileo** — "Dialogo sopra i due massimi sistemi del mondo" → *Dialogue Concerning the Two Chief World Systems*.
- **Martin Luther** — "Sendbrief von Dolmetschen" → *On Translating: An Open Letter*.
- **Copernicus** — "De hypothesibus motuum coelestium commentariolus" → *Commentariolus* (Little Commentary).
- **Montesquieu** — "De L'esprit Des Lois, Tome 1" → *The Spirit of the Laws*.
- **Albrecht Dürer** — "Vier Bücher von Menschlicher Proportion" → *Four Books on Human Proportion*.
- **Jean Bodin** — "Methodus ad facilem historiarum cognitionem" → *Method for the Easy Comprehension of History*; "De la démonomanie des sorciers" → *On the Demon-Mania of Witches*.
- **Agrippa** — "De occulta philosophia libri tres" → *Three Books of Occult Philosophy*; "De Incertitudine et Vanitate Scientiarum" → *On the Uncertainty and Vanity of the Sciences*.
- **Giordano Bruno** — "De la causa, principio e uno" → *Cause, Principle and Unity*; "La cena de le ceneri" → *The Ash Wednesday Supper*; "Spaccio della bestia trionfante" → *The Expulsion of the Triumphant Beast*.
- **Kircher** — "Ars Magna Lucis et Umbrae" → *The Great Art of Light and Shadow*; "Turris Babel" → *Tower of Babel*; "Iter extaticum coeleste" → *Ecstatic Celestial Journey*; "Mundus subterraneus" → *The Subterranean World*.
- **Barthélemy d'Herbelot** — "Bibliothèque orientale..." → *Oriental Library* (Bibliothèque orientale).
- **Bossuet** — "Maximes et Réflexions sur la Comédie" → *Maxims and Reflections on Comedy*.
- **St. John of the Cross** — "The Ascent of Mount Carmel" is already canonical English (fine).

(I emit `title` fixes only for the clearest, highest-value translations to avoid noise; the full list above is for the human reviewer.)

## Name canonical form / duplicate splits

- **Miguel de Cervantes Saavedra** vs **Miguel de Cervantes** — same person, split into two nodes. Canonical: *Miguel de Cervantes*. (Note: *Francisco* Cervantes de Salazar is a genuinely different person — see above.)
- **René Descartes** vs **Rene Descartes** — duplicate (accent variant), same person.
- **François Rabelais** vs **Francois Rabelais** — duplicate (accent variant).
- **Niccolò Machiavelli** vs **Niccolo Machiavelli** — duplicate (accent variant).
- **Blaise Pascal** vs **Pascal** — duplicate; canonical *Blaise Pascal*.
- These are dedupe issues rather than single-field fixes; flagged as `name` type where a canonical form is clear.

## Nationality

- **Baruch Spinoza** — listed Dutch/germanic. Spinoza was Dutch (born Amsterdam) of Portuguese-Sephardic descent; "Dutch" is acceptable. No change.
- **Erasmus** — listed Dutch/germanic. Correct (born Rotterdam). No change.
- **Justus Lipsius** — listed Flemish. Correct (born Overijse, Brabant). No change.
- **Hugo Grotius** — listed Dutch. Correct. No change.
- No confident nationality errors found.

```json
{"fixes": [
  {"name": "Thomas More", "type": "author_dates", "birth_year": 1478, "death_year": 1535, "confidence": "high", "reason": "death 1505 wrong; More executed 1535"},
  {"name": "Francisco Cervantes de Salazar", "type": "author_dates", "birth_year": 1514, "death_year": 1575, "confidence": "high", "reason": "wrong-person: had Miguel de Cervantes' dates 1547-1616; this is the Toledo/Mexico humanist c.1514-1575"},
  {"name": "Edmund Spenser", "type": "author_dates", "birth_year": 1552, "death_year": 1599, "confidence": "high", "reason": "missing birth year; Spenser b. c.1552"},
  {"name": "Francis Bacon", "type": "book_year", "book_title": "Essays=2018", "current": 2018, "correct": 1597, "confidence": "high", "reason": "2018 is a reprint; Bacon's Essays first 1597"},
  {"name": "Blaise Pascal", "type": "book_year", "book_title": "The Physical Treatises of Pascal=1937", "current": 1937, "correct": 1663, "confidence": "high", "reason": "1937 English translation; treatises pub. posthumously 1663"},
  {"name": "Emanuel Swedenborg", "type": "book_year", "book_title": "True Christian Religion, Vol 1=1936", "current": 1936, "correct": 1771, "confidence": "high", "reason": "1936 is translation; Vera Christiana Religio 1771"},
  {"name": "Giovanni Pico della Mirandola", "type": "book_year", "book_title": "De hominis dignitate. Heptaplus. De ente et uno=1942", "current": 1942, "correct": 1486, "confidence": "high", "reason": "1942 modern critical edition; Oratio de hominis dignitate 1486"},
  {"name": "William Congreve", "type": "book_year", "book_title": "The Mourning Bride=2008", "current": 2008, "correct": 1697, "confidence": "high", "reason": "2008 reprint; first performed/published 1697"},
  {"name": "William Shakespeare", "type": "book_year", "book_title": "Macbeth=1623", "current": 1623, "correct": 1606, "confidence": "medium", "reason": "1623 is First Folio print; composed c.1606"},
  {"name": "William Shakespeare", "type": "book_year", "book_title": "The Winter's Tale=1623", "current": 1623, "correct": 1611, "confidence": "medium", "reason": "1623 is First Folio print; composed c.1611"},
  {"name": "Voltaire", "type": "title", "book_title": "Dictionnaire Philosophique=1764", "correct": "Philosophical Dictionary", "confidence": "high", "reason": "French title -> canonical English"},
  {"name": "Voltaire", "type": "title", "book_title": "Histoire de Charles XII=1731", "correct": "History of Charles XII", "confidence": "high", "reason": "French title -> canonical English"},
  {"name": "Voltaire", "type": "title", "book_title": "Siècle de Louis XIV=1751", "correct": "The Age of Louis XIV", "confidence": "high", "reason": "French title -> canonical English"},
  {"name": "Voltaire", "type": "title", "book_title": "La Princesse de Babylone=1768", "correct": "The Princess of Babylon", "confidence": "high", "reason": "French title -> canonical English"},
  {"name": "Gottfried Wilhelm Leibniz", "type": "title", "book_title": "La Monadologie=1714", "correct": "The Monadology", "confidence": "high", "reason": "French title -> canonical English"},
  {"name": "Erasmus", "type": "title", "book_title": "MORIAE ENCOMIUM OR, THE PRAISE OF FOLLY=1508", "correct": "The Praise of Folly", "confidence": "high", "reason": "Latin/caps title -> canonical English"},
  {"name": "Erasmus", "type": "title", "book_title": "Adagia. Lateinisch / Deutsch=1536", "correct": "Adages", "confidence": "high", "reason": "Latin/German edition title -> canonical English"},
  {"name": "Torquato Tasso", "type": "title", "book_title": "Gerusalemme liberata=1581", "correct": "Jerusalem Delivered", "confidence": "high", "reason": "Italian title -> canonical English"},
  {"name": "Torquato Tasso", "type": "title", "book_title": "Gerusalemme Conquistata=1593", "correct": "Jerusalem Conquered", "confidence": "high", "reason": "Italian title -> canonical English"},
  {"name": "Galileo Galilei", "type": "title", "book_title": "Dialogo sopra i due massimi sistemi del mondo=1632", "correct": "Dialogue Concerning the Two Chief World Systems", "confidence": "high", "reason": "Italian title -> canonical English"},
  {"name": "Martin Luther", "type": "title", "book_title": "Sendbrief von Dolmetschen=1530", "correct": "On Translating: An Open Letter", "confidence": "high", "reason": "German title -> canonical English"},
  {"name": "Nicolaus Copernicus", "type": "title", "book_title": "De hypothesibus motuum coelestium commentariolus=1514", "correct": "Commentariolus", "confidence": "high", "reason": "Latin title -> conventional short Latin/English name"},
  {"name": "Montesquieu", "type": "title", "book_title": "De L'esprit Des Lois, Tome 1=1748", "correct": "The Spirit of the Laws", "confidence": "high", "reason": "French title -> canonical English"},
  {"name": "Albrecht Dürer", "type": "title", "book_title": "Vier Bücher von Menschlicher Proportion=1528", "correct": "Four Books on Human Proportion", "confidence": "high", "reason": "German title -> canonical English"},
  {"name": "Jean Bodin", "type": "title", "book_title": "Methodus ad facilem historiarum cognitionem=1566", "correct": "Method for the Easy Comprehension of History", "confidence": "high", "reason": "Latin title -> canonical English"},
  {"name": "Jean Bodin", "type": "title", "book_title": "De la démonomanie des sorciers=1580", "correct": "On the Demon-Mania of Witches", "confidence": "high", "reason": "French title -> canonical English"},
  {"name": "Heinrich Cornelius Agrippa von Nettesheim", "type": "title", "book_title": "De occulta philosophia libri tres=1533", "correct": "Three Books of Occult Philosophy", "confidence": "high", "reason": "Latin title -> canonical English"},
  {"name": "Giordano Bruno", "type": "title", "book_title": "La cena de le ceneri=1584", "correct": "The Ash Wednesday Supper", "confidence": "high", "reason": "Italian title -> canonical English"},
  {"name": "Giordano Bruno", "type": "title", "book_title": "Spaccio della bestia trionfante=1584", "correct": "The Expulsion of the Triumphant Beast", "confidence": "high", "reason": "Italian title -> canonical English"},
  {"name": "Giordano Bruno", "type": "title", "book_title": "De la causa, principio e uno=1584", "correct": "Cause, Principle and Unity", "confidence": "high", "reason": "Italian title -> canonical English"},
  {"name": "Athanasius Kircher", "type": "title", "book_title": "Mundus subterraneus=1664", "correct": "The Subterranean World", "confidence": "high", "reason": "Latin title -> canonical English"},
  {"name": "Athanasius Kircher", "type": "title", "book_title": "Ars Magna Lucis et Umbrae=1646", "correct": "The Great Art of Light and Shadow", "confidence": "high", "reason": "Latin title -> canonical English"},
  {"name": "Jacques-Bénigne Bossuet", "type": "title", "book_title": "Maximes et Réflexions sur la Comédie=1694", "correct": "Maxims and Reflections on Comedy", "confidence": "high", "reason": "French title -> canonical English"},
  {"name": "Miguel de Cervantes Saavedra", "type": "name", "correct": "Miguel de Cervantes", "confidence": "high", "reason": "duplicate of Miguel de Cervantes; canonical short form"},
  {"name": "Rene Descartes", "type": "name", "correct": "René Descartes", "confidence": "high", "reason": "accent-variant duplicate of René Descartes"},
  {"name": "Francois Rabelais", "type": "name", "correct": "François Rabelais", "confidence": "high", "reason": "accent-variant duplicate of François Rabelais"},
  {"name": "Niccolo Machiavelli", "type": "name", "correct": "Niccolò Machiavelli", "confidence": "high", "reason": "accent-variant duplicate of Niccolò Machiavelli"},
  {"name": "Pascal", "type": "name", "correct": "Blaise Pascal", "confidence": "high", "reason": "duplicate of Blaise Pascal; canonical full name"}
]}
```

## Summary

Found **39 fixes**: 3 author-date corrections (Thomas More death 1505→1535; Francisco Cervantes de Salazar wrong-person — had Miguel de Cervantes' dates, corrected to c.1514–1575; Edmund Spenser missing birth → c.1552), 6 book-year corrections (Bacon 2018, Pascal 1937, Swedenborg 1936, Pico 1942, Congreve 2008 — all modern editions/translations; plus two Shakespeare First-Folio years at medium confidence), 21 foreign/non-canonical title normalizations (French/Italian/German/Latin → canonical English across Voltaire, Leibniz, Erasmus, Tasso, Galileo, Luther, Copernicus, Montesquieu, Dürer, Bodin, Agrippa, Bruno, Kircher, Bossuet), and 5 name/duplicate fixes (Cervantes, Descartes, Rabelais, Machiavelli, Pascal accent/duplicate splits). No confident nationality errors, and notably no modern-birth-year wrong-person matches in this batch (the one wrong-person case, Cervantes de Salazar, was assigned another early-modern figure's dates, not a 20th-century one). Six ancient authors (Anacreon, Sappho, Ausonius, Stilpo, Leucippus, Quintus Curtius Rufus) are misplaced into this era via a stray publication-year field but already carry null birth/death, so no date fix is emitted.
