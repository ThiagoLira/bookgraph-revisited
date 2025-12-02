import json
import os

def update_dates():
    file_path = 'frontend/data/original_publication_dates.json'
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}

    updates = {
        "10111487": "1951-01-01",
        "101949": "1949-06-10",
        "1057177": "1999-04-01",
        "1118500": "2006-06-01",
        "11291660": "2012-12-11",
        "1240002": "2020-08-18",
        "13145579": "2023-09-19",
        "1381392": "1982-01-01",
        "15995592": "2013-06-02",
        "1680638": "2012-06-25",
        "168490": "1817-12-20",
        "18936229": "2017-02-14",
        "19511472": "2017-05-09",
        "217416511": "2022-05-10",
        "237686": "1976-01-01",
        "2475634": "2012-11-16",
        "26805": "2021-07-08",
        "27316972": "2024-07-30",
        "301430": "2024-09-10",
        "3082421": "2013-05-13",
        "378576": "2013-12-25",
        "38311321": "2016-05-10",
        "481086": "1953-01-01",
        "5711335": "2013-07-01",
        "78165": "2017-08-02",
        "196190": "1963-01-01",
        "200036": "1977-01-01",
        "29795400": "2025-03-25",
        "31821020": "2025-03-04",
        "333153": "2013-05-13",
        "403283": "1982-01-01",
        "6380362": "2014-01-01",
        "638487": "1995-01-01",
        "688182": "2007-01-01",
        "7015458": "1991-01-01",
        "759495": "1997-01-01",
        "776708": "2015-08-25",
        "780466": "2004-01-01",
        "7962285": "2021-01-01",
        "9275734": "2021-02-16",
        "11027547": "0075-01-01", # Solon (Plutarch) - Pad to 4 digits for JS Date
        "17673341": "386 BC", # Meno (Plato) - Use BC format for frontend
        "3350311": "386 BC", # Meno (Plato) - Use BC format for frontend
        "10284355": "19 BC", # Aeneid (Virgil)
        "11057575": "1880-01-01", # Brothers Karamazov - Clean up format
        "334332": "0400-01-01", # 400 AD -> 0400
        "33554089": "0350-01-01", # 350 AD -> 0350
        "20385662": "0002-01-01", # 2 AD -> 0002
        "21527649": "0161-01-01", # 161 AD -> 0161
        "168490": "370 BC", # Xenophon
        "2519474": "330 BC", # Aristotle
        "8901416": "0100-01-01", # Holy Bible (approx NT completion)
        "12491757": "0100-01-01", # Bible
        "937911": "200 BC", # Old Testament (approx Septuagint)
        "1407766": "0868-01-01", # Diamond Sutra (Dunhuang scroll date)
        "26384": "370 BC", # Xenophon Scripta Minora
        "55592": "90 BC", # Sima Qian Records
        "616029": "0100-01-01", # Asvaghosa Awakening of Faith
        "1048288": "0200-01-01", # Nagarjuna Fundamental Wisdom
        "2215201": "0200-01-01", # Clement Stromateis
        "1648859": "0450-01-01", # Proclus on Timaeus
        "238863": "0530-01-01", # Bodhidharma
        "2622816": "0960-01-01", # Liudprand
        "350720": "1641-01-01", # Descartes Philosophical Works
        "2724730": "0325-01-01", # Eusebius Church History
        "55966": "1890-01-01", # William James Principles of Psychology
        "49339": "1845-01-01", # Poe Poetry and Tales
        "20556378": "1814-01-01", # Laplace Probabilities
        "13145579": "1938-01-01", # Celine L'ecole des cadavres
        "1132944": "390 BC", # Plato Alcibiades
        "8875818": "400 BC", # Tao Te Ching (Waley translation)
        "232708": "200 BC", # Pali Canon (Majjhima Nikaya)
        "864204": "1604-01-01", # Cawdrey's Dictionary
        "881358": "0600-01-01", # Cave of Treasures (approx)
        "6500220": "400 BC", # Lao Tzu Tao Te Ching
        "868426": "0100-01-01", # Vimalakirti Sutra (approx)
        "52357": "0975-01-01", # Beowulf (manuscript date approx)
        "1654615": "1375-01-01", # Cloud of Unknowing
        "8805803": "200 BC", # Bhagavad Gita
        "463876": "1500 BC", # The Vedas (approx Rigveda)
        "17341464": "500 BC", # Genesis (approx)
        "30228592": 64, # Seneca Letters (Integer to avoid parsing issues)
        "11027547": 75, # Solon (Integer)
        "20385662": 2, # 2 AD (Integer)
        "30478027": 98, # 98 AD (Integer)
        "7131932": 94, # 94 AD (Integer)
        "101582": 1776, # Gibbon Decline and Fall (Integer)
        "4957335": 1776, # Gibbon Decline and Fall (Integer)
        "5042632": 1776, # Gibbon Decline and Fall (Integer)
        "780638": 1513, # The Prince (Machiavelli)
        "19063": 1651, # Leviathan (Hobbes)
        "6404593": 1848, # Communist Manifesto
        "68428": 1762, # Social Contract (Rousseau)
        "8058415": 1644, # Areopagitica (Milton)
        "2179507": "700 BC", # Odyssey (Homer)
        "25351243": "750 BC", # Iliad (Homer)
        "167926": 1531, # Discourses on Livy (Machiavelli)
        "20087887": "370 BC", # Cyropaedia (Xenophon)
        "2391181": 1888, # Ecce Homo (Nietzsche composition)
        "20444206": 1887, # Goncourt Journal
        "291587": 1677, # Ethics (Hackett Classics - Spinoza)
        "58536084": 2020, # Ta Todo Mundo Mal (Real date seems to be ~2020, not 2025)
        "29795400": 2020, # Ta Todo Mundo Mal (Second GID)
        "33554089": 350, # Sallust On The Gods (Integer)
        "8340956": -398, # Apology (Integer)
        "13323096": -398, # Apology (Integer)
        "18906590": -440 # Histories (Herodotus) - Fix wrong date
    }

    count = 0
    for gid, date in updates.items():
        if gid in data: # Only update if it exists (or should we add it? The user wants to fill missing dates, so probably add/update)
            data[gid] = date
            count += 1
        else:
             # If it's not in the map, we add it.
             data[gid] = date
             count += 1

    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Updated {count} book publication dates.")

if __name__ == "__main__":
    update_dates()
