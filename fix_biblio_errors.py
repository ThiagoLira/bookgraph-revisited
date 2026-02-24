#!/usr/bin/env python3
"""Fix bibliographic citation errors in BookGraph frontend data.

Uses two safe heuristics + a comprehensive manual fix list.
Heuristics:
  1. Sport infobox on Wikipedia match (football, cricket, etc.)
  2. Criminal categories on Wikipedia match
  3. Anachronistic birth year (born after source book published)
Manual list covers all remaining known errors.
"""

import json
import sys
from pathlib import Path

DATA_DIR = Path("/home/thiago/repos/thiagolira/_projects/book_graph_2/data")

BAD_SPORT_INFOBOXES = {
    "football biography", "ice hockey player", "cricketer",
    "basketball biography", "tennis biography",
}

BAD_CRIMINAL_CATS = ["convicted of murder", "spree shooting"]

# ─── Heuristic Skip List ───
# (file_rel_path) → set of raw.author patterns to skip heuristic checks for.
# These are cases where the heuristic would produce a false positive
# because the match IS correct (e.g., DFW writing about tennis players,
# modern commentators in annotated editions of old texts).
HEURISTIC_SKIP = {
    # DFW legitimately writes about tennis players and filmmakers
    "david_foster_wallace_library/6438.json": {
        "ivan lendl", "michael chang", "andre agassi", "jimmy connors",
    },
    # Kaczynski IS discussed in Sandel's Justice
    "philosophy_stress_test/6868637.json": {"ted kaczynski"},
    # Sacco and Vanzetti ARE discussed in Stalin's Library
    "stalin_library/graph.json": {"sacco and vanzetti"},
    # Modern commentators on Montaigne's Essays (pub 1580) in annotated editions
    "philosophy_stress_test/290752.json": {
        "bayle st. john", "hazlitt", "bouchet", "hallam", "la bruyère",
    },
    # Modern scholars in annotated editions of Pascal's Pensées (pub 1670)
    "philosophy_stress_test/449407.json": {"plazenet", "proust"},
}

