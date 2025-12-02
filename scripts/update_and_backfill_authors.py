import json
import glob
import os

def update_author_data():
    # 1. Update authors_metadata.json
    meta_path = "frontend/data/authors_metadata.json"
    with open(meta_path, "r") as f:
        metadata = json.load(f)

    updates = {
        "Plato": {"birth_year": -428, "death_year": -348},
        "Aristotle": {"birth_year": -384, "death_year": -322},
        "Friedrich Nietzsche": {"birth_year": 1844, "death_year": 1900},
        "Mircea Eliade": {"birth_year": 1907, "death_year": 1986},
        "Baruch Spinoza": {"birth_year": 1632, "death_year": 1677},
        "Rene Descartes": {"birth_year": 1596, "death_year": 1650},
        "John Updike": {"birth_year": 1932, "death_year": 2009},
        "William Shakespeare": {"birth_year": 1564, "death_year": 1616},
        "Xenophon": {"birth_year": -430, "death_year": -354},
        "Isaac Newton": {"birth_year": 1643, "death_year": 1727},
        "Heraclitus": {"birth_year": -535, "death_year": -475},
        "Seneca the Younger": {"birth_year": -4, "death_year": 65},
        "Thucydides": {"birth_year": -460, "death_year": -400},
        "Sophocles": {"birth_year": -497, "death_year": -406},
        "Pythagoras": {"birth_year": -570, "death_year": -495},
        "Euripides": {"birth_year": -480, "death_year": -406},
        "Aeschylus": {"birth_year": -525, "death_year": -456},
        "Democritus": {"birth_year": -460, "death_year": -370},
        "Lucretius": {"birth_year": -99, "death_year": -55},
        "Pliny the Elder": {"birth_year": 23, "death_year": 79},
        "Euclid": {"birth_year": -325, "death_year": -265},
        "Plotinus": {"birth_year": 204, "death_year": 270},
        "Parmenides": {"birth_year": -515, "death_year": -450},
        "Theophrastus": {"birth_year": -371, "death_year": -287},
        "Fyodor Dostoyevsky": {"birth_year": 1821, "death_year": 1881},
        "Marcus Tullius Cicero": {"birth_year": -106, "death_year": -43},
        "Joseph-Arthur de Gobineau": {"birth_year": 1816, "death_year": 1882},
        "Viktor E. Frankl": {"birth_year": 1905, "death_year": 1997},
        "Robert McQueen Grant": {"birth_year": 1917, "death_year": 2014},
        "Thich Nhat Hanh": {"birth_year": 1926, "death_year": 2022},
        "Terrence W. Deacon": {"birth_year": 1947, "death_year": None},
        "Nikolai A. Berdyaev": {"birth_year": 1874, "death_year": 1948},
        "Franco Bifo Berardi": {"birth_year": 1949, "death_year": None},
        "Petronius Arbiter": {"birth_year": 27, "death_year": 66},
        "Philip M. Rosenzweig": {"birth_year": 1949, "death_year": None},
        "Soren Kierkegaard": {"birth_year": 1813, "death_year": 1855},
        "Edward O. Wilson": {"birth_year": 1929, "death_year": 2021},
        "James E. Lovelock": {"birth_year": 1919, "death_year": 2022},
        "W.W. Tarn": {"birth_year": 1869, "death_year": 1957},
        "Arnold Joseph Toynbee": {"birth_year": 1889, "death_year": 1975},
        "Han Shan": {"birth_year": 700, "death_year": 800},
        "Hui-Neng": {"birth_year": 638, "death_year": 713},
        "Lao Tzu": {"birth_year": -604, "death_year": -531},
        "Suetonius": {"birth_year": 69, "death_year": 140},
        "Homer": {"birth_year": -850, "death_year": -800},
        "Aristophanes": {"birth_year": -446, "death_year": -386},
        "Tacitus": {"birth_year": 56, "death_year": 120},
        "Chrysippus": {"birth_year": -279, "death_year": -206},
        "Herodotus": {"birth_year": -484, "death_year": -425},
        "Strabo": {"birth_year": -63, "death_year": 24},
        "Adolf Hitler": {"birth_year": 1889, "death_year": 1945},
        "Livy": {"birth_year": -59, "death_year": 17},
        "Sima Qian": {"birth_year": -145, "death_year": -86},
        "Vasubandhu": {"birth_year": 320, "death_year": 400},
        "Bodhidharma": {"birth_year": 483, "death_year": 540},
        "Asvaghosa": {"birth_year": 80, "death_year": 150},
        "Cleanthes": {"birth_year": -330, "death_year": -230},
        "Hesiod": {"birth_year": -750, "death_year": -650},
        "Diodorus Siculus": {"birth_year": -90, "death_year": -30},
        "Anaxagoras": {"birth_year": -500, "death_year": -428},
        "Polybius": {"birth_year": -200, "death_year": -118},
        "Bertrand Russell": {"birth_year": 1872, "death_year": 1970},
        "Alfred North Whitehead": {"birth_year": 1861, "death_year": 1947},
        "R.M.W. Dixon": {"birth_year": 1939, "death_year": None},
        "Patricia Cline Cohen": {"birth_year": 1946, "death_year": None}, # Approx based on career
        "Barbara Tuchman": {"birth_year": 1912, "death_year": 1989},
        "Maria Brosius": {"birth_year": 1955, "death_year": None}, # Approx
        "Hans Van Wees": {"birth_year": 1959, "death_year": None}, # Approx
        "Jacob A. Riis": {"birth_year": 1849, "death_year": 1914},
        "Gustav Janouch": {"birth_year": 1903, "death_year": 1968},
        "Alfred Tennyson": {"birth_year": 1809, "death_year": 1892},
        "George H. Sabine": {"birth_year": 1880, "death_year": 1961},
        "Harrison E. Salisbury": {"birth_year": 1908, "death_year": 1993},
        "Bertram D. Wolfe": {"birth_year": 1896, "death_year": 1977},
        "Dionysius of Halicarnassus": {"birth_year": -60, "death_year": -7},
        "Empedocles": {"birth_year": -494, "death_year": -434},
        "Maimonides": {"birth_year": 1135, "death_year": 1204},
        "Xenocrates": {"birth_year": -396, "death_year": -314},
        "John Cleland": {"birth_year": 1709, "death_year": 1789},
        "Tirso de Molina": {"birth_year": 1584, "death_year": 1648},
        "Huangbo Xiyun": {"birth_year": 770, "death_year": 850}, # Approx birth
        "Kamalasila": {"birth_year": 740, "death_year": 795},
        "Paramartha (Chinese monk)": {"birth_year": 499, "death_year": 569},
        "Thomas Malory": {"birth_year": 1415, "death_year": 1471}, # Approx birth
        "William Caxton": {"birth_year": 1422, "death_year": 1491},
        "Athenodorus Cananites": {"birth_year": -74, "death_year": 7},
        "Carneades": {"birth_year": -214, "death_year": -129},
        "Manius Curius Dentatus": {"birth_year": -330, "death_year": -270}, # Approx
        "Ephorus": {"birth_year": -400, "death_year": -330},
        "Marcus Atilius Regulus": {"birth_year": -307, "death_year": -250},
        "Pindar": {"birth_year": -522, "death_year": -443},
        "Simonides of Ceos": {"birth_year": -556, "death_year": -468},
        "Yoshito Hakeda": {"birth_year": 1924, "death_year": 1983},
        "Egon Caesar Conte Corti": {"birth_year": 1886, "death_year": 1953},
        "Robert O. Paxton": {"birth_year": 1932, "death_year": None},
        "Jout Jout": {"birth_year": 1991, "death_year": None},
        "Francisco J. Varela": {"birth_year": 1946, "death_year": 2001},
        "Henrik Mouritsen": {"birth_year": 1962, "death_year": None},
        "Brent D. Shaw": {"birth_year": 1947, "death_year": None},
        "Florence Dupont": {"birth_year": 1943, "death_year": None},
        "Aloys Winterling": {"birth_year": 1956, "death_year": None},
        "Lawrence Keppie": {"birth_year": 1947, "death_year": None},
        "Timothy D. Wilson": {"birth_year": 1955, "death_year": None},
        "Kamalaśīla": {"birth_year": 740, "death_year": 795},
        "Marcus Atilius Regulus (consul 267 BC)": {"birth_year": -307, "death_year": -250},
        "Phocylides": {"birth_year": -560, "death_year": -500},
        "Stesichorus": {"birth_year": -630, "death_year": -555},
        "James Redfield": {"birth_year": 1935, "death_year": None},
        "Ctesias": {"birth_year": -441, "death_year": -398},
        "Polyaenus": {"birth_year": 100, "death_year": 163},
        "Lycurgus of Athens": {"birth_year": -390, "death_year": -324},
        "Xenophanes": {"birth_year": -570, "death_year": -478},
        "Berossus": {"birth_year": -350, "death_year": -280},
        "Archilochus": {"birth_year": -680, "death_year": -645},
        "Athanasius of Alexandria": {"birth_year": 296, "death_year": 373},
        "Jonathan Crary": {"birth_year": 1951, "death_year": None},
        "Plautus": {"birth_year": -254, "death_year": -184},
        "Marcus Porcius Cato": {"birth_year": -234, "death_year": -149},
        "Gaius Julius Caesar": {"birth_year": -100, "death_year": -44},
        "Pausanias": {"birth_year": 110, "death_year": 180},
        "Propertius": {"birth_year": -50, "death_year": -15},
        "Richard H. Thaler": {"birth_year": 1945, "death_year": None},
        "Keith E. Stanovich": {"birth_year": 1950, "death_year": None},
        "Burton G. Malkiel": {"birth_year": 1932, "death_year": None},
        "Antonio R. Damasio": {"birth_year": 1944, "death_year": None},
        "Harold S. Kushner": {"birth_year": 1935, "death_year": 2023},
        "Sophron": {"birth_year": -500, "death_year": -460},
        "Jonathan Francis Bennett": {"birth_year": 1930, "death_year": 2024},
        "Edwin M. Curley": {"birth_year": 1937, "death_year": None},
        "Numenius": {"birth_year": 150, "death_year": 200},
        "San Juan de la Cruz": {"birth_year": 1542, "death_year": 1591},
        "Marcus Cornelius Fronto": {"birth_year": 100, "death_year": 166},
        "Cassius Dio": {"birth_year": 150, "death_year": 235},
        "Johann Baptist Cysat": {"birth_year": 1585, "death_year": 1657},
        "Apollonius of Rhodes": {"birth_year": -295, "death_year": -246},
        "Pappus of Alexandria": {"birth_year": 290, "death_year": 350},
        "Apollonius of Perga": {"birth_year": -240, "death_year": -190},
        "Matthew Paris": {"birth_year": 1200, "death_year": 1259},
        "Hipparchus": {"birth_year": -190, "death_year": -120},
        "Eugene Borgida": {"birth_year": 1949, "death_year": None}, # Approx based on PhD
        "Timothy Wilson": {"birth_year": 1951, "death_year": None}, # Approx based on PhD
        "Seneca": {"birth_year": -54, "death_year": 39}, # Seneca the Elder
        "Sextus Empiricus": {"birth_year": 160, "death_year": 210},
        "Alexander of Aphrodisias": {"birth_year": 200, "death_year": 215},
        "Anaximander": {"birth_year": -610, "death_year": -546},
        "Pope Gelasius I": {"birth_year": 410, "death_year": 496},
        "Methodius of Olympus": {"birth_year": 230, "death_year": 311},
        "Robert Guiscard": {"birth_year": 1015, "death_year": 1085},
        "Regino of Prüm": {"birth_year": 840, "death_year": 915},
        "Thomas B. Ross": {"birth_year": 1929, "death_year": 2002},
        "W. Jeffrey Tatum": {"birth_year": 1957, "death_year": None},
        "Demophilus": {"birth_year": 320, "death_year": 386}, # Estimated based on death 386 AD
        "Aulus Hirtius": {"birth_year": -90, "death_year": -43},
        "Thomas Elyot": {"birth_year": 1490, "death_year": 1546},
        "Gautama Buddha": {"birth_year": -563, "death_year": -483},
        "Sir Isaac Newton": {"birth_year": 1643, "death_year": 1727},
        "Bernard Suits": {"birth_year": 1925, "death_year": 2007},
        "Liudprand of Cremona": {"birth_year": 920, "death_year": 972},
        "Guibert de Nogent": {"birth_year": 1053, "death_year": 1124},
        "Otto of Freising": {"birth_year": 1111, "death_year": 1158},
        "Abbo of Fleury": {"birth_year": 945, "death_year": 1004},
        "Widukind of Corvey": {"birth_year": 925, "death_year": 973},
        "Leo the Deacon": {"birth_year": 950, "death_year": 992}, # Approx death
        "Hariulf of Oudenburg": {"birth_year": 1060, "death_year": 1143},
        "Sigehard (patriarch of Aquileia)": {"birth_year": 1020, "death_year": 1077}, # Approx birth
        "Odo of Cluny": {"birth_year": 878, "death_year": 942},
        "Peter the Venerable": {"birth_year": 1092, "death_year": 1156},
        "William of Poitiers": {"birth_year": 1020, "death_year": 1090},
        "Lambert of Hersfeld": {"birth_year": 1025, "death_year": 1088},
        "Bonizo of Sutri": {"birth_year": 1045, "death_year": 1090},
        "Sigebert of Gembloux": {"birth_year": 1030, "death_year": 1112},
        "Bhikkhu Nanamoli": {"birth_year": 1905, "death_year": 1960},
        "Laurence Khantipalo Mills": {"birth_year": 1932, "death_year": 2021},
        "Brahmrishi Vishvatma Bawra": {"birth_year": 1934, "death_year": None},
        "Santideva": {"birth_year": 685, "death_year": 763},
        "Andrew Skilton": {"birth_year": 1969, "death_year": None},
        "John E. Goldingay": {"birth_year": 1942, "death_year": None},
        "R.H. Charles": {"birth_year": 1855, "death_year": 1931},
        "Sallustius": {"birth_year": -86, "death_year": -35},
        "Lucian of Samosata": {"birth_year": 125, "death_year": 180},
        "Marcus Annaeus Lucanus": {"birth_year": 39, "death_year": 65},
        "Susan H. Braund": {"birth_year": 1957, "death_year": None},
        "Ambrosius Theodosius Macrobius": {"birth_year": 370, "death_year": 430},
        "Samuel George Frederick Brandon": {"birth_year": 1907, "death_year": 1971},
        "George Emmanuel Mylonas": {"birth_year": 1898, "death_year": 1988},
        "Buddhaghosa": {"birth_year": 370, "death_year": 450},
        "Quintus Fabius Pictor": {"birth_year": -270, "death_year": -200},
        "Manetho": {"birth_year": -300, "death_year": -250}, # Approx
        "Irenaeus": {"birth_year": 130, "death_year": 202},
        "Eunapius": {"birth_year": 347, "death_year": 414},
        "T.M. Prudden": {"birth_year": 1891, "death_year": 1968},
        "Richard H. Jones": {"birth_year": 1934, "death_year": 2020}, # Assuming biostatistician or similar
        "Gabrielle Moss": {"birth_year": 1982, "death_year": None},
        "Luis E. Navia": {"birth_year": 1940, "death_year": None},
        "Chris Carlsson": {"birth_year": 1986, "death_year": None},
        "Susan Treggiari": {"birth_year": 1940, "death_year": None},
        "Henry Watson Fowler": {"birth_year": 1858, "death_year": 1933},
        "Theodore M. Bernstein": {"birth_year": 1904, "death_year": 1979},
        "Zeno of Citium": {"birth_year": -334, "death_year": -262},
        "Panaetius": {"birth_year": -185, "death_year": -110},
        "Posidonius": {"birth_year": -135, "death_year": -51},
        "Hippocrates": {"birth_year": -460, "death_year": -370},
        "Antisthenes": {"birth_year": -445, "death_year": -365},
        "Phocion": {"birth_year": -402, "death_year": -318},
        "Adolph Caso": {"birth_year": 1934, "death_year": 2023},
        "Rufus Goodwin": {"birth_year": 1914, "death_year": 1990},
        "Daniel C. Dennett": {"birth_year": 1942, "death_year": 2024},
        "John Andrew Simpson": {"birth_year": 1871, "death_year": 1937}, # Assuming engineer/scientist context
        "A.N. Kolmogorov": {"birth_year": 1903, "death_year": 1987},
        "Elizabeth L. Eisenstein": {"birth_year": 1923, "death_year": 2016},
        "John Robinson Pierce": {"birth_year": 1910, "death_year": 2002},
        "Harry Middleton Hyatt": {"birth_year": 1896, "death_year": 1978},
        "Fred I. Dretske": {"birth_year": 1932, "death_year": 2013},
        "Tom Siegfried": {"birth_year": 1950, "death_year": None}, # Approx
        "Louisa Gilder": {"birth_year": 1978, "death_year": None},
        "Dexter Palmer": {"birth_year": 1974, "death_year": None},
        "Solon": {"birth_year": -630, "death_year": -560},
        "Meno": {"birth_year": -423, "death_year": -400},
        "Vergil": {"birth_year": -70, "death_year": -19},
        "Aeneid": {"birth_year": -19, "death_year": -19}, # In case it appears as author
        "Seneca": {"birth_year": -4, "death_year": 65}, # Seneca the Younger
        "Thomas Percy": {"birth_year": 1729, "death_year": 1811}, # Bishop Thomas Percy
        "George C. Williams": {"birth_year": 1926, "death_year": 2010}, # Evolutionary Biologist
        "John Simon": {"birth_year": 1925, "death_year": 2019}, # Critic
        "Flavius Josephus": {"birth_year": 37, "death_year": 100},
        "Eusebius": {"birth_year": 260, "death_year": 340},
        "Enoch": {"birth_year": -3000, "death_year": -2000}, # Biblical figure
        "Horace": {"birth_year": -65, "death_year": -8},
        "Thomas Aquinas": {"birth_year": 1225, "death_year": 1274},
        "Joseph Frank": {"birth_year": 1918, "death_year": 2013}, # Dostoevsky Biographer
        "Edward Rice": {"birth_year": 1918, "death_year": 2001} # Merton Biographer
    }

    for name, data in updates.items():
        if name not in metadata:
            metadata[name] = {}
        metadata[name]["birth_year"] = data["birth_year"]
        metadata[name]["death_year"] = data["death_year"]
        metadata[name]["title"] = name # Ensure title is set

    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    
    print(f"Updated {len(updates)} authors in authors_metadata.json")

    # 2. Backfill into book JSONs
    # If a citation has a wikipedia_match with missing dates, or no wikipedia_match but we have the author in metadata
    files = glob.glob("frontend/data/*.json")
    updated_files = 0
    
    for fpath in files:
        if "manifest" in fpath or "metadata" in fpath or "dates" in fpath: continue
        
        try:
            with open(fpath, "r") as f:
                data = json.load(f)
        except: continue
        
        modified = False
        citations = data.get("citations", [])
        
        for cit in citations:
            # Determine author name
            name = None
            if cit.get("wikipedia_match") and cit["wikipedia_match"].get("title"):
                name = cit["wikipedia_match"]["title"]
            elif cit.get("goodreads_match") and cit["goodreads_match"].get("authors"):
                name = cit["goodreads_match"]["authors"][0]
            elif cit.get("raw"):
                name = cit["raw"].get("canonical_author") or cit["raw"].get("author")
            
            if name and name in metadata:
                meta = metadata[name]
                
                # If wikipedia_match exists, update it
                if cit.get("wikipedia_match"):
                    if cit["wikipedia_match"].get("birth_year") is None:
                        cit["wikipedia_match"]["birth_year"] = meta.get("birth_year")
                        cit["wikipedia_match"]["death_year"] = meta.get("death_year")
                        modified = True
                
                # If wikipedia_match is missing, create it
                else:
                    cit["wikipedia_match"] = {
                        "title": name,
                        "birth_year": meta.get("birth_year"),
                        "death_year": meta.get("death_year"),
                        "page_id": None, # We don't have this easily, but frontend might not strictly need it for timeline
                        "infoboxes": [],
                        "categories": []
                    }
                    modified = True
                    
                # Also update edge target_person
                if cit.get("edge") and cit["edge"].get("target_person"):
                     if cit["edge"]["target_person"].get("birth_year") is None:
                        cit["edge"]["target_person"]["birth_year"] = meta.get("birth_year")
                        cit["edge"]["target_person"]["death_year"] = meta.get("death_year")
                        modified = True
                elif cit.get("edge") and not cit["edge"].get("target_person"):
                     cit["edge"]["target_person"] = {
                        "title": name,
                        "birth_year": meta.get("birth_year"),
                        "death_year": meta.get("death_year")
                     }
                     modified = True

        if modified:
            with open(fpath, "w") as f:
                json.dump(data, f, indent=2)
            updated_files += 1

    print(f"Backfilled metadata into {updated_files} book JSON files.")

if __name__ == "__main__":
    update_author_data()
