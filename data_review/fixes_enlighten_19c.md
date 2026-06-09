# Fixes: enlighten_19c

Human-readable audit notes. Confident findings only. Approximate years acceptable.

## High-impact errors (top-cited / egregious)

- **Jean-Jacques Rousseau** (line 9): nationality "Roman/ancient_classical" is clearly wrong — he was a French-language philosopher born in Geneva, conventionally classed French. Dates 1712–1778 correct. *Confessions=1773* is wrong: published posthumously in 1782 → correct 1782.
- **Richard "Wagner"** (line 123): listed as "1813–None | Greek/ancient_classical | Wagner". This is Richard Wagner, German composer, 1813–1883. Death year and nationality both wrong; this is a duplicate of the proper "Richard Wagner" row (line 179). Fix dates + nationality.
- **Moses** (line 187): "1730–1788 | German | Moses". This is Moses Mendelssohn, German-Jewish Enlightenment philosopher, 1729–1786. Name truncated to "Moses". Correct dates 1729–1786; canonical name Moses Mendelssohn.
- **Geoffrey of Monmouth** (line 188): "None–1155, yr=1866, Welsh". Geoffrey of Monmouth was a 12th-c. chronicler (c.1095–c.1155). The yr=1866 is a misplacement artifact; born ~1095. (Belongs in medieval slice, not here.)
- **Theocritus** (line 190) and **Menander** (line 197): both "Greek/ancient_classical, yr=1862". These are ancient Greek poets/dramatists (Theocritus 3rd c. BCE; Menander c.342–c.290 BCE). Misplaced into 19th-c. slice. Provide approximate BCE dates.
- **Benjamin Franklin** (line 121): "1706–1730". Death year wrong — Franklin died 1790. Correct 1706–1790.

## Wrong book years (modern edition/reprint instead of original publication)

- **Dostoevsky** (line 15): *The Devils=2025* — modern reprint; The Devils is the alt-title of Demons (orig. 1871–72) → 1872.
- **Immanuel Kant** (line 11): *Kant's Political Writings=1970* — modern anthology; the political essays are 18th-c. Flagging as edition year (anthology, original ~1784–1795). Low confidence on a single "correct" year; leaving as anthology note (no fix).
- **Friedrich Nietzsche** (line 7): *Ecce Homo=2011* — written 1888, first published 1908 → 1908. *The Will to Power=1901* ok (posthumous compilation).
- **Herbert Spencer** (line 48): *First Principles=1962* — modern reprint; originally 1862 → 1862.
- **Marcel Proust** (line 14): *Remembrance of Things Past: v. 2/2=1927* and *Le Temps retrouvé=1927* — Le Temps retrouvé (Time Regained) published posthumously 1927, ok.
- **Percy Bysshe Shelley** (line 65): *A Defence Of Poetry=1595* — impossible (Shelley b.1792); written 1821, published 1840 → 1840.
- **Pierre-Simon Laplace** (line 115): *A Philosophical Essay on Probabilities=1994* — modern reprint; original (Essai philosophique sur les probabilités) 1814 → 1814.
- **F. H. Bradley** (line 158): *Appearance and Reality=1994* — reprint; original 1893 → 1893.
- **Benjamin Constant** (line 127): *Political Writings=1988* — modern anthology (Cambridge ed.). Low confidence on single year; no fix.
- **William James** (line 96): *Some Problems of Philosophy=2020* — reprint; published posthumously 1911 → 1911.
- **George Santayana** (line 159): *Three Philosophical Poets=1953* — reprint; original 1910 → 1910.
- **Wallace Stevens** (line 82): *The Auroras of Autumn=1947* — the collection was published 1950 (title poem 1948). → 1950.
- **W.B. Yeats** (line 185): *Sailing to Byzantium=1995* — poem published 1928 → 1928.
- **Ralph Waldo Emerson** (line 59): *Divinity School Address=2007* — delivered/published 1838 → 1838.

## Translated / foreign titles → canonical English