# ─── Manual Fixes ───
# (file_rel_path) → list of match+fix dicts
# Match keys: author, title, wiki_title, wiki_birth, gr_author
# Fix: "null_wiki", "null_gr", "null_both"
MANUAL_FIXES = {
    # ═══ THE HERO WITH A THOUSAND FACES ═══
    "the_hero_with_a_thousand_faces/graph.json": [
        {"author": "Simeon ben Yohai", "fix": "null_wiki", "wiki_title": "Yohai Ben-Nun",
         "reason": "2nd century rabbi → modern Israeli military person"},
        {"author": "John C. Ferguson", "title": "Chinese Mythology", "fix": "null_gr",
         "reason": "Ferguson's work → Michael V. Uschan's book"},
        {"author": "Douglas C. Fox", "title": "African Genesis", "fix": "null_gr",
         "reason": "Frobenius/Fox 1937 → Robert Ardrey 1961"},
        {"author": "Leo Frobenius", "title": "African Genesis", "fix": "null_gr",
         "reason": "Frobenius/Fox 1937 → Robert Ardrey 1961"},
        {"author": "Huang Ti", "fix": "null_wiki", "wiki_title": "Ti Lung",
         "reason": "Yellow Emperor → Hong Kong actor Ti Lung"},
        {"author": "Moses", "fix": "null_wiki", "wiki_birth": 1730,
         "reason": "Biblical Moses → Moses Mendelssohn dates"},
        {"author": "Margaret Sinclair Stevenson", "fix": "null_wiki", "wiki_birth": 1938,
         "reason": "Author of 1915 book → person born 1938"},
        {"author": "Genchi Kato", "fix": "null_wiki", "wiki_birth": 1967,
         "reason": "Shinto scholar (1873) → manga artist born 1967"},
        {"author": "Bates", "title": "Passing of the Aborigines", "fix": "null_wiki", "wiki_birth": 1914,
         "reason": "Irish-Australian Daisy Bates → American civil rights activist"},
        {"author": "Guido Guinizelli", "fix": "null_gr",
         "reason": "Guinizelli's poetry → Dante Gabriel Rossetti anthology"},
        {"author": "Dom Ansgar Nelson", "fix": "null_gr",
         "reason": "Nelson's work → H.A. Reinhold anthology"},
        {"author": "Sadananda", "fix": "null_gr",
         "reason": "Sadananda's work → Swami Nikhilananda translation"},
        {"author": "Mahendranath Gupta", "fix": "null_gr",
         "reason": "Gupta's work → Swami Nikhilananda translation"},
    ],

    # ═══ STALIN'S LIBRARY ═══
    "stalin_library/graph.json": [
        {"author": "Darwin", "fix": "null_wiki", "wiki_title": "Susannah Darwin",
         "reason": "Charles Darwin → his mother Susannah"},
        {"author": "Turaev", "fix": "null_wiki", "wiki_title": "Vladimir Turaev",
         "reason": "Boris Turaev (Egyptologist) → modern mathematician"},
        {"author": "Radek", "fix": "null_wiki",
         "reason": "Karl Radek → Radek Martinek (ice hockey)"},
        {"author": "Heine", "fix": "null_wiki", "wiki_title": "Jakob Heine",
         "reason": "Heinrich Heine → orthopedic surgeon Jakob Heine"},
        {"author": "Struve", "fix": "null_wiki", "wiki_title": "Friedrich Georg Wilhelm von Struve",
         "reason": "Pyotr Struve (economist) → astronomer F.G.W. von Struve"},
        {"author": "Marr", "fix": "null_wiki", "wiki_title": "Wilhelm Marr",
         "reason": "Nikolai Marr (Soviet linguist) → German antisemite"},
        {"author": "Orlov", "fix": "null_wiki", "wiki_title": "Grigory Orlov",
         "reason": "Alexander Orlov (NKVD) → Catherine the Great's lover"},
        {"author": "Razin", "fix": "null_wiki", "wiki_title": "Stenka Razin",
         "reason": "Soviet military historian E.A. Razin → 17th-century rebel"},
        {"author": "Harold Nicolson", "title": "Diplomacy", "fix": "null_gr",
         "reason": "Nicolson's Diplomacy (1939) → Kissinger's Diplomacy (1994)"},
        {"author": "Petrone", "fix": "null_wiki", "wiki_title": "Francisco Petrone",
         "reason": "Karen Petrone (historian) → Argentine actor"},
        {"author": "Oleg Naumov", "fix": "null_wiki",
         "reason": "Historian → convicted murderer"},
        {"author": "Shakespeare", "fix": "null_wiki", "wiki_title": "Anne Hathaway",
         "reason": "William Shakespeare → his wife Anne Hathaway"},
        {"author": "Robert Tucker", "fix": "null_wiki", "wiki_title": "Robert Tucker (mathematician)",
         "reason": "Robert C. Tucker (Sovietologist) → 19th-century mathematician"},
        {"author": "Rieber", "fix": "null_wiki", "wiki_title": "Hallvard Rieber-Mohn",
         "reason": "Alfred J. Rieber (historian) → Norwegian person"},
        {"author": "John Barber", "fix": "null_wiki", "wiki_birth": 1734,
         "reason": "Modern Soviet historian → 18th-century engineer"},
        {"author": "Chris Read", "fix": "null_wiki",
         "reason": "Christopher Read (historian) → cricketer"},
        {"author": "I. Grey", "title": "Ivan the Terrible", "fix": "null_gr",
         "reason": "Ian Grey → Isabel de Madariaga"},
        {"author": "E. Pollock", "fix": "null_gr",
         "reason": "Pollock's work → Milovan Djilas book"},
    ],

    # ═══ WHAT I BELIEVE ═══
    "what_i_believe/graph.json": [
        {"author": "David Copperfield", "fix": "null_wiki",
         "reason": "Dickens character → American magician"},
        {"author": "Ahmes", "fix": "null_wiki", "wiki_birth": 1932,
         "reason": "Ancient Egyptian scribe → modern person"},
    ],

    # ═══ LOVECRAFT ═══
    "lovecraft_-_supernatural_horror_in_literature/graph.json": [
        {"author": "Hoffmann", "fix": "null_wiki", "wiki_title": "Oskar Hoffmann",
         "reason": "E.T.A. Hoffmann → later German sci-fi writer"},
        {"author": "Melville", "fix": "null_wiki", "wiki_title": "Herman Melville",
         "reason": "Lewis Melville (biographer) → Herman Melville"},
        {"author": "Godwin", "fix": "null_wiki", "wiki_title": "Edward William Godwin",
         "reason": "William Godwin (philosopher) → architect"},
        {"author": "Herbert S. Gorman", "fix": "null_wiki", "wiki_birth": 1844,
         "reason": "Herbert Gorman (1893-1954) → person born 1844"},
    ],

    # ═══ FRANCES YATES ═══
    "frances_yates_\u2014_cabbala_e_occultismo/graph.json": [
        {"author": "Pitagora", "fix": "null_wiki", "wiki_title": "Paola Pitagora",
         "reason": "Pythagoras → Italian film actress"},
        {"author": "Baron", "title": "Doctor Faustus", "fix": "null_gr",
         "reason": "Frank Baron (scholar) → Frank Baron (civil engineer)"},
        {"author": "Francois Secret", "fix": "null_wiki", "wiki_birth": 1959,
         "reason": "Scholar born 1911 → person born 1959"},
        {"author": "Bakeless", "fix": "null_wiki", "wiki_birth": 1734,
         "reason": "John Bakeless (1894-1978) → person born 1734"},
        {"author": "Moses", "fix": "null_wiki", "wiki_birth": 1730,
         "reason": "Biblical Moses → Moses Mendelssohn dates"},
        {"author": "Hermes Trismegistus", "fix": "null_wiki", "wiki_birth": 1744,
         "reason": "Legendary Hellenistic figure → 18th-century person"},
    ],

    # ═══ CALVINO CLASSICS ═══
    "calvino_classics/graph.json": [
        {"author": "Nezami", "fix": "null_gr", "gr_author": "Nezami Aroozi",
         "reason": "Nezami Ganjavi → Nezami Aroozi (different author)"},
        {"author": "Lukacs", "fix": "null_wiki", "wiki_title": "John Lukacs",
         "reason": "Georg Lukacs → John Lukacs (American historian)"},
        {"author": "Tolstoy", "fix": "null_wiki", "wiki_title": "Aleksey Nikolayevich Tolstoy",
         "reason": "Leo Tolstoy → Aleksey Nikolayevich Tolstoy"},
        {"author": "Virgil", "fix": "null_wiki", "wiki_title": "Virgil Solis",
         "reason": "Roman poet Virgil → 16th-century German artist"},
        {"author": "Bernardini", "fix": "null_wiki",
         "reason": "Literary scholar → Fulvio Bernardini (footballer)"},
    ],

    # ═══ PHILOSOPHY STRESS TEST ═══
    "philosophy_stress_test/234139935.json": [
        {"author": "Hafiz", "fix": "null_wiki", "wiki_birth": 1931,
         "reason": "Persian poet Hafez → modern person"},
    ],
    "philosophy_stress_test/290752.json": [
        {"author": "Seneca", "title": "Agamemnon", "fix": "null_gr",
         "reason": "Seneca's Agamemnon → 2014 Howard Colyer adaptation"},
        {"author": "Manilius", "fix": "null_wiki",
         "reason": "1st-century Roman poet → wrong person"},
        {"author": "Aulus Gellius", "fix": "null_wiki",
         "reason": "Born c. 125 AD, matched with birth -125"},
        {"author": "Solomon", "fix": "null_wiki",
         "reason": "King Solomon → 'Solomon in Islam' article"},
    ],
    "philosophy_stress_test/929561.json": [
        {"author": "Benito Pererio", "fix": "null_wiki",
         "reason": "Matched to Gomez Pereira — different person"},
        {"author": "Lichtenberg", "fix": "null_wiki", "wiki_birth": 1942,
         "reason": "G.C. Lichtenberg (1742-1799) → person born 1942"},
        {"author": "Carlo Steiner", "fix": "null_wiki", "wiki_birth": 1958,
         "reason": "Anachronistic for 1952 book citation"},
        {"author": "Luis Villamayor", "fix": "null_wiki", "wiki_birth": 1948,
         "reason": "Anachronistic for 1915 book citation"},
        {"author": "Gustaf Janson", "fix": "null_wiki", "wiki_birth": 1940,
         "reason": "Gustaf Janson (1866-1913) → person born 1940"},
        {"author": "Byron", "fix": "null_wiki", "wiki_birth": 1861,
         "reason": "Lord Byron (1788-1824) → person born 1861"},
        {"author": "Muhammad al-Ghazali", "fix": "null_wiki", "wiki_birth": 1917,
         "reason": "Abu Hamid al-Ghazali (1058-1111) → modern person"},
        {"author": "Jung", "fix": "null_wiki",
         "reason": "Carl Jung (died 1961) → wrong death year 1903"},
    ],
    "philosophy_stress_test/1696825.json": [
        {"author": "Johnson", "fix": "null_wiki",
         "reason": "Samuel Johnson (died 1784) → wrong death year 1735"},
        {"author": "Jean Paul", "fix": "null_wiki", "wiki_birth": 1962,
         "reason": "Jean Paul Richter (1763-1825) → person born 1962"},
    ],
    "philosophy_stress_test/35775773.json": [
        {"author": "Lothar Werner", "fix": "null_wiki", "wiki_birth": 1941,
         "reason": "Author of 1935 book → person born 1941"},
        {"author": "Nechayev", "fix": "null_wiki", "wiki_birth": 1792,
         "reason": "Sergei Nechayev (1847-1882) → person born 1792"},
        {"author": "Bruno Weil", "fix": "null_wiki", "wiki_birth": 1949,
         "reason": "Author of 1930 book → person born 1949"},
        {"author": "Neesse", "fix": "null_wiki",
         "reason": "Nazi-era scholar → wrong person"},
        {"author": "Ernst Bayer", "fix": "null_wiki", "wiki_birth": 1925,
         "reason": "Author of 1938 book → wrong person"},
        {"author": "Vassilyev", "fix": "null_wiki", "wiki_birth": 1953,
         "reason": "Author of 1930 book → person born 1953"},
        {"author": "Bruno Bettelheim", "fix": "null_gr",
         "reason": "Bettelheim's work → 'Office of US Chief of Counsel' doc"},
    ],
    "philosophy_stress_test/1343474.json": [
        {"author": "John Thomson", "fix": "null_wiki", "wiki_birth": 1969,
         "reason": "Photographer (1837-1921) → person born 1969"},
        {"author": "Bruce Davidson", "fix": "null_wiki", "wiki_birth": 1949,
         "reason": "Photographer (born 1933) → wrong person born 1949"},
    ],
    "philosophy_stress_test/6868637.json": [
        {"author": "Elizabeth Anderson", "fix": "null_wiki", "wiki_birth": 1897,
         "reason": "Philosopher (born 1959) → person born 1897"},
    ],
    "philosophy_stress_test/35696171.json": [
        {"author": "Wilson", "fix": "null_gr", "gr_author": "Oliver Sacks",
         "reason": "Wilson & Daly → Oliver Sacks book"},
    ],

    # ═══ THIAGO LIBRARY ═══
    "thiago_library/11890280.json": [
        {"author": "Tom Holland", "fix": "null_wiki", "wiki_birth": 1943,
         "reason": "Historian (born 1968) → filmmaker born 1943"},
    ],

    # ═══ UMBERTO ECO ═══
    "umberto_eco_collection/25188293.json": [
        {"author": "Juvenal", "fix": "null_wiki", "wiki_title": "Juvenal of Jerusalem",
         "reason": "Roman satirist → Juvenal of Jerusalem"},
    ],
    "umberto_eco_collection/13326582.json": [
        {"author": "Cervantes", "fix": "null_wiki",
         "wiki_title": "Francisco Cervantes de Salazar",
         "reason": "Miguel de Cervantes → Francisco Cervantes de Salazar"},
    ],
    "umberto_eco_collection/44326249.json": [
        {"author": "Jacques de Vitry", "fix": "null_wiki", "wiki_title": "Philippe de Vitry",
         "reason": "Jacques de Vitry → Philippe de Vitry"},
        {"author": "Francis Bacon", "fix": "null_wiki", "wiki_title": "Nathaniel Bacon",
         "reason": "Francis Bacon → Nathaniel Bacon (Jesuit)"},
        {"author": "Cervantes", "fix": "null_wiki",
         "wiki_title": "Francisco Cervantes de Salazar",
         "reason": "Miguel de Cervantes → Francisco Cervantes de Salazar"},
        {"author": "Revelation", "fix": "null_gr",
         "reason": "Book of Revelation → John R. Rice commentary"},
        {"author": "Stendhal", "fix": "null_gr", "gr_author": "Gustave Flaubert",
         "reason": "Stendhal's work → Gustave Flaubert book"},
    ],
    "umberto_eco_collection/182833229.json": [
        {"author": "Biondolillo", "fix": "null_wiki",
         "reason": "Francesco Biondolillo → Chelsea Biondolillo"},
        {"author": "Peirce", "fix": "null_wiki",
         "reason": "Charles Sanders Peirce → Benjamin Peirce"},
        {"author": "Tapie", "fix": "null_wiki",
         "reason": "Victor Lucien Tapie → Michel Tapie"},
        {"author": "George Lakoff", "fix": "null_gr",
         "reason": "Lakoff's work → Steinberg/Jakobovits anthology"},
        {"author": "James McCawley", "fix": "null_gr",
         "reason": "McCawley's work → Steinberg/Jakobovits anthology"},
    ],

    # ═══ WESTERN CANON BATCH ═══
    "western_canon_batch/1063554.json": [
        {"author": "Marlowe", "fix": "null_wiki", "wiki_birth": 1942,
         "reason": "Christopher Marlowe (1564-1593) → person born 1942"},
        {"title": "Practice of Philosophy", "fix": "null_gr",
         "reason": "Langer's work → Hymers on Wittgenstein"},
        {"author": "Virgil", "fix": "null_wiki", "wiki_title": "Virgil Shaw",
         "reason": "Roman poet → Virgil Shaw (modern musician)"},
        {"author": "Theodor H. Gaster", "fix": "null_gr",
         "reason": "Gaster's work → wrong GR user entry"},
        {"author": "Marianne Moore", "fix": "null_gr", "gr_author": "Gulzar",
         "reason": "Moore's poetry → Gulzar anthology"},
        {"author": "John Donne", "fix": "null_gr", "gr_author": "Douglas Rushkoff",
         "reason": "Donne's work → Rushkoff book"},
        {"author": "Samuel Butler", "fix": "null_gr", "gr_author": "JoAnn Ross",
         "reason": "Butler's work → JoAnn Ross novel"},
        {"author": "W. P. Ker", "fix": "null_gr", "gr_author": "Isaac Asimov",
         "reason": "Ker's literary criticism → Asimov book"},
        {"author": "Louis L. Martz", "fix": "null_gr", "gr_author": "Cleanth Brooks",
         "reason": "Martz's work → Brooks anthology"},
    ],
    "western_canon_batch/39813.json": [
        {"author": "Kevin Hart", "fix": "null_wiki", "wiki_birth": 1979,
         "reason": "Literary critic (born 1954) → comedian Kevin Hart"},
        {"author": "Schelling", "fix": "null_wiki", "wiki_title": "Caroline Schelling",
         "reason": "F.W.J. Schelling → Caroline Schelling"},
    ],
    "western_canon_batch/3590017.json": [
        {"author": "William Robertson", "fix": "null_wiki", "wiki_birth": 1865,
         "reason": "Historian (1721-1793) → VC recipient born 1865"},
        {"author": "Trebellius Pollio", "fix": "null_wiki", "wiki_title": "Vedius Pollio",
         "reason": "Trebellius Pollio → Vedius Pollio — wrong person"},
        {"author": "Valerius Maximus", "fix": "null_wiki", "wiki_title": "Terentius Maximus",
         "reason": "Valerius Maximus → Terentius Maximus"},
        {"author": "Nazarius", "fix": "null_wiki", "wiki_birth": 1556,
         "reason": "4th-century panegyrist → 16th-century person"},
        {"author": "Photius", "fix": "null_wiki", "wiki_title": "Photius Fisk",
         "reason": "Patriarch Photius I → Photius Fisk"},
        {"author": "Barclay", "title": "Morale", "fix": "null_gr",
         "reason": "Wrong GR match — different work by Robert Barclay"},
        {"author": "Pliny", "title": "Historia Naturalis", "fix": "null_gr",
         "reason": "Pliny's ancient work → Dan Chiasson poetry (2005)"},
        {"author": "Keating", "title": "History of Ireland", "fix": "null_gr",
         "reason": "Geoffrey Keating → Edmund Curtis (1936)"},
        {"author": "Cicero", "title": "de Natura Deorum", "fix": "null_both",
         "reason": "Cicero's work → J.B. Mayor commentary"},
        {"author": "Eutychius", "fix": "null_wiki",
         "reason": "Eutychius of Alexandria → Eutychius (exarch)"},
        {"author": "Bertholdt", "fix": "null_wiki", "wiki_birth": 1944,
         "reason": "Theologian (1774-1822) → person born 1944"},
        {"author": "Peter Patricius", "fix": "null_wiki", "wiki_birth": 1529,
         "reason": "6th-century diplomat → 16th-century person"},
        {"author": "John Whittaker", "fix": "null_wiki", "wiki_birth": 1955,
         "reason": "Historian (1735-1808) → modern person"},
        {"author": "Jordanes", "fix": "null_wiki", "wiki_birth": 1955,
         "reason": "6th-century Gothic historian → modern person"},
        {"author": "Thomas Shaw", "fix": "null_wiki", "wiki_birth": 1850,
         "reason": "Traveler (1694-1751) → person born 1850"},
        {"author": "Nardini", "fix": "null_wiki", "wiki_birth": 1965,
         "reason": "Antiquarian (c.1613-1661) → person born 1965"},
        {"author": "John Pearson", "fix": "null_wiki", "wiki_birth": 1825,
         "reason": "Bishop (1613-1686) → person born 1825"},
        {"author": "Julian", "fix": "null_wiki", "wiki_birth": 1904,
         "reason": "Julian the Apostate (331-363) → person born 1904"},
        {"author": "Blair", "fix": "null_wiki", "wiki_birth": 1950,
         "reason": "Early 19th-century author → person born 1950"},
        {"author": "Henry Wotton", "fix": "null_gr", "gr_author": "Michael Grant",
         "reason": "Wotton's work → Michael Grant book"},
        {"author": "Abraham ben David", "fix": "null_gr", "gr_author": "Wilhelm Schickard",
         "reason": "Abraham ben David → Wilhelm Schickard book"},
    ],
    "western_canon_batch/17997242.json": [
        {"author": "Benjamin Franklin", "fix": "null_wiki",
         "reason": "Franklin death year 1730 is wrong (should be 1790)"},
        {"author": "Fritz Reiche", "title": "Quantum Theory", "fix": "null_gr",
         "reason": "Reiche's Quantum Theory → David Bohm's book"},
        {"author": "Quine", "fix": "null_wiki",
         "reason": "W.V.O. Quine death year 1932 is wrong (should be 2000)"},
        {"author": "Kopp", "title": "Geschichte der Chemie", "fix": "null_both",
         "reason": "Hermann Kopp (1817-1892) → person born 1954"},
        {"author": "J. R. Partington", "fix": "null_gr", "gr_author": "Isaac Asimov",
         "reason": "Partington's chemistry history → Asimov book"},
    ],
    "western_canon_batch/80795.json": [
        {"author": "Isidore", "fix": "null_wiki", "wiki_birth": 1870,
         "reason": "Isidore of Seville (c.560-636) → person born 1870"},
        {"author": "Bartsch", "fix": "null_wiki", "wiki_birth": 1946,
         "reason": "Karl Bartsch (1832-1888) → person born 1946"},
        {"author": "Meredith", "fix": "null_wiki", "wiki_birth": 1957,
         "reason": "George Meredith (1828-1909) → person born 1957"},
        {"author": "Hafiz", "fix": "null_wiki", "wiki_birth": 1931,
         "reason": "Persian poet Hafez → modern person"},
    ],
}


