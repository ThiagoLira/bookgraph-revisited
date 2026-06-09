# Books to Process Next — corrected for what the pipeline actually extracts

**Key principle (validated against the 29 existing sources):** the pipeline extracts
**inline mentions of other authors/works** from a source text. So a book is only worth
processing if it *names other works* — i.e. **non-fiction with a citational habit**:
philosophy, history, criticism, science, essays. Every current source is exactly this
(Eco, Gibbon, Arendt, Frye, Bloom, Montaigne, Sontag…). Even *Meditations* (aphoristic
philosophy) yielded only 12 edges.

**Fiction, poetry, and drama do NOT cite — they allude.** Shakespeare, Homer, the
novelists and poets are worth far more as the **cited nodes** they already are than as
sources (feeding them in yields near-nothing or hallucinated allusions). So they are
*removed* from the processing list below.

Ranking = number of distinct sources citing them (post-audit dates shown).

## ✅ Process these — citation-rich non-fiction (high yield expected)
| Author (dates) | citing srcs | Suggested citational text |
|---|---|---|
| **Aristotle** (−384–−322) | 18 | *Metaphysics* / *Politics* (surveys predecessors) |
| **Augustine of Hippo** (354–430) | 13 | *City of God* (dense classical + scriptural citation) |
| **Hegel** (1770–1831) | 12 | *Lectures on the History of Philosophy* |
| **Immanuel Kant** (1724–1804) | 10 | *Critique of Pure Reason* |
| **Cicero** (−106–−43) | 10 | *De Natura Deorum* / *On Duties* |
| **Seneca the Younger** (4–65) | 9 | *Letters from a Stoic* (name-only node — big gain) |
| **Thomas Aquinas** (1225–1274) | 9 | *Summa Theologica* (enormous citation apparatus) |
| **John Stuart Mill** (1806–1873) | 9 | *On Liberty* / *Utilitarianism* |
| **Voltaire** (1694–1778) | 9 | *Philosophical Dictionary* (not *Candide*) |
| **Tacitus** (56–120) | 8 | *Annals* (names his sources) |
| **Plutarch** (46–120) | 8 | *Parallel Lives* / *Moralia* (cites sources constantly) |
| **Arthur Schopenhauer** (1788–1860) | 8 | *The World as Will and Representation* |
| **Baruch Spinoza** (1632–1677) | 8 | *Theologico-Political Treatise* |
| **Leibniz** (1646–1716) | 8 | *New Essays on Human Understanding* |
| **Sigmund Freud** (1856–1939) | 7 | *The Interpretation of Dreams* |
| **Karl Marx** (1818–1883) | 7 | *Capital* (heavy footnoting) |
| **David Hume** (1711–1776) | 7 | *A Treatise of Human Nature* |
| **Thomas Hobbes** (1588–1679) | 7 | *Leviathan* |
| **Pliny the Elder** (23–79) | 7 | *Natural History* (cites hundreds of authors) |

## 🟡 Borderline — worth a try, mixed yield
- **Plato** (23 srcs) — dialogues *name* predecessors (Homer, Hesiod, the pre-Socratics) but loosely; *The Republic* may yield moderate edges.
- **Descartes** (12) — *Meditations* references few; *Principles* engages scholastics.
- **Dante** (10) — *Divine Comedy* is allusion-dense (Virgil, Aristotle, scripture); narrative, but unusually citational for poetry.
- **Wittgenstein** (7) — sparse referencing; modest yield.

## ❌ Leave as cited-only nodes (fiction / poetry / drama — don't process as sources)
Shakespeare, Homer, Virgil, Horace, Ovid, Sophocles, Euripides, Apuleius · Tolstoy,
Dostoevsky, Proust, Flaubert, Dickens, Joyce, Kafka, Cervantes, Melville, Conrad ·
Baudelaire, Goethe (*Faust*/novels), Oscar Wilde. They're already valuable as the
high-degree targets everyone points at.

### …but grab the *non-fiction* of a few fiction authors instead
- **Tolstoy** → *What Is Art?* (engages aesthetics literature)
- **T. S. Eliot** → *The Sacred Wood* / selected essays (criticism, citational)
- **Oscar Wilde** → *The Critic as Artist* / *Intentions* (essays)

### Procurement notes
- Prefer scholarly editions (Loeb/Oxford) for the ancients — richer inline naming = more edges.
- "Name-only" nodes (Seneca, Heraclitus) gain the most structurally since they currently have zero attached works.
