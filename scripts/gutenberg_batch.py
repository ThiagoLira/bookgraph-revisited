#!/usr/bin/env python3
import sys, importlib.util, re
spec=importlib.util.spec_from_file_location("gf","scripts/gutenberg_fetch.py")
gf=importlib.util.module_from_spec(spec); spec.loader.exec_module(gf)

JUNK=re.compile(r'\b(boys|girls|children|commentary|letters to dead|selections|story of|abridged|for young|reader|index|companion|life of|guide to|outline)\b',re.I)
LANG=re.compile(r'\((modern greek|finnish|german|french|latin|spanish|italian|dutch|portuguese|swedish|esperanto|tagalog|welsh)\b',re.I)

# (query, slug, author_hint)
JOBS=[
 ("Thucydides Peloponnesian War","thucydides_peloponnesian_war","thucydides"),
 ("Plutarch Lives","plutarch_lives","plutarch"),
 ("Pliny Natural History","pliny_natural_history","pliny"),
 ("Diogenes Laertius Lives Philosophers","diogenes_laertius_lives","diogenes"),
 ("Lucretius On the Nature of Things","lucretius_de_rerum_natura","lucretius"),
 ("Tacitus Annals","tacitus_annals","tacitus"),
 ("Livy History of Rome","livy_history_of_rome","livy"),
 ("Suetonius Twelve Caesars","suetonius_twelve_caesars","suetonius"),
 ("Polybius Histories","polybius_histories","polybius"),
 ("Cicero De Officiis Offices","cicero_de_officiis","cicero"),
 ("Cicero Nature of the Gods","cicero_nature_of_gods","cicero"),
 ("Quintilian Institutes of Oratory","quintilian_institutio","quintilian"),
 ("Boethius Consolation of Philosophy","boethius_consolation","boethius"),
 ("Augustine City of God","augustine_city_of_god","augustine"),
 ("Augustine Confessions","augustine_confessions","augustine"),
 ("Burton Anatomy of Melancholy","burton_anatomy_melancholy","burton"),
 ("Frazer Golden Bough","frazer_golden_bough","frazer"),
 ("Locke Essay Concerning Human Understanding","locke_essay_human_understanding","locke"),
 ("Hobbes Leviathan","hobbes_leviathan","hobbes"),
 ("Spinoza Ethics","spinoza_ethics","spinoza"),
 ("Hume Treatise of Human Nature","hume_treatise","hume"),
 ("Adam Smith Wealth of Nations","smith_wealth_of_nations","smith"),
 ("Darwin Origin of Species","darwin_origin_of_species","darwin"),
 ("Bacon Novum Organum","bacon_novum_organum","bacon"),
 ("Machiavelli Discourses Livy","machiavelli_discourses","machiavelli"),
 ("Vasari Lives of the Painters","vasari_lives_artists","vasari"),
 ("Emerson Essays","emerson_essays","emerson"),
 ("Emerson Representative Men","emerson_representative_men","emerson"),
 ("Ruskin Stones of Venice","ruskin_stones_of_venice","ruskin"),
 ("Matthew Arnold Culture and Anarchy","arnold_culture_anarchy","arnold"),
 ("Walter Pater Renaissance","pater_renaissance","pater"),
 ("Carlyle Heroes Hero Worship","carlyle_heroes","carlyle"),
 ("Tocqueville Democracy in America","tocqueville_democracy","tocqueville"),
 ("William James Varieties Religious Experience","james_varieties","james"),
 ("Coleridge Biographia Literaria","coleridge_biographia","coleridge"),
 ("Tolstoy What Is Art","tolstoy_what_is_art","tolstoy"),
 ("Schopenhauer Studies in Pessimism","schopenhauer_essays","schopenhauer"),
 ("Nietzsche Birth of Tragedy","nietzsche_birth_of_tragedy","nietzsche"),
 ("Spencer First Principles","spencer_first_principles","spencer"),
 ("Voltaire Philosophical Dictionary","voltaire_phil_dictionary","voltaire"),
 ("Montesquieu Spirit of Laws","montesquieu_spirit_of_laws","montesquieu"),
 ("Wilde Intentions","wilde_intentions","wilde"),
]

def pick(rows,hint):
    cands=[]
    for eid,title,sub,dl in rows:
        if JUNK.search(title): continue
        if LANG.search(title) or LANG.search(sub): continue
        if hint and hint.lower() not in (sub.lower()+" "+title.lower()): 
            # allow if author hint missing in metadata but title strongly matches
            pass
        n=int(dl.replace(',','') or 0)
        cands.append((n,eid,title,sub))
    cands.sort(reverse=True)
    return cands[0] if cands else None

for q,slug,hint in JOBS:
    try:
        rows=gf.search(q)
    except Exception as e:
        print(f"SEARCHFAIL {slug}: {e}"); continue
    p=pick(rows,hint)
    if not p:
        print(f"NOMATCH {slug}"); continue
    n,eid,title,sub=p
    print(f">> {slug}: id {eid} '{title[:45]}' ({sub[:20]}, {n} dl)")
    gf.get(eid,slug)