def has_sport_infobox(wiki_match):
    if not wiki_match:
        return False
    return any(ib.lower() in BAD_SPORT_INFOBOXES
               for ib in wiki_match.get("infoboxes", []))


def has_criminal_categories(wiki_match):
    if not wiki_match:
        return False
    cats_text = " ".join(c.lower() for c in wiki_match.get("categories", []))
    return any(kw in cats_text for kw in BAD_CRIMINAL_CATS)


def is_anachronistic(wiki_match, pub_year):
    if not wiki_match or not pub_year:
        return False
    birth = wiki_match.get("birth_year")
    return bool(birth and isinstance(birth, (int, float))
                and birth > 0 and birth > pub_year)


def null_wiki(citation):
    citation["wikipedia_match"] = None
    if citation.get("edge"):
        citation["edge"]["target_person"] = None


def null_gr(citation):
    citation["goodreads_match"] = None
    if citation.get("edge"):
        citation["edge"]["target_book_id"] = None
        citation["edge"]["target_author_ids"] = []


def matches_fix(citation, fix):
    raw = citation.get("raw", {})
    wiki = citation.get("wikipedia_match")
    gr = citation.get("goodreads_match")

    if "author" in fix:
        raw_author = (raw.get("author") or "").lower()
        raw_canonical = (raw.get("canonical_author") or "").lower()
        fix_author = fix["author"].lower()
        if fix_author not in raw_author and fix_author not in raw_canonical:
            return False

    if "title" in fix:
        raw_title = (raw.get("title") or "").lower()
        if fix["title"].lower() not in raw_title:
            return False

    if "wiki_title" in fix:
        if not wiki or fix["wiki_title"].lower() not in (wiki.get("title") or "").lower():
            return False

    if "wiki_birth" in fix:
        if not wiki or wiki.get("birth_year") != fix["wiki_birth"]:
            return False

    if "gr_author" in fix:
        if not gr:
            return False
        gr_authors_str = " ".join(gr.get("authors", [])).lower()
        if fix["gr_author"].lower() not in gr_authors_str:
            return False

    return True