- **Goethe** (line 10): *Römische Elegien* → "Roman Elegies"; *West-Ostlicher Divan* → "West-Eastern Divan"; *Kampagne in Frankreich* → "Campaign in France"; *Literarischer Sansculottismus* → "Literary Sansculottism".
- **Stendhal** (line 19): *Le Rouge et le Noir* → "The Red and the Black"; *Souvenirs d'égotisme* → "Memoirs of an Egotist".
- **Proust** (line 14): *Du côté de chez Swann* → "Swann's Way"; *Le Temps retrouvé (À la recherche du temps perdu #7)* → "Time Regained".
- **Victor Hugo** (line 42): *Les Misérables* (standard untranslated, keep); *La Légende des Siècles* → "The Legend of the Ages".
- **Baudelaire** (line 21): *Les Fleurs du mal* → "The Flowers of Evil" (canonical English).
- **Charles Baudelaire** dup-title in same row already.
- **Heinrich Heine** (line 35): *Deutschland: A Winter's Tale* is already English-ish; fine.
- **Diderot** (line 36): *Le neveu de Rameau* → "Rameau's Nephew".
- **Rilke** (line 27): *Duineser Elegien* → "Duino Elegies".
- **Mallarmé** (line 61): *Sur l'évolution littéraire: Réponse à l'enquête de Jules Huret* → keep (no standard English title; minor).
- **Buffon** (line 86): *Histoire Naturelle, Générale et Particulière* → "Natural History, General and Particular".
- **Simmel** (line 87): *Soziologie* → "Sociology".
- **Hugo / Balzac** (line 126): *Le Père Goriot* → "Father Goriot" (often kept as "Le Père Goriot"; canonical English "Old Goriot"/"Père Goriot"); *Sarrasine* keep; *La Fille Aux Yeux D'Or* → "The Girl with the Golden Eyes"; *Eugénie Grandet* keep (standard).
- **Gustave Le Bon** (line 125): *Psychologie des Foules* → "The Crowd: A Study of the Popular Mind".
- **Joris-Karl Huysmans** (line 104): *À rebours* → "Against Nature" (duplicate of "Against Nature: A Rebours" in same row).
- **Jules Verne** (line 146): *L'île mystérieuse* → "The Mysterious Island".
- **Chateaubriand** (line 171): *Vie de Rancé* → "The Life of Rancé".
- **Alfred Jarry** (line 172): *Ubu Roi* → "King Ubu" (often kept as Ubu Roi; minor).
- **Leopardi** (line 166): *L'infinito* → "The Infinite"; *Canti* → "Canti" (standard); *Zibaldone* keep.
- **Jung** (line 193): *Wandlungen und Symbole der Libido* → "Psychology of the Unconscious" / later "Symbols of Transformation".
- **Croce** (line 144): *La poesia* → "Poetry"; *Storia dell'estetica* → "History of Aesthetics".
- **Saussure** etc. — no titles listed.
- **Hölderlin**, **Novalis** — no titles.
- **Kleist** (line 107): *Über das Marionettentheater* → "On the Marionette Theatre".

(Many foreign titles are low-priority graph-display issues; the JSON below includes the clearest high-confidence ones.)

## Name canonical form / duplicate splits

- **Fyodor Dostoevsky** (line 15) vs **Fyodor Dostoyevsky** (line 46) vs **Dostoevsky** would be duplicates. Canonical: "Fyodor Dostoevsky".
- **Honoré de Balzac** (line 22) vs **Honore de Balzac** (line 126): same person; canonical "Honoré de Balzac". Line 22 has no books, line 126 has them — duplicate split.
- **Émile Zola** (line 33) vs **Emile Zola** (line 102): duplicate; canonical "Émile Zola".
- **Søren Kierkegaard** (line 34) vs **Soren Kierkegaard** (line 194): duplicate; canonical "Søren Kierkegaard".
- **E.M. Forster** (line 62) vs **E. M. Forster** (line 77): duplicate.
- **G. K. Chesterton** (line 63) vs none — fine.
- **G. H. Hardy** (line 113) vs **G.H. Hardy** (line 114): duplicate.
- **W.B. Yeats** (line 185) vs **W. B. Yeats** (line 201) vs **Yeats** (line 162): triple duplicate; canonical "W. B. Yeats".
- **Carl Jung** (line 105) vs **C.G. Jung** (line 193): duplicate; canonical "Carl Jung".
- **Nathaniel Hawthorne** (line 54) vs **Hawthorne** (line 153): duplicate; "Hawthorne" dates 1809–1871 are WRONG (Hawthorne was 1804–1864) — bad match.
- **Keats** (line 164, 1795–1821, no books) vs **John Keats** (line 68): duplicate.
- **Tennyson** (line 191): canonical "Alfred, Lord Tennyson"; dates 1811–1887 wrong — Tennyson was 1809–1892. Bad match.

## Date errors (wrong-person or transcription)

- **Hawthorne** (line 153): 1809–1871 → should be 1804–1864 (Nathaniel Hawthorne).
- **Tennyson** (line 191): 1811–1887 → should be 1809–1892 (Alfred Tennyson).
- **Robert Spence Hardy** (line 148): 1803–1868 → the Wesleyan missionary/Pali scholar R. Spence Hardy was 1803–1868. Correct, keep. Nationality British ok.
- **Multatuli** (line 138): 1820–1887 — Eduard Douwes Dekker (Multatuli) 1820–1887. Correct.
- **Giovanni Battista Piranesi** (line 163): 1720–1778. Correct; *Le Carceri=1973* is a modern reprint — original etchings c.1750 → ~1750.
- **Ferdinando Galiani** (line 108): 1728–1787. Correct.

## Nationality errors

- **Rousseau** (line 9): "Roman/ancient_classical" → French (Genevan/Swiss; conventionally French).
- **Wagner** (line 123): "Greek/ancient_classical" → German.
- **Theocritus** / **Menander**: Greek is correct (ancient Greek) — but era misplaced; no nationality fix.
- **Nikolai Gogol** (line 50): listed "Ukrainian/slavic". Gogol was born in Ukraine but wrote in Russian and is conventionally classed Russian. Debatable; Ukrainian is defensible — leaving as-is (no fix, low confidence).
- **Multatuli** (line 138), **Huizinga** (line 202): "Dutch/germanic" correct.

```json
{"fixes": [
  {"name": "Jean-Jacques Rousseau", "type": "nationality", "correct": "French", "confidence": "high", "reason": "Genevan/French-language philosopher, not Roman/ancient_classical"},
  {"name": "Jean-Jacques Rousseau", "type": "book_year", "book_title": "Confessions", "current": 1773, "correct": 1782, "confidence": "high", "reason": "Confessions published posthumously 1782"},
  {"name": "Wagner", "type": "author_dates", "birth_year": 1813, "death_year": 1883, "confidence": "high", "reason": "Richard Wagner died 1883; duplicate of Richard Wagner row"},
  {"name": "Wagner", "type": "nationality", "correct": "German", "confidence": "high", "reason": "Richard Wagner was German, not Greek/ancient_classical"},
  {"name": "Moses", "type": "author_dates", "birth_year": 1729, "death_year": 1786, "confidence": "high", "reason": "Moses Mendelssohn lived 1729-1786"},
  {"name": "Geoffrey of Monmouth", "type": "author_dates", "birth_year": 1095, "death_year": 1155, "confidence": "medium", "reason": "12th-century chronicler, b. c.1095; yr=1866 is a misplacement"},
  {"name": "Theocritus", "type": "author_dates", "birth_year": -300, "death_year": -260, "confidence": "medium", "reason": "Ancient Greek poet, 3rd c. BCE; misplaced into 19th c."},
  {"name": "Menander", "type": "author_dates", "birth_year": -342, "death_year": -290, "confidence": "medium", "reason": "Ancient Greek dramatist c.342-c.290 BCE; misplaced"},
  {"name": "Benjamin Franklin", "type": "author_dates", "birth_year": 1706, "death_year": 1790, "confidence": "high", "reason": "Franklin died 1790, not 1730"},
  {"name": "Fyodor Dostoevsky", "type": "book_year", "book_title": "The Devils", "current": 2025, "correct": 1872, "confidence": "high", "reason": "modern reprint; Demons/The Devils orig. 1871-72"},
  {"name": "Friedrich Nietzsche", "type": "book_year", "book_title": "Ecce Homo", "current": 2011, "correct": 1908, "confidence": "high", "reason": "written 1888, first published 1908"},
  {"name": "Herbert Spencer", "type": "book_year", "book_title": "First Principles", "current": 1962, "correct": 1862, "confidence": "high", "reason": "modern reprint; original 1862"},
  {"name": "Percy Bysshe Shelley", "type": "book_year", "book_title": "A Defence Of Poetry", "current": 1595, "correct": 1840, "confidence": "high", "reason": "impossible 1595; written 1821, pub. 1840"},
  {"name": "Pierre-Simon Laplace", "type": "book_year", "book_title": "A Philosophical Essay on Probabilities", "current": 1994, "correct": 1814, "confidence": "high", "reason": "modern reprint; original 1814"},
  {"name": "F. H. Bradley", "type": "book_year", "book_title": "Appearance and Reality", "current": 1994, "correct": 1893, "confidence": "high", "reason": "modern reprint; original 1893"},
  {"name": "William James", "type": "book_year", "book_title": "Some Problems of Philosophy: A Beginning of an Introduction to Philosophy", "current": 2020, "correct": 1911, "confidence": "high", "reason": "modern reprint; posthumous 1911"},
  {"name": "George Santayana", "type": "book_year", "book_title": "Three Philosophical Poets: Lucretius, Dante And Goethe", "current": 1953, "correct": 1910, "confidence": "high", "reason": "modern reprint; original 1910"},
  {"name": "Wallace Stevens", "type": "book_year", "book_title": "The Auroras of Autumn", "current": 1947, "correct": 1950, "confidence": "high", "reason": "collection published 1950"},
  {"name": "W.B. Yeats", "type": "book_year", "book_title": "Sailing to Byzantium", "current": 1995, "correct": 1928, "confidence": "high", "reason": "poem published 1928 (The Tower)"},
  {"name": "Ralph Waldo Emerson", "type": "book_year", "book_title": "Divinity School Address", "current": 2007, "correct": 1838, "confidence": "high", "reason": "delivered/published 1838"},
  {"name": "Giovanni Battista Piranesi", "type": "book_year", "book_title": "Le Carceri", "current": 1973, "correct": 1750, "confidence": "medium", "reason": "modern reprint; etchings c.1750"},
  {"name": "Hawthorne", "type": "author_dates", "birth_year": 1804, "death_year": 1864, "confidence": "high", "reason": "Nathaniel Hawthorne 1804-1864; 1809-1871 is wrong"},
  {"name": "Tennyson", "type": "author_dates", "birth_year": 1809, "death_year": 1892, "confidence": "high", "reason": "Alfred Tennyson 1809-1892; 1811-1887 is wrong"},
  {"name": "Goethe", "type": "title", "book_title": "Römische Elegien", "correct": "Roman Elegies", "confidence": "high", "reason": "German title -> canonical English"},
  {"name": "Goethe", "type": "title", "book_title": "West-Ostlicher Divan", "correct": "West-Eastern Divan", "confidence": "high", "reason": "German title -> canonical English"},
  {"name": "Goethe", "type": "title", "book_title": "Kampagne in Frankreich", "correct": "Campaign in France", "confidence": "high", "reason": "German title -> English"},
  {"name": "Stendhal", "type": "title", "book_title": "Le Rouge et le Noir", "correct": "The Red and the Black", "confidence": "high", "reason": "French title -> canonical English"},
  {"name": "Stendhal", "type": "title", "book_title": "Souvenirs d'égotisme", "correct": "Memoirs of an Egotist", "confidence": "high", "reason": "French title -> canonical English"},
  {"name": "Marcel Proust", "type": "title", "book_title": "Du côté de chez Swann", "correct": "Swann's Way", "confidence": "high", "reason": "French title -> canonical English"},
  {"name": "Marcel Proust", "type": "title", "book_title": "Le Temps retrouvé (À la recherche du temps perdu #7)", "correct": "Time Regained", "confidence": "high", "reason": "French title -> canonical English"},
  {"name": "Charles Baudelaire", "type": "title", "book_title": "Les Fleurs du mal", "correct": "The Flowers of Evil", "confidence": "high", "reason": "French title -> canonical English"},
  {"name": "Denis Diderot", "type": "title", "book_title": "Le neveu de Rameau", "correct": "Rameau's Nephew", "confidence": "high", "reason": "French title -> canonical English"},
  {"name": "Rainer Maria Rilke", "type": "title", "book_title": "Duineser Elegien", "correct": "Duino Elegies", "confidence": "high", "reason": "German title -> canonical English"},
  {"name": "Jules Verne", "type": "title", "book_title": "L'île mystérieuse", "correct": "The Mysterious Island", "confidence": "high", "reason": "French title -> canonical English"},
  {"name": "Gustave Le Bon", "type": "title", "book_title": "Psychologie des Foules", "correct": "The Crowd: A Study of the Popular Mind", "confidence": "high", "reason": "French title -> canonical English"},
  {"name": "Honore de Balzac", "type": "title", "book_title": "La Fille Aux Yeux D'Or", "correct": "The Girl with the Golden Eyes", "confidence": "high", "reason": "French title -> canonical English"},
  {"name": "Victor Hugo", "type": "title", "book_title": "La Légende des Siècles", "correct": "The Legend of the Ages", "confidence": "high", "reason": "French title -> canonical English"},
  {"name": "Georg Simmel", "type": "title", "book_title": "Soziologie", "correct": "Sociology", "confidence": "high", "reason": "German title -> English"},
  {"name": "Heinrich von Kleist", "type": "title", "book_title": "Über das Marionettentheater", "correct": "On the Marionette Theatre", "confidence": "high", "reason": "German title -> English"},
  {"name": "François-René de Chateaubriand", "type": "title", "book_title": "Vie de Rancé", "correct": "The Life of Rancé", "confidence": "high", "reason": "French title -> English"},
  {"name": "Benedetto Croce", "type": "title", "book_title": "Storia dell'estetica", "correct": "History of Aesthetics", "confidence": "medium", "reason": "Italian title -> English"}
]}
```

## Summary

Across the enlighten_19c slice I flagged roughly **41 confident fixes**: **7 author_dates** corrections (Wagner, Moses Mendelssohn, Geoffrey of Monmouth, Theocritus, Menander, Benjamin Franklin, plus bad-match Hawthorne and Tennyson rows = 8 if counting both Hawthorne/Tennyson), **2 nationality** corrections (Rousseau "Roman"→French, Wagner "Greek"→German), **12 book_year** corrections (mostly modern reprint/translation years swapped in for original publication: Dostoevsky 2025, Nietzsche 2011, Spencer 1962, Shelley 1595→1840, Laplace 1994, Bradley 1994, James 2020, Santayana 1953, Stevens 1947→1950, Yeats 1995, Emerson 2007, Piranesi 1973, plus Rousseau's Confessions 1773→1782), and **~17 title** normalizations of German/French/Italian titles to canonical English. Separately noted (not all in JSON) numerous **duplicate-split** name pairs that should merge: Dostoevsky/Dostoyevsky, Honoré/Honore de Balzac, Émile/Emile Zola, Søren/Soren Kierkegaard, the three Yeats rows, two Forster rows, two Hardy rows, Carl/C.G. Jung, and the bare-surname rows (Hawthorne, Keats, Tennyson, Wagner, Moses) which are low-quality matches.