def process_file(filepath, rel_path, log):
    with open(filepath) as f:
        data = json.load(f)

    source = data.get("source", {})
    pub_year = source.get("publication_year")
    manual_fixes = MANUAL_FIXES.get(rel_path, [])
    skip_set = HEURISTIC_SKIP.get(rel_path, set())

    changed = False
    for i, citation in enumerate(data.get("citations", [])):
        wiki = citation.get("wikipedia_match")
        gr = citation.get("goodreads_match")
        raw = citation.get("raw", {})
        raw_author = raw.get("author", "?")

        # Check if this citation should skip heuristics
        skip_heuristic = any(
            s in (raw_author or "").lower() for s in skip_set
        )

        # ── Heuristic 1: Sport infobox ──
        if wiki and has_sport_infobox(wiki) and not skip_heuristic:
            log.append(f"  [{rel_path}] #{i} '{raw_author}' — SPORT_INFOBOX → {wiki.get('title')}")
            null_wiki(citation)
            changed = True
            wiki = None

        # ── Heuristic 2: Criminal categories ──
        if wiki and has_criminal_categories(wiki) and not skip_heuristic:
            log.append(f"  [{rel_path}] #{i} '{raw_author}' — CRIMINAL_CAT → {wiki.get('title')}")
            null_wiki(citation)
            changed = True
            wiki = None

        # ── Heuristic 3: Anachronistic birth year ──
        if wiki and is_anachronistic(wiki, pub_year) and not skip_heuristic:
            log.append(f"  [{rel_path}] #{i} '{raw_author}' — ANACHRONISTIC born {wiki.get('birth_year')} > pub {pub_year} → {wiki.get('title')}")
            null_wiki(citation)
            changed = True
            wiki = None

        # ── Manual fixes ──
        for fix in manual_fixes:
            fix_type = fix["fix"]
            if fix_type in ("null_wiki", "null_both") and wiki is None:
                if fix_type == "null_wiki":
                    continue
            if fix_type in ("null_gr", "null_both") and gr is None:
                if fix_type == "null_gr":
                    continue

            if matches_fix(citation, fix):
                if fix_type in ("null_wiki", "null_both") and wiki is not None:
                    log.append(f"  [{rel_path}] #{i} '{raw_author}' — MANUAL_WIKI: {fix['reason']}")
                    null_wiki(citation)
                    wiki = None
                    changed = True
                if fix_type in ("null_gr", "null_both") and gr is not None:
                    log.append(f"  [{rel_path}] #{i} '{raw_author}' — MANUAL_GR: {fix['reason']}")
                    null_gr(citation)
                    gr = None
                    changed = True

    if changed:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    return changed


def main():
    log = []
    files_fixed = 0
    total_fixes = 0

    json_files = []
    for path in DATA_DIR.rglob("*.json"):
        if path.name in ("manifest.json", "datasets.json",
                         "original_publication_dates.json",
                         "authors_metadata.json", "manual_run.json"):
            continue
        rel = str(path.relative_to(DATA_DIR))
        if any(x in rel for x in ("raw_extracted_citations",
                                   "preprocessed_extracted_citations",
                                   "final_citations_metadata_goodreads")):
            continue
        json_files.append((path, rel))

    print(f"Processing {len(json_files)} JSON files...")

    for filepath, rel_path in sorted(json_files):
        before_len = len(log)
        was_changed = process_file(filepath, rel_path, log)
        fixes_in_file = len(log) - before_len
        if was_changed:
            files_fixed += 1
            total_fixes += fixes_in_file
            print(f"  ✓ {rel_path}: {fixes_in_file} fixes")

    print(f"\nDone. Fixed {total_fixes} errors across {files_fixed} files.")
    print("\n─── Change Log ───")
    for entry in log:
        print(entry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
